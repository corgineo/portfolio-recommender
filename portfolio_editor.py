"""모의 포트폴리오 화면 (별도 페이지)

- 추천 비중에서 시작해 상품을 더하거나 빼고, 슬라이더로 비중을 바꿔요.
- 비중 합계는 100%를 넘을 수 없어요: 슬라이더를 남은 비중보다 크게 움직이면 남은 만큼으로 바로 맞춰져요.
- 값은 session_state['mock'] 에 저장해서 다른 페이지에 다녀와도 그대로 남아요.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import recommender as rc
import service as svc
from portfolio_core import allocate
from ui import html, esc, won, card_title, dot

STEP = 0.5
GROUP_ORDER = ['채권·예금', '주식', '대안투자', '자산배분']
TERMS = {
    '목표 비중과 실제 비중': '목표 비중은 정한 비율, 실제 비중은 1주 단위로 산 금액의 비율이에요.',
    '남는 현금': '비워 둔 비중과 1주 가격보다 작아 사지 못한 금액을 합한 돈이에요.',
    '최대 낙폭(MDD)': '분석 기간 중 이전 최고점에서 가장 크게 떨어진 비율이에요. 앞으로의 최대 손실 한도는 아니에요.',
    '변동성': '수익률이 흔들린 정도예요. 클수록 오르내림이 커요.',
}


def _wkey(name):
    return f'mw_{name}'


def _state(res, ss):
    """추천이 바뀌면(성향·예산·상품 범위) 모의 포트폴리오를 새 추천으로 다시 시작해요"""
    rec_pct = svc.floor_pct(res['weights'], STEP)
    sig = (tuple(sorted(rec_pct.items())), int(ss.budget))
    m = ss.get('mock')
    if not m or m.get('sig') != sig:
        m = {'sig': sig, 'rec': rec_pct, 'w': dict(rec_pct), 'budget': int(ss.budget), 'msg': ''}
        ss['mock'] = m
        for k in [k for k in ss.keys() if str(k).startswith('mw_') or k in ('mock_budget_w', 'mock_items_w')]:
            del ss[k]
    return m


def _reset(ss):
    m = ss['mock']
    m['w'] = dict(m['rec'])
    m['msg'] = ''
    for k in [k for k in ss.keys() if str(k).startswith('mw_') or k == 'mock_items_w']:
        del ss[k]


def _on_slide(ss, name):
    """슬라이더를 움직이면: 합계가 100%를 넘지 않게 그 자리에서 잘라요"""
    m = ss['mock']
    want = float(ss[_wkey(name)])
    got = svc.clamp_weight(name, want, m['w'])
    if got < want:
        ss[_wkey(name)] = got
        m['msg'] = f'합계가 100%를 넘지 않도록 {got:.1f}%로 맞췄어요. 더 담으려면 다른 상품 비중을 먼저 줄여 주세요.'
    else:
        m['msg'] = ''
    m['w'][name] = got


def _on_items(ss):
    m = ss['mock']
    chosen = list(ss['mock_items_w'])
    for n in list(m['w']):
        if n not in chosen:
            del m['w'][n]
            ss.pop(_wkey(n), None)
    for n in chosen:
        m['w'].setdefault(n, 0.0)
    m['msg'] = ''


def _on_budget(ss):
    v = ss.get('mock_budget_w')
    if v:
        ss['mock']['budget'] = int(v)


def render(res, data, ss, go_page, open_detail):
    products, prices = data['products'], data['prices']
    last = prices.ffill().iloc[-1]
    m = _state(res, ss)
    colors = rc.color_map(sorted(products, key=lambda n: (GROUP_ORDER.index(products[n]['group'])
                                                          if products[n]['group'] in GROUP_ORDER else 9,
                                                          -res['weights'].get(n, 0))),
                          svc.group_of(products))
    colors.update(res['colors'])

    # 고를 수 있는 상품: 지금 상품 범위에서 가격이 있는 것 (현금 제외)
    choices = [n for n in rc.ETF_NAMES] + [n for v in data['extra'].values() for n in v] + list(data.get('picks', []))
    choices = [n for n in choices if n in prices and pd.notna(last.get(n))]
    order = {n: i for i, n in enumerate(choices)}
    choices.sort(key=lambda n: (GROUP_ORDER.index(products[n]['group']) if products[n]['group'] in GROUP_ORDER else 9,
                                order[n]))

    html(f"""<div class="res-hero mock-hero"><div class="tags"><span>#모의투자</span><span>#{esc(res['judge']['type'])}</span>
      <span>#{esc(res['profile'])}배분</span></div>
      <h2>내가 조정하는 모의 포트폴리오</h2>
      <div class="desc">추천 비중에서 시작해요. 상품을 더하거나 빼고 비중을 바꿔 보면, 금액·수량과 과거 성과가 바로 다시 계산돼요.
      실제 주문은 되지 않아요.</div></div>""")

    top1, top2, top3 = st.columns([1.2, 1, 1], vertical_alignment='bottom')
    if 'mock_budget_w' not in ss:
        ss['mock_budget_w'] = m['budget']
    top1.number_input('모의 투자 예산 (원)', min_value=10_000, max_value=10_000_000_000, step=100_000,
                      key='mock_budget_w', on_change=_on_budget, args=(ss,), format='%d')
    top2.button('추천 비중으로 되돌리기', width='stretch', key='mock_reset', on_click=_reset, args=(ss,))
    top3.button('추천 결과로 돌아가기', width='stretch', key='mock_back', on_click=go_page, args=('result',))
    budget = m['budget']
    st.caption(f'가격은 {data["as_of"]:%Y.%m.%d} 종가(원) 기준이에요. 수수료·세금·호가 차이는 계산에서 빼요.'
               + (f' 미국 상품은 {data["us_as_of"]} 미국 종가 × 환율 {data["fx"]:,.1f}원으로 환산했어요.' if data['fx'] else ''))

    # 1. 상품 고르기 + 비중
    total = sum(m['w'].values())
    remain = max(0.0, 100 - total)
    with st.container(border=True):
        card_title('1. 상품과 비중 정하기', '0%로 두면 사지 않아요. 합계는 100%를 넘을 수 없고, 남은 비중은 현금으로 둬요.')
        if 'mock_items_w' not in ss:
            ss['mock_items_w'] = [n for n in choices if n in m['w']]
        st.multiselect('담을 상품', choices, key='mock_items_w', on_change=_on_items, args=(ss,),
                       format_func=lambda n: f'{products[n]["short"]} · {rc.BASE_DESC.get(n, products[n]["group"])}',
                       placeholder='상품을 골라 주세요')
        # 합계 막대
        seg = ''.join(f'<i style="width:{v:.2f}%;background:{colors.get(n, "#98a2b3")}"></i>'
                      for n, v in sorted(m['w'].items(), key=lambda x: -x[1]) if v > 0)
        html(f"""<div class="sumbar"><div class="bar">{seg}<i style="width:{remain:.2f}%;background:#e4e7ec"></i></div>
             <div class="lab"><span>합계 <b>{total:.1f}%</b></span><span>남은 비중(현금) <b>{remain:.1f}%</b></span></div></div>""")
        if m.get('msg'):
            st.info(m['msg'])
        items = [n for n in choices if n in m['w']]
        if not items:
            st.info('담은 상품이 없어요. 위에서 상품을 고르거나 "추천 비중으로 되돌리기"를 눌러 주세요.')
        cols = st.columns(2, gap='large')
        for i, n in enumerate(items):
            k = _wkey(n)
            if k not in ss:
                ss[k] = float(m['w'][n])
            p = products[n]
            rec = m['rec'].get(n, 0.0)
            with cols[i % 2]:
                st.slider(f'{p["short"]} · {rc.GROUP_SHORT.get(p["group"], p["group"])} (추천 {rec:.1f}%)',
                          0.0, 100.0, step=STEP, key=k, on_change=_on_slide, args=(ss, n), format='%.1f%%')

    weights = {n: m['w'][n] for n in items}
    total = sum(weights.values())
    assets_names = sorted(set(items) | set(m['rec']), key=lambda n: -max(weights.get(n, 0), m['rec'].get(n, 0)))
    assets = pd.DataFrame([dict(ticker=n, name=products[n]['short'], asset_class=products[n]['group'],
                                price=float(last[n]), as_of=f'{data["as_of"]:%Y-%m-%d}', source=products[n]['source'])
                           for n in assets_names])
    try:
        if assets.empty:
            raise ValueError('담은 상품이 없어요.')
        mine, cash = allocate(assets, {n: weights.get(n, 0.0) for n in assets_names}, budget)
        base, base_cash = allocate(assets, {n: m['rec'].get(n, 0.0) for n in assets_names}, budget)
    except ValueError as exc:
        mine, cash, base, base_cash = None, budget, None, budget
        if not assets.empty:
            st.error(f'계산할 수 없어요: {exc}')

    # 2. 결과
    with st.container(border=True):
        card_title('2. 내 구성으로 사면', f'예산 {won(budget)} · 1주 단위로 계산해요')
        if mine is not None:
            k1, k2, k3 = st.columns(3)
            k1.metric('사는 금액', f'{budget - cash:,.0f}원')
            k2.metric('남는 현금', f'{cash:,.0f}원')
            k3.metric('추천안의 남는 현금', f'{base_cash:,.0f}원')
            rows = mine[mine.target_pct > 0].sort_values('target_pct', ascending=False)
            body = ''.join(
                f'<tr><td>{dot(colors.get(r.ticker, "#98a2b3"))}<span class="nm">{esc(r.name)}</span></td>'
                f'<td>{r.target_pct:.1f}%</td><td>{r.actual_pct:.1f}%</td><td class="amt">{r.purchase_amount:,.0f}원</td>'
                f'<td>{r.price:,.0f}원</td><td>{"<span class=zero>0주</span>" if r.quantity == 0 else f"{r.quantity:,}주"}</td></tr>'
                for r in rows.itertuples())
            body += (f'<tr class="cash"><td>{dot("#98a2b3")}<span class="nm">현금</span></td><td>{100 - total:.1f}%</td>'
                     f'<td>{cash / budget * 100:.1f}%</td><td class="amt">{cash:,.0f}원</td><td></td><td></td></tr>')
            html(f'<div class="hold-wrap"><table class="holdings compact"><thead><tr><th>상품</th><th>목표 비중</th>'
                 f'<th>실제 비중</th><th>금액</th><th>현재가</th><th>수량</th></tr></thead><tbody>{body}</tbody></table></div>')
            unbought = rows[rows.quantity == 0]
            if not unbought.empty:
                st.warning('배정 금액이 1주 가격보다 작아 사지 못하는 상품이 있어요: ' + ', '.join(unbought.name)
                           + '. 비중을 늘리거나 예산을 키워 보세요.')
            export = mine.copy()
            export['budget_krw'] = budget
            export['remaining_cash_krw'] = cash
            st.download_button('내 구성 CSV로 내려받기', export.to_csv(index=False).encode('utf-8-sig'),
                               'my_portfolio.csv', 'text/csv', key='mock_download')
        else:
            st.info('담은 상품이 없어 전액 현금이에요.')

    # 3. 추천안과 비교
    with st.container(border=True):
        card_title('3. 추천안과 비교', '자산군별 비중과 상품별 변화를 같이 봐요')
        g_rec, g_mine = {}, {}
        for n, v in m['rec'].items():
            g_rec[products[n]['group']] = g_rec.get(products[n]['group'], 0) + v
        for n, v in weights.items():
            g_mine[products[n]['group']] = g_mine.get(products[n]['group'], 0) + v
        g_rec['유동성'] = 100 - sum(m['rec'].values())
        g_mine['유동성'] = 100 - total
        fig = go.Figure()
        for g in GROUP_ORDER + ['유동성']:
            fig.add_bar(y=['내 구성', '추천안'], x=[g_mine.get(g, 0), g_rec.get(g, 0)], name=rc.GROUP_SHORT[g],
                        orientation='h', marker_color=rc.GROUP_BASE[g],
                        hovertemplate=f'{rc.GROUP_SHORT[g]} %{{x:.1f}}%<extra></extra>')
        fig.update_layout(barmode='stack', height=170, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)',
                          plot_bgcolor='rgba(0,0,0,0)', font=dict(family='Pretendard', color='#475467'),
                          legend=dict(orientation='h', y=-0.3), xaxis=dict(range=[0, 100], ticksuffix='%', showgrid=False))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        changed = [(n, weights.get(n, 0) - m['rec'].get(n, 0)) for n in assets_names]
        changed = [(n, d) for n, d in changed if abs(d) > 1e-9]
        if not changed:
            st.write('지금 구성은 추천안과 같아요.')
        else:
            lines = ''.join(f'<li>{dot(colors.get(n, "#98a2b3"))}{esc(products[n]["short"])}: 추천보다 '
                            f'<b>{abs(d):.1f}%p {"늘렸어요" if d > 0 else "줄였어요"}</b></li>' for n, d in changed[:12])
            more = f'<li>외 {len(changed) - 12}개</li>' if len(changed) > 12 else ''
            html(f'<ul class="changes">{lines}{more}</ul>')
        big = max(((g, v) for g, v in g_mine.items() if g != '유동성'), key=lambda x: x[1], default=None)
        if big and big[1] > 60:
            st.info(f'{rc.GROUP_SHORT[big[0]]}에 {big[1]:.1f}%를 담았어요. 한 자산군에 많이 몰리면 그 자산이 떨어질 때 '
                    '함께 크게 흔들릴 수 있어요.')

    # 4. 과거 성과 비교
    with st.container(border=True):
        try:
            cmp = svc.compare_weights(prices, {n: v * 100 for n, v in res['weights'].items() if n != rc.CASH}, weights)
            card_title('4. 과거 성과 비교', f'{cmp["start"]:%Y.%m.%d} ~ {cmp["end"]:%Y.%m.%d} · 시작값 100 · 지금 비중을 '
                                           '매일 유지했다고 본 모의 계산이에요')
            fig2 = go.Figure()
            for label, color, dash in [('추천안', '#98a2b3', 'dot'), ('내 구성', '#2563eb', None)]:
                fig2.add_scatter(x=cmp['nav'].index, y=cmp['nav'][label], name=label,
                                 line=dict(color=color, width=3 if dash is None else 2, dash=dash))
            fig2.update_layout(height=280, margin=dict(t=10, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)',
                               plot_bgcolor='rgba(0,0,0,0)', font=dict(family='Pretendard', color='#475467'),
                               legend=dict(orientation='h', y=1.12, x=0), hovermode='x unified',
                               yaxis=dict(gridcolor='#f2f4f7'), xaxis=dict(showgrid=False))
            st.plotly_chart(fig2, width='stretch', config={'displayModeBar': False})
            st.dataframe(cmp['metrics'].round(1), width='stretch')
            st.caption('현금 수익률 0%, 수수료·세금 제외. 과거 성과이며 앞으로의 수익을 보장하지 않아요.')
        except ValueError as exc:
            card_title('4. 과거 성과 비교', '')
            st.warning(f'과거 성과를 계산할 수 없어요: {exc}')

    with st.expander('용어 풀이'):
        for term, desc in TERMS.items():
            st.markdown(f'**{term}**: {desc}')

    if items:
        d1, d2 = st.columns([2, 1], vertical_alignment='bottom')
        pick = d1.selectbox('담은 상품 자세히 보기', items, format_func=lambda n: products[n]['short'], key='mock_detail_pick')
        d2.button('분석 보기', width='stretch', key='mock_detail_go', on_click=open_detail, args=(pick, 'mock'))
    return {'weights': weights, 'budget': budget, 'cash': cash}
