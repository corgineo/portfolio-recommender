"""포트폴리오 추천 서비스 (초안)

실행: streamlit run app.py
화면은 3개예요: 첫 화면(home) → 진단(quiz, 한 화면에 한 문항) → 결과(result)
계산은 모두 recommender.py 에 있고, 이 파일은 화면만 담당해요. 디자인은 assets/style.css.
"""
import importlib
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import recommender as rc

importlib.reload(rc)   # recommender.py 를 고쳐도 서버를 다시 켜지 않고 바로 반영되게

APP_NAME = '첫 포트폴리오'          # 서비스 이름 (팀에서 정하면 여기만 바꾸면 돼요)
COLOR = {'KBOND': '#2563eb', 'USD': '#12b76a', 'CASH': '#98a2b3', 'KOSPI200': '#f04438', 'SP500': '#7a5af8',
         'TOPIX': '#ee46bc', 'CSI300': '#f79009', 'EUROSTOXX50': '#06aed4', 'OIL': '#875bf7'}
GROUP_COLOR = {'채권·예금': '#2563eb', '주식': '#f04438', '대안투자': '#12b76a', '자산배분': '#7a5af8', '유동성': '#98a2b3'}
SHORT = {'KOSPI200': 'KODEX 200', 'SP500': 'TIGER 미국S&P500선물', 'TOPIX': 'TIGER 일본TOPIX', 'CSI300': 'TIGER 차이나CSI300',
         'EUROSTOXX50': 'TIGER 유로스탁스50', 'KBOND': 'KOSEF 통안채1년', 'OIL': 'TIGER 원유선물', 'USD': 'KOSEF 미국달러선물',
         'CASH': '현금 (CMA·예금)'}
DESC = {'KOSPI200': '국내 대형주 200', 'SP500': '미국 주식', 'TOPIX': '일본 주식', 'CSI300': '중국 주식',
        'EUROSTOXX50': '유럽 주식', 'KBOND': '국내 단기채권', 'OIL': '원유', 'USD': '미국 달러', 'CASH': '언제든 꺼내 쓸 돈'}
CODE = {v['name']: k for k, v in rc.ETF_INFO.items()}

st.set_page_config(page_title=APP_NAME, page_icon='📊', layout='wide', initial_sidebar_state='collapsed')
st.markdown(f"<style>{(Path(__file__).parent / 'assets' / 'style.css').read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True)


@st.cache_data
def get_data():
    prices = rc.load_prices()
    rets, avg_returns, cov_mat = rc.model_inputs(prices)
    return prices, rets, avg_returns, cov_mat


prices, rets, avg_returns, cov_mat = get_data()

# ── 화면 상태 ─────────────────────────────────────────────────────────
ss = st.session_state
ss.setdefault('page', 'home')
ss.setdefault('step', 0)                       # 진단: 0 = 투자 조건, 1~5 = 설문 문항
ss.setdefault('ans', [None] * len(rc.QUESTIONS))
ss.setdefault('budget', 10_000_000)
ss.setdefault('period', '1~3년')
N_STEPS = 1 + len(rc.QUESTIONS)


def go_page(page, step=0):
    ss.page, ss.step = page, step


def restart():
    ss.ans = [None] * len(rc.QUESTIONS)
    go_page('quiz', 0)


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def won(v):
    return f'{v / 1e8:,.1f}억원' if v >= 1e8 else f'{v / 1e4:,.0f}만원'


def card_title(title, desc):
    html(f'<h3 class="ct">{title}</h3><p class="cd">{desc}</p>')


# ── 공통: 상단 바 · 푸터 ───────────────────────────────────────────────
def nav():
    """상단 바: 로고를 누르면 어느 화면에서든 첫 화면으로 돌아가요. 메뉴도 누를 수 있어요."""
    done = None not in ss.ans
    with st.container(key='navbar', horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
        st.button(APP_NAME, key='nav_logo', on_click=go_page, args=('home',))
        with st.container(key='navmenu', horizontal=True, horizontal_alignment='right', width='content', gap='medium'):
            for label, page, step, enabled in [('서비스 소개', 'home', 0, True),
                                               ('투자성향 진단', 'quiz', 0, True),
                                               ('추천 결과', 'result', 0, done)]:
                st.button(label, key=f'nav_{page}', on_click=go_page, args=(page, step), disabled=not enabled,
                          type='primary' if ss.page == page else 'secondary')


def footer():
    html(f"""<div class="foot"><b>{APP_NAME}</b> · 데이터처리프로그래밍 기말 팀 프로젝트 (초안)<br>
    데이터: 국내 상장 ETF 8종 종가 ({prices.index[0]:%Y.%m.%d} ~ {prices.index[-1]:%Y.%m.%d}) · FinanceDataReader<br>
    교육용 시뮬레이션이며 투자 권유가 아니에요. 과거 수익률이 미래 수익을 보장하지 않아요.</div>""")


# ── 1. 첫 화면 ───────────────────────────────────────────────────────
def page_home():
    w, d, _ = rc.build_portfolio('성장형', cov_mat)
    perf = rc.performance(w, rets)
    bar = ''.join(f'<i style="width:{v * 100:.1f}%;background:{COLOR[n]}"></i>' for n, v in w.items())
    legend = ''.join(f'<div><span class="dot" style="background:{COLOR[n]}"></span>{DESC[n]}<b>{v:.0%}</b></div>'
                     for n, v in list(w.items())[:6])

    left, right = st.columns([1.1, 0.9], gap='large')
    with left:
        html("""<div class="hero"><span class="eyebrow">주식 처음 하는 사람을 위한 자산배분</span>
        <h1>처음 하는 투자,<br><em>무엇을 얼마나</em> 살지<br>3분이면 알려드려요</h1>
        <p class="sub">질문 5개에 답하면 투자 성향을 진단하고, 포트폴리오 이론으로
        국내 상장 ETF를 어떻게 나눠 담을지 금액과 수량까지 계산해 드려요.</p></div>""")
        c1, _ = st.columns([1, 1])
        c1.button('투자성향 진단 시작하기', type='primary', width='stretch', on_click=restart)
    with right:
        html(f"""<div class="hero-card">
        <div class="tags"><span>#균형성장</span><span>#글로벌분산</span><span>#위험균형</span></div>
        <div class="t">예시 · 성장형 · 1,000만원</div>
        <div class="v">연 {perf['return']:.1%} 기대</div>
        <div class="g">변동성 {perf['vol']:.1%} · 최대 낙폭 {perf['mdd']:.1%}</div>
        <div class="bar">{bar}</div><div class="legend">{legend}</div></div>""")

    html("""<div class="section-title"><div class="k">특징</div><h2>초보자도 이해할 수 있는 추천</h2></div>
    <div class="features">
      <div class="feature"><div class="ic">📝</div><h3>질문 5개로 성향 진단</h3>
        <p>투자 경험, 목적, 손실을 견디는 정도를 물어 안정형부터 공격형까지 4가지로 나눠요.</p></div>
      <div class="feature"><div class="ic">📐</div><h3>포트폴리오 이론으로 계산</h3>
        <p>최소분산·위험균형 모형으로 위험을 고르게 나눠요. 감이 아니라 공분산 행렬로 비중을 정해요.</p></div>
      <div class="feature"><div class="ic">🌏</div><h3>ETF 8종으로 세계 분산</h3>
        <p>한국·미국·일본·중국·유럽 주식과 채권, 달러, 원유를 1주 단위로 살 수 있게 알려드려요.</p></div>
    </div>
    <div class="section-title"><div class="k">추천 과정</div><h2>이렇게 추천해요</h2></div>
    <div class="steps">
      <div class="step"><div class="n">STEP 1</div><h4>조건 입력</h4><p>예산과 투자 기간을 정해요.</p></div>
      <div class="step"><div class="n">STEP 2</div><h4>성향 진단</h4><p>설문 점수로 4가지 성향 중 하나를 골라요. 기간이 짧으면 한 단계 보수적으로.</p></div>
      <div class="step"><div class="n">STEP 3</div><h4>자산 나누기</h4><p>성향별로 채권·주식·대안투자·현금 비율을 정해요.</p></div>
      <div class="step"><div class="n">STEP 4</div><h4>상품 비중 계산</h4><p>자산군 안에서 수업 모형으로 ETF 비중을 최적화해요.</p></div>
    </div>
    <div class="cta-band"><h3>내 성향에 맞는 포트폴리오를 확인해 보세요</h3><p>예산과 기간을 정하고 5문항에 답하면 돼요.</p></div>""")
    _, mid, _ = st.columns([1, 0.6, 1])
    mid.button('진단 시작하기', type='primary', width='stretch', on_click=restart, key='cta2')


# ── 2. 진단 화면 ─────────────────────────────────────────────────────
def save_answer(i):
    choice = ss.get(f'q{i}_w')
    if choice is not None:
        ss.ans[i] = rc.QUESTIONS[i][1].index(choice)
        ss.step += 1                            # 고르면 바로 다음 문항으로
        if ss.step == N_STEPS:
            ss.page = 'result'


def set_budget():
    ss.budget = int(ss.budget_w)


def pick_budget():
    preset = {'100만원': 1_000_000, '500만원': 5_000_000, '1,000만원': 10_000_000, '3,000만원': 30_000_000}
    if ss.get('budget_pill'):
        ss.budget = preset[ss.budget_pill]
        ss.budget_w = ss.budget


def set_period():
    ss.period = ss.period_w


def page_quiz():
    s = ss.step
    pct = (s + 1) / N_STEPS * 100
    if s == 0:
        title, sub, label = '투자 조건을 알려주세요', '예산을 바꿔도 추천 비율은 같아요. 금액과 수량만 달라져요.', '투자 조건'
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
            html('<div class="lbl">투자 기간</div>')
            with st.container(key='period'):
                st.radio('투자 기간', rc.PERIODS, index=rc.PERIODS.index(ss.period), key='period_w',
                         on_change=set_period, label_visibility='collapsed')
        else:
            i = s - 1
            q, options = rc.QUESTIONS[i]
            st.radio(q, options, index=ss.ans[i], key=f'q{i}_w', on_change=save_answer, args=(i,),
                     label_visibility='collapsed')

        st.write('')
        b1, b2 = st.columns(2)
        b1.button('이전', width='stretch',
                  on_click=(lambda: go_page('home')) if s == 0 else (lambda: go_page('quiz', s - 1)))
        if s == 0:
            b2.button('다음', type='primary', width='stretch', on_click=lambda: go_page('quiz', 1))
        else:
            answered = ss.ans[s - 1] is not None
            last = s == N_STEPS - 1
            b2.button('결과 보기' if last else '다음', type='primary', width='stretch', disabled=not answered,
                      on_click=(lambda: go_page('result')) if last else (lambda: go_page('quiz', s + 1)))


# ── 3. 결과 화면 ─────────────────────────────────────────────────────
def page_result():
    if None in ss.ans:
        go_page('quiz', ss.ans.index(None) + 1)
        st.rerun()

    judge = rc.judge_profile(ss.ans, ss.period)
    profile = judge['profile']
    weights, detail, sleeves = rc.build_portfolio(profile, cov_mat)
    perf = rc.performance(weights, rets)
    alloc = rc.allocate_budget(weights, prices, ss.budget)
    tags = rc.hashtags(profile, ss.period, weights, detail)
    model = rc.MODEL_BY_PROFILE[profile]

    note = (f'<div class="note">설문 결과는 {judge["base"]}이지만 투자 기간이 1년 미만이라 한 단계 보수적으로 추천했어요.</div>'
            if judge['adjusted'] else '')
    html(f"""<div class="res-hero">
      <div class="tags">{''.join(f'<span>{t}</span>' for t in tags)}</div>
      <div class="who">설문 점수 <b>{judge['score']}점</b> / 20점 · {ss.period} 투자</div>
      <h2>당신은 {profile} 투자자예요</h2>{note}
      <div class="kpis">
        <div class="kpi"><div class="l">총 투자금</div><div class="v">{won(ss.budget)}</div></div>
        <div class="kpi"><div class="l">예상 연수익률</div><div class="v up">{perf['return']:+.1%}</div></div>
        <div class="kpi"><div class="l">변동성 (위험)</div><div class="v">{perf['vol']:.1%}</div></div>
        <div class="kpi"><div class="l">최대 낙폭 (MDD)</div><div class="v down">{perf['mdd']:.1%}</div></div>
      </div></div>""")

    c1, c2 = st.columns([1, 1], gap='medium')
    with c1:
        with st.container(border=True):
            card_title('상품별 비중', '어떤 ETF를 얼마나 담는지')
            fig = go.Figure(go.Pie(labels=[SHORT[n] for n in weights.index], values=(weights * 100).round(1),
                                   hole=0.62, sort=False, marker=dict(colors=[COLOR[n] for n in weights.index],
                                                                       line=dict(color='#fff', width=2)),
                                   texttemplate='%{value:.0f}%', textfont=dict(size=12),
                                   hovertemplate='%{label}<br>%{value:.1f}%<extra></extra>'))
            fig.update_layout(height=400, margin=dict(t=10, b=10, l=10, r=10), showlegend=True,
                              legend=dict(font=dict(size=12), orientation='h', x=0.5, xanchor='center', y=-0.05),
                              paper_bgcolor='rgba(0,0,0,0)', font=dict(family='Pretendard'),
                              annotations=[dict(text=f'<b>{won(ss.budget)}</b>', showarrow=False,
                                                font=dict(size=17, color='#101828'))])
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    with c2:
        with st.container(border=True):
            card_title('자산군별 비중', f'{profile} 기준으로 자산을 나눈 비율')
            table = rc.PROFILE_TABLE[profile]
            rows = ''
            for g in rc.GROUPS:
                names = ', '.join(DESC[n] for n, v in sleeves[g].items() if v > 0.01)
                rows += (f'<div class="grow"><div class="top">{g}<span>{table[g]}%</span></div>'
                         f'<div class="track"><i style="width:{table[g]}%;background:{GROUP_COLOR[g]}"></i></div>'
                         f'<div class="sub">{names}</div></div>')
            html(f'<div class="groups">{rows}</div>')

    # 보유 목록
    body = ''
    for _, r in alloc.iterrows():
        name = next(n for n, lbl in rc.NAME_TO_LABEL.items() if lbl == r['상품'])
        cash = name == rc.CASH
        code = '' if cash else f' · {CODE[name]}'
        price = '' if cash else f'{r["현재가(원)"]:,.0f}원'
        qty = '' if cash else f'{r["수량(주)"]:,.0f}주'
        body += (f'<tr class="{"cash" if cash else ""}"><td><span class="dot" style="background:{COLOR[name]}"></span>'
                 f'<span class="nm">{SHORT[name]}</span><div class="sub">{DESC[name]}{code}</div></td>'
                 f'<td>{r["비중(%)"]:.1f}%</td><td class="amt">{r["금액(원)"]:,.0f}원</td><td>{price}</td><td>{qty}</td></tr>')
    with st.container(border=True):
        card_title('이렇게 사면 돼요', f'{prices.index[-1]:%Y.%m.%d} 종가 기준 · 1주 단위로 사고 남은 돈은 현금으로 둬요')
        html(f"""<div class="hold-wrap"><table class="holdings"><thead><tr><th>상품</th><th>목표 비중</th><th>금액</th>
        <th>현재가</th><th>수량</th></tr></thead><tbody>{body}</tbody></table></div>""")

    # 과거 성과: 예금처럼 안전한 단기채권에만 넣었을 때와 비교
    safe = rc.safe_index(rets)
    start = perf['index'].index[0]
    end_pf, end_safe = ss.budget * perf['index'].iloc[-1] / 100, ss.budget * safe.iloc[-1] / 100
    with st.container(border=True):
        card_title(f'{rc.LOOKBACK_YEARS}년 전에 이 비중으로 시작했다면?',
                   f'{start:%Y.%m}부터 지금까지 · 예금처럼 안전한 단기채권(통안채)에만 넣었을 때와 비교')
        fig3 = go.Figure()
        fig3.add_scatter(x=safe.index, y=ss.budget * safe / 100 / 1e4, name='단기채권만 (예금 수준)',
                         line=dict(color='#98a2b3', width=2, dash='dot'),
                         hovertemplate='%{y:,.0f}만원<extra>단기채권만</extra>')
        fig3.add_scatter(x=perf['index'].index, y=ss.budget * perf['index'] / 100 / 1e4, name='추천 포트폴리오',
                         line=dict(color='#2563eb', width=3), fill='tonexty', fillcolor='rgba(37,99,235,.08)',
                         hovertemplate='%{y:,.0f}만원<extra>추천 포트폴리오</extra>')
        fig3.update_layout(height=300, margin=dict(t=10, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)',
                           plot_bgcolor='rgba(0,0,0,0)', font=dict(family='Pretendard', color='#475467'),
                           legend=dict(orientation='h', y=1.12, x=0), hovermode='x unified',
                           yaxis=dict(gridcolor='#f2f4f7', tickformat=',.0f', ticksuffix='만원'),
                           xaxis=dict(showgrid=False))
        st.plotly_chart(fig3, width='stretch', config={'displayModeBar': False})
        html(f"""<div class="compare">
          <div><span>추천 포트폴리오</span><b>{won(ss.budget)} → {won(end_pf)}</b><em class="up">{end_pf / ss.budget - 1:+.1%}</em></div>
          <div><span>단기채권만 (예금 수준)</span><b>{won(ss.budget)} → {won(end_safe)}</b><em>{end_safe / ss.budget - 1:+.1%}</em></div>
          <div><span>가장 크게 떨어졌을 때</span><b>약 {won(abs(perf['mdd']) * ss.budget)} 손실</b><em class="down">{perf['mdd']:.1%}</em></div>
        </div>""")

    # 추천 근거: 사용자가 이해할 수 있는 말로
    t = rc.PROFILE_TABLE[profile]
    topics = ['투자 경험', '투자 목적', '10% 떨어지면', '견딜 수 있는 손실', '전체 재산 중 비중']
    picked = ''.join(f'<li><span>{topics[i]}</span>{rc.QUESTIONS[i][1][a]} <em>{a + 1}점</em></li>'
                     for i, a in enumerate(ss.ans))
    ranges = {'안정형': '5∼8점', '안정성장형': '9∼12점', '성장형': '13∼16점', '공격형': '17∼20점'}
    why_split = {
        '안정형': '원금을 지키는 게 가장 중요한 성향이라 대부분을 채권·예금에 두고, 주식은 5%만 담아요.',
        '안정성장형': '안정이 먼저지만 예금보다는 조금 더 벌 수 있게, 채권을 줄이고 대안투자와 자산배분 상품을 섞어요.',
        '성장형': '수익과 안정의 균형을 맞추려고 채권·주식·대안투자를 비슷한 크기로 나눠요.',
        '공격형': '높은 수익을 위해 주식을 가장 많이 담고, 채권은 10%로 줄여요.',
    }[profile]
    vol = pd.Series(np.sqrt(np.diag(cov_mat)), index=cov_mat.index)   # 상품별 연 변동성
    alt = sleeves['대안투자']
    if model == 'MVP':
        why_weight = ('전체 가격이 가장 덜 흔들리는 조합을 찾았어요. 덜 흔들리는 상품을 많이 담고, '
                      '서로 반대로 움직이는 상품을 섞어 흔들림을 줄여요.')
    else:
        why_weight = ('모든 상품이 전체 위험을 똑같이 나눠 지도록 했어요. 많이 흔들리는 상품은 적게, '
                      '덜 흔들리는 상품은 많이 담아요.')
    why_weight += (f' 예를 들어 대안투자에서 원유(1년 변동성 {vol["OIL"]:.0%})는 {alt["OIL"]:.0%}, '
                   f'달러(변동성 {vol["USD"]:.0%})는 {alt["USD"]:.0%}를 담았어요.')
    note_short = ' 투자 기간이 1년 미만이라 한 단계 보수적으로 바꿨어요.' if judge['adjusted'] else ''

    html(f"""<div class="section-title left"><div class="k">추천 근거</div><h2>왜 이렇게 추천했나요?</h2></div>
    <div class="how">
      <div><b>왜 {profile}인가요?</b>
        <ul class="picked">{picked}</ul>
        <p>보수적인 답일수록 낮은 점수(1∼4점)를 매겨 더하면 <strong>{judge['score']}점</strong>이에요. {ranges[judge['base']]}이면 {judge['base']}이에요.{note_short}</p></div>
      <div><b>왜 이렇게 나눴나요?</b>
        <p>{why_split}</p>
        <p>채권·예금 {t['채권·예금']}% · 주식 {t['주식']}% · 대안투자 {t['대안투자']}% · 자산배분 {t['자산배분']}% · 현금 {t['유동성']}%. 투자성향별 추천 자산배분표(법률신문, 신한 PB 기고)를 기준으로 했어요.</p></div>
      <div><b>왜 이 ETF를 이만큼 담나요?</b>
        <p>{why_weight}</p></div>
      <div><b>숫자는 어떻게 읽나요?</b>
        <p><strong>예상 연수익률 {perf['return']:.1%}</strong>: 최근 {rc.LOOKBACK_YEARS}년 동안 이 비중이었다면 1년에 평균 이만큼 늘었어요.</p>
        <p><strong>변동성 {perf['vol']:.1%}</strong>: 1년 수익률이 평균에서 보통 이 정도 오르내려요. 클수록 위험해요.</p>
        <p><strong>최대 낙폭 {perf['mdd']:.1%}</strong>: 가장 나빴던 때 고점에서 이만큼 떨어졌어요.</p></div>
    </div>""")
    with st.expander('계산 방법 자세히 보기 (수업 내용)'):
        st.markdown(f"""
- **기대수익률·공분산**: 최근 {rc.LOOKBACK_YEARS}년 일간수익률(`pct_change`)의 평균 × 240, 공분산 행렬 × 240 (연율화)
- **포트폴리오 변동성**: √(wᵀΣw)
- **{rc.MODEL_NAME[model]}**: `scipy.optimize.minimize(method='SLSQP')`, 비중 합 = 1, 0 ≤ 비중 ≤ 1 (공매도 없음)
  {'· 목표: 변동성 √(wᵀΣw) 최소화' if model == 'MVP' else '· 목표: 위험기여도 RCᵢ = wᵢ × (Σw)ᵢ / σₚ 를 모든 상품에서 σₚ / n 으로 같게'}
- **자산배분 몫**: 8종 전체를 위험균형으로 섞은 묶음
- **지표**: 연수익률 = 일간 평균 × 240, 변동성 = 일간 표준편차 × √240, MDD = 누적성과 ÷ 그때까지 최고점 − 1 의 최솟값
""")
        rows = [{'자산군': g, '상품': SHORT[n], '자산군 안 비중': f'{w:.1%}'}
                for g, s in sleeves.items() for n, w in s.items() if w > 0.0005]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')

    st.write('')
    _, b1, b2, b3, _ = st.columns([0.5, 0.7, 0.7, 0.7, 0.5])
    b1.button('처음 화면으로', width='stretch', on_click=go_page, args=('home',), key='res_home')
    b2.button('조건 바꾸기', width='stretch', on_click=lambda: go_page('quiz', 0))
    b3.button('처음부터 다시 진단', type='primary', width='stretch', on_click=restart)


def scroll_top():
    """화면(페이지·문항)이 바뀌면 맨 위로 올려요"""
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
{'home': page_home, 'quiz': page_quiz, 'result': page_result}[ss.page]()
footer()
