"""기존 앱에서 render_portfolio_editor(assets, recommended_weights)를 호출한다."""
import pandas as pd
import streamlit as st
from portfolio_core import allocate, validate_assets, validate_weights

TERMS = {
    'ETF': '여러 주식이나 채권 등을 묶어 주식처럼 거래하는 펀드야.',
    '목표 비중과 실제 비중': '목표 비중은 설정한 비율, 실제 비중은 정수 주수로 계산한 매수금액의 비율이야.',
    '잔여 현금': '직접 남겨 둔 현금과 1주 미만이라 매수하지 못한 금액을 합한 값이야.',
    '최대 낙폭(MDD)': '분석 기간 중 이전 최고점에서 가장 크게 하락한 비율이야. 미래의 최대 손실 한도는 아니야.',
    '변동성': '분석 기간에 수익률이 흔들린 정도야. 손실 확률과 같은 뜻은 아니야.',
}


def render_portfolio_editor(assets, recommended_weights, *, default_budget=1_000_000,
                            key='portfolio_c', analysis_fn=None, demo=False):
    """비중 단위는 0~100(%). 가격·예산은 KRW. analysis_fn 계약은 README 참고."""
    st.header('내가 조정하는 모의 포트폴리오')
    if demo:
        st.warning('연습용 가상 상품·가격이야. 실제 ETF나 투자 추천 데이터가 아니야.')
    try:
        assets = validate_assets(assets)
        codes = assets.ticker.tolist()
        recommended = validate_weights(recommended_weights, codes)
        if default_budget <= 0:
            raise ValueError('기본 예산은 0보다 커야 해.')
    except (ValueError, TypeError) as exc:
        st.error(str(exc))
        return None
    signature = (tuple(codes), tuple(recommended.items()))
    def wk(t):
        return f'{key}_weight_{t}'
    def reset():
        for t in codes:
            st.session_state[wk(t)] = recommended[t]
    if st.session_state.get(f'{key}_signature') != signature:
        reset()
        st.session_state[f'{key}_signature'] = signature
    if st.session_state.get(f'{key}_default_budget') != int(default_budget):
        st.session_state[f'{key}_budget'] = int(default_budget)
        st.session_state[f'{key}_default_budget'] = int(default_budget)
    budget = st.number_input('모의 투자 예산 (원)', min_value=1,
                             step=10000, key=f'{key}_budget')
    st.caption('가격은 표시된 기준일의 원화 1주 가격이야. 수수료·세금·호가 차이는 계산에서 제외해.')
    st.button('추천 비중으로 초기화', on_click=reset, key=f'{key}_reset')
    st.subheader('1. 투자 비중 조정')
    st.caption('종목을 제외하려면 0%로 설정해. 합계가 100% 미만이면 나머지는 현금으로 남아.')
    cols = st.columns(2)
    weights = {}
    for i, row in enumerate(assets.itertuples(index=False)):
        with cols[i % 2]:
            weights[row.ticker] = st.slider(f'{row.name} · {row.asset_class} (%)',
                0.0, 100.0, step=1.0, key=wk(row.ticker))
    total = sum(weights.values())
    st.metric('설정한 비중 합계', f'{total:.1f}%')
    if total > 100 + 1e-8:
        st.error('합계를 100% 이하로 조정해 줘. 잘못된 비중으로 계산하거나 다운로드하지 않아.')
        return None
    st.info(f'목표 현금 비중: {max(0, 100-total):.1f}%')
    base, base_cash = allocate(assets, recommended, budget)
    edited, cash = allocate(assets, weights, budget)
    st.subheader('2. 추천안과 내 구성 비교')
    comparison = pd.DataFrame({'상품': assets.name, '추천 비중 (%)': [recommended[t] for t in codes],
                               '내 비중 (%)': [weights[t] for t in codes]})
    comparison.loc[len(comparison)] = ['현금', max(0, 100-sum(recommended.values())), max(0, 100-total)]
    st.bar_chart(comparison.set_index('상품'))
    c1, c2, c3 = st.columns(3)
    c1.metric('내 구성 매수금액', f'{budget-cash:,.0f}원')
    c2.metric('내 구성 잔여 현금', f'{cash:,.0f}원')
    c3.metric('추천안 잔여 현금', f'{base_cash:,.0f}원')
    labels = {'ticker':'종목코드', 'name':'상품명', 'asset_class':'자산군', 'target_pct':'목표 비중 (%)',
              'target_amount':'목표 금액 (원)', 'price':'1주 가격 (원)', 'quantity':'수량 (주)',
              'purchase_amount':'매수금액 (원)', 'actual_pct':'실제 비중 (%)', 'as_of':'가격 기준일', 'source':'출처'}
    st.dataframe(edited.rename(columns=labels), hide_index=True, width='stretch')
    unbought = edited[(edited.target_pct > 0) & (edited.quantity == 0)]
    if not unbought.empty:
        st.warning('배정 금액이 1주 가격보다 작은 상품: ' + ', '.join(unbought.name))
    if not edited.purchase_amount.sum():
        st.info('현재 구성으로는 매수할 상품이 없어. 예산 또는 비중을 조정할 수 있어.')
    st.subheader('3. 변경한 내용 이해하기')
    changes = [(r.name, weights[r.ticker]-recommended[r.ticker]) for r in assets.itertuples()]
    changed = [(n,d) for n,d in changes if abs(d)>1e-8]
    if not changed:
        st.write('현재 목표 비중은 추천안과 같아.')
    for name, delta in changed:
        st.write(f'• {name}: 추천안보다 {abs(delta):.1f}%p {"늘렸어" if delta>0 else "줄였어"}.')
    group = edited.groupby('asset_class').target_pct.sum()
    if not group.empty and group.max() > 60:
        st.info(f'{group.idxmax()}에 목표 예산의 {group.max():.1f}%를 배정했어. 다른 자산군과 비교해 봐.')
    if analysis_fn is None:
        st.caption('과거 성과 비교는 B 담당의 분석 함수 연결 후 표시돼. 현재는 구성·금액 비교를 제공해.')
    else:
        try:
            # 실제 정수 수량과 현금을 전달해 B가 목표 비중과 혼동하지 않도록 한다.
            result = analysis_fn(base.copy(), edited.copy(), base_cash, cash, budget)
            st.subheader('4. 과거 성과 비교')
            st.write(result['methodology'])
            st.dataframe(result['metrics'], width='stretch')
            st.line_chart(result['nav'])
            st.caption('과거 성과이며 미래 수익을 보장하지 않아. 분석 방법과 비용 반영 여부를 확인해.')
        except Exception:
            st.error('성과 분석에 실패했어. B 담당의 데이터와 함수 반환 형식을 확인해 줘.')
    with st.expander('용어와 데이터 출처 확인'):
        for term, description in TERMS.items():
            st.markdown(f'**{term}**: {description}')
        st.dataframe(assets[['ticker','name','as_of','source']], hide_index=True)
    export = edited.copy()
    export['budget_krw'] = budget
    export['remaining_cash_krw'] = cash
    st.download_button('내 구성 CSV 다운로드', export.to_csv(index=False).encode('utf-8-sig'),
                        'my_portfolio.csv', 'text/csv', key=f'{key}_download')
    return {'allocation': edited, 'cash':cash, 'weights':weights, 'budget':budget}
