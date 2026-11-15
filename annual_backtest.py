"""연 1회 리밸런싱 과거 전략 (원래 8종 ETF + 연도별 팩터 종목)

출처: 팀원(sehui) 브랜치 origin/sehui 5948ee3 의 backtest.py · recommender.py(8종 ETF 버전) 연 1회 리밸런싱 백테스트.
현재 서비스 추천(recommender.build_portfolio, ETF 20종 + 거래대금 상위 종목)과는 별개의 '과거 전략'이에요.

왜 별도 모듈인가
- backtest.py 는 rc.ETF_NAMES 와 rc.build_portfolio 를 그대로 불러요. 지금 rc 는 ETF 20종 · 3% 정리 규칙이라
  그대로 부르면 팀원이 만든 8종 전략이 아닌 다른 전략을 조용히 계산하게 돼요.
- 그래서 유니버스(LEGACY_ETFS)·성향표·모형 규칙을 이 파일 안에 고정하고, rc 에서는 순수 최적화 함수
  (minimum_variance, risk_parity)만 빌려 써요. 전역 설정을 바꾸지 않아요(monkeypatch 없음).

원래 8종 전략 규칙 (팀원 코드 그대로)
- 성향표의 자산군 비중 × 자산군 안 비중. 자산군 안은 안정형·안정성장형 MVP, 성장형·공격형 RP.
- 채권·예금 = KBOND, 주식 = 국내외 주식 ETF 5종, 대안투자 = OIL · USD, 자산배분 = 8종 전체 RP, 유동성 = 현금.
- 팩터 종목을 쓰면 주식 몫의 절반은 그해 팩터 종목 같은 비중, 절반은 주식 ETF 최적화 비중.
- 0.05% 이하 비중만 버리고 다시 합 1로 맞춰요. 현재 서비스의 3% 최소 비중 정리는 쓰지 않아요.

시점 처리 (팀원 버전보다 보수적으로 고친 부분)
- data/factor_picks.csv 의 리밸런싱일(선정일)은 그날 종가로 PER·PBR 순위를 매긴 날이에요.
  같은 종가에 바로 샀다고 하면 이미 알고 있는 가격으로 거래한 것이 되므로,
  선정일까지의 자료로 목표 비중을 정하고 '다음 거래일 종가'에 매매해요 (판단 → 실행 1거래일 시차).
- 매매일 종가 이후의 수익률부터 새 보유 비중이 적용돼요.
- 재무 자료는 (회계연도 + 1)년 4월부터 쓸 수 있다고 가정해요 (실제 공시일을 검증한 point-in-time 자료가 아니에요).

비용·현금
- 거래비용: 매매 금액(현금 제외, |목표 − 보유| 합) × bp. 처음 매수할 때도 같은 bp 를 물려요.
- 현금: 연 rf 를 달력 일수로 복리 적용 ((1 + rf) ** (일수 / 365) − 1).
- 분배금·배당·세금은 빼요 (가격 수익률만).
- 보유 중인 자산 가격이 비어 있거나 0 이하이면 0% 수익으로 메우지 않고 ValueError 를 내요.
"""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

import factor
import recommender as rc

ROOT = Path(__file__).resolve().parent
ETF_FILE = ROOT / 'data' / 'etf_prices.csv'
STOCK_FILE = ROOT / 'data' / 'stock_prices.csv'
PICKS_FILE = ROOT / 'data' / 'factor_picks.csv'

# ── 고정 규칙 (현재 서비스 설정이 바뀌어도 이 전략은 그대로) ─────────────────────────
LEGACY_ETFS = ('KOSPI200', 'SP500', 'TOPIX', 'CSI300', 'EUROSTOXX50', 'KBOND', 'OIL', 'USD')
LEGACY_MEMBERS = {
    '채권·예금': ['KBOND'],
    '주식': ['KOSPI200', 'SP500', 'TOPIX', 'CSI300', 'EUROSTOXX50'],
    '대안투자': ['OIL', 'USD'],
}
LEGACY_LABEL = {'KOSPI200': 'KODEX 200', 'SP500': 'TIGER 미국S&P500선물', 'TOPIX': 'TIGER 일본TOPIX',
                'CSI300': 'TIGER 차이나CSI300', 'EUROSTOXX50': 'TIGER 유로스탁스50', 'KBOND': 'KIWOOM 통안채1년',
                'OIL': 'TIGER 원유선물', 'USD': 'KIWOOM 미국달러선물', 'CASH': '현금'}
GROUPS = ['채권·예금', '주식', '대안투자', '자산배분', '유동성']
PROFILE_TABLE = {   # 팀원 코드의 성향표 (채권·예금, 주식, 대안투자, 자산배분, 유동성 %)
    '안정형': {'채권·예금': 73, '주식': 5, '대안투자': 2, '자산배분': 10, '유동성': 10},
    '안정성장형': {'채권·예금': 39, '주식': 9, '대안투자': 26, '자산배분': 16, '유동성': 10},
    '성장형': {'채권·예금': 24, '주식': 26, '대안투자': 30, '자산배분': 10, '유동성': 10},
    '공격형': {'채권·예금': 10, '주식': 44, '대안투자': 26, '자산배분': 10, '유동성': 10},
}
MODEL_BY_PROFILE = {'안정형': 'MVP', '안정성장형': 'MVP', '성장형': 'RP', '공격형': 'RP'}
PROFILES = list(PROFILE_TABLE)
CASH = 'CASH'
STOCK_SHARE = 0.5
LOOKBACK_YEARS = 3
DAYS = 240            # 변동성 연율화용 (서비스 다른 화면과 같은 기준)
MIN_HISTORY = 120     # 공분산 계산에 필요한 최소 일간 수익률 개수
DUST = 0.0005         # 팀원 코드: 이 이하 비중은 버림

BP = 0.001            # 거래비용: 매매 금액의 0.1%
RF = 0.03             # 현금 연이율 3%
INIT = 100.0          # 시작값
BENCH = 'KBOND'       # 비교 기준: 국내 단기채권 ETF 매수 후 보유


# ── 1. 데이터 ──────────────────────────────────────────────────────────
def load_data(etf_file=ETF_FILE, stock_file=STOCK_FILE, picks_file=PICKS_FILE):
    """8종 ETF 가격 · 팩터 종목 가격 · 연도별 선정 종목. ETF 거래일 달력 기준으로 맞춰요."""
    etf = pd.read_csv(etf_file, index_col=0, parse_dates=True).sort_index()
    missing = [c for c in LEGACY_ETFS if c not in etf.columns]
    if missing:
        raise ValueError(f'8종 ETF 가격 열이 없습니다: {", ".join(missing)}')
    stocks = pd.read_csv(stock_file, index_col=0, parse_dates=True).sort_index()
    picks = factor.load_picks(picks_file)
    return {'etf': etf[list(LEGACY_ETFS)], 'stocks': stocks.reindex(etf.index), 'picks': picks}


def data_version(paths=(ETF_FILE, STOCK_FILE, PICKS_FILE)):
    """입력 파일 내용 해시 (캐시 키). 파일이 바뀌면 값이 바뀌어요."""
    h = hashlib.sha1()
    for p in paths:
        h.update(Path(p).name.encode())
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:16]


# ── 2. 일정: 선정일(판단) → 다음 거래일(매매) ─────────────────────────────────
def schedule(index, picks):
    """선정일마다 다음 거래일을 매매일로. 다음 거래일이 아직 없으면 그해는 빼요."""
    rows = []
    for t in sorted(picks['리밸런싱일'].drop_duplicates()):
        if t > index[-1]:
            continue  # 아직 가격 자료가 없는 미래 선정 내역은 과거 계산에 포함하지 않음
        selected = picks.loc[picks['리밸런싱일'] == t]
        fiscal_years = pd.to_numeric(selected['회계연도'], errors='raise')
        if fiscal_years.isna().any() or any(
            not float(y).is_integer() or t < pd.Timestamp(int(y) + 1, 4, 1)
            for y in fiscal_years
        ):
            raise ValueError(f'{t:%Y-%m-%d} 선정 내역에 당시 이용할 수 없는 회계연도 자료가 있습니다.')
        if t not in index:
            raise ValueError(f'선정일 {t:%Y-%m-%d} 이 가격 자료의 거래일이 아닙니다.')
        after = index[index > t]
        if len(after):
            rows.append({'selection': t, 'execution': after[0]})
    if not rows:
        raise ValueError('실행 가능한 연간 재조정 내역이 없습니다.')
    return pd.DataFrame(rows)


# ── 3. 목표 비중 (원래 8종 규칙) ────────────────────────────────────────────
def legacy_cov(etf_prices, end):
    """end(선정일) 까지의 최근 3년 일간수익률로 연율화 공분산 (8종만)"""
    p = etf_prices.loc[:end, list(LEGACY_ETFS)]
    recent = p.loc[p.index[-1] - pd.DateOffset(years=LOOKBACK_YEARS):]
    rets = recent.pct_change(fill_method=None).iloc[1:]
    if len(rets) < MIN_HISTORY or not np.isfinite(rets.to_numpy()).all():
        raise ValueError(f'{pd.Timestamp(end):%Y-%m-%d} 기준 8종 ETF 가격 이력이 부족하거나 비어 있습니다.')
    return rets.cov() * DAYS


def optimize(names, cov, model):
    """자산군 안 비중 (팀원 코드: 실패하면 변동성 역수 비중)"""
    if len(names) == 1:
        return pd.Series(1.0, index=names)
    sub = cov.loc[names, names].values
    w = rc.minimum_variance(sub) if model == 'MVP' else rc.risk_parity(sub)
    w = np.clip(np.nan_to_num(w, nan=0.0), 0, None)
    if not np.isfinite(w).all() or w.sum() <= 0:
        inv = 1 / np.sqrt(np.diag(sub))
        w = inv / inv.sum()
    return pd.Series(w / w.sum(), index=names)


def legacy_weights(profile, cov, picks=None):
    """성향표 × 자산군 안 비중 → 상품별 목표 비중 (합 1, 현금 포함)"""
    table = PROFILE_TABLE[profile]
    model = MODEL_BY_PROFILE[profile]
    picks = list(picks or [])
    eq = optimize(LEGACY_MEMBERS['주식'], cov, model)
    if picks:
        eq = pd.concat([eq * (1 - STOCK_SHARE), pd.Series(STOCK_SHARE / len(picks), index=picks)])
    sleeves = {
        '채권·예금': optimize(LEGACY_MEMBERS['채권·예금'], cov, model),
        '주식': eq,
        '대안투자': optimize(LEGACY_MEMBERS['대안투자'], cov, model),
        '자산배분': optimize(list(LEGACY_ETFS), cov, 'RP'),
        '유동성': pd.Series(1.0, index=[CASH]),
    }
    w = pd.concat([table[g] / 100 * sleeves[g] for g in GROUPS])
    w = w.groupby(level=0).sum()
    w = w[w > DUST]
    return (w / w.sum()).sort_values(ascending=False)


def target_weights(profile, data, use_factor=True):
    """매매일 × 상품 목표 비중표와 일정표. 각 행은 선정일까지의 가격·종목만 사용해요."""
    sch = schedule(data['etf'].index, data['picks'])
    rows = {}
    for r in sch.itertuples():
        cov = legacy_cov(data['etf'], r.selection)
        names = factor.picks_on(data['picks'], r.selection) if use_factor else []
        rows[r.execution] = legacy_weights(profile, cov, names)
    W = pd.DataFrame(rows).T.fillna(0.0)
    cols = [c for c in W.columns if c != CASH] + [CASH]
    return W[cols], sch


# ── 4. 누적가치 ─────────────────────────────────────────────────────────
def _check_prices(px_row, names, day):
    bad = [n for n in names if not (np.isfinite(px_row[n]) and px_row[n] > 0)]
    if bad:
        raise ValueError(f'{day:%Y-%m-%d} 보유 자산 가격이 비어 있거나 0 이하입니다: {", ".join(bad)}')


def simulate(W, prices, init=INIT, bp=BP, rf=RF, end=None):
    """W: 매매일 × 목표 비중(현금 포함), prices: 거래일 × 자산 가격.

    - 첫 매매일 종가에 init 을 목표 비중대로 사고, 산 금액 × bp 를 비용으로 빼요.
    - 다음 날부터 보유 금액 × (1 + 가격 수익률), 현금은 달력 일수만큼 rf 복리.
    - 다음 매매일 종가에 목표 비중으로 다시 맞추고 |목표 − 보유|(현금 제외) 합 × bp 를 빼요.
    반환: nav, 일별 보유 금액, 매매일별 매매 비율(turnover), 매매일별 비용
    """
    assets = [c for c in W.columns if c != CASH]
    days = prices.index[(prices.index >= W.index[0]) & ((prices.index <= end) if end is not None else True)]
    px = prices.reindex(days)
    missing = [a for a in assets if a not in px.columns]
    if missing:
        raise ValueError(f'가격 자료가 없는 자산이 있습니다: {", ".join(missing)}')
    px = px[assets]
    cash_i = len(assets)
    w_tgt = W[assets + [CASH]].to_numpy(dtype=float)
    rebal = {days.get_loc(t): i for i, t in enumerate(W.index) if t in days}
    if 0 not in rebal:
        raise ValueError('첫 매매일이 가격 자료에 없습니다.')

    hold = np.zeros((len(days), len(assets) + 1))
    turnover, costs = {}, {}
    p = px.to_numpy(dtype=float)
    for d in range(len(days)):
        if d == 0:
            h = np.zeros(len(assets) + 1)
            h[cash_i] = init
        else:
            prev = hold[d - 1]
            held = [a for a, v in zip(assets, prev[:cash_i]) if v > 0]
            _check_prices(px.iloc[d], held, days[d])
            r = np.zeros(len(assets) + 1)
            idx = [assets.index(a) for a in held]
            r[idx] = p[d, idx] / p[d - 1, idx] - 1
            r[cash_i] = (1 + rf) ** ((days[d] - days[d - 1]).days / 365) - 1
            h = prev * (1 + r)
        if d in rebal:
            w = w_tgt[rebal[d]]
            _check_prices(px.iloc[d], [a for a, v in zip(assets, w[:cash_i]) if v > 0], days[d])
            total = h.sum()
            trade = np.abs(w[:cash_i] * total - h[:cash_i]).sum()
            cost = trade * bp
            h = w * (total - cost)
            turnover[days[d]] = trade / total
            costs[days[d]] = cost
        hold[d] = h
    nav = pd.Series(hold.sum(axis=1), index=days)
    holdings = pd.DataFrame(hold, index=days, columns=assets + [CASH])
    return nav, holdings, pd.Series(turnover, dtype=float), pd.Series(costs, dtype=float)


def benchmark(prices, start, init=INIT, bp=BP, end=None, name=BENCH):
    """단기채권 ETF 를 start 종가에 사서(비용 bp) 계속 보유"""
    s = prices[name].loc[start:end]
    if not np.isfinite(s.to_numpy()).all() or (s <= 0).any():
        raise ValueError(f'{name} 가격이 비어 있거나 0 이하입니다.')
    return init * (1 - bp) * s / s.iloc[0]


# ── 5. 성과 지표 ───────────────────────────────────────────────────────
def metrics(nav, init=INIT):
    """처음 투자금 init 기준. CAGR = (최종 ÷ 투자금) ^ (365.25 ÷ 달력 일수) − 1 (일평균 × 240 아님)"""
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    total = nav.iloc[-1] / init - 1
    path = pd.concat([pd.Series([init]), nav.reset_index(drop=True)])
    mdd = (path / path.cummax() - 1).min()
    vol = nav.pct_change().dropna().std() * np.sqrt(DAYS)
    return {'cum': total, 'cagr': (1 + total) ** (1 / years) - 1 if years > 0 else np.nan,
            'mdd': mdd, 'vol': vol, 'final': nav.iloc[-1], 'years': years}


def yearly(navs, init=INIT):
    """달력 연도별 수익률. 첫 해는 투자금 init 부터, 마지막 해는 마지막 거래일까지 (부분 연도 표시)"""
    end_of_year = navs.groupby(navs.index.year).tail(1)
    prev = pd.concat([pd.DataFrame([[init] * navs.shape[1]], columns=navs.columns), end_of_year.iloc[:-1]])
    out = pd.DataFrame(end_of_year.to_numpy() / prev.to_numpy() - 1, columns=navs.columns,
                       index=end_of_year.index.year)
    first, last = navs.index[0], navs.index[-1]
    out['기간'] = [f'{first:%m.%d}~12월말' if y == first.year else (f'1월~{last:%m.%d}' if y == last.year else '연간')
                 for y in out.index]
    return out


# ── 6. 한 번에 실행 ────────────────────────────────────────────────────
def run(profile, use_factor=True, bp=BP, rf=RF, data=None, end=None):
    """한 성향의 연 1회 리밸런싱 과거 전략 결과"""
    if profile not in PROFILE_TABLE:
        raise ValueError(f'알 수 없는 성향: {profile}')
    data = data if data is not None else load_data()
    W, sch = target_weights(profile, data, use_factor)
    prices = data['etf'].join(data['stocks'][[c for c in W.columns if c in data['stocks'].columns
                                              and c not in data['etf'].columns]])
    nav, holdings, turnover, costs = simulate(W, prices, bp=bp, rf=rf, end=end)
    bench = benchmark(data['etf'], nav.index[0], bp=bp, end=nav.index[-1])
    navs = pd.DataFrame({'연 1회 리밸런싱 전략': nav, '단기채권 ETF 보유': bench})
    picks = data['picks']
    sel = []
    for r in sch.itertuples():
        p = picks[picks['리밸런싱일'] == r.selection]
        sel.append({'선정일': r.selection, '매매일': r.execution,
                    '재무 기준 회계연도': int(p['회계연도'].iloc[0]) if len(p) else None,
                    '팩터 종목': ', '.join(p['종목명']) if use_factor else '-'})
    return {'navs': navs, 'metrics': {c: metrics(navs[c]) for c in navs},
            'yearly': yearly(navs), 'weights': W, 'schedule': sch, 'selections': pd.DataFrame(sel),
            'turnover': turnover, 'costs': costs, 'holdings': holdings,
            'start': nav.index[0], 'end': nav.index[-1], 'bp': bp, 'rf': rf, 'init': INIT,
            'profile': profile, 'use_factor': use_factor}


if __name__ == '__main__':
    d = load_data()
    for prof in PROFILES:
        res = run(prof, data=d)
        m = res['metrics']
        print(f"{prof} {res['start']:%Y-%m-%d}~{res['end']:%Y-%m-%d} "
              + ' | '.join(f"{k}: CAGR {v['cagr']:.2%} MDD {v['mdd']:.2%}" for k, v in m.items()))
