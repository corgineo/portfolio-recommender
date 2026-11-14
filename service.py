"""화면에 필요한 계산을 한곳에 모았어요 (Streamlit 없이도 테스트할 수 있게)

- 상품 범위(scope): 'base' = 기존 국내 ETF 8종, 'wide' = + 거래대금 상위 종목(국내·미국 통합) · 채권 ETF · 국내 추가 ETF(extra_data)
- recommend(): 설문 답 + 예산 + 상품 범위 → 투자성향, 비중, 매수 수량, 과거 성과
- compare_weights(): 모의 포트폴리오(내 비중)와 추천 비중의 과거 성과 비교
"""
from pathlib import Path

import numpy as np
import pandas as pd

import recommender as rc

FIN_KR_FILE = Path(__file__).parent / 'data' / '재무_2026.csv'
SCOPES = {'wide': '거래대금 상위 종목·국내 추가 ETF까지', 'base': '국내 ETF 8종만'}


# ── 상품 범위별 데이터 ─────────────────────────────────────────────────
def load_scope(scope='wide'):
    """반환: prices(원화), rets, cov, products(이름→정보), extra, universe, as_of, notes"""
    base_prices = rc.load_prices()
    universe = rc.load_universe() if scope == 'wide' else None
    if scope == 'wide' and universe is None:
        scope = 'base'                                   # 데이터가 없으면 기본 범위로 대신해요
    products = rc.base_products()
    if scope == 'base':
        rets, _, cov = rc.model_inputs(base_prices)
        return dict(scope='base', prices=base_prices, rets=rets, cov=cov, products=products, extra={}, picks=[],
                    universe=None, as_of=base_prices.index[-1], fx=None, us_as_of=None)
    picks = rc.current_picks()                           # 저PER·저PBR·고ROE 순위합 상위 종목 (factor.py)
    stock = pd.read_csv(rc.STOCK_FILE, index_col=0, parse_dates=True)[picks]
    prices = universe['prices'].drop(columns=picks, errors='ignore').join(stock)
    extra = rc.universe_extra(universe, prices)
    names = rc.ETF_NAMES + [n for v in extra.values() for n in v]
    rets, _, cov = rc.model_inputs(prices, names=names)
    products.update(rc.universe_products(universe))
    products.update(rc.factor_products(picks))
    fx = universe['fx']
    us_as_of = universe['meta'].get('us_last_session')
    fx_used = None
    if fx is not None and us_as_of:
        fx_used = float(fx.loc[:pd.Timestamp(us_as_of)].iloc[-1])
    return dict(scope='wide', prices=prices, rets=rets, cov=cov, products=products, extra=extra, picks=picks,
                universe=universe, as_of=prices.index[-1], fx=fx_used, us_as_of=us_as_of)


def group_of(products):
    return lambda n: products.get(n, {}).get('group', '유동성')


# ── 추천 ───────────────────────────────────────────────────────────────
def recommend(answers, budget, data):
    """설문 답(0~4 × 7) + 예산(원) + load_scope() 결과 → 화면에 필요한 값"""
    if not budget or budget <= 0:
        raise ValueError('예산은 0원보다 커야 해요.')
    judge = rc.judge_profile(answers)
    profile = judge['profile']
    prices = data['prices']
    last = prices.ffill().iloc[-1]
    if data['scope'] == 'wide':
        weights, detail, sleeves = rc.build_portfolio(profile, data['cov'], picks=data['picks'], extra=data['extra'],
                                                      budget=budget, last_prices=last)
    else:
        weights, detail, sleeves = rc.build_portfolio(profile, data['cov'])
    perf = rc.performance(weights, data['rets'])
    labels = {n: p['short'] for n, p in data['products'].items()}
    alloc = rc.allocate_budget(weights, prices, budget, labels=labels)
    colors = rc.color_map(list(weights.index), group_of(data['products']))
    tags = rc.hashtags(profile, judge['period'], weights, detail)
    group_w = detail.groupby('group')['weight'].sum()
    return dict(judge=judge, profile=profile, weights=weights, detail=detail, sleeves=sleeves, perf=perf,
                alloc=alloc, colors=colors, tags=tags, group_w=group_w, dropped=detail.attrs.get('dropped', []),
                model=rc.MODEL_BY_PROFILE[profile])


# ── 결과 화면: 연 1회 리밸런싱 백테스트 ───────────────────────────────────
def backtest_summary(profile, use_factor):
    """매년 4월 그때까지의 데이터로 추천 규칙을 다시 적용했을 때 (backtest.py)

    use_factor: 팩터 종목을 담는 범위면 True. 거래대금 상위 종목은 지금 순위라 과거에 고를 수 없어서 빼고,
    국내 ETF 8종(+ 그해 팩터 종목)으로 계산해요.
    반환: navs(추천 방식·단기채권 누적가치, 시작 100), perf(지표), yearly(연도별 수익률), picks(연도별 종목)
    """
    import backtest as bt
    import factor
    res = bt.compare(profile)
    main = '추천(팩터 종목 포함)' if use_factor else '추천(ETF만)'
    cols = [main, '단기채권만'] + (['추천(ETF만)'] if use_factor else [])
    rename = {main: '추천 방식'}
    picks = None
    if use_factor:
        p = factor.load_picks()
        picks = p.groupby(p['리밸런싱일'].dt.date)['종목명'].apply(', '.join)
    navs = res['navs'][cols].rename(columns=rename)
    return dict(navs=navs, perf=res['perf'][cols].rename(columns=rename),
                yearly=res['yearly'][cols].rename(columns=rename), picks=picks,
                start=navs.index[0], end=navs.index[-1], bp=bt.BP, rf=bt.RF, init=bt.INIT)


# ── 모의 포트폴리오: 과거 성과 비교 ───────────────────────────────────────
def compare_weights(prices, base_pct, edited_pct):
    """base_pct·edited_pct: 이름 → 비중(%) (합 ≤ 100, 나머지는 현금 0%).
    최근 LOOKBACK_YEARS 년 동안 매일 목표 비중을 유지했다고 가정한 사후 비교. 값이 비면 ValueError."""
    names = sorted({n for n, v in {**base_pct, **edited_pct}.items() if v > 0 and n != rc.CASH})
    recent = prices.sort_index().loc[prices.index.max() - pd.DateOffset(years=rc.LOOKBACK_YEARS):]
    if not names:
        daily = pd.DataFrame(index=recent.index[1:])
    else:
        missing = [n for n in names if n not in recent.columns]
        if missing:
            raise ValueError(f'가격 기록이 없는 상품이 있어요: {", ".join(missing)}')
        daily = recent[names].ffill(limit=5).pct_change(fill_method=None).iloc[1:]
        if len(daily) < 60 or daily.isna().any().any() or not np.isfinite(daily.to_numpy()).all():
            raise ValueError('성과 비교에 필요한 공통 가격 기록이 부족하거나 비어 있어요.')
    metrics, curves = [], {}
    for label, pct in [('추천안', base_pct), ('내 구성', edited_pct)]:
        w = pd.Series({n: pct.get(n, 0) / 100 for n in names}, dtype=float)
        ret = daily[names] @ w if names else pd.Series(0.0, index=daily.index)
        nav = pd.concat([pd.Series([100.0], index=[recent.index[0]]), (1 + ret).cumprod() * 100])
        curves[label] = nav
        metrics.append({'구성': label, '연환산 수익률(%)': ret.mean() * rc.DAYS * 100,
                        '변동성(%)': ret.std() * np.sqrt(rc.DAYS) * 100,
                        '최대 낙폭(%)': (nav / nav.cummax() - 1).min() * 100,
                        '기간 수익률(%)': (nav.iloc[-1] / 100 - 1) * 100})
    return {'metrics': pd.DataFrame(metrics).set_index('구성'), 'nav': pd.DataFrame(curves),
            'start': recent.index[0], 'end': recent.index[-1]}


def floor_pct(weights, step=0.5):
    """추천 비중(0~1) → 슬라이더용 %(step 단위로 내림, 합 ≤ 100). 현금은 빼요."""
    out = {}
    for n, w in weights.items():
        if n == rc.CASH:
            continue
        out[n] = float(np.floor(w * 100 / step + 1e-9) * step)
    return out


def clamp_weight(name, value, current):
    """name 의 새 비중 value 를 다른 상품 합계를 넘지 않게(합 ≤ 100) 잘라요. current: 이름 → 비중(%)"""
    others = sum(v for n, v in current.items() if n != name)
    cap = max(0.0, 100.0 - others)
    return float(min(max(value, 0.0), cap))


# ── 기업 분석: 재무 자료 ────────────────────────────────────────────────
def load_fin_kr(path=FIN_KR_FILE):
    fin = pd.read_csv(path, dtype={'종목코드': str})
    fin['종목코드'] = fin['종목코드'].str.replace('A', '', regex=False)
    return fin


def financials_kr(fin, code, years=6):
    """국내 종목 연간 재무(천원) → 억원 표. 빈 값은 NaN 그대로 (0으로 채우지 않아요)."""
    d = fin[fin['종목코드'] == code].sort_values('회계연도')
    if d.empty:
        return None
    d = d[d[['매출액', '영업이익', '부채총계', '자본총계']].notna().any(axis=1)].tail(years)
    if d.empty:
        return None
    out = pd.DataFrame({
        '연도': d['회계연도'].astype(int).astype(str) + '년',
        '결산': d['결산월'].astype(int).astype(str) + '월',
        '매출액': d['매출액'] / 1e5,            # 천원 → 억원
        '영업이익': d['영업이익'] / 1e5,
        '당기순이익': d['당기순이익'] / 1e5,
        '부채총계': d['부채총계'] / 1e5,
        '자본총계': d['자본총계'] / 1e5,
    })
    out['부채비율(%)'] = np.where(out['자본총계'] > 0, out['부채총계'] / out['자본총계'] * 100, np.nan)
    out['영업이익률(%)'] = np.where(out['매출액'] > 0, out['영업이익'] / out['매출액'] * 100, np.nan)
    return out.reset_index(drop=True)


def financials_us(fin_us, ticker, years=6):
    """미국 종목 연간 재무(SEC 10-K, 달러) → 억 달러 표. 빈 값은 NaN 그대로."""
    if fin_us is None or fin_us.empty:
        return None
    d = fin_us[fin_us['ticker'] == ticker].sort_values('fiscal_end').tail(years)
    if d.empty:
        return None
    end = pd.to_datetime(d['fiscal_end'])
    out = pd.DataFrame({
        '연도': end.dt.strftime('%Y.%m 결산'),
        '결산': end.dt.strftime('%Y-%m-%d'),
        '매출액': d['revenue'] / 1e8,          # 달러 → 억 달러
        '영업이익': d['operating_income'] / 1e8,
        '당기순이익': d['net_income'] / 1e8,
        '부채총계': d['liabilities'] / 1e8,
        '자본총계': d['equity'] / 1e8,
        '부채 출처': d['liabilities_note'].fillna(''),
    })
    out['부채비율(%)'] = np.where(out['자본총계'] > 0, out['부채총계'] / out['자본총계'] * 100, np.nan)
    out['영업이익률(%)'] = np.where(out['매출액'] > 0, out['영업이익'] / out['매출액'] * 100, np.nan)
    return out.reset_index(drop=True)


def price_stats(series):
    """가격 시계열(최근 3년) → 연환산 수익률·변동성·최대 낙폭. 기록이 60일 미만이면 None"""
    s = series.dropna()
    if len(s) < 60:
        return None
    r = s.pct_change().dropna()
    nav = s / s.iloc[0]
    return {'return': r.mean() * rc.DAYS, 'vol': r.std() * np.sqrt(rc.DAYS),
            'mdd': (nav / nav.cummax() - 1).min(), 'total': nav.iloc[-1] - 1,
            'start': s.index[0], 'end': s.index[-1]}
