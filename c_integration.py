"""기존 recommender의 0~1 이름 비중을 C 화면의 코드별 %로 변환."""
import numpy as np
import pandas as pd
import recommender as rc
from portfolio_editor import render_portfolio_editor


def build_assets(prices):
    rows = []
    for ticker, info in rc.ETF_INFO.items():
        rows.append(dict(ticker=ticker, name=info['label'], asset_class=info['group'],
                         price=prices.iloc[-1][info['name']],
                         as_of=prices.index[-1].strftime('%Y-%m-%d'),
                         source='FinanceDataReader · 기존 data/etf_prices.csv'))
    return pd.DataFrame(rows)


def compare_target_weights(prices, base, edited, base_cash, edited_cash, budget):
    # 수량은 오늘 가격 기준이므로 과거 고정 보유 수량으로 사용하지 않는다.
    # 아래는 목표 비중을 매일 유지하는 기존 모형과 같은 가정의 비교다.
    recent = prices.sort_index().loc[prices.index.max() - pd.DateOffset(years=rc.LOOKBACK_YEARS):]
    daily = recent.pct_change(fill_method=None).iloc[1:]
    if len(daily) < 2 or daily.isna().any().any() or not np.isfinite(daily.to_numpy()).all():
        raise ValueError('성과 비교에 필요한 공통 가격 데이터가 부족하거나 누락됐어.')
    metrics, curves = [], {}
    for label, alloc in [('추천안', base), ('수정안', edited)]:
        code_to_name = {k: v['name'] for k,v in rc.ETF_INFO.items()}
        weight = pd.Series({code_to_name[r.ticker]: r.target_pct / 100 for r in alloc.itertuples()})
        returns = daily[weight.index] @ weight
        nav = pd.concat([pd.Series([100.0], index=[recent.index[0]]), (1+returns).cumprod()*100])
        curves[label] = nav
        metrics.append({'구성': label, '과거 연환산 산술평균 수익률 (%)': returns.mean()*rc.DAYS*100,
                        '과거 연환산 변동성 (%)':returns.std()*np.sqrt(rc.DAYS)*100,
                        '최대 낙폭 (%)':(nav/nav.cummax()-1).min()*100})
    return {'metrics':pd.DataFrame(metrics).set_index('구성'), 'nav':pd.DataFrame(curves),
            'methodology': f'{recent.index[0]:%Y-%m-%d} ~ {recent.index[-1]:%Y-%m-%d} · '
            f'현재 목표 비중을 과거 종가 수익률에 적용한 사후 시뮬레이션. 매일 목표 비중 유지, '
            f'연 {rc.DAYS}거래일, 현금 수익률 0%, 비용·세금 제외. '
            '현재 수량 및 잔여 현금의 과거 보유 성과가 아니며, 당시 실제 추천이나 미래 예측도 아니야. '
            '분배금·가격 조정 반영 여부는 원본 CSV 제공자에게 확인해야 해. 시작값은 100이야.'}


def render_existing_editor(prices, weights, budget):
    assets = build_assets(prices)
    recommended = {code: float(weights.get(info['name'],0))*100 for code,info in rc.ETF_INFO.items()}
    return render_portfolio_editor(assets, recommended, default_budget=budget,
        key='existing_recommendation_c',
        analysis_fn=lambda *args: compare_target_weights(prices, *args))
