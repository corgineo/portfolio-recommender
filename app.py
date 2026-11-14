"""첫 포트폴리오 · 포트폴리오 추천 서비스

실행: streamlit run app.py
화면: 첫 화면(home) → 진단(quiz) → 결과(result) → 모의 포트폴리오(mock) · 투자상품(products) · 종목 분석(detail)
계산은 recommender.py · service.py, 디자인은 assets/style.css 에 있어요.
"""
import importlib
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import recommender as rc
import service as svc
import portfolio_editor as pe
import stock_detail as sd
from ui import html, esc, won, card_title, dot

importlib.reload(rc)   # recommender.py 를 고쳐도 서버를 다시 켜지 않고 바로 반영되게

APP_NAME = '첫 포트폴리오'
CIRCLED = ['①', '②', '③', '④', '⑤']
GROUP_ONE_LINE = {   # 자산군별 초보자용 한 줄 설명
    '채권·예금': '이자를 받는 안전한 쪽이에요. 주식이 떨어질 때 버팀목이 돼요.',
    '주식': '회사의 주인이 되는 몫이에요. 오르내림이 크지만 길게 보면 성장을 기대해요.',
    '대안투자': '금·원유·달러처럼 주식·채권과 다르게 움직여 함께 덜 흔들리게 해 줘요.',
    '자산배분': '주식·채권·대안투자를 미리 골고루 섞어 둔 묶음이에요. 한 번에 분산 효과를 얻어요.',
    '유동성': '급할 때 바로 꺼내 쓸 수 있게 현금(CMA·예금)으로 남겨 둬요.',
}
GROUP_SHORT = rc.GROUP_SHORT

st.set_page_config(page_title=APP_NAME, page_icon='📊', layout='wide', initial_sidebar_state='collapsed')
style_file = Path(__file__).parent / 'assets' / 'style.css'
if style_file.exists():
    st.markdown(f"<style>{style_file.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


# ── 데이터 (한 번 읽으면 재사용) ────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_scope(scope):
    return svc.load_scope(scope)


@st.cache_data(show_spinner='추천 포트폴리오를 계산하고 있어요...')
def get_result(answers, budget, scope):
    return svc.recommend(list(answers), budget, get_scope(scope))


try:
    BASE = get_scope('base')
except FileNotFoundError:
    st.error('data/etf_prices.csv 가 없어요. data 폴더를 그대로 두거나 python update_data.py 로 만들어 주세요.')
    st.stop()
HAS_WIDE = rc.load_universe() is not None

# ── 화면 상태 (페이지를 오가도 유지돼요) ──────────────────────────────────
ss = st.session_state
ss.setdefault('page', 'home')
ss.setdefault('step', 0)                       # 진단: 0 = 투자 조건, 1~7 = 설문 문항
ss.setdefault('ans', [None] * len(rc.QUESTIONS))
ss.setdefault('budget', 10_000_000)
ss.setdefault('scope', 'wide' if HAS_WIDE else 'base')
ss.setdefault('show_all_hold', False)
ss.setdefault('detail', None)
ss.setdefault('detail_from', 'products')
if len(ss.ans) != len(rc.QUESTIONS):          # 예전 5문항 상태가 남아 있으면 새로 시작
    ss.ans = [None] * len(rc.QUESTIONS)
N_STEPS = 1 + len(rc.QUESTIONS)


def go_page(page, step=0):
    ss.page, ss.step = page, step


def restart():
    ss.ans = [None] * len(rc.QUESTIONS)
    go_page('quiz', 0)


def open_detail(name, back):
    ss.detail, ss.detail_from = name, back
    go_page('detail')


def done():
    return None not in ss.ans


def current():
    """지금 조건의 추천 결과와 데이터"""
    data = get_scope(ss.scope)
    return get_result(tuple(ss.ans), int(ss.budget), ss.scope), data


# ── 공통: 상단 바 · 푸터 ───────────────────────────────────────────────
def nav():
    with st.container(key='navbar', horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
        st.button(APP_NAME, key='nav_logo', on_click=go_page, args=('home',))
        with st.container(key='navmenu', horizontal=True, horizontal_alignment='right', width='content', gap='medium'):
            for label, page, enabled in [('서비스 소개', 'home', True), ('투자성향 진단', 'quiz', True),
                                         ('추천 결과', 'result', done()), ('모의 포트폴리오', 'mock', done()),
                                         ('투자상품', 'products', True)]:
                on = ss.page == page or (page == 'products' and ss.page == 'detail')
                st.button(label, key=f'nav_{page}', on_click=go_page, args=(page, 0), disabled=not enabled,
                          type='primary' if on else 'secondary')


def footer():
    u = rc.load_universe()
    extra = ''
    if u is not None:
        m = u['meta']
        extra = (f"<br>거래대금 상위 종목: 국내 {m['kr_last_session']} · 미국 {m['us_last_session']} 장 마감 기준 "
                 '(FinanceDataReader · Nasdaq 공개 스크리너 · 미국 재무 SEC EDGAR)')
    html(f"""<div class="foot"><b>{APP_NAME}</b> · 주식을 처음 하는 분을 위한 자산배분 도우미<br>
    데이터: 국내 상장 ETF 8종 종가 ({BASE['as_of']:%Y.%m.%d}까지) · FinanceDataReader{extra}<br>
    모의 계산이며 투자 권유가 아니에요. 과거 수익률이 미래 수익을 보장하지 않아요.</div>""")


# ── 1. 첫 화면 ───────────────────────────────────────────────────────
def page_home():
    w, d, _ = rc.build_portfolio('성장형', BASE['cov'])
    perf = rc.performance(w, BASE['rets'])
    colors = rc.color_map(list(w.index), svc.group_of(BASE['products']))
    bar = ''.join(f'<i style="width:{v * 100:.1f}%;background:{colors[n]}"></i>' for n, v in w.items())
    legend = ''.join(f'<div>{dot(colors[n])}{rc.BASE_DESC[n]}<b>{v:.0%}</b></div>' for n, v in list(w.items())[:6])

    left, right = st.columns([1.1, 0.9], gap='large')
    with left:
        html("""<div class="hero"><span class="eyebrow">주식 처음 하는 사람을 위한 자산배분</span>
        <h1>처음 하는 투자,<br><em>무엇을 얼마나</em> 살지<br>3분이면 알려드려요</h1>
        <p class="sub">질문 7개에 답하면 투자 성향을 진단하고, 채권·주식·대안투자를
        어떻게 나눠 담을지 금액과 수량까지 계산해 드려요.</p></div>""")
        c1, _ = st.columns([1, 1])
        c1.button('투자성향 진단 시작하기', type='primary', width='stretch', on_click=restart)
    with right:
        html(f"""<div class="hero-card">
        <div class="tags"><span>#균형성장</span><span>#글로벌분산</span><span>#위험균형</span></div>
        <div class="t">예시 · 성장형 배분 · 국내 ETF 8종</div>
        <div class="v">과거 연환산 {perf['return']:.1%}</div>
        <div class="g">변동성 {perf['vol']:.1%} · 최대 낙폭 {perf['mdd']:.1%}</div>
        <div class="bar">{bar}</div><div class="legend">{legend}</div></div>""")

    wide_txt = ('국내 ETF 8종에 국내·미국 거래대금 상위 종목, 채권 ETF, 국내 채권·금·혼합 ETF까지 넓혀 고를 수 있어요.'
                if HAS_WIDE else '한국·미국·일본·중국·유럽 주식과 채권, 달러, 원유를 1주 단위로 살 수 있게 알려드려요.')
    html(f"""<div class="section-title"><div class="k">특징</div><h2>초보자도 이해할 수 있는 추천</h2></div>
    <div class="features">
      <div class="feature"><div class="ic">📝</div><h3>질문 7개로 성향 진단</h3>
        <p>나이, 투자 기간, 기대 수익, 손실을 견디는 정도를 물어 안정 추구형부터 공격 추구형까지 나눠요.</p></div>
      <div class="feature"><div class="ic">📐</div><h3>위험을 고르게 나눠요</h3>
        <p>상품마다 얼마나 흔들렸는지, 서로 같이 움직였는지를 보고 한쪽에 위험이 몰리지 않게 비중을 정해요.</p></div>
      <div class="feature"><div class="ic">🌏</div><h3>살 수 있는 상품으로</h3>
        <p>{wide_txt}</p></div>
    </div>
    <div class="section-title"><div class="k">추천 과정</div><h2>이렇게 추천해요</h2></div>
    <div class="steps">
      <div class="step"><div class="n">STEP 1</div><h4>조건 입력</h4><p>예산과 고를 상품 범위를 정해요.</p></div>
      <div class="step"><div class="n">STEP 2</div><h4>성향 진단</h4><p>7문항 점수(0~28점)로 투자성향을 정해요.</p></div>
      <div class="step"><div class="n">STEP 3</div><h4>자산 나누기</h4><p>성향별로 채권·주식·대안투자·현금 비율을 정해요.</p></div>
      <div class="step"><div class="n">STEP 4</div><h4>상품 비중 계산</h4><p>자산군 안에서 위험이 고르게 나뉘도록 상품 비중을 계산해요.</p></div>
    </div>
    <div class="cta-band"><h3>내 성향에 맞는 포트폴리오를 확인해 보세요</h3><p>예산을 정하고 7문항에 답하면 돼요.</p></div>""")
    _, mid, _ = st.columns([1, 0.6, 1])
    mid.button('진단 시작하기', type='primary', width='stretch', on_click=restart, key='cta2')


# ── 2. 진단 화면 ─────────────────────────────────────────────────────
def save_answer(i):
    choice = ss.get(f'q{i}_w')
    if choice is not None:
        ss.ans[i] = int(choice)
        ss.step += 1                            # 고르면 바로 다음 문항으로
        if ss.step == N_STEPS:
            ss.page = 'result'


def set_budget():
    if ss.get('budget_w') is not None:
        ss.budget = int(ss.budget_w)


def pick_budget():
    preset = {'100만원': 1_000_000, '500만원': 5_000_000, '1,000만원': 10_000_000, '3,000만원': 30_000_000}
    if ss.get('budget_pill'):
        ss.budget = preset[ss.budget_pill]
        ss.budget_w = ss.budget


def set_scope():
    ss.scope = ss.scope_w


def page_quiz():
    s = ss.step
    pct = (s + 1) / N_STEPS * 100
    if s == 0:
        title, sub, label = '투자 조건을 알려주세요', '예산이 바뀌면 금액과 수량이 달라져요.', '투자 조건'
    else:
        title, sub, label = rc.QUESTIONS[s - 1][0], '가장 가까운 답을 하나 골라 주세요.', f'질문 {s} / {len(rc.QUESTIONS)}'

    _, body, _ = st.columns([1, 2.2, 1])
    with body:
        html(f"""<div class="quiz-head"><div class="meta"><span>{label}</span><span>{s + 1} / {N_STEPS}</span></div>
        <div class="track"><i style="width:{pct:.0f}%"></i></div>
        <div class="qn">{'STEP 1 · 투자 조건' if s == 0 else 'STEP 2 · 투자성향 진단'}</div><h2>{title}</h2><p>{sub}</p></div>""")
        if s == 0:
            if 'budget_w' not in ss:
                ss.budget_w = ss.budget
            st.number_input('투자 예산 (원)', min_value=100_000, max_value=1_000_000_000, step=1_000_000,
                            key='budget_w', on_change=set_budget, format='%d')
            html(f'<div class="won">= {won(ss.budget)}</div>')
            st.pills('빠른 선택', ['100만원', '500만원', '1,000만원', '3,000만원'], key='budget_pill',
                     on_change=pick_budget, label_visibility='collapsed')
            html('<div class="lbl">추천에 쓸 상품</div>')
            options = list(svc.SCOPES) if HAS_WIDE else ['base']
            with st.container(key='scope'):
                st.radio('추천에 쓸 상품', options, index=options.index(ss.scope) if ss.scope in options else 0,
                         key='scope_w', on_change=set_scope, label_visibility='collapsed',
                         format_func=lambda k: {'wide': '국내 ETF + 거래대금 상위 종목 + 국내 채권·금·혼합 ETF',
                                                'base': '국내 ETF 8종만 (원화로 거래, 단순하게)'}[k])
            if HAS_WIDE:
                html('<p class="cd">거래대금 상위 종목은 미국 상품이 많아 환율에 따라 원화 금액이 달라질 수 있어요. '
                     '예산이 작으면 1주도 살 수 없는 상품은 빼고 다시 계산해요.</p>')
        else:
            i = s - 1
            q, options = rc.QUESTIONS[i]
            st.radio(q, list(range(len(options))), index=ss.ans[i], key=f'q{i}_w', on_change=save_answer, args=(i,),
                     label_visibility='collapsed', format_func=lambda k, o=options: f'{CIRCLED[k]}  {o[k]}')

        st.write('')
        b1, b2 = st.columns(2)
        b1.button('이전', width='stretch', key='quiz_prev',
                  on_click=(lambda: go_page('home')) if s == 0 else (lambda: go_page('quiz', s - 1)))
        if s == 0:
            b2.button('다음', type='primary', width='stretch', key='quiz_next', on_click=lambda: go_page('quiz', 1))
        else:
            answered = ss.ans[s - 1] is not None
            last = s == N_STEPS - 1
            b2.button('결과 보기' if last else '다음', type='primary', width='stretch', disabled=not answered,
                      key='quiz_next', on_click=(lambda: go_page('result')) if last else (lambda: go_page('quiz', s + 1)))


# ── 3. 결과 화면 ─────────────────────────────────────────────────────
def donut(weights, colors, products, budget):
    names = list(weights.index)
    vals = (weights * 100).round(1)
    text = [f'{v:.0f}%' if v >= 3 else '' for v in vals]
    fig = go.Figure(go.Pie(labels=[products[n]['short'] for n in names], values=vals, hole=0.62, sort=False,
                           marker=dict(colors=[colors[n] for n in names], line=dict(color='#fff', width=2)),
                           text=text, textinfo='text', textfont=dict(size=12),
                           hovertemplate='%{label}<br>%{value:.1f}%<extra></extra>'))
    many = len(names) > 9
    fig.update_layout(height=360 if many else 400, margin=dict(t=10, b=10, l=10, r=10), showlegend=not many,
                      legend=dict(font=dict(size=12), orientation='h', x=0.5, xanchor='center', y=-0.05),
                      paper_bgcolor='rgba(0,0,0,0)', font=dict(family='Pretendard'),
                      annotations=[dict(text=f'<b>{won(budget)}</b>', showarrow=False, font=dict(size=17, color='#101828'))])
    return fig


def group_key_html():
    return '<div class="gkey">' + ''.join(
        f'<span>{dot(rc.GROUP_BASE[g])}{GROUP_SHORT[g]}</span>' for g in ['채권·예금', '주식', '대안투자', '유동성']) + '</div>'


def holdings_table(res, data, show_all):
    alloc, colors, products = res['alloc'], res['colors'], data['products']
    rows = alloc[alloc['name'] != rc.CASH]
    rows = rows.sort_values('비중(%)', ascending=False)
    cash = alloc[alloc['name'] == rc.CASH].iloc[0]
    limit = 6
    shown = rows if show_all else rows.head(limit)
    body = ''
    for _, r in shown.iterrows():
        p = products[r['name']]
        code = f' · {esc(p["code"])}' if p.get('code') else ''
        usd = ''
        if p.get('currency') == 'USD' and data['universe'] is not None:
            loc = data['universe']['local'][r['name']].dropna()
            usd = f'<div class="fx">${loc.iloc[-1]:,.2f}</div>' if len(loc) else ''
        qty = f'{r["수량(주)"]:,.0f}주' if r['수량(주)'] > 0 else '<span class="zero">0주</span>'
        body += (f'<tr><td>{dot(colors[r["name"]])}<span class="nm">{esc(p["short"])}</span>'
                 f'<span class="sub1">{esc(p["desc"]) if p["desc"] != p["short"] else ""}{code}</span></td>'
                 f'<td>{r["비중(%)"]:.1f}%</td><td class="amt">{r["금액(원)"]:,.0f}원</td>'
                 f'<td>{r["현재가(원)"]:,.0f}원{usd}</td><td>{qty}</td></tr>')
    body += (f'<tr class="cash"><td>{dot(colors.get(rc.CASH, "#98a2b3"))}<span class="nm">현금 (CMA·예금)</span>'
             f'<span class="sub1">목표 현금 + 1주 미만이라 못 산 돈</span></td>'
             f'<td>{cash["비중(%)"]:.1f}%</td><td class="amt">{cash["금액(원)"]:,.0f}원</td><td></td><td></td></tr>')
    return body, len(rows), limit


def page_result():
    if not done():
        go_page('quiz', ss.ans.index(None) + 1)
        st.rerun()
    res, data = current()
    judge, profile, perf, weights = res['judge'], res['profile'], res['perf'], res['weights']
    products, colors, budget = data['products'], res['colors'], ss.budget

    note = ''
    if judge['short_term']:
        note = ('<div class="note">투자 기간이 1년 이내라면 주식 비중이 큰 상품은 손실을 회복할 시간이 부족할 수 있어요. '
                '모의 포트폴리오에서 채권·현금 비중을 늘려 비교해 보세요.</div>')
    lo, hi = judge['type_range']
    html(f"""<div class="res-hero">
      <div class="tags">{''.join(f'<span>{t}</span>' for t in res['tags'])}</div>
      <div class="who">설문 점수 <b>{judge['score']}점</b> / {rc.MAX_SCORE}점 · 투자 기간 {judge['period']}</div>
      <h2>당신은 {judge['type']} 투자자예요</h2>
      <div class="desc">{judge['type_desc']} ({lo}~{hi}점) · <b>{profile}</b> 자산배분을 추천해요</div>{note}
      <div class="kpis">
        <div class="kpi"><div class="l">총 투자금</div><div class="v">{won(budget)}</div></div>
        <div class="kpi"><div class="l">과거 연환산 수익률</div><div class="v up">{perf['return']:+.1%}</div></div>
        <div class="kpi"><div class="l">변동성 (위험)</div><div class="v">{perf['vol']:.1%}</div></div>
        <div class="kpi"><div class="l">최대 낙폭 (MDD)</div><div class="v down">{perf['mdd']:.1%}</div></div>
      </div></div>""")

    with st.container(key='res_actions', horizontal=True, gap='small'):
        st.button('모의 포트폴리오 만들기', type='primary', key='to_mock_top', on_click=go_page, args=('mock',))
        st.button('투자상품 살펴보기', key='to_products_top', on_click=go_page, args=('products',))
        st.button('조건·상품 범위 바꾸기', key='to_cond_top', on_click=go_page, args=('quiz', 0))
    scope_txt = ('국내 ETF 8종 + 거래대금 상위 종목 + 국내 추가 ETF' if data['scope'] == 'wide' else '국내 ETF 8종')
    st.caption(f'추천에 쓴 상품 범위: {scope_txt} · 가격 기준일 {data["as_of"]:%Y.%m.%d}'
               + (f' (미국 상품은 {data["us_as_of"]} 미국 종가 × 환율 {data["fx"]:,.1f}원)' if data['fx'] else ''))

    c1, c2 = st.columns([1, 1], gap='medium')
    with c1:
        with st.container(border=True):
            card_title('상품별 비중', '색으로 자산군을 구분해요')
            html(group_key_html())
            st.plotly_chart(donut(weights, colors, products, budget), width='stretch', config={'displayModeBar': False})
    with c2:
        with st.container(border=True):
            card_title('자산군별 비중', '자산배분이란? 성격이 다른 자산에 돈을 나눠 담아 한쪽이 떨어져도 덜 흔들리게 하는 방법이에요.')
            table = rc.PROFILE_TABLE[profile]
            rows = ''
            for g in rc.GROUPS:
                if g == '유동성':
                    names = '현금'
                else:
                    held = [n for n, v in res['sleeves'][g].items() if v > 0.01]
                    names = ', '.join(products[n]['short'] for n in held[:5]) + (f' 외 {len(held) - 5}개' if len(held) > 5 else '')
                color = rc.GROUP_BASE[g]
                fill = ('linear-gradient(90deg,#2563eb 0 34%,#ef4444 34% 67%,#16a34a 67%)' if g == '자산배분' else color)
                rows += (f'<div class="grow"><div class="top"><span class="gname">{dot(color) if g != "자산배분" else ""}{g}</span>'
                         f'<span>{table[g]}%</span></div>'
                         f'<div class="track"><i style="width:{table[g]}%;background:{fill}"></i></div>'
                         f'<div class="one">{GROUP_ONE_LINE[g]}</div><div class="sub">{esc(names)}</div></div>')
            html(f'<div class="groups">{rows}</div>')

    # 보유 목록
    body, n_rows, limit = holdings_table(res, data, ss.show_all_hold)
    with st.container(border=True):
        card_title('이렇게 사면 돼요', f'{data["as_of"]:%Y.%m.%d} 종가 기준 · 1주 단위로 사고 남은 돈은 현금으로 둬요')
        html(f"""<div class="hold-wrap"><table class="holdings compact"><thead><tr><th>상품</th><th>목표 비중</th><th>금액</th>
        <th>현재가</th><th>수량</th></tr></thead><tbody>{body}</tbody></table></div>""")
        if n_rows > limit:
            st.button(f'접기' if ss.show_all_hold else f'더보기 (전체 {n_rows}개 상품)', key='more_hold',
                      on_click=lambda: ss.update(show_all_hold=not ss.show_all_hold))
        if res['dropped']:
            st.caption(f'예산 {won(budget)}으로는 1주도 살 수 없는 상품 {len(res["dropped"])}개를 빼고 다시 계산했어요. '
                       '예산을 늘리면 더 많은 상품에 나눠 담을 수 있어요.')
        held = [n for n in weights.index if n != rc.CASH]
        d1, d2 = st.columns([2, 1], vertical_alignment='bottom')
        pick = d1.selectbox('종목 자세히 보기', held, format_func=lambda n: f'{products[n]["short"]} · {products[n]["desc"]}',
                            key='res_detail_pick')
        d2.button('분석 보기', key='res_detail_go', width='stretch', on_click=open_detail, args=(pick, 'result'))

    st.caption('아래 과거 성과는 지금 정한 비중을 같은 과거 기간에 적용한 모의 계산이에요. 실제 그때의 추천 성과가 아니며, '
               '매일 비중 유지·현금 수익률 0%·거래비용 제외 가정이에요.')

    # 과거 성과 비교
    safe = rc.safe_index(data['rets'])
    start = perf['index'].index[0]
    end_pf, end_safe = budget * perf['index'].iloc[-1] / 100, budget * safe.iloc[-1] / 100
    with st.container(border=True):
        card_title(f'{rc.LOOKBACK_YEARS}년 전에 이 비중으로 시작했다면?',
                   f'{start:%Y.%m}부터 지금까지 · 단기채권 ETF에만 넣었을 때와 비교 · 원금보장 상품이 아님')
        yf = ',.1f' if budget < 2_000_000 else ',.0f'      # 예산이 작으면 눈금이 같은 숫자로 겹치지 않게 소수 한 자리
        fig3 = go.Figure()
        fig3.add_scatter(x=safe.index, y=budget * safe / 100 / 1e4, name='단기채권 ETF만',
                         line=dict(color='#98a2b3', width=2, dash='dot'),
                         hovertemplate='%{y:' + yf + '}만원<extra>단기채권만</extra>')
        fig3.add_scatter(x=perf['index'].index, y=budget * perf['index'] / 100 / 1e4, name='추천 포트폴리오',
                         line=dict(color='#2563eb', width=3), fill='tonexty', fillcolor='rgba(37,99,235,.08)',
                         hovertemplate='%{y:' + yf + '}만원<extra>추천 포트폴리오</extra>')
        fig3.update_layout(height=300, margin=dict(t=10, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)',
                           plot_bgcolor='rgba(0,0,0,0)', font=dict(family='Pretendard', color='#475467'),
                           legend=dict(orientation='h', y=1.12, x=0), hovermode='x unified',
                           yaxis=dict(gridcolor='#f2f4f7', tickformat=yf, ticksuffix='만원'),
                           xaxis=dict(showgrid=False))
        st.plotly_chart(fig3, width='stretch', config={'displayModeBar': False})
        html(f"""<div class="compare">
          <div><span>추천 포트폴리오</span><b>{won(budget)} → {won(end_pf)}</b><em class="up">{end_pf / budget - 1:+.1%}</em></div>
          <div><span>단기채권 ETF만</span><b>{won(budget)} → {won(end_safe)}</b><em>{end_safe / budget - 1:+.1%}</em></div>
          <div><span>가장 크게 떨어졌을 때</span><b>약 {won(abs(perf['mdd']) * budget)} 손실</b><em class="down">{perf['mdd']:.1%}</em></div>
        </div>""")

    # 추천 근거
    t = rc.PROFILE_TABLE[profile]
    picked = ''.join(f'<li><span>{rc.TOPICS[i]}</span>{CIRCLED[a]} {esc(rc.QUESTIONS[i][1][a])} <em>{rc.POINTS[a]}점</em></li>'
                     for i, a in enumerate(ss.ans))
    bands = ' · '.join(f'{lo}~{hi}점 {name}' for lo, hi, name, _ in rc.TYPES)
    blo, bhi = judge['band_range']
    split_note = (f' 위험 중립형은 범위가 넓어 11~17점은 안정성장형, 18~24점은 성장형 배분을 써요.'
                  if judge['type'] == '위험 중립형' else '')
    why_split = {
        '안정형': '원금을 지키는 게 가장 중요한 성향이라 대부분을 채권·예금에 두고, 주식은 5%만 담아요.',
        '안정성장형': '안정이 먼저지만 예금보다는 조금 더 벌 수 있게, 채권을 줄이고 대안투자와 자산배분 상품을 섞어요.',
        '성장형': '수익과 안정의 균형을 맞추려고 채권·주식·대안투자를 비슷한 크기로 나눠요.',
        '공격형': '높은 수익을 위해 주식을 가장 많이 담고, 채권은 10%로 줄여요.',
    }[profile]
    vol = pd.Series(np.sqrt(np.diag(data['cov'])), index=data['cov'].index)
    alt = res['sleeves']['대안투자']
    if res['model'] == 'MVP':
        why_weight = ('전체 가격이 가장 덜 흔들리는 조합을 찾았어요. 덜 흔들리는 상품을 많이 담고, '
                      '서로 반대로 움직이는 상품을 섞어 흔들림을 줄여요.')
    else:
        why_weight = ('모든 상품이 전체 위험을 똑같이 나눠 지도록 했어요. 많이 흔들리는 상품은 적게, '
                      '덜 흔들리는 상품은 많이 담아요.')
    if 'OIL' in alt and 'USD' in alt:
        why_weight += (f' 예를 들어 대안투자에서 원유(1년 변동성 {vol["OIL"]:.0%})는 {alt["OIL"]:.0%}, '
                       f'달러(변동성 {vol["USD"]:.0%})는 {alt["USD"]:.0%}를 담았어요.')

    html(f"""<div class="section-title left"><div class="k">추천 근거</div><h2>왜 이렇게 추천했나요?</h2></div>
    <div class="how">
      <div><b>왜 {judge['type']}인가요?</b>
        <ul class="picked">{picked}</ul>
        <p>공격적인 답일수록 높은 점수(①4점 ~ ⑤0점)를 매겨 더하면 <strong>{judge['score']}점</strong>이에요.
        판정 기준은 {bands}이에요.{split_note}</p></div>
      <div><b>왜 이렇게 나눴나요?</b>
        <p>{why_split}</p>
        <p>채권·예금 {t['채권·예금']}% · 주식 {t['주식']}% · 대안투자 {t['대안투자']}% · 자산배분 {t['자산배분']}% · 현금 {t['유동성']}%.
        투자성향별 추천 자산배분표(법률신문, 신한 PB 기고)의 {profile}({blo}~{bhi}점) 비율이에요.</p></div>
      <div><b>왜 이 상품을 이만큼 담나요?</b>
        <p>{why_weight}</p></div>
      <div><b>숫자는 어떻게 읽나요?</b>
        <p><strong>과거 연환산 수익률 {perf['return']:.1%}</strong>: 최근 {rc.LOOKBACK_YEARS}년 동안 이 비중이었다면 1년에 평균 이만큼 늘었어요.</p>
        <p><strong>변동성 {perf['vol']:.1%}</strong>: 1년 수익률이 평균에서 보통 이 정도 오르내려요. 클수록 위험해요.</p>
        <p><strong>최대 낙폭 {perf['mdd']:.1%}</strong>: 가장 나빴던 때 고점에서 이만큼 떨어졌어요.</p></div>
    </div>""")
    with st.expander('계산 방법 자세히 보기'):
        st.markdown(f"""
- **기대수익률·공분산**: 최근 {rc.LOOKBACK_YEARS}년 일간수익률의 평균 × 240, 공분산 행렬 × 240 (1년 기준으로 환산)
- **포트폴리오 변동성**: √(wᵀΣw)
- **{rc.MODEL_NAME[res['model']]}**: 비중 합 = 1, 0 ≤ 비중 ≤ 1 (빌려서 팔기 없음)
  {'· 목표: 변동성 √(wᵀΣw) 최소화' if res['model'] == 'MVP' else '· 목표: 위험기여도 RCᵢ = wᵢ × (Σw)ᵢ / σₚ 를 모든 상품에서 σₚ / n 으로 같게'}
- **자산배분 몫**: 국내 ETF 8종 전체를 위험균형으로 섞은 묶음
- **미국 상품**: 미국 종가 × 같은 날 원/달러 환율로 원화 환산, 한국 장 마감 시점에 이미 알려진 전날 미국 종가만 사용
- **지표**: 연수익률 = 일간 평균 × 240, 변동성 = 일간 표준편차 × √240, MDD = 누적성과 ÷ 그때까지 최고점 − 1 의 최솟값
""")
        rows = [{'자산군': g, '상품': products[n]['short'], '자산군 안 비중': f'{w:.1%}'}
                for g, s in res['sleeves'].items() for n, w in s.items() if w > 0.0005]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')

    st.write('')
    with st.container(key='mock_cta'):
        html('<div class="cta-band"><h3>비중을 직접 바꿔 보고 싶나요?</h3>'
             '<p>모의 포트폴리오에서 상품을 더하거나 빼고, 추천안과 성과를 비교할 수 있어요.</p></div>')
        _, mid, _ = st.columns([1, 0.7, 1])
        mid.button('모의 포트폴리오 만들기', type='primary', width='stretch', key='to_mock_bottom',
                   on_click=go_page, args=('mock',))
    st.write('')
    _, b1, b2, b3, _ = st.columns([0.5, 0.7, 0.7, 0.7, 0.5])
    b1.button('처음 화면으로', width='stretch', on_click=go_page, args=('home',), key='res_home')
    b2.button('조건 바꾸기', width='stretch', on_click=go_page, args=('quiz', 0), key='res_cond')
    b3.button('처음부터 다시 진단', type='primary', width='stretch', on_click=restart, key='res_restart')


# ── 4. 모의 포트폴리오 · 투자상품 · 종목 분석 ─────────────────────────────
def page_mock():
    if not done():
        go_page('quiz', ss.ans.index(None) + 1)
        st.rerun()
    res, data = current()
    pe.render(res, data, ss, go_page, open_detail)


def page_products():
    sd.render_products(get_scope('wide') if HAS_WIDE else BASE, ss, go_page, open_detail, has_wide=HAS_WIDE)


def page_detail():
    data = get_scope('wide') if HAS_WIDE else BASE
    sd.render_detail(ss.detail, data, ss, go_page)


def scroll_top():
    """화면(페이지·문항)이 바뀌면 맨 위로 올려요"""
    where = f'{ss.page}-{ss.step}-{ss.detail}'
    if ss.get('_where') != where:
        ss._where = where
        components.html(f"""<script>/*{where}*/
        const d = window.parent.document;
        for (const sel of ['[data-testid=stMain]', '[data-testid=stAppViewContainer]', 'section.main']) {{
          const el = d.querySelector(sel); if (el) el.scrollTo(0, 0);
        }}
        window.parent.scrollTo(0, 0);</script>""", height=0)


# ── 실행 ─────────────────────────────────────────────────────────────
scroll_top()
nav()
{'home': page_home, 'quiz': page_quiz, 'result': page_result, 'mock': page_mock,
 'products': page_products, 'detail': page_detail}.get(ss.page, page_home)()
footer()
