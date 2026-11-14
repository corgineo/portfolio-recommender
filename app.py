"""첫 포트폴리오 · 포트폴리오 추천 서비스

실행: streamlit run app.py
화면: 첫 화면(home) → 진단(quiz) → 결과(result) → 나만의 포트폴리오(mock) · 상품 둘러보기(products) · 상품 설명(detail)
계산은 recommender.py · service.py, 디자인은 assets/style.css 에 있어요.
화면 원칙: 데스크톱은 주 영역 : 보조 영역 = 8 : 5, 좁은 화면은 한 열. 한 화면에 주요 행동 하나, 나머지는 '펼쳐 보기'.
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
from ui import (html, esc, won, won_exact, dot, section, donut_svg, plot_style, GROUP_EASY, GROUP_ONE, GROUP_ORDER, TERMS,
                easy_group, BRAND)

importlib.reload(rc)   # recommender.py 를 고쳐도 서버를 다시 켜지 않고 바로 반영되게

APP_NAME = '첫 포트폴리오'
BUILD = '나만의 포트폴리오'
CIRCLED = ['①', '②', '③', '④', '⑤']
GROUP_SHORT = rc.GROUP_SHORT

# 설문 원문(rc.QUESTIONS)은 그대로 두고, 문항마다 쉬운 한 줄 풀이와 낱말 풀이만 따로 붙여요.
Q_EASY = [
    '지금 나이에 해당하는 칸을 골라 주세요.',
    '이 돈을 꺼내 쓰지 않고 넣어 둘 수 있는 기간이에요.',
    '돈을 불리는 것(수익률)과 넣은 돈을 지키는 것(원금보전) 중 무엇을 더 중요하게 보나요?',
    '주식시장이 평소처럼 움직일 때, 이 투자로 얼마나 벌기를 바라나요?',
    '앞으로 10년 동안 주식시장이 계속 좋지 않다면, 내 투자 결과는 어때야 한다고 생각하나요?',
    '3년 동안 투자한다면, 손실을 어디까지 받아들일 수 있나요?',
    '3개월처럼 짧은 기간에 손실이 나면 어떤 마음이 들 것 같나요?',
]
Q_TERMS = [
    {},
    {},
    {'수익률': '넣은 돈에 비해 늘어난(또는 줄어든) 비율이에요.',
     '원금보전': '처음 넣은 돈(원금)이 줄어들지 않게 지키는 것이에요.'},
    {'시장 수익률': '주식시장 전체(예: 코스피 지수)가 오르내린 만큼의 수익이에요.',
     '상회 · 하회': '상회는 그보다 높다, 하회는 그보다 낮다는 뜻이에요.'},
    {'침체': '주가가 오랫동안 떨어지거나 오르지 못하는 시기예요.',
     '원금 수준 유지': '처음 넣은 돈만큼은 남아 있어야 한다는 뜻이에요.'},
    {'원금 손실': '넣은 돈보다 줄어드는 것이에요.', '감내': '참고 견딘다는 뜻이에요.'},
    {'20% 손실': '100만원이 80만원이 되는 정도예요.', '감내': '참고 견딘다는 뜻이에요.'},
]
TYPE_TINY = {'안정 추구형': '안정', '위험 중립형': '중립', '공격 추구형': '공격'}   # 점수 막대용 짧은 이름
TYPE_EASY = {   # 투자성향 → 초보자용 한 줄
    '안정 추구형': '손실을 피하는 게 가장 중요해요. 크게 벌기보다 물가보다 조금 나은 수익을 바라는 편이에요.',
    '위험 중립형': '어느 정도 오르내림은 견딜 수 있어요. 오래 두고 천천히 늘리기를 바라는 편이에요.',
    '공격 추구형': '큰 오르내림을 견디더라도 높은 수익을 바라는 편이에요. 그만큼 크게 잃을 수도 있어요.',
}

st.set_page_config(page_title=APP_NAME, page_icon='📊', layout='wide', initial_sidebar_state='collapsed')
style_file = Path(__file__).parent / 'assets' / 'style.css'
if style_file.exists():
    st.markdown(f"<style>{style_file.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


# ── 데이터 (한 번 읽으면 재사용) ────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_scope(scope):
    return svc.load_scope(scope)


@st.cache_data(show_spinner='과거 성과를 계산하고 있어요...')
def get_backtest(profile, use_factor):
    return svc.backtest_summary(profile, use_factor)


@st.cache_data(show_spinner='추천을 계산하고 있어요...')
def get_result(answers, budget, scope):
    return svc.recommend(list(answers), budget, get_scope(scope))


try:
    BASE = get_scope('base')
except FileNotFoundError:
    st.error('가격 자료를 불러오지 못했어요. 잠시 뒤 새로고침해 보고, 계속 안 되면 서비스 운영자에게 알려 주세요.')
    st.stop()
HAS_WIDE = rc.load_universe() is not None

# ── 화면 상태 (페이지를 오가도 유지돼요) ──────────────────────────────────
ss = st.session_state
ss.setdefault('page', 'home')
ss.setdefault('step', 0)                       # 진단: 0 = 예산, 1~7 = 설문 문항
ss.setdefault('ans', [None] * len(rc.QUESTIONS))
ss.setdefault('budget', 10_000_000)
ss.setdefault('scope', 'wide' if HAS_WIDE else 'base')
ss.setdefault('show_all_hold', False)
ss.setdefault('detail', None)
ss.setdefault('detail_from', 'products')
ss.setdefault('after_quiz', None)              # 'mock' 이면 진단을 마친 뒤 나만의 포트폴리오로 바로 가요
if len(ss.ans) != len(rc.QUESTIONS):          # 예전 5문항 상태가 남아 있으면 새로 시작
    ss.ans = [None] * len(rc.QUESTIONS)
N_STEPS = 1 + len(rc.QUESTIONS)


def go_page(page, step=None):
    ss.page = page
    if step is not None:
        ss.step = step


def restart():
    """처음부터 진단 (끝나면 추천 결과로)"""
    ss.ans = [None] * len(rc.QUESTIONS)
    ss.after_quiz = None
    go_page('quiz', 0)


def resume_quiz():
    """진단을 하다 다른 화면에 다녀오면, 답하지 않은 첫 문항부터 이어서 해요"""
    if all(a is None for a in ss.ans):
        go_page('quiz', 0)
    elif None in ss.ans:
        go_page('quiz', ss.ans.index(None) + 1)
    else:
        go_page('quiz', 0)


def start_for_build():
    """나만의 포트폴리오 소개 화면에서 시작: 진단을 마치면 제작 공간으로 돌아와요"""
    ss.after_quiz = 'mock'
    resume_quiz()


def finish_quiz():
    ss.page = ss.after_quiz or 'result'
    ss.after_quiz = None


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
    """메뉴 3개. '나만의 포트폴리오'는 진단 전후 모두 늘 보이고 강조돼요"""
    first = ('내 추천', 'result', go_page, ('result',)) if done() else ('성향 진단', 'quiz', resume_quiz, ())
    items = [first, (BUILD, 'mock', go_page, ('mock',)), ('상품 둘러보기', 'products', go_page, ('products',))]
    with st.container(key='navbar', horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
        st.button(APP_NAME, key='nav_logo', on_click=go_page, args=('home',))
        with st.container(key='navmenu', horizontal=True, horizontal_alignment='right', width='content', gap='small'):
            for label, page, fn, args in items:
                on = ss.page == page or (page == 'products' and ss.page == 'detail')
                st.button(label, key=f'nav_{page}', on_click=fn, args=args, type='primary' if on else 'secondary')


def footer():
    u = rc.load_universe()
    extra = ''
    if u is not None:
        m = u['meta']
        extra = (f" · 거래대금 순위 국내 {m['kr_last_session']} · 미국 {m['us_last_session']} 장 마감 기준"
                 ' (FinanceDataReader · Nasdaq 공개 스크리너 · 미국 재무 SEC EDGAR)')
    html(f"""<div class="foot"><div class="brand"><i></i><b>{APP_NAME}</b></div>
    <p>투자가 처음인 분을 위한 포트폴리오 제작 도구예요. 화면의 구성은 모두 모의 구성이며 실제 주문·결제·계좌 연결은 되지 않아요.
    투자 권유가 아니고, 과거 결과가 앞으로의 수익을 보장하지 않아요.</p>
    <p class="src">자료: 국내 상장 ETF 8종 종가 ({BASE['as_of']:%Y.%m.%d}까지) · FinanceDataReader{extra}</p></div>""")


def group_legend(group_w, budget, show_desc=True):
    """자산 종류 범례: 색 + 이름 + % + 금액 (색만으로 구분하지 않아요)"""
    rows = ''
    for g in GROUP_ORDER:
        w = float(group_w.get(g, 0))
        if w <= 0:
            continue
        desc = f'<em>{GROUP_ONE[g]}</em>' if show_desc else ''
        rows += (f'<li><span class="sw" style="background:{rc.GROUP_BASE[g]}"></span>'
                 f'<span class="nm"><b>{easy_group(g)}</b>{desc}</span>'
                 f'<span class="pc">{w:.0%}</span><span class="am">{won(budget * w)}</span></li>')
    return f'<ul class="legend">{rows}</ul>'


# ── 1. 첫 화면 ───────────────────────────────────────────────────────
def page_home():
    example = rc.PROFILE_TABLE['성장형']
    ex_budget = 10_000_000
    segs = [(easy_group(g), example[g], rc.GROUP_BASE[g]) for g in GROUP_ORDER]

    with st.container(key='home_hero'):
        left, right = st.columns([8, 5], gap='large', vertical_alignment='center')
        with left:
            html(f"""<div class="hero"><span class="eyebrow">투자가 처음인 분을 위한 포트폴리오 제작 도구</span>
            <h1>추천을 받고 끝내지 말고,<br><em>내 포트폴리오</em>를<br>직접 완성해 보세요</h1>
            <p class="sub">질문 7개로 내 투자 성향에 맞는 출발점을 받고, 상품 하나씩 비중을 바꾸며
            <b>내 돈이 어디에 얼마씩</b> 들어가는지 바로 확인해요.</p></div>""")
            with st.container(key='home_ctas', horizontal=True, gap='small'):
                st.button(f'{BUILD} 제작하기', type='primary', key='home_build', on_click=go_page, args=('mock',))
                if done():
                    st.button('내 추천 다시 보기', key='home_result', on_click=go_page, args=('result',))
                elif any(a is not None for a in ss.ans):
                    n = ss.ans.index(None) + 1
                    st.button(f'이어서 진단하기 (질문 {n} / {len(rc.QUESTIONS)})', key='home_resume', on_click=resume_quiz)
                else:
                    st.button('투자 성향부터 알아보기', key='home_start', on_click=restart)
            if done() or any(a is not None for a in ss.ans):
                st.button('처음부터 다시 진단하기', key='home_start', on_click=restart, type='tertiary')
            html('<p class="hint">약 3분 · 회원가입 없음 · 실제 주문은 되지 않는 모의 구성이에요</p>')
        with right:
            html(f"""<figure class="hero-fig"><figcaption><span class="tag">예시</span>1,000만원을 이렇게 나눌 수 있어요</figcaption>
            {donut_svg(segs, '예시 예산', won(ex_budget), '5가지로 나눔', size=220, thick=30, label='예시 배분')}
            {group_legend(pd.Series({g: example[g] / 100 for g in GROUP_ORDER}), ex_budget, show_desc=False)}
            <p class="fig-note">‘위험 중립형’ 중 한 예시예요. 내 맞춤 추천은 진단 후에 보여 드려요.</p></figure>""")

    html(f"""<ol class="journey">
      <li><span>1</span><div><b>성향 진단</b><p>질문 7개로 손실을 견디는 정도를 알아봐요.</p></div></li>
      <li><span>2</span><div><b>추천 구성 확인</b><p>내 예산을 5가지 자산에 얼마씩 둘지 봐요.</p></div></li>
      <li class="key"><span>3</span><div><b>{BUILD} 제작</b><p>상품 하나씩 비중을 바꾸면 금액·수량이 바로 다시 계산돼요.</p></div></li>
    </ol>""")


# ── 2. 진단 화면 ─────────────────────────────────────────────────────
def save_answer(i):
    choice = ss.get(f'q{i}_w')
    if choice is not None:
        ss.ans[i] = int(choice)
        ss.step += 1                            # 고르면 바로 다음 문항으로
        if ss.step == N_STEPS:
            finish_quiz()


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


def steps_bar(s):
    """진행 표시: 예산 + 질문 7개 = 8칸"""
    cells = ''.join(f'<i class="{"on" if k < s else ("now" if k == s else "")}"></i>' for k in range(N_STEPS))
    return f'<div class="steps" aria-hidden="true">{cells}</div>'


def page_quiz():
    s = ss.step
    _, body, _ = st.columns([1, 2.6, 1])
    with body:
        back_note = (f'<div class="flow-note">진단을 마치면 <b>{BUILD}</b> 제작 화면으로 바로 이어져요.</div>'
                     if ss.get('after_quiz') == 'mock' else '')
        if s == 0:
            html(f"""<div class="quiz-head">{back_note}<div class="meta"><span>시작 전 · 예산 정하기</span><span>질문 7개 남음</span></div>
            {steps_bar(s)}
            <h2>얼마로 시작해 볼까요?</h2>
            <p>실제 돈이 빠져나가지 않아요. 이 금액으로 상품을 몇 주씩 살 수 있는지 계산해 드려요.</p></div>""")
            if 'budget_w' not in ss:
                ss.budget_w = ss.budget
            st.number_input('투자해 볼 금액 (원)', min_value=100_000, max_value=1_000_000_000, step=1_000_000,
                            key='budget_w', on_change=set_budget, format='%d')
            html(f'<div class="won">= {won(ss.budget)}</div>')
            st.pills('자주 쓰는 금액', ['100만원', '500만원', '1,000만원', '3,000만원'], key='budget_pill',
                     on_change=pick_budget, label_visibility='collapsed')
            with st.expander('추천에 쓸 상품 범위 바꾸기 (선택 · 안 바꿔도 돼요)'):
                options = list(svc.SCOPES) if HAS_WIDE else ['base']
                st.radio('추천에 쓸 상품', options, index=options.index(ss.scope) if ss.scope in options else 0,
                         key='scope_w', on_change=set_scope, label_visibility='collapsed',
                         format_func=lambda k: {'wide': '넓게 (기본) · 국내 ETF + 많이 거래되는 국내·미국 종목 + 국내 채권·금 ETF',
                                                'base': '단순하게 · 국내 ETF 8종만 (모두 원화로 거래)'}[k])
                if HAS_WIDE:
                    html('<p class="cd">‘넓게’는 미국 상품이 섞여 환율에 따라 원화 금액이 달라질 수 있어요. '
                         '예산이 작아 1주도 살 수 없는 상품은 빼고 다시 계산해요.</p>')
        else:
            i = s - 1
            q, options = rc.QUESTIONS[i]
            terms = ''.join(f'<li><b>{esc(t)}</b> {esc(d)}</li>' for t, d in Q_TERMS[i].items())
            html(f"""<div class="quiz-head">{back_note}<div class="meta"><span>질문 {s} / {len(rc.QUESTIONS)} · {rc.TOPICS[i]}</span>
            <span>고르면 다음 질문으로 넘어가요</span></div>
            {steps_bar(s)}
            <h2>{esc(q)}</h2><p class="easy">{esc(Q_EASY[i])}</p>
            {f'<ul class="terms"><li class="h">낱말 풀이</li>{terms}</ul>' if terms else ''}</div>""")
            st.radio(q, list(range(len(options))), index=ss.ans[i], key=f'q{i}_w', on_change=save_answer, args=(i,),
                     label_visibility='collapsed', format_func=lambda k, o=options: f'{CIRCLED[k]}  {o[k]}')

        st.write('')
        b1, b2 = st.columns(2)
        b1.button('이전', width='stretch', key='quiz_prev',
                  on_click=(lambda: go_page('home')) if s == 0 else (lambda: go_page('quiz', s - 1)))
        if s == 0:
            b2.button('다음: 질문 시작', type='primary', width='stretch', key='quiz_next', on_click=lambda: go_page('quiz', 1))
        else:
            answered = ss.ans[s - 1] is not None
            last = s == N_STEPS - 1
            last_label = f'{BUILD}로' if ss.get('after_quiz') == 'mock' else '결과 보기'
            b2.button(last_label if last else '다음', type='primary', width='stretch', disabled=not answered,
                      key='quiz_next', on_click=finish_quiz if last else (lambda: go_page('quiz', s + 1)))
        if s > 0:
            html('<p class="hint center">‘이전’을 누르면 앞 질문의 답을 바꿀 수 있어요. 고른 답은 그대로 남아 있어요.</p>')


# ── 3. 결과 화면 ─────────────────────────────────────────────────────
def product_donut(weights, colors, products, budget):
    """상품별 비중 (펼쳐 보기 안)"""
    names = list(weights.index)
    vals = (weights * 100).round(1)
    text = [f'{v:.0f}%' if v >= 3 else '' for v in vals]
    fig = go.Figure(go.Pie(labels=[products[n]['short'] for n in names], values=vals, hole=0.62, sort=False,
                           marker=dict(colors=[colors[n] for n in names], line=dict(color='#fff', width=2)),
                           text=text, textinfo='text', textfont=dict(size=12),
                           hovertemplate='%{label}<br>%{value:.1f}%<extra></extra>'))
    many = len(names) > 9
    plot_style(fig, 340 if many else 380, legend=not many,
               annotations=[dict(text=f'<b>{won(budget)}</b>', showarrow=False, font=dict(size=17, color='#16213B'))])
    fig.update_layout(legend=dict(orientation='h', x=0.5, xanchor='center', y=-0.05))
    return fig


def holdings_rows(res, data, show_all, limit=5):
    """보유 목록 HTML 행. 기본은 금액이 큰 상위 limit개만, 펼치면 전체와 현재가·비중까지.
    금액 칸에는 예산 대비 작은 막대를 함께 그려요."""
    alloc, colors, products = res['alloc'], res['colors'], data['products']
    budget = float(alloc['금액(원)'].sum()) or 1.0
    rows = alloc[alloc['name'] != rc.CASH].sort_values('금액(원)', ascending=False)
    cash = alloc[alloc['name'] == rc.CASH].iloc[0]
    shown = rows if show_all else rows.head(limit)
    body = ''
    for _, r in shown.iterrows():
        p = products[r['name']]
        c = colors[r['name']]
        usd = ''
        if show_all and p.get('currency') == 'USD' and data['universe'] is not None:
            loc = data['universe']['local'][r['name']].dropna()
            usd = f'<div class="fx">${loc.iloc[-1]:,.2f}</div>' if len(loc) else ''
        qty = f'{r["수량(주)"]:,.0f}주' if r['수량(주)'] > 0 else '<span class="zero">0주</span>'
        extra = (f'<td>{r["비중(%)"]:.1f}%</td><td>{r["현재가(원)"]:,.0f}원{usd}</td>' if show_all else '')
        share = r['금액(원)'] / budget * 100
        body += (f'<tr><td>{dot(c)}<span class="nm">{esc(p["short"])}</span>'
                 f'<span class="sub1">{esc(easy_group(p["group"]))}{" · " + esc(p["desc"]) if show_all and p["desc"] != p["short"] else ""}</span></td>'
                 f'{extra}<td class="amt">{r["금액(원)"]:,.0f}원<span class="mbar"><i style="width:{share:.1f}%;background:{c}"></i></span></td>'
                 f'<td>{qty}</td></tr>')
    cash_extra = f'<td>{cash["비중(%)"]:.1f}%</td><td></td>' if show_all else ''
    cshare = cash['금액(원)'] / budget * 100
    body += (f'<tr class="cash"><td>{dot(colors.get(rc.CASH, "#98a2b3"))}<span class="nm">남겨 둘 돈 (현금)</span>'
             f'<span class="sub1">정한 현금 + 1주가 안 돼 못 산 잔돈</span></td>'
             f'{cash_extra}<td class="amt">{cash["금액(원)"]:,.0f}원<span class="mbar"><i style="width:{cshare:.1f}%;background:#98a2b3"></i></span></td><td></td></tr>')
    head = ('<th>상품</th><th>비중</th><th>현재가</th><th>금액</th><th>수량</th>' if show_all
            else '<th>상품</th><th>사는 금액</th><th>수량</th>')
    return head, body, len(rows)


def score_bar(score):
    """0~28점 위에 3개 성향 구간과 내 점수를 표시"""
    total = rc.MAX_SCORE + 1
    zones = ''.join(f'<div style="flex:{hi - lo + 1}" class="z{k}"><span>{TYPE_TINY.get(name, name)}</span><em>{lo}~{hi}점</em></div>'
                    for k, (lo, hi, name, _) in enumerate(rc.TYPES))   # 막대 위는 짧게(안정·중립·공격), 전체 이름은 아래 설명에
    pos = (score + 0.5) / total * 100
    return (f'<div class="score"><div class="lab">내 답의 점수 <b>{score}점</b> / {rc.MAX_SCORE}점</div>'
            f'<div class="zones">{zones}<i class="mk" style="left:{pos:.1f}%"></i></div></div>')


def page_result():
    if not done():
        go_page('quiz', ss.ans.index(None) + 1)
        st.rerun()
    res, data = current()
    judge, profile, perf, weights = res['judge'], res['profile'], res['perf'], res['weights']
    products, colors, budget = data['products'], res['colors'], ss.budget
    group_w = res['group_w']
    alloc = res['alloc']
    cash_amt = float(alloc.loc[alloc['name'] == rc.CASH, '금액(원)'].iloc[0])
    spent = budget - cash_amt

    # ① 맨 위: 내 성향 · 예산 · 제작 CTA | 점수 막대
    note = ''
    if judge['short_term']:
        note = ('<div class="note">투자 기간 1년 이내라고 답했어요. 주식이 많은 구성은 떨어졌을 때 손실을 회복할 시간이 부족할 수 있어요. '
                f'{BUILD}에서 채권·현금 몫을 늘려 비교해 보세요.</div>')
    scope_txt = '넓게 (국내·미국 상품)' if data['scope'] == 'wide' else '국내 ETF 8종'
    with st.container(key='res_top'):
        left, right = st.columns([8, 5], gap='large', vertical_alignment='center')
        with left:
            html(f"""<div class="res-hero"><div class="who">진단 결과</div>
              <h2>당신은 {judge['type']} 투자자예요</h2>
              <p class="desc">{TYPE_EASY[judge['type']]}</p>
              <div class="chips"><span>예산 <b>{won(budget)}</b></span><span>투자 기간 <b>{judge['period']}</b></span>
              <span>상품 범위 <b>{scope_txt}</b></span></div>{note}</div>""")
            with st.container(key='res_actions', horizontal=True, gap='small'):
                st.button(f'{BUILD} 제작하기', type='primary', key='to_mock_top', on_click=go_page, args=('mock',))
                st.button('예산·상품 범위 바꾸기', key='to_cond_top', on_click=go_page, args=('quiz', 0))
        with right:
            html(f'<div class="side-card">{score_bar(judge["score"])}'
                 f'<p class="cd">공격적인 답일수록 점수가 높아요. 구간: '
                 + ' · '.join(f'{name} {lo_}~{hi_}점' for lo_, hi_, name, _ in rc.TYPES) + '</p></div>')

    # ② 돈을 이렇게 나눠요: 큰 도넛 + 금액 범례 (목표 비율)
    segs = [(easy_group(g), float(group_w.get(g, 0)) * 100, rc.GROUP_BASE[g]) for g in GROUP_ORDER]
    with st.container(key='card_split'):
        section('1', '돈을 이렇게 나눠요', f'{won(budget)}을 성격이 다른 상품에 나눠 담아, 위험이 한곳에 몰리지 않게 해요.')
        c1, c2 = st.columns([5, 8], gap='large', vertical_alignment='center')
        with c1:
            html(donut_svg(segs, '내 예산', won(budget), '목표 비율', size=250, thick=34, label='자산 종류별 목표 비율'))
        with c2:
            html(group_legend(group_w, budget) + '<p class="cap">금액은 목표 비율로 나눈 값이에요. 1주 단위로 사면 아래처럼 조금 달라져요.</p>')

    # ③ 이렇게 사면 돼요: 실제 사는 돈 · 남는 돈 + 짧은 표
    head, body, n_rows = holdings_rows(res, data, ss.show_all_hold)
    with st.container(key='card_buy'):
        section('2', '이렇게 사면 돼요 (예시)', '1주 단위로 사면 실제로 쓰는 돈과 남는 돈이에요. 실제 주문은 되지 않아요.')
        n_buy = int(((alloc['name'] != rc.CASH) & (alloc['수량(주)'] > 0)).sum())
        html(f"""<div class="kpis"><div><span>실제로 사는 돈</span><b>{won_exact(spent)}</b><em>{spent:,.0f}원 · 예산의 {spent / budget:.1%}</em></div>
        <div><span>남는 현금</span><b>{won_exact(cash_amt)}</b><em>{cash_amt:,.0f}원 · 정한 현금 + 1주가 안 돼 남은 돈</em></div>
        <div><span>추천 상품</span><b>{n_rows}개</b><em>그중 1주 이상 사는 상품 {n_buy}개</em></div></div>""")
        html(f'<div class="hold-wrap"><table class="holdings compact"><thead><tr>{head}</tr></thead>'
             f'<tbody>{body}</tbody></table></div>')
        if n_rows > 5:
            st.button('접기' if ss.show_all_hold else f'전체 {n_rows}개 상품 보기 (비중·현재가 포함)', key='more_hold',
                      on_click=lambda: ss.update(show_all_hold=not ss.show_all_hold))
        st.caption(f'{data["as_of"]:%Y.%m.%d} 종가 기준 · 원화 · 수수료·세금 제외'
                   + (f' · 미국 상품은 {data["us_as_of"]} 미국 종가 × 환율 {data["fx"]:,.1f}원' if data['fx'] else ''))
        if res['dropped']:
            st.caption(f'예산 {won(budget)}으로는 1주도 살 수 없는 상품 {len(res["dropped"])}개를 빼고 다시 계산했어요. '
                       '예산을 늘리면 더 많은 상품에 나눠 담을 수 있어요.')

    with st.container(key='cta_band', horizontal=True, vertical_alignment='center', horizontal_alignment='distribute'):
        html(f"""<div class="cta-band"><b>이 추천은 출발점이에요</b>
        <p>{BUILD}에서 상품을 빼고 더하거나 비중을 바꾸면, 금액과 수량이 바로 다시 계산돼요.</p></div>""")
        st.button(f'{BUILD} 제작하기 →', key='to_mock_bottom', on_click=go_page, args=('mock',))

    # ── 여기부터는 필요할 때만 펼쳐 보기 ──
    html('<div class="more-h">더 알아보기 <span>필요할 때만 펼쳐 보세요</span></div>')
    held = [n for n in weights.index if n != rc.CASH]
    with st.expander('상품 하나씩 자세히 보기 (자산 종류 설명 포함)'):
        html('<ul class="terms plain">' + ''.join(f'<li>{dot(rc.GROUP_BASE[g])}<b>{GROUP_EASY[g][0]}</b> {GROUP_EASY[g][1]}</li>'
                                                   for g in GROUP_ORDER) + '</ul>')
        d1, d2 = st.columns([2, 1], vertical_alignment='bottom')
        pick = d1.selectbox('어떤 상품인지 볼 상품', held,
                            format_func=lambda n: f'{products[n]["short"]} · {products[n]["desc"]}', key='res_detail_pick')
        d2.button('설명 보기', key='res_detail_go', width='stretch', on_click=open_detail, args=(pick, 'result'))
        html('<p class="cd">상품별 비중 · 색은 자산 종류예요 (채권 파랑 · 주식 빨강/주황 · 다른 자산 초록 · 현금 회색)</p>')
        st.plotly_chart(product_donut(weights, colors, products, budget), width='stretch', config={'displayModeBar': False})

    # 과거 성과: 매년 4월 그때까지의 데이터로 같은 방식을 다시 적용한 백테스트 (backtest.py)
    use_factor = bool(data.get('picks'))
    bt = get_backtest(profile, use_factor)
    bp = bt['perf']['추천 방식']
    navs = bt['navs'] / bt['init']
    pf, safe = navs['추천 방식'], navs['단기채권만']
    end_pf, end_safe = budget * pf.iloc[-1], budget * safe.iloc[-1]
    rule = '국내 ETF 8종 + 그해 저평가 우량주 5종목' if use_factor else '국내 ETF 8종'
    with st.expander(f'{bt["start"]:%Y년 %m월}부터 매년 이 방식으로 추천받았다면? (과거 모의 계산)'):
        html(f"""<p class="warnline">앞으로도 이렇게 된다는 뜻이 아니에요. {bt['start']:%Y.%m}부터 매년 4월, 그때까지 알 수 있던
        자료로만 비중을 다시 정해 거꾸로 계산한 값이에요. 사고팔 때 비용 {bt['bp']:.1%}, 현금은 연 {bt['rf']:.0%} 예금 금리로 봤고,
        분배금·세금은 빠져 있어요.</p>""")
        yf = ',.1f' if budget < 2_000_000 else ',.0f'      # 예산이 작으면 눈금이 같은 숫자로 겹치지 않게 소수 한 자리
        fig3 = go.Figure()
        fig3.add_scatter(x=safe.index, y=budget * safe / 1e4, name='단기채권 ETF만',
                         line=dict(color='#98a2b3', width=2, dash='dot'),
                         hovertemplate='%{y:' + yf + '}만원<extra>단기채권만</extra>')
        fig3.add_scatter(x=pf.index, y=budget * pf / 1e4, name='추천 방식',
                         line=dict(color=BRAND, width=3), fill='tonexty', fillcolor='rgba(46,91,127,.08)',
                         hovertemplate='%{y:' + yf + '}만원<extra>추천 방식</extra>')
        plot_style(fig3, 280, hovermode='x unified', top=24)
        fig3.update_yaxes(tickformat=yf, ticksuffix='만원')
        st.plotly_chart(fig3, width='stretch', config={'displayModeBar': False})
        html(f"""<div class="compare">
          <div><span>추천 방식 (과거 계산)</span><b>{won(budget)} → {won(end_pf)}</b><em>{end_pf / budget - 1:+.1%}</em></div>
          <div><span>단기채권 ETF만 (원금 보장 아님)</span><b>{won(budget)} → {won(end_safe)}</b><em>{end_safe / budget - 1:+.1%}</em></div>
          <div><span>가장 크게 떨어졌던 때</span><b>당시 최고점에서 {abs(bp['MDD']):.1%} 하락</b><em class="down">그때까지 가장 높았던 값보다 내려간 비율이에요. 처음 넣은 돈 기준 손실액이 아니에요.</em></div>
        </div>
        <ul class="terms plain">
          <li><b>연평균 수익률 {bp['CAGR']:+.1%}</b> 처음과 마지막 값으로 구한 1년 평균 수익률이에요. 해마다 그만큼 벌었다는 뜻은 아니에요.</li>
          <li><b>변동성 {bp['변동성(연율화)']:.1%}</b> {TERMS['변동성']}</li>
          <li><b>최대 낙폭 {bp['MDD']:.1%}</b> {TERMS['최대 낙폭']}</li>
        </ul>""")
        st.caption(f'계산에 쓴 상품: {rule}. 거래대금 상위 종목은 지금 순위라 과거 시점에는 고를 수 없어서 빼고 계산했어요.')
        yearly = bt['yearly'].map(lambda v: f'{v:+.1%}')
        yearly.index = [f'{y}년' for y in yearly.index]
        html('<p class="cd">해마다 얼마나 늘거나 줄었나요?</p>')
        st.dataframe(yearly, width='stretch')
        if use_factor:
            st.caption("'추천(ETF만)'은 저평가 우량주 없이 국내 ETF 8종만 썼을 때예요.")
            picks = bt['picks'].rename_axis('다시 고른 날').rename('고른 종목 (저PER·저PBR·고ROE 순위합 상위 5)')
            st.dataframe(picks, width='stretch')

    # 추천 근거
    t = rc.PROFILE_TABLE[profile]
    lo, hi = judge['type_range']
    picked = ''.join(f'<li><span>{rc.TOPICS[i]}</span>{CIRCLED[a]} {esc(rc.QUESTIONS[i][1][a])} <em>{rc.POINTS[a]}점</em></li>'
                     for i, a in enumerate(ss.ans))
    bands = ' · '.join(f'{lo_}~{hi_}점 {name}' for lo_, hi_, name, _ in rc.TYPES)
    blo, bhi = judge['band_range']
    split_note = (f' 위험 중립형은 범위가 넓어 11~17점은 안정성장형, 18~24점은 성장형 배분을 써요.'
                  if judge['type'] == '위험 중립형' else '')
    why_split = {
        '안정형': '손실을 피하는 게 가장 중요한 성향이라 대부분을 채권에 두고, 주식은 5%만 담아요.',
        '안정성장형': '안정이 먼저지만 예금보다는 조금 더 벌 수 있게, 채권을 줄이고 다른 자산과 여러 자산 묶음을 섞어요.',
        '성장형': '수익과 안정의 균형을 맞추려고 채권·주식·다른 자산을 비슷한 크기로 나눠요.',
        '공격형': '높은 수익을 바라는 성향이라 주식을 가장 많이 담고, 채권은 10%로 줄여요.',
    }[profile]
    vol = pd.Series(np.sqrt(np.diag(data['cov'])), index=data['cov'].index)
    alt = res['sleeves']['대안투자']
    if res['model'] == 'MVP':
        why_weight = ('같은 종류 안에서는 전체 값이 가장 덜 흔들리는 조합을 찾았어요. 덜 흔들리는 상품을 많이 담고, '
                      '서로 반대로 움직이는 상품을 섞어 흔들림을 줄여요.')
    else:
        why_weight = ('같은 종류 안에서는 모든 상품이 전체 흔들림을 똑같이 나눠 지도록 했어요(위험균형). 많이 흔들리는 상품은 적게, '
                      '덜 흔들리는 상품은 많이 담아요.')
    if 'OIL' in alt and 'USD' in alt:
        why_weight += (f' 예를 들어 다른 자산 안에서 원유(1년 변동성 {vol["OIL"]:.0%})는 {alt["OIL"]:.0%}, '
                       f'달러(변동성 {vol["USD"]:.0%})는 {alt["USD"]:.0%}를 담았어요.')
    held_picks = [n for n in data.get('picks', []) if n in weights.index]
    if held_picks:
        why_weight += (f' 주식 몫의 절반은 이익에 비해 싸고(PER·PBR이 낮고) 돈을 잘 버는(ROE가 높은) 국내 기업 '
                       f'{", ".join(held_picks)}에 똑같이 나눠 담았어요. 매년 4월 새 재무제표로 다시 골라요.')
    with st.expander('왜 이렇게 추천했나요? (내 답과 점수, 나누는 기준)'):
        html(f"""<div class="tags light">{''.join(f'<span>{esc(x)}</span>' for x in res['tags'])}</div>
        <div class="how">
          <div><b>왜 {judge['type']}인가요?</b>
            <ul class="picked">{picked}</ul>
            <p>공격적인 답일수록 높은 점수(①4점 ~ ⑤0점)를 매겨 더하면 <strong>{judge['score']}점</strong> / {rc.MAX_SCORE}점이에요.
            판정 기준은 {bands}이에요({judge['type']}: {lo}~{hi}점).{split_note}</p></div>
          <div><b>왜 이렇게 나눴나요?</b>
            <p>{why_split}</p>
            <p>채권 {t['채권·예금']}% · 주식 {t['주식']}% · 다른 자산 {t['대안투자']}% · 여러 자산 묶음 {t['자산배분']}% · 현금 {t['유동성']}%.
            투자성향별 추천 자산배분표(법률신문, 신한 PB 기고)의 {profile}({blo}~{bhi}점) 비율이에요.</p></div>
          <div><b>왜 이 상품을 이만큼 담나요?</b><p>{why_weight}</p></div>
        </div>""")

    st.write('')
    with st.container(key='res_more_actions', horizontal=True, gap='small'):
        st.button('처음부터 다시 진단', key='res_restart', on_click=restart)
        st.button('상품 둘러보기', key='to_products_top', on_click=go_page, args=('products',))


# ── 4. 나만의 포트폴리오 · 상품 둘러보기 · 상품 설명 ─────────────────────
def page_mock():
    if not done():
        pe.render_intro(ss, start_for_build, BUILD)
        return
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
