"""나만의 포트폴리오 (제작 공간, 별도 페이지) — 서비스의 핵심 기능

- 진단 전: 제작 소개/시작 화면(render_intro). 맞춤 추천 없이 가짜 구성을 보여 주지 않고, 화면 예시임을 밝혀요.
- 진단 후: 워크벤치(render). 데스크톱은 조절 패널 38% : 라이브 프리뷰 62% (5:8), 좁은 화면은 한 열.
- 추천 비중에서 시작해요. 한 번에 상품 하나를 골라 그 상품의 비중만 슬라이더로 바꿔요.
- 비중 합계는 100%를 넘을 수 없어요: 슬라이더를 남은 비중보다 크게 움직이면 남은 만큼으로 바로 맞춰져요.
- 값은 session_state['mock'] 에 저장해서 다른 페이지에 다녀와도 그대로 남아요. (내부 이름 mock 은 호환을 위해 유지)
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import recommender as rc
import service as svc
from portfolio_core import allocate
from ui import html, esc, won, won_exact, dot, easy_group, donut_svg, GROUP_TINY, plot_style, BRAND, TERMS as UI_TERMS

STEP = 0.5
GROUP_ORDER = ['채권·예금', '주식', '대안투자', '자산배분']
TERMS = {
    '포트폴리오': UI_TERMS['포트폴리오'],
    '비중': UI_TERMS['비중'],
    '목표 비중과 실제 비중': '목표 비중은 내가 정한 비율, 실제 비중은 1주 단위로 산 금액의 비율이에요.',
    '남는 현금': '비워 둔 비중과 1주 가격보다 작아 사지 못한 금액을 합한 돈이에요.',
    '최대 낙폭(MDD)': UI_TERMS['최대 낙폭'],
    '변동성': UI_TERMS['변동성'],
}


def _wkey(name):
    return f'mw_{name}'


def _state(res, ss):
    """추천이 바뀌면(성향·예산·상품 범위) 제작 구성을 새 추천으로 다시 시작해요"""
    rec_pct = svc.floor_pct(res['weights'], STEP)
    sig = (tuple(sorted(rec_pct.items())), int(ss.budget))
    m = ss.get('mock')
    if not m or m.get('sig') != sig:
        m = {'sig': sig, 'rec': rec_pct, 'w': dict(rec_pct), 'budget': int(ss.budget), 'msg': ''}
        ss['mock'] = m
        for k in [k for k in ss.keys() if str(k).startswith('mw_') or k in ('mock_budget_w', 'mock_items_w', 'mock_pick')]:
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
    added = [n for n in chosen if n not in m['w']]
    for n in list(m['w']):
        if n not in chosen:
            del m['w'][n]
            ss.pop(_wkey(n), None)
    for n in chosen:
        m['w'].setdefault(n, 0.0)
    if added:
        ss['mock_pick'] = m['pick'] = added[-1]          # 새로 더한 상품을 바로 조절할 수 있게 골라 둬요
    m['msg'] = ''


def _on_pick(ss):
    ss['mock']['pick'] = ss.get('mock_pick')
    ss['mock']['msg'] = ''


def _on_budget(ss):
    v = ss.get('mock_budget_w')
    if v:
        ss['mock']['budget'] = int(v)


def _pick_line(name, p, pct, mine, budget):
    """고른 상품 한 줄: 목표 금액 → 1주 가격 × 수량 = 실제로 사는 금액 (allocate 결과를 그대로 읽어요)"""
    if pct <= 0:
        return '<p class="pickline">0%라 이 상품은 사지 않아요.</p>'
    if mine is None or name not in set(mine.ticker):
        return ''
    r = mine[mine.ticker == name].iloc[0]
    target = r.target_amount
    if r.quantity == 0:
        return (f'<p class="pickline warn">목표 금액 {target:,.0f}원이 1주 가격 {r.price:,.0f}원보다 작아 '
                f'<b>0주</b>예요 (한 주를 살 돈이 부족해요). 이 돈은 남는 현금에 더해져요.</p>')
    return (f'<p class="pickline">목표 금액 {target:,.0f}원 → 1주 {r.price:,.0f}원 × <b>{r.quantity:,}주</b> = '
            f'실제로 <b>{r.purchase_amount:,.0f}원</b>어치 사요. 1주가 안 되는 나머지 {target - r.purchase_amount:,.0f}원은 남는 현금이에요.</p>')


# ── 진단 전: 제작 소개/시작 화면 ──────────────────────────────────────────
def render_intro(ss, start, title):
    """맞춤 구성이 아닌 '화면 예시'만 보여 줘요. 실제 제작은 7문항 진단이 끝나야 시작돼요."""
    partial = any(a is not None for a in ss.ans)
    n = ss.ans.index(None) + 1 if None in ss.ans else len(ss.ans)
    ex = rc.PROFILE_TABLE['성장형']
    segs = [(easy_group(g), ex[g], rc.GROUP_BASE[g]) for g in GROUP_ORDER + ['유동성']]
    with st.container(key='build_intro'):
        left, right = st.columns([8, 5], gap='large', vertical_alignment='center')
        with left:
            html(f"""<div class="page-h big"><span class="eyebrow">핵심 기능 · 포트폴리오 제작</span>
            <h1>{title}</h1>
            <p class="lead">추천 구성을 출발점으로, 상품을 하나씩 골라 비중을 바꾸며 <b>내 기준의 투자 구성</b>을 완성해요.
            바꿀 때마다 도넛 그래프와 사는 금액·수량·남는 현금이 함께 다시 계산돼요.</p></div>
            <ol class="mini-steps">
              <li class="{'on' if partial else ''}"><span>1</span><b>성향 진단 7문항</b><em>약 3분 · 제작의 출발점을 정해요</em></li>
              <li><span>2</span><b>추천 구성에서 시작</b><em>내 성향의 추천 비중이 먼저 채워져요</em></li>
              <li><span>3</span><b>상품 하나씩 조절</b><em>더하기·빼기 · 예산 바꾸기 · CSV 저장</em></li>
            </ol>
            <div class="need">실제 추천에 기반해 만들려면 먼저 <b>7문항 성향 진단</b>이 필요해요.
            진단을 마치면 이 화면으로 바로 돌아와 제작을 시작해요.</div>""")
            label = f'진단 이어서 하고 만들기 (질문 {n} / 7)' if partial else '성향 진단하고 만들기 시작'
            st.button(label, type='primary', key='build_start', on_click=start)
        with right:
            rows = ''.join(f'<tr><td>{dot(c)}{esc(nm.split(" (")[0])}</td><td>{v}%</td></tr>' for nm, v, c in segs)
            html(f"""<figure class="hero-fig bench-demo"><figcaption><span class="tag">화면 예시</span>제작 공간은 이렇게 생겼어요</figcaption>
            <div class="demo-ctl"><span>조절할 상품</span><div class="fake-sel">상품 하나 고르기 ▾</div>
              <div class="fake-slider"><i style="width:26%"></i><b style="left:26%"></b></div></div>
            <div class="demo-out">{donut_svg(segs, '목표 비율', '합계 100%', '', size=150, thick=22, label='화면 예시 구성')}
              <table class="mini">{rows}</table></div>
            <p class="fig-note">예시 비율(위험 중립형 중 한 경우)이에요. 내 맞춤 구성이 아니에요.</p></figure>""")


# ── 진단 후: 워크벤치 ───────────────────────────────────────────────────
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
    budget = m['budget']

    items = [n for n in choices if n in m['w']]
    total = sum(m['w'].values())
    remain = max(0.0, 100 - total)
    # 금액·수량 계산 (portfolio_core.allocate): 조절 패널 한 줄 안내와 프리뷰가 같은 결과를 써요
    weights = {n: m['w'][n] for n in items}
    assets_names = sorted(set(items) | set(m['rec']), key=lambda n: -max(weights.get(n, 0), m['rec'].get(n, 0)))
    assets = pd.DataFrame([dict(ticker=n, name=products[n]['short'], asset_class=products[n]['group'],
                                price=float(last[n]), as_of=f'{data["as_of"]:%Y-%m-%d}', source=products[n]['source'])
                           for n in assets_names])
    calc_err = None
    try:
        if assets.empty:
            raise ValueError('담은 상품이 없어요.')
        mine, cash = allocate(assets, {n: weights.get(n, 0.0) for n in assets_names}, budget)
        base, base_cash = allocate(assets, {n: m['rec'].get(n, 0.0) for n in assets_names}, budget)
    except ValueError as exc:
        mine, cash, base, base_cash = None, budget, None, budget
        if not assets.empty:
            calc_err = str(exc)

    total = sum(weights.values())
    # 자산 종류별 합계 (추천 vs 내 구성, 목표 비율)
    g_rec, g_mine = {}, {}
    for n, v in m['rec'].items():
        g_rec[products[n]['group']] = g_rec.get(products[n]['group'], 0) + v
    for n, v in weights.items():
        g_mine[products[n]['group']] = g_mine.get(products[n]['group'], 0) + v
    g_rec['유동성'] = 100 - sum(m['rec'].values())
    g_mine['유동성'] = 100 - total

    # 머리: 전용 타이틀 + 출발점 + 되돌리기
    with st.container(key='bench_head'):
        h1, h2 = st.columns([8, 5], vertical_alignment='bottom')
        with h1:
            html(f"""<div class="page-h"><span class="eyebrow">포트폴리오 제작하기 · 모의 구성 (실제 주문 없음)</span>
            <h1>나만의 포트폴리오</h1>
            <p><b>{esc(res['judge']['type'])}</b> 추천 구성에서 시작했어요. 상품 하나를 골라 비중을 바꾸면 구성 그래프와 금액이 바로 바뀌어요.</p></div>""")
        with h2:
            with st.container(key='bench_tools', horizontal=True, horizontal_alignment='right', gap='small'):
                st.button('추천대로 되돌리기', key='mock_reset', on_click=_reset, args=(ss,))
                st.button('추천 결과 보기', key='mock_back', on_click=go_page, args=('result',))

    with st.container(key='bench'):
        ctl, prev = st.columns([5, 8], gap='large')
        # ── 왼쪽 38%: 조절 패널 ──
        with ctl:
            with st.container(border=True, key='mock_edit'):
                html(f"""<div class="panel-h"><b>조절하기</b><span>제작 예산 {won(budget)}</span></div>
                <div class="sumbar"><div class="bar">{''.join(f'<i style="width:{v:.2f}%;background:{colors.get(n, "#98a2b3")}"></i>' for n, v in sorted(m['w'].items(), key=lambda x: -x[1]) if v > 0)}<i style="width:{remain:.2f}%;background:#E4DED3"></i></div>
                <div class="lab"><span>담은 비중 <b>{total:.1f}%</b></span><span>비워 둔 비중(현금) <b>{remain:.1f}%</b></span></div></div>""")
                if m.get('msg'):
                    st.info(m['msg'])
                if not items:
                    st.info('담은 상품이 없어요. 아래 "상품 더하기·빼기"에서 상품을 고르거나 "추천대로 되돌리기"를 눌러 주세요.')
                else:
                    if ss.get('mock_pick') not in items:     # 다른 화면에 다녀오면 위젯 값이 지워져서, 저장해 둔 선택으로 되살려요
                        ss['mock_pick'] = m.get('pick') if m.get('pick') in items else max(items, key=lambda n: m['w'].get(n, 0))
                    pick = st.selectbox('① 조절할 상품 고르기', items, key='mock_pick', on_change=_on_pick, args=(ss,),
                                        format_func=lambda n: f'{products[n]["short"]} · {easy_group(products[n]["group"])}')
                    m['pick'] = pick
                    k = _wkey(pick)
                    if k not in ss:
                        ss[k] = float(m['w'][pick])
                    p = products[pick]
                    rec = m['rec'].get(pick, 0.0)
                    st.slider(f'② {p["short"]}의 비중 (추천 {rec:.1f}%)',
                              0.0, 100.0, step=STEP, key=k, on_change=_on_slide, args=(ss, pick), format='%.1f%%')
                    html(_pick_line(pick, p, m['w'].get(pick, 0.0), mine, budget))
                    html(f'<p class="hint">최대 {m["w"].get(pick, 0) + remain:.1f}%까지 올릴 수 있어요 '
                         f'(비워 둔 비중 {remain:.1f}% 포함).</p>')
                with st.expander(f'상품 더하기·빼기 (선택 {len(items)}개)'):
                    if 'mock_items_w' not in ss:
                        ss['mock_items_w'] = [n for n in choices if n in m['w']]
                    st.multiselect('담을 상품', choices, key='mock_items_w', on_change=_on_items, args=(ss,),
                                   format_func=lambda n: f'{products[n]["short"]} · {rc.BASE_DESC.get(n, easy_group(products[n]["group"]))}',
                                   placeholder='상품을 골라 주세요')
                    st.caption('새로 더한 상품은 0%에서 시작해요. 위 ①에서 골라 비중을 올려 주세요.')
                with st.expander(f'제작 예산 바꾸기 (지금 {won(budget)})'):
                    if 'mock_budget_w' not in ss:
                        ss['mock_budget_w'] = m['budget']
                    st.number_input('제작 예산 (원)', min_value=10_000, max_value=10_000_000_000, step=100_000,
                                    key='mock_budget_w', on_change=_on_budget, args=(ss,), format='%d')
                    st.caption('여기서 바꾼 예산은 나만의 포트폴리오에만 적용돼요. 추천 자체를 다시 받으려면 추천 결과 화면의 "예산·상품 범위 바꾸기"를 눌러 주세요.')

        # ── 오른쪽 62%: 라이브 프리뷰 ──
        with prev:
            with st.container(border=True, key='mock_preview'):
                spent = budget - cash
                html(f"""<div class="kpis tight"><div><span>제작 예산</span><b>{won_exact(budget)}</b><em>{budget:,.0f}원</em></div>
                <div class="hl"><span>실제로 사는 돈</span><b>{won_exact(spent)}</b><em>{spent:,.0f}원 · 예산의 {spent / budget:.1%}</em></div>
                <div><span>남는 현금</span><b>{won_exact(cash)}</b><em>{cash:,.0f}원 · 비워 둔 비중 + 잔돈</em></div></div>""")
                if calc_err:
                    st.error(f'계산할 수 없어요: {calc_err}')
                segs = [(products[n]['short'], v, colors.get(n, '#98a2b3'))
                        for n, v in sorted(weights.items(), key=lambda x: (GROUP_ORDER.index(products[x[0]]['group'])
                                                                           if products[x[0]]['group'] in GROUP_ORDER else 9, -x[1]))]
                segs.append(('현금(비워 둔 비중)', 100 - total, '#98a2b3'))
                comp = ''
                for g in GROUP_ORDER + ['유동성']:
                    a, b = g_mine.get(g, 0), g_rec.get(g, 0)
                    if a <= 0.05 and b <= 0.05:
                        continue
                    d = a - b
                    diff = (f'<em class="{"up" if d > 0 else "dn"}">{"+" if d > 0 else "−"}{abs(d):.1f}%p</em>'
                            if abs(d) >= 0.05 else '<em>추천과 같음</em>')
                    comp += (f'<li><span class="sw" style="background:{rc.GROUP_BASE[g]}"></span><span class="nm">{GROUP_TINY[g]}</span>'
                             f'<span class="cb"><i style="width:{min(a, 100):.1f}%;background:{rc.GROUP_BASE[g]}"></i>'
                             f'<u style="left:{min(b, 100):.1f}%" title="추천 {b:.1f}%"></u></span>'
                             f'<b>{a:.1f}%</b><span class="rc">추천 {b:.1f}% {diff}</span></li>')
                html(f"""<div class="bench-viz">{donut_svg(segs, '담은 비중', f'{total:.1f}%', f'선택한 상품 {len(items)}개', size=210, thick=30, label='내 구성 상품별 목표 비율')}
                <div class="cmp"><div class="cmp-h">자산 종류별 목표 비율 <span>막대 = 내 구성 · 세로선 = 추천</span></div><ul>{comp}</ul></div></div>""")
                if mine is not None:
                    rows = mine[mine.target_pct > 0].sort_values('target_pct', ascending=False)
                    top = rows.head(6)
                    body = ''.join(
                        f'<tr><td>{dot(colors.get(r.ticker, "#98a2b3"))}<span class="nm">{esc(r.name)}</span></td>'
                        f'<td>{r.target_pct:.1f}%</td><td>{"<span class=zero>0주</span>" if r.quantity == 0 else f"{r.quantity:,}주"}</td>'
                        f'<td class="amt">{r.purchase_amount:,.0f}원</td></tr>' for r in top.itertuples())
                    more = (f'<tr class="more"><td colspan="4">외 {len(rows) - 6}개 상품 · 아래 ‘전체 표’에서 볼 수 있어요</td></tr>'
                            if len(rows) > 6 else '')
                    body += more + (f'<tr class="cash"><td>{dot("#98a2b3")}<span class="nm">남는 현금</span></td><td>{100 - total:.1f}%</td>'
                                    f'<td></td><td class="amt">{cash:,.0f}원</td></tr>')
                    html(f'<div class="hold-wrap"><table class="holdings compact"><thead><tr><th>상품</th><th>목표 비중</th>'
                         f'<th>수량</th><th>사는 금액</th></tr></thead><tbody>{body}</tbody></table></div>')
                    st.caption(f'{data["as_of"]:%Y.%m.%d} 종가 · 1주 단위 · 원화 · 수수료·세금 제외'
                               + (f' · 미국 상품은 {data["us_as_of"]} 미국 종가 × 환율 {data["fx"]:,.1f}원' if data['fx'] else ''))
                    unbought = rows[rows.quantity == 0]
                    if not unbought.empty:
                        st.warning('정한 금액이 1주 가격보다 작아 사지 못하는 상품이 있어요: ' + ', '.join(unbought.name)
                                   + '. 비중을 늘리거나 예산을 키워 보세요.')
                else:
                    st.info('담은 상품이 없어 전액 현금이에요.')
                big = max(((g, v) for g, v in g_mine.items() if g != '유동성'), key=lambda x: x[1], default=None)
                if big and big[1] > 60:
                    st.info(f'{easy_group(big[0])}에 {big[1]:.1f}%를 담았어요. 한 종류에 많이 몰리면 그 자산이 떨어질 때 '
                            '전체가 함께 크게 흔들릴 수 있어요.')
                st.caption('결과 화면의 ‘여러 자산 묶음’ 몫은 기본 ETF(채권·달러 등)로 담기기 때문에, 여기서는 실제로 담는 상품의 종류에 더해져 있어요.')

    html('<div class="more-h">더 알아보기 <span>필요할 때만 펼쳐 보세요</span></div>')
    with st.expander('전체 상품 표 · CSV 내려받기 · 상품 설명'):
        if mine is not None:
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
            st.caption(f'추천 구성대로 샀을 때 남는 현금: {base_cash:,.0f}원')
            export = mine.copy()
            export['budget_krw'] = budget
            export['remaining_cash_krw'] = cash
            st.download_button('내 구성 CSV로 내려받기', export.to_csv(index=False).encode('utf-8-sig'),
                               'my_portfolio.csv', 'text/csv', key='mock_download')
        else:
            st.info('담은 상품이 없어 전액 현금이에요.')
        if items:
            d1, d2 = st.columns([2, 1], vertical_alignment='bottom')
            pick_d = d1.selectbox('담은 상품 설명 보기', items, format_func=lambda n: products[n]['short'], key='mock_detail_pick')
            d2.button('설명 보기', width='stretch', key='mock_detail_go', on_click=open_detail, args=(pick_d, 'mock'))

    with st.expander('추천 구성과 무엇이 달라졌나요?'):
        fig = go.Figure()
        for g in GROUP_ORDER + ['유동성']:
            fig.add_bar(y=['내 구성', '추천'], x=[g_mine.get(g, 0), g_rec.get(g, 0)], name=easy_group(g),
                        orientation='h', marker_color=rc.GROUP_BASE[g],
                        hovertemplate=f'{easy_group(g)} %{{x:.1f}}%<extra></extra>')
        plot_style(fig, 200, barmode='stack')
        fig.update_layout(legend=dict(orientation='h', y=-0.3))
        fig.update_xaxes(range=[0, 100], ticksuffix='%')
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        changed = [(n, weights.get(n, 0) - m['rec'].get(n, 0)) for n in assets_names]
        changed = [(n, d) for n, d in changed if abs(d) > 1e-9]
        if not changed:
            st.write('지금 구성은 추천과 같아요.')
        else:
            lines = ''.join(f'<li>{dot(colors.get(n, "#98a2b3"))}{esc(products[n]["short"])}: 추천보다 '
                            f'<b>{abs(d):.1f}%p {"늘렸어요" if d > 0 else "줄였어요"}</b></li>' for n, d in changed[:12])
            more = f'<li>외 {len(changed) - 12}개</li>' if len(changed) > 12 else ''
            html(f'<ul class="changes">{lines}{more}</ul>')

    with st.expander('지난 3년에 이렇게 나눴다면? (과거 모의 계산)'):
        try:
            cmp = svc.compare_weights(prices, {n: v * 100 for n, v in res['weights'].items() if n != rc.CASH}, weights)
            html(f'<p class="warnline">{cmp["start"]:%Y.%m.%d} ~ {cmp["end"]:%Y.%m.%d} · 시작값 100 · 지금 비중을 매일 유지했다고 '
                 '보고 거꾸로 계산한 값이에요. 앞으로도 이렇게 된다는 뜻이 아니에요. 현금 수익률 0%, 분배금·수수료·세금 제외.</p>')
            fig2 = go.Figure()
            for label, color, dash in [('추천안', '#98a2b3', 'dot'), ('내 구성', BRAND, None)]:
                fig2.add_scatter(x=cmp['nav'].index, y=cmp['nav'][label], name=label,
                                 line=dict(color=color, width=3 if dash is None else 2, dash=dash))
            plot_style(fig2, 260, hovermode='x unified', top=24)
            st.plotly_chart(fig2, width='stretch', config={'displayModeBar': False})
            st.dataframe(cmp['metrics'].round(1), width='stretch')
        except ValueError as exc:
            st.warning(f'과거 성과를 계산할 수 없어요: {exc}')

    with st.expander('낱말 풀이'):
        for term, desc in TERMS.items():
            st.markdown(f'**{term}**: {desc}')

    return {'weights': weights, 'budget': budget, 'cash': cash}
