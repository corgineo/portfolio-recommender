"""연 1회 리밸런싱 백테스팅 + 성과 지표

강의 '성과평가_백테스팅' 의 cal_nav_module.py (cal_nav) 와 재무성과_백테스팅 노트북 (ret_risk_profile) 방식:
- 매년 4월 첫 거래일에 그날까지의 데이터만으로 비중을 다시 정해요 (미래 데이터를 쓰지 않음).
  · ETF 비중: 직전 3년 공분산으로 recommender.build_portfolio 를 다시 실행
  · 개별 종목: 직전 회계연도 재무 + 그날 주가의 PER · PBR · ROE 순위합 상위 종목 (factor.py, 미리 data/factor_picks.csv 에 저장)
- 리밸런싱 사이에는 가격이 움직이는 대로 보유 금액(→ 비중)이 변해요.
- 리밸런싱 때 사고판 금액 × 거래비용(BP)을 빼요.
- 현금은 예금금리(RF)로 불어나고, 샤프·소르티노도 RF 를 빼고 계산해요.

실행: python backtest.py   (성향별 성과표 출력)
"""
import numpy as np
import pandas as pd

import factor
import recommender as rc

BP = 0.001     # 거래비용: 사고판 금액의 0.1%
RF = 0.03      # 무위험수익률 = 현금(예금) 금리, 연 3%
INIT = 100     # 시작값 (강의 index_100 과 같게 100)


# ── 1. 데이터 ─────────────────────────────────────────────────────────
def load_data():
    """ETF + 팩터 종목 가격, 연도별 선정 종목"""
    prices = rc.load_prices(with_stocks=True)
    picks = factor.load_picks()
    return prices, picks


def daily_returns(prices, rf=RF):
    """일간수익률. 현금은 연 rf 를 거래일로 나눈 만큼, 상장 전·데이터 없는 날은 0"""
    rets = prices.pct_change().fillna(0)
    rets[rc.CASH] = (1 + rf) ** (1 / rc.DAYS) - 1
    return rets


# ── 2. 리밸런싱 시점별 목표 비중 ─────────────────────────────────────────
def target_weights(profile, prices, picks, use_factor=True):
    """리밸런싱일 × 상품 비중표 (강의 cal_nav 의 W 와 같은 모양)"""
    etf_prices = prices[rc.ETF_NAMES]
    rows = {}
    for t in picks['리밸런싱일'].drop_duplicates():
        _, _, cov_mat = rc.model_inputs(etf_prices, end=t)       # t 까지의 3년만
        names = factor.picks_on(picks, t) if use_factor else None
        weights, _, _ = rc.build_portfolio(profile, cov_mat, names)
        rows[t] = weights
    return pd.DataFrame(rows).T.fillna(0)


# ── 3. 누적가치 계산 (강의 cal_nav 와 같은 규칙) ──────────────────────────
def cal_nav(W, rets, init=INIT, bp=BP, ed_date=None):
    """W: 리밸런싱일 × 비중, rets: 일간수익률
    - 첫날 W 대로 산 뒤, 매일 보유 금액 × (1 + 수익률)
    - 리밸런싱일 장마감에 목표 비중으로 맞추고, |새 보유 − 현재 보유| 합 × bp 를 비용으로 뺌
    반환: 누적가치(nav), 일별 실제 비중(Pw), 리밸런싱 때 사고판 비율(turnover)
    """
    rets = rets.loc[W.index[0]:ed_date, W.columns]
    r = rets.values
    w_target = W.values
    rebal_pos = {rets.index.get_loc(t): i for i, t in enumerate(W.index)}

    holdings = np.zeros_like(r)
    turnover = {}
    holdings[0] = w_target[0] * init
    for d in range(1, len(r)):
        h = holdings[d - 1] * (1 + r[d])
        if d in rebal_pos:
            total = h.sum()
            new = w_target[rebal_pos[d]] * total
            trade = np.abs(new - h).sum()
            turnover[rets.index[d]] = trade / total
            h = w_target[rebal_pos[d]] * (total - trade * bp)
        holdings[d] = h

    nav = pd.Series(holdings.sum(axis=1), index=rets.index)
    Pw = pd.DataFrame(holdings, index=rets.index, columns=W.columns).div(nav, axis=0)
    return nav, Pw, pd.Series(turnover, dtype=float)


# ── 4. 성과 지표 (강의 ret_risk_profile 기준, 연율화는 사이트와 같은 240일) ────
def performance_table(navs, rf=RF):
    """navs: 이름 → 누적가치 (DataFrame 열). 행 = 지표, 열 = 포트폴리오"""
    out = {}
    for name, nav in navs.items():
        nav = nav.dropna()
        ret = nav.pct_change().dropna()
        years = (nav.index[-1] - nav.index[0]).days / 365.25
        cum = nav.iloc[-1] / nav.iloc[0] - 1
        cagr = (1 + cum) ** (1 / years) - 1
        vol = ret.std() * np.sqrt(rc.DAYS)
        down_vol = ret[ret < 0].std() * np.sqrt(rc.DAYS)
        mdd = (nav / nav.cummax() - 1).min()
        out[name] = {'누적수익률': cum, 'CAGR': cagr, '변동성(연율화)': vol,
                     '샤프비율': (cagr - rf) / vol, '음의 변동성(연율화)': down_vol,
                     '소르티노': (cagr - rf) / down_vol, 'MDD': mdd}
    return pd.DataFrame(out)


def yearly_returns(navs):
    """연도별 수익률 (첫 해는 시작일부터, 마지막 해는 마지막 날까지)"""
    year_end = navs.resample('YE').last()
    yearly = year_end.pct_change()
    yearly.iloc[0] = year_end.iloc[0] / navs.iloc[0] - 1
    yearly.index = yearly.index.year
    return yearly


# ── 5. 한 번에 실행 ──────────────────────────────────────────────────
def run_backtest(profile, use_factor=True, bp=BP, rf=RF, data=None):
    """한 성향의 백테스트 결과 (nav, 리밸런싱 비중 W, 일별 비중 Pw, 회전율)"""
    prices, picks = data if data is not None else load_data()
    W = target_weights(profile, prices, picks, use_factor)
    nav, Pw, turnover = cal_nav(W, daily_returns(prices, rf), bp=bp)
    return {'nav': nav, 'weights': W, 'daily_weights': Pw, 'turnover': turnover}


def compare(profile, bp=BP, rf=RF, data=None):
    """추천(팩터 종목 포함) vs 추천(ETF만) vs 단기채권만 vs KOSPI200만

    반환: 누적가치 표(navs), 성과 지표(perf), 연도별 수익률(yearly), 팩터 포함 백테스트 결과(result)
    """
    data = data if data is not None else load_data()
    prices = data[0]
    with_factor = run_backtest(profile, True, bp, rf, data)
    etf_only = run_backtest(profile, False, bp, rf, data)
    start = with_factor['nav'].index[0]
    bench = (1 + prices.loc[start:, ['KBOND', 'KOSPI200']].pct_change().fillna(0)).cumprod() * INIT
    navs = pd.DataFrame({'추천(팩터 종목 포함)': with_factor['nav'], '추천(ETF만)': etf_only['nav'],
                         '단기채권만': bench['KBOND'], 'KOSPI200만': bench['KOSPI200']})
    return {'navs': navs, 'perf': performance_table(navs, rf), 'yearly': yearly_returns(navs),
            'result': with_factor}


if __name__ == '__main__':
    pd.set_option('display.width', 200)
    data = load_data()
    for profile in rc.PROFILES:
        res = compare(profile, data=data)
        nav = res['navs']
        print(f"\n=== {profile} ({nav.index[0]:%Y-%m-%d} ~ {nav.index[-1]:%Y-%m-%d}, "
              f"연 1회 4월 리밸런싱, 거래비용 {BP:.1%}, 예금금리 {RF:.0%}) ===")
        print(res['perf'].round(3).to_string())
        print('연도별 수익률')
        print(res['yearly'].round(3).to_string())
        print('평균 회전율', f"{res['result']['turnover'].mean():.1%}")
