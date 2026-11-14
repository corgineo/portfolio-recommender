"""팀 추천(recommender)의 0~1 이름 비중을 편집기(portfolio_editor)의 코드별 %로 바꿔 연결해요."""
import numpy as np
import pandas as pd
import recommender as rc
from portfolio_editor import render_portfolio_editor

SOURCE_ETF = 'FinanceDataReader · data/etf_prices.csv'
SOURCE_KR = 'FinanceDataReader · data/stock_kr.csv'
SOURCE_US = 'FinanceDataReader · data/stock_us.csv (미국 종가 × 원/달러 환율)'
SOURCE_FACTOR = 'FinanceDataReader · data/stock_prices.csv'


def build_assets(prices, extra=()):
    rows = []
    for ticker, info in rc.ETF_INFO.items():
        rows.append(dict(ticker=ticker, name=info['label'], asset_class=info['group'],
                         price=prices.iloc[-1][info['name']],
                         as_of=prices.index[-1].strftime('%Y-%m-%d'), source=SOURCE_ETF))
    cat = rc.STOCK_CATALOG
    for name in extra:                                  # 이번 추천에 들어간 개별 종목
        in_cat = cat is not None and name in cat.index
        code = cat.at[name, 'code'] if in_cat else name
        source = (SOURCE_US if cat.at[name, 'currency'] == 'USD' else SOURCE_KR) if in_cat else SOURCE_FACTOR
        rows.append(dict(ticker=code, name=rc.NAME_TO_LABEL.get(name, name), asset_class='주식',
                         price=prices[name].ffill().iloc[-1],
                         as_of=prices[name].dropna().index[-1].strftime('%Y-%m-%d'), source=source))
    return pd.DataFrame(rows)


def _code_to_name(prices=None):
    """종목코드 → 가격 표의 열 이름 (ETF: '069500' → 'KOSPI200', 개별주: '005930' → 열 이름)"""
    m = {k: v['name'] for k, v in rc.ETF_INFO.items()}
    cat = rc.STOCK_CATALOG
    if cat is not None:
        m.update({r['code']: n for n, r in cat.iterrows()})
    return m


def compare_target_weights(prices, base, edited, base_cash, edited_cash, budget):
    """추천안과 수정안의 목표 비중을 최근 LOOKBACK_YEARS 년 종가 수익률에 적용한 사후 비교.
    오늘 가격으로 계산한 수량을 과거 보유 수량으로 쓰지 않아요 (매일 목표 비중 유지 가정)."""
    recent = prices.sort_index().loc[prices.index.max() - pd.DateOffset(years=rc.LOOKBACK_YEARS):]
    daily = recent.pct_change(fill_method=None).iloc[1:]
    used = {r.ticker for r in list(base.itertuples()) + list(edited.itertuples()) if r.target_pct > 0}
    # 이름이 곧 열 이름인 종목(팩터 종목)만 그대로 쓰고, ETF·개별주 코드는 열 이름 매핑을 우선해요.
    # (예전에는 {**매핑, **{t: t}} 순서라 '069500' → '069500' 으로 덮여 ETF 열을 찾지 못했어요)
    code_to_name = {**{t: t for t in used}, **_code_to_name(prices)}
    cols = sorted({code_to_name[t] for t in used})
    missing = [c for c in cols if c not in daily.columns]
    if missing:
        raise ValueError(f'가격 자료가 없는 상품이 있어요: {", ".join(missing)}')
    daily = daily[cols]
    if len(daily) < 2 or daily.isna().any().any() or not np.isfinite(daily.to_numpy()).all():
        raise ValueError('성과 비교에 필요한 공통 가격 자료가 부족해요.')
    metrics, curves = [], {}
    for label, alloc in [('추천안', base), ('내 구성', edited)]:
        alloc = alloc[alloc.target_pct > 0]
        weight = pd.Series({code_to_name[r.ticker]: r.target_pct / 100 for r in alloc.itertuples()}, dtype=float)
        returns = daily[weight.index] @ weight if len(weight) else pd.Series(0.0, index=daily.index)
        nav = pd.concat([pd.Series([100.0], index=[recent.index[0]]), (1 + returns).cumprod() * 100])
        curves[label] = nav
        metrics.append({'구성': label, '연환산 수익률 (%)': returns.mean() * rc.DAYS * 100,
                        '변동성 (%)': returns.std() * np.sqrt(rc.DAYS) * 100,
                        '최대 낙폭 (%)': (nav / nav.cummax() - 1).min() * 100})
    return {'metrics': pd.DataFrame(metrics).set_index('구성'), 'nav': pd.DataFrame(curves),
            'start': recent.index[0], 'end': recent.index[-1],
            'methodology': f'{recent.index[0]:%Y.%m.%d} ~ {recent.index[-1]:%Y.%m.%d} · 시작값 100 · '
            '지금 목표 비중을 매일 유지했다고 가정한 과거 모의 계산이에요. 현금 수익 0%, 분배금·수수료·세금은 빠져 있어요. '
            '앞으로의 수익을 보장하지 않아요.'}


def editor_inputs(prices, weights):
    """편집기 입력: 상품표(assets)와 코드별 추천 비중(%)"""
    prices = prices.ffill()                             # 개별 종목은 마지막 날 가격이 비어 있으면 직전 가격 (상장 전 NaN 은 그대로)
    extra = [n for n in weights.index if n not in rc.ETF_NAMES and n != rc.CASH]
    assets = build_assets(prices, extra)
    code_to_name = _code_to_name(prices)
    tickers = set(assets.ticker)
    recommended = {c: float(weights.get(n, 0)) * 100 for c, n in code_to_name.items() if c in tickers}
    for name in extra:                                  # 팩터 종목처럼 코드가 products.csv 에 없는 경우: 이름이 키
        if rc.STOCK_CATALOG is None or name not in rc.STOCK_CATALOG.index:
            recommended[name] = float(weights.get(name, 0)) * 100
    return prices, assets, recommended


def render_existing_editor(prices, weights, budget, colors=None):
    prices, assets, recommended = editor_inputs(prices, weights)
    code_to_name = {**{t: t for t in assets.ticker}, **_code_to_name(prices)}
    ticker_colors = None
    if colors:                                          # 결과 화면과 같은 색 (이름 → 코드)
        ticker_colors = {t: colors[code_to_name[t]] for t in assets.ticker if code_to_name[t] in colors}
    return render_portfolio_editor(assets, recommended, default_budget=budget,
                                   key='existing_recommendation_c', colors=ticker_colors,
                                   analysis_fn=lambda *args: compare_target_weights(prices, *args))
