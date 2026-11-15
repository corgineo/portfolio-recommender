"""첫 포트폴리오 · 포트폴리오 추천 서비스

실행: streamlit run app.py
화면: 첫 화면(home) → 진단(quiz, 예산 + 7문항) → 결과(result) → 나만의 포트폴리오 제작하기(mock) · 기업 분석(company)
추천 계산은 recommender.py(팀 core: ETF 20종 + 개별 종목, choose_picks), 편집기는 c_integration.py · portfolio_editor.py,
기업 재무는 company_financials.py, 디자인은 assets/style.css · ui.py 에 있어요.
결과 화면의 '연 1회 리밸런싱 과거 전략'은 annual_backtest.py (팀원 sehui 백테스트, 원래 8종 ETF 고정)예요.
화면 원칙: 데스크톱은 주 영역 : 보조 영역 = 1.618 : 1, 좁은 화면은 한 열. 한 화면에 주요 행동 하나.
"""
import importlib
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import annual_backtest as ab
import recommender as rc
from c_integration import render_existing_editor
from company_financials import render_company_financials
from ui import (html, esc, won, won_exact, dot, section, donut_svg, plot_style, GROUP_EASY, GROUP_ONE, GROUP_ORDER,
                GROUP_TINY, TERMS, easy_group, BRAND)

importlib.reload(rc)   # recommender.py 를 고쳐도 서버를 다시 켜지 않고 바로 반영되게
importlib.reload(ab)

APP_NAME = '첫 포트폴리오'
BUILD = '나만의 포트폴리오 제작하기'
GOLD = [1.618, 1]                 # 주 영역 : 보조 영역
CIRCLED = ['①', '②', '③', '④', '⑤']
TOP_N = 6                         # 표는 상위 6개 + 더보기

# 설문 원문(rc.QUESTIONS)은 그대로 두고, 문항마다 쉬운 한 줄 풀이만 따로 붙여요.
Q_EASY = [
    '현재 나이에 해당하는 구간을 선택해 주세요.',
    '투자금을 인출하지 않고 운용할 수 있는 기간입니다.',
    '수익률과 원금보전 중 우선하는 기준을 선택해 주세요.',
    '일반적인 시장 상황에서 기대하는 수익 수준입니다.',
    '향후 10년간 주식시장 침체를 가정했을 때 기대하는 성과 수준입니다.',
    '3년 투자 기간에 감내할 수 있는 손실 수준입니다.',
    '3개월 단기 손실에 대한 태도입니다.',
]
TYPE_TINY = {'안정 추구형': '안정', '위험 중립형': '중립', '공격 추구형': '공격'}
TYPE_EASY = {
    '안정 추구형': '손실 회피를 우선하며 물가 상승률을 웃도는 수익을 목표로 합니다.',
    '위험 중립형': '일정 수준의 가격 변동을 감수하며 장기적으로 완만한 수익을 추구합니다.',
    '공격 추구형': '큰 가격 변동을 감수하며 높은 수익을 추구합니다. 손실 규모도 커질 수 있습니다.',
}

# ── 상품 이름 · 한 줄 설명 · 코드 (ETF 20종은 직접, 개별 종목은 products.csv · factor_picks.csv 에서) ──
SHORT = {'KOSPI200': 'KODEX 200', 'SP500': 'TIGER 미국S&P500선물', 'TOPIX': 'TIGER 일본TOPIX', 'CSI300': 'TIGER 차이나CSI300',
         'EUROSTOXX50': 'TIGER 유로스탁스50', 'KBOND': 'KIWOOM 통안채1년', 'OIL': 'TIGER 원유선물', 'USD': 'KIWOOM 미국달러선물',
         'CASH': '현금', 'NASDAQ100': 'TIGER 미국나스닥100', 'DIVIDEND': 'PLUS 고배당주', 'GOLD': 'KODEX 골드선물(H)',
         'REIT': 'TIGER 리츠부동산인프라', 'KTB3Y': 'KODEX 국고채3년', 'SHORTBOND': 'KODEX 단기채권',
         'CORPBOND': 'RISE 중기우량회사채', 'KTB10Y': 'KIWOOM 국고채10년', 'UST10Y': 'TIGER 미국채10년선물',
         'UST30Y_H': 'KODEX 미국30년국채울트라선물(H)', 'MIX_K200_UST': 'KODEX 200미국채혼합50',
         'MIX_DIVIDEND': 'PLUS 고배당주채권혼합'}
DESC = {'KOSPI200': '국내 대형주 200', 'SP500': '미국 주식', 'TOPIX': '일본 주식', 'CSI300': '중국 주식',
        'EUROSTOXX50': '유럽 주식', 'KBOND': '국내 단기채권', 'OIL': '원유', 'USD': '미국 달러', 'CASH': '수시 입출금 자금',
        'NASDAQ100': '미국 성장주', 'DIVIDEND': '국내 배당주', 'GOLD': '금', 'REIT': '리츠·부동산',
        'KTB3Y': '국내 국고채 3년', 'SHORTBOND': '국내 단기채권', 'CORPBOND': '국내 회사채', 'KTB10Y': '국내 국고채 10년',
        'UST10Y': '미국 장기국채', 'UST30Y_H': '미국 장기국채(환헤지)',
        'MIX_K200_UST': '국내 주식·미국 채권 혼합', 'MIX_DIVIDEND': '국내 배당주·채권 혼합'}
CODE = {v['name']: k for k, v in rc.ETF_INFO.items()}
_CAT = rc.STOCK_CATALOG if rc.STOCK_CATALOG is not None else pd.DataFrame(columns=['code', 'name', 'sub_class', 'currency'])


def _factor_codes():
    try:
        import factor
        p = factor.load_picks()
        return dict(zip(p['종목명'], p['종목코드']))
    except Exception:
        return {}


FACTOR_CODE = _factor_codes()


def short(n):
    return SHORT.get(n) or (_CAT.at[n, 'name'] if n in _CAT.index else n)


def desc(n):
    if n in DESC:
        return DESC[n]
    if n in _CAT.index:
        return _CAT.at[n, 'sub_class'] + (' · 원화 환산' if _CAT.at[n, 'currency'] == 'USD' else '')
    return '국내 가치주 (PER·PBR·ROE 기준)'


def code(n):
    return CODE.get(n) or (_CAT.at[n, 'code'] if n in _CAT.index else FACTOR_CODE.get(n, ''))


def is_us(n):
    return n in _CAT.index and _CAT.at[n, 'currency'] == 'USD'


st.set_page_config(page_title=APP_NAME, page_icon='📊', layout='wide', initial_sidebar_state='collapsed')
style_file = Path(__file__).parent / 'assets' / 'style.css'
if style_file.exists():
    st.markdown(f"<style>{style_file.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def get_data():
    prices = rc.load_prices(with_stocks=True, with_candidates=True)     # ETF 20종 + 팩터 종목 + 거래대금 상위 개별주
    rets, avg_returns, cov_mat = rc.model_inputs(prices)
    return prices, rets, avg_returns, cov_mat


try:
    prices, rets, avg_returns, cov_mat = get_data()
except FileNotFoundError:
    st.error('가격 자료를 불러오지 못했습니다. ETF 가격 파일을 확인해 주세요.')
    st.stop()
AS_OF = prices.index[-1]


@st.cache_data(show_spinner='추천 구성 계산 중...')
def recommend(answers, budget):
    """설문 답 + 예산 → 팀 추천 로직(choose_picks → build_portfolio → allocate_budget) 결과"""
    judge = rc.judge_profile(list(answers))
    profile = judge['profile']
    picks = rc.choose_picks(profile, prices, budget)              # 개별 종목: 반은 팩터, 반은 거래대금 상위
    weights, detail, sleeves = rc.build_portfolio(profile, cov_mat, picks)
    perf = rc.performance(weights, rets)
    alloc = rc.allocate_budget(weights, prices, budget)
    alloc['name'] = [n for n in weights.index if n != rc.CASH] + [rc.CASH]
    order = sorted(weights.index, key=lambda n: (GROUP_ORDER.index(rc.group_of(n)), -weights[n]))
    return dict(judge=judge, profile=profile, picks=picks, weights=weights, detail=detail, sleeves=sleeves,
                perf=perf, alloc=alloc, colors=rc.color_map(order), model=rc.MODEL_BY_PROFILE[profile],
                tags=rc.hashtags(profile, judge['period'], weights, detail))


# ── 화면 상태 (페이지를 오가도 유지돼요) ──────────────────────────────────
ss = st.session_state
ss.setdefault('page', 'home')
ss.setdefault('step', 0)                       # 진단: 0 = 예산, 1~7 = 설문 문항
ss.setdefault('ans', [None] * len(rc.QUESTIONS))
ss.setdefault('budget', 10_000_000)
ss.setdefault('show_all_hold', False)
ss.setdefault('after_quiz', None)              # 'mock' 이면 진단을 마친 뒤 제작 화면으로 바로 가요
ss.setdefault('company_pick', None)
if len(ss.ans) != len(rc.QUESTIONS):          # 예전 5문항 상태가 남아 있으면 새로 시작
    ss.ans = [None] * len(rc.QUESTIONS)
N_STEPS = 1 + len(rc.QUESTIONS)


def go_page(page, step=None):
    ss.page = page
    if step is not None:
        ss.step = step


def restart():
    ss.ans = [None] * len(rc.QUESTIONS)
    ss.after_quiz = None
    go_page('quiz', 0)


def resume_quiz():
    """진단을 하다 다른 화면에 다녀오면, 답하지 않은 첫 문항부터 이어서 해요"""
    if None in ss.ans and any(a is not None for a in ss.ans):
        go_page('quiz', ss.ans.index(None) + 1)
    else:
        go_page('quiz', 0)


def start_for_build():
    ss.after_quiz = 'mock'
    resume_quiz()


def finish_quiz():
    ss.page = ss.after_quiz or 'result'
    ss.after_quiz = None


def open_company(name):
    ss.company_pick = name
    go_page('company')


def clear_company():
    ss.company_pick = None


def done():
    return None not in ss.ans


def current():
    return recommend(tuple(ss.ans), int(ss.budget))


# ── 공통: 상단 바 · 푸터 ───────────────────────────────────────────────
def nav():
    first = ('추천 결과', 'result', go_page, ('result',)) if done() else ('투자성향 진단', 'quiz', resume_quiz, ())
    items = [first, (BUILD, 'mock', go_page, ('mock',)), ('기업 분석', 'company', open_company, (None,))]
    with st.container(key='navbar', horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
        st.button(APP_NAME, key='nav_logo', on_click=go_page, args=('home',))
        with st.container(key='navmenu', horizontal=True, horizontal_alignment='right', width='content', gap='small'):
            for label, page, fn, args in items:
                st.button(label, key=f'nav_{page}', on_click=fn, args=args,
                          type='primary' if ss.page == page else 'secondary')


def footer():
    html(f"""<div class="foot"><div class="brand"><i></i><b>{APP_NAME}</b></div>
    <p>투자 입문자를 위한 포트폴리오 추천·구성 서비스입니다. 모든 구성은 모의 계산이며 실제 주문과 계좌 연결은 제공하지 않습니다.
    투자 권유가 아니며, 과거 성과는 미래 수익을 보장하지 않습니다.</p>
    <p class="src">가격: FinanceDataReader · {AS_OF:%Y.%m.%d} 종가 기준 · 원화(미국 종목은 원/달러 환율 적용)
    · 재무: 국내 상장사 연간 자료</p></div>""")


def group_legend(group_w, budget, show_desc=True):
    """자산 종류 범례: 색 + 이름 + % + 금액 (색만으로 구분하지 않아요)"""
    rows = ''
    for g in GROUP_ORDER:
        w = float(group_w.get(g, 0))
        if w <= 0:
            continue
        d = f'<em>{GROUP_ONE[g]}</em>' if show_desc else ''
        rows += (f'<li><span class="sw" style="background:{rc.GROUP_BASE[g]}"></span>'
                 f'<span class="nm"><b>{easy_group(g)}</b>{d}</span>'
                 f'<span class="pc">{w:.0%}</span><span class="am">{won(budget * w)}</span></li>')
    return f'<ul class="legend">{rows}</ul>'


def price_caption(names):
    """표 아래 기준일·통화 캡션. 팩터 종목은 가격 파일 마지막 날이 달라서 따로 적어요"""
    txt = f'{AS_OF:%Y.%m.%d} 종가 기준 · 원화 · 1주 단위 · 수수료·세금 제외'
    stale = sorted({prices[n].last_valid_index() for n in names if n in prices and n != rc.CASH
                    and prices[n].last_valid_index() < AS_OF})
    if stale:
        txt += f' · 일부 국내 가치주는 최근 거래일인 {stale[0]:%Y.%m.%d} 종가 기준'
    if any(is_us(n) for n in names):
        txt += ' · 미국 종목은 현지 종가에 원/달러 환율을 적용한 원화 가격'
    return txt


# ── 1. 첫 화면 ───────────────────────────────────────────────────────
def page_home():
    example = rc.PROFILE_TABLE['성장형']
    ex_budget = 10_000_000
    segs = [(easy_group(g), example[g], rc.GROUP_BASE[g]) for g in GROUP_ORDER]
    with st.container(key='home_hero'):
        left, right = st.columns(GOLD, gap='large', vertical_alignment='center')
        with left:
            html(f"""<div class="hero"><span class="eyebrow">투자 입문자를 위한 포트폴리오 서비스</span>
            <h1>투자성향에 맞춘<br><em>포트폴리오 설계</em></h1>
            <p class="sub">투자성향과 예산을 기준으로 ETF·개별 주식의 비중과 매수 수량을 제안합니다.
            추천안을 확인하고 <b>나만의 포트폴리오</b>로 조정할 수 있습니다.</p></div>""")
            with st.container(key='home_ctas', horizontal=True, gap='small'):
                if done():
                    st.button('추천 결과 보기', type='primary', key='home_result', on_click=go_page, args=('result',))
                elif any(a is not None for a in ss.ans):
                    n = ss.ans.index(None) + 1
                    st.button(f'진단 이어서 하기 ({n}/{len(rc.QUESTIONS)})', type='primary', key='home_resume',
                              on_click=resume_quiz)
                else:
                    st.button('투자성향 진단 시작', type='primary', key='home_start', on_click=restart)
                st.button(BUILD, key='home_build', on_click=go_page, args=('mock',))
            html('<p class="hint">소요 시간 약 3분 · 회원가입 불필요 · 모의 구성(실제 주문 없음)</p>')
        with right:
            html(f"""<figure class="hero-fig"><figcaption><span class="tag">예시</span>1,000만원 배분 예시</figcaption>
            {donut_svg(segs, '예시 예산', won(ex_budget), '5개 자산군', size=220, thick=30, label='예시 배분')}
            {group_legend(pd.Series({g: example[g] / 100 for g in GROUP_ORDER}), ex_budget, show_desc=False)}
            <p class="fig-note">성장형 자산배분 예시입니다. 맞춤 구성은 진단 후 제공됩니다.</p></figure>""")

    html(f"""<ol class="journey">
      <li><span>1</span><div><b>투자성향 진단</b><p>7개 문항으로 투자 기간과 손실 감내 수준을 확인합니다.</p></div></li>
      <li><span>2</span><div><b>추천 구성 확인</b><p>ETF·개별 종목의 비중과 매수 수량을 제시합니다.</p></div></li>
      <li class="key"><span>3</span><div><b>{BUILD}</b><p>비중을 조정하면 금액·수량·과거 성과가 즉시 재계산됩니다.</p></div></li>
    </ol>""")


# ── 2. 진단 화면 (한 화면에 한 질문) ───────────────────────────────────
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
    preset = {'10만원': 100_000, '100만원': 1_000_000, '1,000만원': 10_000_000, '3,000만원': 30_000_000}
    if ss.get('budget_pill'):
        ss.budget = preset[ss.budget_pill]
        ss.budget_w = ss.budget


def steps_bar(s):
    cells = ''.join(f'<i class="{"on" if k < s else ("now" if k == s else "")}"></i>' for k in range(N_STEPS))
    return f'<div class="steps" aria-hidden="true">{cells}</div>'


def page_quiz():
    s = min(ss.step, N_STEPS - 1)
    _, body, _ = st.columns([1, 2.6, 1])
    with body:
        back_note = (f'<div class="flow-note">진단 완료 후 <b>{BUILD}</b> 화면으로 이동합니다.</div>'
                     if ss.get('after_quiz') == 'mock' else '')
        if s == 0:
            html(f"""<div class="quiz-head">{back_note}<div class="meta"><span>준비 · 투자 예산</span><span>문항 7개</span></div>
            {steps_bar(s)}
            <h2>투자 예산</h2>
            <p>실제 자금은 이동하지 않습니다. 입력한 금액으로 상품별 매수 가능 수량을 계산합니다.</p></div>""")
            if 'budget_w' not in ss:
                ss.budget_w = ss.budget
            st.number_input('투자 예산 (원, 최소 10만원)', min_value=100_000, max_value=1_000_000_000, step=1_000_000,
                            key='budget_w', on_change=set_budget, format='%d')
            html(f'<div class="won">= {won(ss.budget)}</div>')
            st.pills('예산 빠른 선택', ['10만원', '100만원', '1,000만원', '3,000만원'], key='budget_pill',
                     on_change=pick_budget, label_visibility='collapsed')
        else:
            i = s - 1
            q, options = rc.QUESTIONS[i]
            html(f"""<div class="quiz-head">{back_note}<div class="meta"><span>질문 {s} / {len(rc.QUESTIONS)} · {rc.TOPICS[i]}</span>
            <span>선택하면 다음 문항으로 이동합니다</span></div>
            {steps_bar(s)}
            <h2>{esc(q)}</h2><p class="easy">{esc(Q_EASY[i])}</p></div>""")
            st.radio(q, list(range(len(options))), index=ss.ans[i], key=f'q{i}_w', on_change=save_answer, args=(i,),
                     label_visibility='collapsed', format_func=lambda k, o=options: f'{CIRCLED[k]}  {o[k]}')

        st.write('')
        b1, b2 = st.columns(2)
        b1.button('이전', width='stretch', key='quiz_prev',
                  on_click=(lambda: go_page('home')) if s == 0 else (lambda: go_page('quiz', s - 1)))
        if s == 0:
            b2.button('진단 시작', type='primary', width='stretch', key='quiz_next',
                      on_click=lambda: go_page('quiz', 1))
        else:
            last = s == N_STEPS - 1
            b2.button(('포트폴리오 제작으로 이동' if ss.get('after_quiz') == 'mock' else '결과 보기') if last else '다음',
                      type='primary', width='stretch', disabled=ss.ans[s - 1] is None, key='quiz_next',
                      on_click=finish_quiz if last else (lambda: go_page('quiz', s + 1)))
            html('<p class="hint center">‘이전’ 버튼으로 이전 문항의 응답을 수정할 수 있습니다.</p>')


# ── 3. 결과 화면 ─────────────────────────────────────────────────────
def score_bar(score):
    """0~28점 위에 3개 성향 구간과 내 점수를 표시"""
    total = rc.MAX_SCORE + 1
    zones = ''.join(f'<div style="flex:{hi - lo + 1}" class="z{k}"><span>{TYPE_TINY.get(name, name)}</span><em>{lo}~{hi}점</em></div>'
                    for k, (lo, hi, name, _) in enumerate(rc.TYPES))
    pos = (score + 0.5) / total * 100
    return (f'<div class="score"><div class="lab">진단 점수 <b>{score}점</b> / {rc.MAX_SCORE}점</div>'
            f'<div class="zones">{zones}<i class="mk" style="left:{pos:.1f}%"></i></div></div>')


def product_donut(weights, colors, budget):
    """현금까지 포함한 전체 100% 도넛 (가운데 예산 = 표의 목표 비중 합계와 같아요)"""
    names = sorted(weights.index, key=lambda n: (GROUP_ORDER.index(rc.group_of(n)), -weights[n]))
    vals = [round(weights[n] * 100, 1) for n in names]
    fig = go.Figure(go.Pie(labels=[short(n) for n in names], values=vals, hole=0.62, sort=False,
                           marker=dict(colors=[colors[n] for n in names], line=dict(color='#fff', width=2)),
                           text=[f'{v:.0f}%' if v >= 4 else '' for v in vals], textinfo='text', textfont=dict(size=12),
                           customdata=[GROUP_TINY[rc.group_of(n)] for n in names],
                           direction='clockwise',
                           hovertemplate='%{label} · %{customdata}<br>%{value:.1f}%<extra></extra>'))
    plot_style(fig, 300, legend=False,
               annotations=[dict(text=f'<b>{won(budget)}</b>', showarrow=False, font=dict(size=16, color='#16213B'))])
    return fig


def holdings_table(alloc, colors, show_all):
    rows = alloc[alloc['name'] != rc.CASH].sort_values('금액(원)', ascending=False)
    cash = alloc[alloc['name'] == rc.CASH].iloc[0]
    total = float(alloc['금액(원)'].sum()) or 1.0
    shown = rows if show_all else rows.head(TOP_N)
    body = ''
    for _, r in shown.iterrows():
        n, c = r['name'], colors[r['name']]
        qty = f'{r["수량(주)"]:,.0f}주' if r['수량(주)'] > 0 else '<span class="zero">0주</span>'
        sub = ' · '.join(x for x in [GROUP_TINY[rc.group_of(n)], desc(n), code(n)] if x)
        body += (f'<tr><td>{dot(c)}<span class="nm">{esc(short(n))}</span><span class="sub1">{esc(sub)}</span></td>'
                 f'<td>{r["비중(%)"]:.1f}%</td><td>{r["현재가(원)"]:,.0f}원</td>'
                 f'<td class="amt">{r["금액(원)"]:,.0f}원<span class="mbar"><i style="width:{r["금액(원)"] / total * 100:.1f}%;background:{c}"></i></span></td>'
                 f'<td>{qty}</td></tr>')
    if not show_all and len(rows) > TOP_N:
        body += f'<tr class="more"><td colspan="5">외 {len(rows) - TOP_N}개 상품 · 전체 목록은 아래 버튼으로 확인</td></tr>'
    body += (f'<tr class="cash"><td>{dot(rc.GROUP_BASE["유동성"])}<span class="nm">잔여 현금</span>'
             f'<span class="sub1">현금 비중 {cash["비중(%)"]:.0f}% + 1주 미만 잔액</span></td><td>{cash["비중(%)"]:.1f}%</td><td></td>'
             f'<td class="amt">{cash["금액(원)"]:,.0f}원<span class="mbar"><i style="width:{cash["금액(원)"] / total * 100:.1f}%;background:#98a2b3"></i></span></td><td></td></tr>')
    return (f'<div class="hold-wrap"><table class="holdings compact"><thead><tr><th>상품</th><th>목표 비중</th><th>기준가</th>'
            f'<th>매수 예정 금액</th><th>수량</th></tr></thead><tbody>{body}</tbody></table></div>'), len(rows)


@st.cache_data(show_spinner='과거 전략 계산 중...')
def annual_strategy(profile, version, bp, rf):
    """연 1회 리밸런싱 과거 전략 (annual_backtest). 캐시 키: 성향 · 입력 자료 버전 · 거래비용 · 현금 이율"""
    return ab.run(profile, bp=bp, rf=rf)


def _pct_cell(v):
    return '-' if pd.isna(v) else f'<span class="{"dn" if v < 0 else ""}">{v:+.1%}</span>'


def annual_section(profile):
    """결과 화면 4: 원래 8종 ETF + 연도별 가치주로 매년 4월 리밸런싱한 과거 전략 (현재 추천 구성과 별개)"""
    with st.container(key='card_annual'):
        try:
            res = annual_strategy(profile, ab.data_version(), ab.BP, ab.RF)
        except (OSError, ValueError) as exc:
            section('4', '연 1회 리밸런싱 전략 과거 성과')
            st.warning(f'과거 전략 성과를 계산하지 못했습니다. {exc}')
            return
        navs, m = res['navs'], res['metrics']
        S, B = navs.columns
        section('4', '연 1회 리밸런싱 전략 과거 성과',
                f'{res["start"]:%Y.%m.%d} ~ {res["end"]:%Y.%m.%d} · {profile} 배분 규칙을 매년 4월 다시 적용한 모의 계산입니다.')
        html('<p class="scope-note"><b>검증 대상: 국내 ETF 8종 + 연도별 가치주 5종.</b> '
             '현재 추천 포트폴리오와 별도로 계산한 참고 성과입니다.</p>')
        fig = go.Figure()
        fig.add_scatter(x=navs.index, y=navs[B], name='단기채권 ETF', line=dict(color='#98a2b3', width=2, dash='dot'),
                        hovertemplate='%{y:.1f}<extra>단기채권 ETF</extra>')
        fig.add_scatter(x=navs.index, y=navs[S], name='연 1회 리밸런싱 전략', line=dict(color=BRAND, width=3),
                        hovertemplate='%{y:.1f}<extra>연 1회 리밸런싱 전략</extra>')
        plot_style(fig, 260, hovermode='x unified', top=24)
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False}, key='res_annual')
        html(f"""<div class="compare">
          <div><span>연평균 성장률(CAGR)</span><b>{m[S]['cagr']:+.1%}</b><em>단기채권 ETF {m[B]['cagr']:+.1%}</em></div>
          <div><span>최대 낙폭</span><b>고점 대비 {abs(m[S]['mdd']):.1%} 하락</b><em>단기채권 ETF {abs(m[B]['mdd']):.1%}</em></div>
          <div><span>기간 수익률</span><b>{m[S]['cum']:+.1%}</b><em>시작값 100 → {m[S]['final']:.1f}</em></div>
        </div>
        <p class="warnline">과거 성과이며 미래 수익을 보장하지 않습니다. 시작값 100 · 거래비용 {res['bp']:.1%}(첫 매수 포함) ·
        현금 연 {res['rf']:.0%} 가정 · 분배금·세금 제외.</p>""")

        y = res['yearly']
        with st.expander('연도별 수익률'):
            rows = ''.join(f'<tr><td>{yr}년</td><td>{y.at[yr, "기간"]}</td><td><b>{_pct_cell(y.at[yr, S])}</b></td>'
                           f'<td>{_pct_cell(y.at[yr, B])}</td></tr>' for yr in y.index)
            html(f'<div class="hold-wrap"><table class="mtab wide"><thead><tr><th>연도</th><th>기간</th><th>전략</th>'
                 f'<th>단기채권 ETF</th></tr></thead><tbody>{rows}</tbody></table></div>')
        W, sel = res['weights'], res['selections']
        with st.expander('연도별 편입 종목과 비중'):
            years = [f'{t:%Y}' for t in W.index]
            stock_cols = [c for c in W.columns if c not in ab.LEGACY_ETFS and c != ab.CASH]
            lines = [(ab.LEGACY_LABEL[n], W[n]) for n in ab.LEGACY_ETFS]
            lines += [('국내 가치주 5종 합계', W[stock_cols].sum(axis=1)), ('현금', W[ab.CASH])]
            head = ''.join(f'<th>{yr}</th>' for yr in years)
            body = ''.join(f'<tr><td>{esc(lab)}</td>' + ''.join(f'<td>{v:.1%}</td>' for v in s) + '</tr>' for lab, s in lines)
            html(f'<div class="hold-wrap"><table class="mtab wide"><thead><tr><th>목표 비중</th>{head}</tr></thead>'
                 f'<tbody>{body}</tbody></table></div>')
            picks = ''.join(f'<li><b>{r["매매일"]:%Y.%m.%d} 매매</b> · {r["재무 기준 회계연도"]}년 재무 기준 · '
                            f'{esc(r["팩터 종목"])}</li>' for _, r in sel.iterrows())
            html(f'<ul class="terms plain">{picks}</ul>'
                 '<p class="cap">선정일은 매년 4월 첫 거래일이며, 매매는 다음 거래일 종가 기준입니다.</p>')
        with st.expander('검증 조건 및 유의사항'):
            html(f"""<ul class="terms plain">
              <li><b>리밸런싱</b> 매년 4월 첫 거래일(선정일)까지의 가격으로 목표 비중을 정하고, 다음 거래일 종가에 매매합니다.
              매매 후의 수익률부터 새 비중이 적용됩니다.</li>
              <li><b>배분 기준</b> {profile}의 자산군별 목표 비중을 적용하며, 주식 배분액의 절반은 연도별 가치주 5종에 균등 배분합니다.</li>
              <li><b>가치주 선정</b> 직전 회계연도 재무와 선정일 종가로 계산한 PER·PBR·ROE 순위 합산 상위 5종입니다.
              재무 자료는 회계연도 다음 해 4월부터 이용할 수 있다고 가정하며, 종목별 실제 공시일을 확인한 자료는 아닙니다.</li>
              <li><b>비용·현금</b> 매매 금액의 {res['bp']:.1%}를 거래비용으로 차감합니다(첫 매수 포함). 현금은 연 {res['rf']:.0%} 이자를 가정합니다.
              분배금·배당과 세금은 반영하지 않습니다. 비교 기준인 단기채권 ETF도 같은 매수 비용을 차감합니다.</li>
              <li><b>성과 지표</b> CAGR은 시작 금액 대비 최종 금액을 연 복리로 환산한 값으로, 일평균 수익률을 연환산한 값과 다릅니다.</li>
              <li><b>한계</b> 가치주 후보는 현재 보유한 재무 자료의 종목 범위에서 선정하므로, 이후 상장폐지된 종목이 빠져 있을 수 있습니다.
              현재 추천에 쓰는 추가 ETF 12종과 거래대금 상위 종목은 포함하지 않습니다.</li>
            </ul>""")


def page_result():
    if not done():
        resume_quiz()
        st.rerun()
    res = current()
    judge, profile, perf, weights, alloc = res['judge'], res['profile'], res['perf'], res['weights'], res['alloc']
    colors, budget = res['colors'], ss.budget
    table = rc.PROFILE_TABLE[profile]
    group_w = pd.Series({g: table[g] / 100 for g in GROUP_ORDER})
    cash_amt = float(alloc.loc[alloc['name'] == rc.CASH, '금액(원)'].iloc[0])
    spent = budget - cash_amt

    # ① 성향 · 예산 · 주 행동(제작하기) | 점수 막대
    note = ''
    if judge['short_term']:
        note = (f'<div class="note">투자 기간 1년 이내: 주식 비중이 높은 구성은 손실 회복 기간이 부족할 수 있습니다. '
                f'{BUILD}에서 채권·현금 비중을 높인 구성과 비교해 보세요.</div>')
    with st.container(key='res_top'):
        left, right = st.columns(GOLD, gap='large', vertical_alignment='center')
        with left:
            html(f"""<div class="res-hero"><div class="who">진단 결과</div>
              <h2>{judge['type']} 투자자</h2>
              <p class="desc">{TYPE_EASY[judge['type']]} 자산배분 기준: <b>{profile}</b></p>
              <div class="chips"><span>예산 <b>{won(budget)}</b></span><span>투자 기간 <b>{judge['period']}</b></span>
              <span>추천 상품 <b>{len(weights) - (rc.CASH in weights.index)}개</b></span></div>{note}</div>""")
            with st.container(key='res_actions', horizontal=True, gap='small'):
                st.button(BUILD, type='primary', key='to_mock_top', on_click=go_page, args=('mock',))
                st.button('예산 변경', key='to_cond_top', on_click=go_page, args=('quiz', 0))
        with right:
            html(f'<div class="side-card">{score_bar(judge["score"])}'
                 f'<p class="cd">공격적인 응답일수록 점수가 높습니다. '
                 + ' · '.join(f'{name} {lo_}~{hi_}점' for lo_, hi_, name, _ in rc.TYPES) + '</p>'
                 f'<div class="tags light">{"".join(f"<span>{esc(x)}</span>" for x in res["tags"])}</div></div>')

    # ② 자산군 나누기
    segs = [(easy_group(g), table[g], rc.GROUP_BASE[g]) for g in GROUP_ORDER]
    with st.container(key='card_split'):
        section('1', '자산군별 배분', f'{won(budget)}을 성격이 다른 5개 자산군에 배분합니다.')
        c1, c2 = st.columns([1, 1.618], gap='large', vertical_alignment='center')
        with c1:
            html(donut_svg(segs, '투자 예산', won(budget), '목표 비중', size=250, thick=34, label='자산군별 목표 비중'))
        with c2:
            html(group_legend(group_w, budget)
                 + '<p class="cap">목표 비중 기준 금액입니다. 1주 단위로 매수하면 실제 금액과 차이가 있습니다.</p>')

    # ③ 상품별 구성: 도넛 + 상위 6개 표
    with st.container(key='card_buy'):
        section('2', '매수 계획', '1주 단위 매수 기준의 상품별 수량과 금액입니다. 실제 주문은 실행되지 않습니다.')
        n_buy = int(((alloc['name'] != rc.CASH) & (alloc['수량(주)'] > 0)).sum())
        n_items = int((alloc['name'] != rc.CASH).sum())
        html(f"""<div class="kpis"><div><span>매수 예정 금액</span><b>{won_exact(spent)}</b><em>예산의 {spent / budget:.1%}</em></div>
        <div><span>잔여 현금</span><b>{won_exact(cash_amt)}</b><em>현금 비중 + 1주 미만 잔액</em></div>
        <div><span>추천 상품</span><b>{n_items}개</b><em>1주 이상 매수 {n_buy}개</em></div></div>""")
        c1, c2 = st.columns([1, 1.618], gap='large')
        with c1:
            st.plotly_chart(product_donut(weights, colors, budget), width='stretch',
                            config={'displayModeBar': False}, key='res_product_donut')
            html('<p class="cap">색상 기준: 주식 빨강·주황 · 채권 파랑 · 대안투자 초록 · 자산배분 보라 · 현금 회색</p>')
        with c2:
            tbl, n_rows = holdings_table(alloc, colors, ss.show_all_hold)
            html(tbl)
            if n_rows > TOP_N:
                st.button('접기' if ss.show_all_hold else f'전체 {n_rows}개 보기', key='more_hold',
                          on_click=lambda: ss.update(show_all_hold=not ss.show_all_hold))
        st.caption(price_caption(list(weights.index)))
        if n_buy < n_items:
            st.caption(f'예산 {won(budget)} 기준, 배정 금액이 1주 가격보다 작아 매수하지 않는 상품이 {n_items - n_buy}개 있습니다. '
                       '해당 금액은 잔여 현금에 포함됩니다.')

    with st.container(key='cta_band', horizontal=True, vertical_alignment='center', horizontal_alignment='distribute'):
        html(f"""<div class="cta-band"><b>추천 구성 조정</b>
        <p>{BUILD}에서 비중을 조정하면 금액·수량·과거 성과가 즉시 재계산됩니다.</p></div>""")
        st.button(f'{BUILD} →', key='to_mock_bottom', on_click=go_page, args=('mock',))

    # ④ 과거 성과 (짧은 주의 문구 + 기준 기간)
    safe = rc.safe_index(rets)
    start = perf['index'].index[0]
    end_pf, end_safe = budget * perf['index'].iloc[-1] / 100, budget * safe.iloc[-1] / 100
    with st.container(key='card_perf'):
        section('3', f'현재 추천 구성의 최근 {rc.LOOKBACK_YEARS}년 성과',
                f'{start:%Y.%m.%d} ~ {perf["index"].index[-1]:%Y.%m.%d} · 현재 목표 비중을 매일 유지한다고 가정한 모의 계산입니다.')
        yf = ',.1f' if budget < 2_000_000 else ',.0f'
        fig3 = go.Figure()
        fig3.add_scatter(x=safe.index, y=budget * safe / 100 / 1e4, name='단기채권 ETF',
                         line=dict(color='#98a2b3', width=2, dash='dot'),
                         hovertemplate='%{y:' + yf + '}만원<extra>단기채권 ETF</extra>')
        fig3.add_scatter(x=perf['index'].index, y=budget * perf['index'] / 100 / 1e4, name='추천 구성',
                         line=dict(color=BRAND, width=3), fill='tonexty', fillcolor='rgba(46,91,127,.08)',
                         hovertemplate='%{y:' + yf + '}만원<extra>추천 구성</extra>')
        plot_style(fig3, 280, hovermode='x unified', top=24)
        fig3.update_yaxes(tickformat=yf, ticksuffix='만원')
        st.plotly_chart(fig3, width='stretch', config={'displayModeBar': False}, key='res_perf')
        html(f"""<div class="compare">
          <div><span>추천 구성</span><b>{won(budget)} → {won(end_pf)}</b><em>기간 수익률 {end_pf / budget - 1:+.1%} · 연환산 수익률(일평균) {perf['return']:+.1%}</em></div>
          <div><span>단기채권 ETF</span><b>{won(budget)} → {won(end_safe)}</b><em>기간 수익률 {end_safe / budget - 1:+.1%}</em></div>
          <div><span>최대 낙폭</span><b>고점 대비 {abs(perf['mdd']):.1%} 하락</b><em>변동성(연환산) {perf['vol']:.1%}</em></div>
        </div>
        <p class="warnline">과거 성과이며 미래 수익을 보장하지 않습니다. 현금 수익률 0% 가정, 분배금·수수료·세금 제외.</p>""")

    annual_section(profile)

    # 더 알아보기
    html('<div class="more-h">상세 정보</div>')
    picked = ''.join(f'<li><span>{rc.TOPICS[i]}</span>{CIRCLED[a]} {esc(rc.QUESTIONS[i][1][a])} <em>{rc.POINTS[a]}점</em></li>'
                     for i, a in enumerate(ss.ans))
    lo, hi = judge['type_range']
    blo, bhi = judge['band_range']
    split_note = (' 위험 중립형은 구간이 넓어 11~17점은 안정성장형, 18~24점은 성장형 배분을 적용합니다.'
                  if judge['type'] == '위험 중립형' else '')
    why_split = {
        '안정형': '손실 회피를 우선해 대부분을 채권에 배분하고 주식은 5%로 제한합니다.',
        '안정성장형': '안정성을 우선하되 예금 이상의 수익을 위해 채권 비중을 낮추고 대안투자와 혼합형 ETF를 함께 배분합니다.',
        '성장형': '수익과 안정의 균형을 위해 채권·주식·대안투자를 비슷한 비중으로 배분합니다.',
        '공격형': '높은 수익을 추구해 주식 비중을 가장 크게 두고 채권은 10%로 제한합니다.',
    }[profile]
    why_weight = (('채권·주식·대안투자 안의 비중은 최근 3년 가격 기준 최소분산 방식으로 정합니다. '
                   '구성 전체의 가격 변동이 가장 작은 조합입니다.'
                   if res['model'] == 'MVP' else
                   '채권·주식·대안투자 안의 비중은 최근 3년 가격 기준 위험균형 방식으로 정합니다. '
                   '각 상품이 전체 가격 변동에 기여하는 정도가 같도록, 변동이 큰 상품은 적게 담습니다.')
                  + ' 자산배분(혼합형 ETF) 몫은 투자성향과 관계없이 위험균형 방식으로 배분합니다.')
    stock_total = table['주식'] / 100 * rc.STOCK_SHARE
    slots = min(rc.MAX_STOCKS, int(stock_total / rc.MIN_WEIGHT + 1e-9))      # 팀 choose_picks 와 같은 개수 공식
    n_picks = len(res['picks'])
    if slots == 0:
        why_weight += (f' 이 성향은 주식 비중({table["주식"]}%)이 작아 개별 종목에 나누면 종목당 비중이 3% 미만이 되므로, '
                       '개별 종목 없이 ETF만 편입합니다.')
    elif n_picks == 0:
        why_weight += (f' 주식 몫의 절반은 개별 종목 최대 {slots}개에 배분하는 것이 원칙이나, 예산 {won(budget)}에서는 '
                       '종목당 배정 금액이 1주 가격보다 작아 개별 종목을 편입하지 않았습니다. 해당 비중은 주식 ETF에 배분했습니다. '
                       '예산을 늘리면 개별 종목이 함께 추천됩니다.')
    else:
        why_weight += (f' 주식 몫의 절반은 개별 종목 {n_picks}개에 같은 비중으로 배분합니다. 그중 절반은 가치 지표(PER·PBR·ROE) '
                       '순위 상위 국내 종목, 절반은 최근 거래대금 상위 국내·미국 종목입니다. 최근 3년 가격이 모두 있고 '
                       '예산으로 1주 이상 매수할 수 있는 종목만 선택하며, 조건에 맞지 않으면 다음 순위 종목을 선택합니다.')
        if n_picks < slots:
            why_weight += f' 예산 내 매수 가능한 종목이 부족해 {slots}개 대신 {n_picks}개를 편입했습니다.'
    small = [short(n) for n, v in weights.items() if n != rc.CASH and v < rc.MIN_WEIGHT - 1e-9]
    min_note = '최종 비중이 3% 미만인 상품은 제외하고 같은 자산군의 다른 상품에 다시 배분합니다.'
    if small:
        min_note += (f' 단, {", ".join(small)}처럼 자산군에 상품이 하나만 남으면 3% 미만이어도 그대로 편입합니다.')
    with st.expander('추천 근거 (응답 점수와 배분 기준)'):
        html(f"""<div class="how">
          <div><b>투자성향 판정</b>
            <ul class="picked">{picked}</ul>
            <p>응답별 점수(①4점 ~ ⑤0점)의 합계는 <strong>{judge['score']}점</strong> / {rc.MAX_SCORE}점이며,
            {judge['type']} 구간은 {lo}~{hi}점입니다.{split_note}</p></div>
          <div><b>자산군 배분</b><p>{why_split}</p>
            <p>채권 {table['채권·예금']}% · 주식 {table['주식']}% · 대안투자 {table['대안투자']}% · 자산배분 {table['자산배분']}% · 현금 {table['유동성']}%
            (투자성향별 자산배분표의 {profile}, {blo}~{bhi}점)</p></div>
          <div><b>상품별 비중</b><p>{why_weight} {min_note}</p></div>
        </div>""")
    with st.expander('자산군 설명과 용어 정의'):
        html('<ul class="terms plain">' + ''.join(f'<li>{dot(rc.GROUP_BASE[g])}<b>{GROUP_EASY[g][0]}</b> {GROUP_EASY[g][1]}</li>'
                                                   for g in GROUP_ORDER)
             + ''.join(f'<li><b>{k}</b> {v}</li>' for k, v in TERMS.items()) + '</ul>')
    stocks = [n for n in weights.index if rc.group_of(n) == '주식' and n not in rc.ETF_NAMES]
    if stocks:
        with st.expander(f'편입 기업 정보 · 주요 사업과 재무 (개별 종목 {len(stocks)}개)'):
            d1, d2 = st.columns([2, 1], vertical_alignment='bottom')
            pick = d1.selectbox('기업 선택', stocks, key='res_company_pick',
                                format_func=lambda n: f'{short(n)} · {"미국" if is_us(n) else "국내"}')
            d2.button('기업 정보 보기', key='res_company_go', width='stretch', on_click=open_company, args=(pick,))
            html('<p class="cap">모든 편입 종목의 주요 사업을 제공합니다. 매출액·영업이익·부채비율은 국내 기업만 제공합니다.</p>')

    with st.container(key='res_more_actions', horizontal=True, gap='small'):
        st.button('진단 다시 하기', key='res_restart', on_click=restart)


# ── 4. 나만의 포트폴리오 제작하기 ───────────────────────────────────────
def page_mock():
    if not done():
        partial = any(a is not None for a in ss.ans)
        n = ss.ans.index(None) + 1
        ex = rc.PROFILE_TABLE['성장형']
        segs = [(easy_group(g), ex[g], rc.GROUP_BASE[g]) for g in GROUP_ORDER]
        with st.container(key='build_intro'):
            left, right = st.columns(GOLD, gap='large', vertical_alignment='center')
            with left:
                html(f"""<div class="page-h big"><span class="eyebrow">포트폴리오 제작</span>
                <h1>{BUILD}</h1>
                <p class="lead">추천 구성을 기준으로 상품별 비중을 조정해 <b>나만의 포트폴리오</b>를 구성합니다.
                비중을 바꾸면 매수 예정 금액·수량·잔여 현금과 과거 성과가 즉시 재계산됩니다.</p></div>
                <ol class="mini-steps">
                  <li class="{'on' if partial else ''}"><span>1</span><b>투자성향 진단 7문항</b><em>소요 시간 약 3분</em></li>
                  <li><span>2</span><b>추천 구성 불러오기</b><em>투자성향별 추천 비중 자동 입력</em></li>
                  <li><span>3</span><b>비중 조정</b><em>합계 최대 100% · 미배분 비중은 현금</em></li>
                </ol>""")
                st.button(f'진단 이어서 하기 ({n}/7)' if partial else '투자성향 진단 시작',
                          type='primary', key='build_start', on_click=start_for_build)
            with right:
                html(f"""<figure class="hero-fig"><figcaption><span class="tag">예시</span>시작 구성</figcaption>
                {donut_svg(segs, '목표 비중', '합계 100%', '', size=180, thick=26, label='시작 구성 예시')}
                <p class="fig-note">성장형 예시 비중입니다. 맞춤 구성은 진단 후 적용됩니다.</p></figure>""")
        return
    res = current()
    with st.container(key='bench_head'):
        h1, h2 = st.columns(GOLD, vertical_alignment='bottom')
        with h1:
            html(f"""<div class="page-h"><span class="eyebrow">모의 구성 · 실제 주문 없음</span>
            <h1>{BUILD}</h1>
            <p><b>{esc(res['judge']['type'])}</b> · {res['profile']} 추천 비중 기준입니다. 비중을 조정하면 그래프와 금액이 즉시 갱신됩니다.</p></div>""")
        with h2:
            with st.container(key='bench_tools', horizontal=True, horizontal_alignment='right', gap='small'):
                st.button('추천 결과 보기', key='mock_back', on_click=go_page, args=('result',))
    render_existing_editor(prices, res['weights'], ss.budget, colors=res['colors'])


def page_company():
    focus = []
    if done():
        w = current()['weights']
        focus = [dict(name=short(n), code=code(n), us=is_us(n)) for n in w.index
                 if rc.group_of(n) == '주식' and n not in rc.ETF_NAMES]
    pick = ss.company_pick
    render_company_financials(focus=focus, preselect=(code(pick) or pick) if pick else None,
                              preselect_name=short(pick) if pick else None, on_clear=clear_company)


def scroll_top():
    where = f'{ss.page}-{ss.step}'
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
 'company': page_company}.get(ss.page, page_home)()
footer()
