"""나만의 포트폴리오 제작하기 화면. 앱에서 render_portfolio_editor(assets, recommended_weights)로 불러요.

계산 규칙(팀 구현 유지): 비중 단위 0~100(%), 0.01% 정밀도. 합계가 100%를 넘으면 방금 바꾼 상품만 '100 − 다른 상품 합계'로
잘라요(cap_value). 다른 상품은 절대 자동으로 바꾸지 않아요. 남은 비중은 현금, 1주 단위 매수(portfolio_core.allocate),
과거 성과 비교는 analysis_fn 콜백.

화면 구조
- 맨 위: 예산 · 담은 비중 · 실제로 사는 돈 · 남는 현금 요약
- 왼쪽: 자산 종류 필터(전체/채권/주식/다른 자산/자산배분) + 상품 목록(한 번에 5개, 더 보기). 행마다 짧은 슬라이더 + 정확한 % 입력.
- 오른쪽(스크롤해도 따라오는 비교 패널): 구성 차이 · 과거 성과 · 구성 도넛 탭
- 아래 펼침: 실제 매수표 · CSV, 낱말 풀이
모든 비중은 위젯 key 가 아니라 session_state[f'{key}_model']['w'] 에, 제작 예산은 ['budget'] 에 보관해요. Streamlit 은 화면에 그리지 않은
위젯의 key 를 지우기 때문에, 필터·더 보기·페이지 왕복 뒤에도 값이 남도록 위젯 값은 매번 model 에서 채워요.
"""
import plotly.graph_objects as go
import streamlit as st

import recommender as rc
from portfolio_core import allocate, validate_assets, validate_weights
from ui import html, esc, won, won_exact, dot, donut_svg, plot_style, GROUP_TINY, BRAND, TERMS as UI_TERMS

GROUP_ORDER = ['채권·예금', '주식', '대안투자', '자산배분']
FILTERS = ['전체'] + GROUP_ORDER
PAGE = 5                         # 목록 한 번에 보여 줄 행 수
TERMS = {
    'ETF': UI_TERMS['ETF'],
    '목표 비중과 실제 비중': '목표 비중은 정하신 비율, 실제 비중은 1주 단위로 산 금액의 비율이에요.',
    '남는 현금': '비워 둔 비중과 1주 가격보다 작아 사지 못한 금액을 합한 돈이에요.',
    '최대 낙폭': UI_TERMS['최대 낙폭'],
    '변동성': UI_TERMS['변동성'],
}


def cap_value(ticker, values):
    """values(코드 → %)에서 ticker 의 값을 '100 − 다른 상품 합계' 이하로 잘라 돌려줘요 (팀 cap_weight 와 같은 규칙)"""
    other_total = sum(v for t, v in values.items() if t != ticker)
    return min(values[ticker], max(0.0, 100.0 - other_total))


def _order(assets, recommended):
    gi = {g: i for i, g in enumerate(GROUP_ORDER)}
    cls = assets.set_index('ticker')['asset_class']
    return sorted(assets.ticker, key=lambda t: (gi.get(cls[t], 9), -recommended[t]))


def render_portfolio_editor(assets, recommended_weights, *, default_budget=1_000_000,
                            key='portfolio_c', analysis_fn=None, demo=False, colors=None):
    """비중 단위는 0~100(%). 가격·예산은 원화."""
    if demo:
        st.warning('연습용 가상 상품·가격이에요. 실제 ETF나 추천 자료가 아니에요.')
    try:
        assets = validate_assets(assets)
        codes = assets.ticker.tolist()
        recommended = validate_weights(recommended_weights, codes)
        if default_budget <= 0:
            raise ValueError('기본 예산은 0보다 커야 해요.')
    except (ValueError, TypeError) as exc:
        st.error(str(exc))
        return None
    info = assets.set_index('ticker')
    order = _order(assets, recommended)
    colors = dict(colors or {})
    auto = rc.color_map(order, lambda t: info.at[t, 'asset_class'])
    for t in codes:
        colors.setdefault(t, auto[t])
    signature = (tuple(codes), tuple(recommended.items()))
    ss = st.session_state
    mkey, fkey, xkey, msgkey = f'{key}_model', f'{key}_filter', f'{key}_extra', f'{key}_msg'
    bkey = f'{key}_budget'                               # 예산 위젯 key (값의 원본은 model['budget'])

    def sk(t):
        return f'{key}_s_{t}'

    def nk(t):
        return f'{key}_n_{t}'

    def model():
        return ss[mkey]

    def reset():
        """추천 비중으로 되돌리기 (필터·제작 예산은 그대로 두고, 더한 ETF 와 바꾼 비중을 모두 되돌려요)"""
        old = ss.get(mkey, {})
        ss[mkey] = {'w': dict(recommended), 'extra': [], 'filter': old.get('filter', '전체'), 'shown': {},
                    'budget': int(old.get('budget') or default_budget)}
        for k in [k for k in ss.keys() if str(k).startswith((f'{key}_s_', f'{key}_n_'))] + [xkey]:
            ss.pop(k, None)
        ss[msgkey] = ''

    def apply(t, value):
        """한 상품 비중 바꾸기: 팀 규칙대로 그 상품만 남은 한도까지로 잘라요"""
        values = dict(model()['w'])
        values[t] = max(0.0, float(value))
        capped = cap_value(t, values)
        if values[t] > capped + 1e-12:
            ss[msgkey] = (f'{info.at[t, "name"]}: 합계가 100%를 넘지 않도록 {capped:.2f}%로 맞췄어요. '
                          '더 담으시려면 다른 상품 비중을 먼저 줄여 주세요.')
        else:
            ss[msgkey] = ''
        model()['w'][t] = capped
        ss[sk(t)] = capped
        ss[nk(t)] = capped

    def on_slider(t):
        apply(t, ss[sk(t)])

    def on_number(t):
        apply(t, ss[nk(t)] if ss.get(nk(t)) is not None else 0.0)

    def on_budget():
        v = ss.get(bkey)
        if v is not None and int(v) >= 1:
            model()['budget'] = int(v)

    def on_filter():
        model()['filter'] = ss.get(fkey) or '전체'

    def on_extra():
        m_ = model()
        chosen = list(ss.get(xkey) or [])
        for t in m_['extra']:
            if t not in chosen:                         # 목록에서 뺀 ETF 는 0%로
                m_['w'][t] = 0.0
        m_['extra'] = chosen
        ss[msgkey] = ''

    def more(f, n):
        model()['shown'][f] = n

    if ss.get(f'{key}_signature') != signature or mkey not in ss:
        reset()
        ss[f'{key}_signature'] = signature
    m = model()
    if ss.get(f'{key}_default_budget') != int(default_budget):   # 설문 예산(기본 예산)이 바뀌면 새 기본 예산으로
        m['budget'] = int(default_budget)
        ss[f'{key}_default_budget'] = int(default_budget)
    budget = int(m.get('budget') or default_budget)
    m['budget'] = budget
    ss[bkey] = budget                                    # 위젯 값은 model 에서 채워요 (페이지 왕복 뒤에도 유지)

    # ── 계산 (모든 값은 model 에서) ──
    weights = {t: float(m['w'][t]) for t in codes}
    total = sum(weights.values())
    remain = max(0.0, 100 - total)
    base, base_cash = allocate(assets, recommended, budget)
    edited, cash = allocate(assets, weights, budget)
    g_rec = base.groupby('asset_class').target_pct.sum()
    g_mine = edited.groupby('asset_class').target_pct.sum()
    g_rec['유동성'] = max(0.0, 100 - sum(recommended.values()))
    g_mine['유동성'] = remain
    spent = budget - cash
    changed = sorted(((t, weights[t] - recommended[t]) for t in codes if abs(weights[t] - recommended[t]) > 1e-8),
                     key=lambda x: -abs(x[1]))

    # ── 맨 위: 예산 · 요약 ──
    with st.container(key='bench_top'):
        c0, c1, c2, c3 = st.columns([1.2, 1, 1, 1], vertical_alignment='bottom')
        with c0:
            st.number_input('제작 예산 (원)', min_value=1, step=10000, key=bkey, format='%d', on_change=on_budget)
        bar = ''.join(f'<i style="width:{weights[t]:.2f}%;background:{colors[t]}"></i>' for t in order if weights[t] > 0)
        with c1:
            html(f"""<div class="sum1"><span>담은 비중</span><b>{total:.1f}%</b>
            <div class="sumbar"><div class="bar">{bar}<i style="width:{remain:.2f}%;background:#E4DED3"></i></div></div></div>""")
        with c2:
            html(f'<div class="sum1"><span>실제로 사는 돈</span><b>{won_exact(spent)}</b><em>예산의 {spent / budget:.1%}</em></div>')
        with c3:
            # mob-sum: 폭 640px 이하에서만 화면 아래에 고정되는 짧은 요약 (데스크톱에서는 숨김)
            html(f'<div class="sum1"><span>남는 현금</span><b>{won_exact(cash)}</b><em>남은 비중 {remain:.1f}% + 잔돈</em></div>'
                 f'<div class="mob-sum" role="status"><span>담은 <b>{total:.1f}%</b></span>'
                 f'<span>현금 <b>{won(cash)}</b></span><span>변경 <b>{len(changed)}개</b></span>'
                 f'<a href="#cmp-view">비교 보기</a></div>')

    left, right = st.container(key='bench').columns([1.15, 1], gap='large')

    # ── 왼쪽: 자산 종류 필터 + 상품 목록 ──
    with left:
        with st.container(border=True, key='mock_edit'):
            listed = [t for t in order if recommended[t] > 0 or t in m['extra'] or weights[t] > 0]
            counts = {f: sum(1 for t in listed if f == '전체' or info.at[t, 'asset_class'] == f) for f in FILTERS}
            if ss.get(fkey) not in FILTERS:             # 다른 페이지에 다녀오면 위젯 값이 지워져서 model 에서 되살려요
                ss[fkey] = m['filter']
            st.segmented_control('자산 종류', FILTERS, key=fkey, on_change=on_filter, label_visibility='collapsed',
                                 format_func=lambda f: f'{"전체" if f == "전체" else GROUP_TINY[f]} {counts[f]}')
            flt = ss.get(fkey) or '전체'
            m['filter'] = flt
            rows = [t for t in listed if flt == '전체' or info.at[t, 'asset_class'] == flt]
            n_show = min(len(rows), m['shown'].get(flt, PAGE))
            html('<p class="hint">슬라이더로 대략, 오른쪽 칸에 숫자로 정확히 정해요(0.01% 단위). 합계는 100%를 넘을 수 없고 '
                 '다른 상품은 자동으로 바뀌지 않아요. 더 담으려면 다른 상품 비중을 먼저 줄여 주세요.</p>')
            if ss.get(msgkey):
                st.info(ss[msgkey])
            if not rows:
                st.caption('이 종류에는 담은 상품이 없어요. 아래 ‘추천에 없던 ETF 더하기’에서 고를 수 있어요.')
            for t in rows[:n_show]:
                ss[sk(t)] = weights[t]                  # 위젯 값은 항상 model 에서 채워요
                ss[nk(t)] = weights[t]
                rec, cur = recommended[t], weights[t]
                d = cur - rec
                diff = ('추천과 같음' if abs(d) < 0.005 else
                        f'<em class="{"up" if d > 0 else "dn"}">{"+" if d > 0 else "−"}{abs(d):.2f}%p</em>')
                with st.container(key=f'{key}_row_{t}'):
                    html(f'<div class="erow">{dot(colors[t])}<b>{esc(info.at[t, "name"])}</b>'
                         f'<span class="cd">{esc(t)} · {esc(GROUP_TINY.get(info.at[t, "asset_class"], ""))}</span>'
                         f'<span class="rd">추천 {rec:.2f}% → 내 {cur:.2f}% · {diff}</span></div>')
                    a, b = st.columns([2.3, 1], vertical_alignment='center')
                    a.slider(f'{info.at[t, "name"]} 비중', 0.0, 100.0, step=0.5, key=sk(t), on_change=on_slider,
                             args=(t,), format='%.1f%%', label_visibility='collapsed')
                    b.number_input(f'{info.at[t, "name"]} 비중 (%)', min_value=0.0, max_value=100.0, step=1.0,
                                   key=nk(t), on_change=on_number, args=(t,), format='%.2f',
                                   label_visibility='collapsed')
            if len(rows) > PAGE:
                with st.container(key=f'{key}_pager', horizontal=True, gap='small'):
                    if n_show < len(rows):
                        st.button(f'더 보기 ({len(rows) - n_show}개 남음)', key=f'{key}_more',
                                  on_click=more, args=(flt, n_show + PAGE))
                    if n_show > PAGE:
                        st.button('접기', key=f'{key}_less', on_click=more, args=(flt, PAGE))
            st.button('추천 비중으로 되돌리기', on_click=reset, key=f'{key}_reset', width='stretch')
            extras = [t for t in order if recommended[t] <= 0]
            with st.expander(f'추천에 없던 ETF 더하기 ({len(extras)}개 중 선택)'):
                ss[xkey] = [t for t in m['extra'] if t in extras]
                st.multiselect('더할 ETF', extras, key=xkey, on_change=on_extra, placeholder='ETF를 골라 주세요',
                               format_func=lambda t: f'{info.at[t, "name"]} · {GROUP_TINY.get(info.at[t, "asset_class"], "")}')
                st.caption('더한 ETF는 0%로 목록에 들어가요. 목록에서 비중을 정해 주세요. 여기서 빼면 0%로 돌아가요.')

    # ── 오른쪽: 비교 패널 (스크롤해도 따라와요) ──
    with right:
        with st.container(border=True, key='cmp_panel'):
            html('<div id="cmp-view" class="panel-h"><b>추천안과 비교</b><span>바꾸면 바로 다시 계산돼요</span></div>')
            t1, t2, t3 = st.tabs(['구성 차이', '과거 성과', '구성 도넛'])
            with t1:
                fig = go.Figure()
                for g in GROUP_ORDER + ['유동성']:
                    fig.add_bar(y=['내 구성', '추천안'], x=[float(g_mine.get(g, 0)), float(g_rec.get(g, 0))],
                                name=GROUP_TINY[g], orientation='h', marker_color=rc.GROUP_BASE[g],
                                hovertemplate=f'{GROUP_TINY[g]} %{{x:.1f}}%<extra></extra>')
                plot_style(fig, 170, barmode='stack')
                fig.update_layout(legend=dict(orientation='h', y=-0.35, font=dict(size=12)))
                fig.update_xaxes(range=[0, 100], ticksuffix='%')
                st.plotly_chart(fig, width='stretch', config={'displayModeBar': False}, key=f'{key}_groupbar')
                gl = ''
                for g in GROUP_ORDER + ['유동성']:
                    a_, b_ = float(g_mine.get(g, 0)), float(g_rec.get(g, 0))
                    if a_ <= 0.005 and b_ <= 0.005:
                        continue
                    dd = a_ - b_
                    dtxt = '추천과 같음' if abs(dd) < 0.05 else ('+' if dd > 0 else '−') + f'{abs(dd):.1f}%p'
                    gl += f'<li>{dot(rc.GROUP_BASE[g])}{GROUP_TINY[g]} <b>{a_:.1f}%</b><span>{dtxt}</span></li>'
                html(f'<ul class="gdiff">{gl}</ul>')
                if changed:
                    lines = ''.join(f'<li>{dot(colors[t])}{esc(info.at[t, "name"])} <b>{"+" if d > 0 else "−"}{abs(d):.2f}%p</b></li>'
                                    for t, d in changed[:5])
                    more_txt = f'<li class="m">외 {len(changed) - 5}개</li>' if len(changed) > 5 else ''
                    html(f'<ul class="changes one">{lines}{more_txt}</ul>')
                else:
                    html('<p class="cap">지금 구성은 추천안과 같아요.</p>')
            with t2:
                if analysis_fn is None:
                    st.caption('과거 성과 비교 기능이 연결되지 않았어요.')
                else:
                    try:
                        result = analysis_fn(base.copy(), edited.copy(), base_cash, cash, budget)
                        fig2 = go.Figure()
                        for lab, color, dash in [('추천안', '#98a2b3', 'dot'), ('내 구성', BRAND, None)]:
                            fig2.add_scatter(x=result['nav'].index, y=result['nav'][lab], name=lab,
                                             line=dict(color=color, width=3 if dash is None else 2, dash=dash),
                                             hovertemplate='%{y:.1f}<extra>' + lab + '</extra>')
                        plot_style(fig2, 210, hovermode='x unified', top=24)
                        st.plotly_chart(fig2, width='stretch', config={'displayModeBar': False}, key=f'{key}_nav')
                        mt = result['metrics']
                        trs = ''.join(
                            f'<tr><td>{c.split(" (")[0]}</td><td>{mt.at["추천안", c]:.1f}%</td><td><b>{mt.at["내 구성", c]:.1f}%</b></td>'
                            f'<td>{mt.at["내 구성", c] - mt.at["추천안", c]:+.1f}%p</td></tr>' for c in mt.columns)
                        html(f'<table class="mtab"><thead><tr><th></th><th>추천안</th><th>내 구성</th><th>차이</th></tr></thead>'
                             f'<tbody>{trs}</tbody></table>')
                        html(f'<p class="warnline">{esc(result["methodology"])}</p>')
                    except Exception as exc:            # noqa: BLE001 — 화면은 계속 쓸 수 있게
                        st.warning(f'과거 성과를 계산하지 못했어요. {exc}')
            with t3:
                segs = [(info.at[t, 'name'], weights[t], colors[t]) for t in order if weights[t] > 0]
                segs.append(('현금', remain, rc.GROUP_BASE['유동성']))
                n_items = int((edited.target_pct > 0).sum())
                html(f'<div class="dn-wrap">{donut_svg(segs, "담은 비중", f"{total:.1f}%", f"상품 {n_items}개", size=190, thick=28, label="내 구성 상품별 목표 비율")}</div>')
                html('<p class="cap">색은 자산 종류예요: 주식 빨강·주황 · 채권 파랑 · 다른 자산 초록 · 자산배분 보라 · 현금 회색</p>')

    rows_df = edited[edited.target_pct > 0].sort_values('target_pct', ascending=False)
    unbought = rows_df[rows_df.quantity == 0]
    if not unbought.empty:
        st.warning('배정 금액이 1주 가격보다 작아 사지 못하는 상품이 있어요: ' + ', '.join(unbought.name)
                   + '. 비중을 늘리거나 예산을 키워 보세요.')
    big = g_mine.drop('유동성')
    if not big.empty and big.max() > 60:
        st.info(f'{GROUP_TINY.get(big.idxmax(), big.idxmax())}에 {big.max():.1f}%를 담으셨어요. '
                '한 종류에 많이 몰리면 그 자산이 떨어질 때 전체가 크게 흔들릴 수 있어요.')

    # ── 아래 펼침: 실제 매수표 · CSV · 낱말 풀이 ──
    with st.expander(f'실제 매수표 · CSV 내려받기 (상품 {len(rows_df)}개)'):
        body = ''.join(
            f'<tr><td>{dot(colors[r.ticker])}<span class="nm">{esc(r.name)}</span>'
            f'<span class="sub1">{esc(GROUP_TINY.get(r.asset_class, r.asset_class))} · {esc(r.ticker)} · 1주 {r.price:,.0f}원</span></td>'
            f'<td>{r.target_pct:.2f}%</td><td>{"<span class=zero>0주</span>" if r.quantity == 0 else f"{r.quantity:,}주"}</td>'
            f'<td class="amt">{r.purchase_amount:,.0f}원</td></tr>' for r in rows_df.itertuples())
        body += (f'<tr class="cash"><td>{dot(rc.GROUP_BASE["유동성"])}<span class="nm">남는 현금</span>'
                 f'<span class="sub1">남은 비중 + 1주가 안 돼 남은 돈</span></td><td>{remain:.2f}%</td><td></td>'
                 f'<td class="amt">{cash:,.0f}원</td></tr>')
        html(f'<div class="hold-wrap"><table class="holdings compact"><thead><tr><th>상품</th><th>목표 비중</th>'
             f'<th>수량</th><th>사는 금액</th></tr></thead><tbody>{body}</tbody></table></div>')
        dates = sorted(set(rows_df['as_of']))
        st.caption(f'가격 기준일 {", ".join(d.replace("-", ".") for d in dates) or "-"} 종가 · 원화 1주 가격 · 수수료·세금 제외'
                   + (' · 미국 종목은 원/달러 환율로 환산' if rows_df['source'].str.contains('미국').any() else '')
                   + f' · 추천안대로 사면 남는 현금 {base_cash:,.0f}원')
        export = edited.copy()
        export['budget_krw'] = budget
        export['remaining_cash_krw'] = cash
        st.download_button('내 구성 CSV 내려받기', export.to_csv(index=False).encode('utf-8-sig'),
                           'my_portfolio.csv', 'text/csv', key=f'{key}_download')
    with st.expander('낱말 풀이'):
        for term, description in TERMS.items():
            st.markdown(f'**{term}**: {description}')
    return {'allocation': edited, 'cash': cash, 'weights': weights, 'budget': budget}
