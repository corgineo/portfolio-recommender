"""팀원 통합 + TODO 4·5·6 회귀 검증

실행: uv run --no-project --python .venv/bin/python --with pytest pytest -q tests
"""
import random
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import recommender as rc                    # noqa: E402
import c_integration as ci                  # noqa: E402
import company_financials as cf             # noqa: E402
from portfolio_core import allocate         # noqa: E402
from portfolio_editor import cap_value, nav_compare_figure, group_compare_figure   # noqa: E402

BUDGETS = [100_000, 1_000_000, 10_000_000]


@pytest.fixture(scope='module')
def data():
    prices = rc.load_prices(with_stocks=True, with_candidates=True)
    rets, _, cov = rc.model_inputs(prices)
    return prices, rets, cov


# ── TODO4: 설문 7문항 ────────────────────────────────────────────────
def answers_for(score):
    """점수 score(0~28)가 나오는 답 (①=4점 … ⑤=0점)"""
    ans, left = [], score
    for _ in range(7):
        p = min(4, left)
        ans.append(4 - p)
        left -= p
    return ans


def test_seven_questions_five_options():
    assert len(rc.QUESTIONS) == 7
    assert all(len(opts) == 5 for _, opts in rc.QUESTIONS)
    assert rc.QUESTIONS[1][0] == '당신의 투자 기간은?'
    assert rc.POINTS == [4, 3, 2, 1, 0] and rc.MAX_SCORE == 28
    assert not hasattr(rc, 'PERIODS')                   # 별도 기간 질문 제거


@pytest.mark.parametrize('score,profile,kind', [
    (0, '안정형', '안정 추구형'), (10, '안정형', '안정 추구형'),
    (11, '안정성장형', '위험 중립형'), (17, '안정성장형', '위험 중립형'),
    (18, '성장형', '위험 중립형'), (24, '성장형', '위험 중립형'),
    (25, '공격형', '공격 추구형'), (28, '공격형', '공격 추구형')])
def test_score_boundaries(score, profile, kind):
    j = rc.judge_profile(answers_for(score))
    assert j['score'] == score and j['profile'] == profile and j['type'] == kind


def test_period_from_question2_without_downgrade():
    ans = [0] * 7
    ans[1] = 4                                          # 1년 이내
    j = rc.judge_profile(ans)
    assert j['period'] == '1년 이내' and j['short_term']
    assert j['score'] == 24 and j['profile'] == '성장형'   # 예전처럼 한 단계 낮추지 않아요


@pytest.mark.parametrize('bad', [[0] * 6, [0] * 6 + [None], [0] * 6 + [5]])
def test_invalid_answers(bad):
    with pytest.raises(ValueError):
        rc.judge_profile(bad)


# ── TODO1~3 팀 core 유지: 성향 4 × 예산 3 ──────────────────────────────
@pytest.mark.parametrize('profile', rc.PROFILES)
@pytest.mark.parametrize('budget', BUDGETS)
def test_team_core_recommendation(data, profile, budget):
    prices, rets, cov = data
    picks = rc.choose_picks(profile, prices, budget)
    total = rc.PROFILE_TABLE[profile]['주식'] / 100 * rc.STOCK_SHARE
    n = min(rc.MAX_STOCKS, int(total / rc.MIN_WEIGHT + 1e-9))
    assert len(picks) <= n <= rc.MAX_STOCKS
    if profile == '안정형':
        assert picks == []                              # 주식 5% → 개별 종목 0개
    last = prices.ffill().iloc[-1]
    for p in picks:                                     # 예산으로 1주 이상 살 수 있는 종목만
        assert last[p] <= budget * total / n
    w, detail, sleeves = rc.build_portfolio(profile, cov, picks)
    assert abs(w.sum() - 1) < 1e-9
    assert len(w) - 1 <= 30
    g = detail.groupby('group')['weight'].sum()
    for grp in rc.GROUPS:                               # 자산군 비중 = 성향표
        assert abs(g.get(grp, 0) - rc.PROFILE_TABLE[profile][grp] / 100) < 1e-6
    if picks:                                           # 주식 몫의 절반 = 개별 종목 (같은 비중)
        assert abs(w[picks].sum() - total) < 1e-6
        assert np.allclose(w[picks], total / len(picks))
    for grp, sl in sleeves.items():                     # 3% 최소 비중 (자산군에 상품이 하나만 남으면 예외, 팀 규칙)
        if grp != '유동성' and len(sl) > 1:
            final = sl * rc.PROFILE_TABLE[profile][grp] / 100
            assert (final >= rc.MIN_WEIGHT - 1e-9).all(), (grp, final)
    alloc = rc.allocate_budget(w, prices, budget)
    stocks = alloc.iloc[:-1]
    assert (stocks['금액(원)'] <= budget * stocks['비중(%)'] / 100 + 1e-6).all()
    assert (stocks['수량(주)'] == stocks['수량(주)'].astype(int)).all()
    assert 0 <= alloc['금액(원)'].iloc[-1] <= budget
    assert abs(alloc['금액(원)'].sum() - budget) < 1e-6


def test_team_core_matches_baseline(data):
    """팀원 core 추천 12조건(성향 4 × 예산 3)이 통합 전 기준값과 같아요"""
    import json
    base = json.loads((ROOT / 'tests' / 'data' / 'team_core_baseline.json').read_text(encoding='utf-8'))
    prices, _, cov = data
    assert len(base) == 12
    for k, v in base.items():
        profile, budget = k.split(':')
        picks = rc.choose_picks(profile, prices, int(budget))
        assert picks == v['picks'], k
        w, _, _ = rc.build_portfolio(profile, cov, picks)
        assert set(w.index) == set(v['weights']), k
        for n, x in v['weights'].items():
            assert w[n] == pytest.approx(x, abs=1e-9), (k, n)


def test_products_codes_are_strings():
    p = pd.read_csv(ROOT / 'data' / 'products.csv', dtype=str)
    assert {'069500', '005930', '000660', 'NVDA'} <= set(p['code'])
    assert {'005930', '000660', '028260'} <= set(rc.STOCK_CATALOG['code'])


def test_no_lookahead_fill_before_listing(data):
    prices = data[0]
    raw = pd.read_csv(ROOT / 'data' / 'stock_kr.csv', index_col=0, parse_dates=True)
    col = rc.STOCK_CATALOG.index[rc.STOCK_CATALOG['code'] == '373220'][0]      # LG에너지솔루션 2022-01 상장
    first = raw[col].first_valid_index()
    assert prices.ffill().loc[:first, col].iloc[:-1].isna().all()


# ── 통합 버그: compare_target_weights 코드 → 열 이름 매핑 ─────────────────
def _editor_frames(prices, weights, edit=None):
    prices_f, assets, rec = ci.editor_inputs(prices, weights)
    mine = dict(rec)
    for k, v in (edit or {}).items():
        mine[k] = v
    base, bc = allocate(assets, rec, 1_000_000)
    edited, ec = allocate(assets, mine, 1_000_000)
    return prices_f, base, edited, bc, ec


@pytest.mark.parametrize('profile', ['안정형', '공격형'])
def test_compare_uses_etf_columns(data, profile):
    prices, _, cov = data
    picks = rc.choose_picks(profile, prices, 10_000_000)
    w, _, _ = rc.build_portfolio(profile, cov, picks)
    pf, base, edited, bc, ec = _editor_frames(prices, w, {'069500': 0.0})
    out = ci.compare_target_weights(pf, base, edited, bc, ec, 1_000_000)
    m = out['metrics']
    assert list(m.index) == ['추천안', '내 구성'] and m.notna().all().all()
    assert out['nav'].iloc[0].eq(100).all()
    # 추천안 곡선이 recommender.performance 와 같은 비중·같은 수익률을 쓰는지 (ETF 열이 빠지면 달라져요)
    perf = rc.performance(w, pf.loc[out['start']:].pct_change(fill_method=None).iloc[1:])
    assert abs(m.loc['추천안', '연환산 수익률 (%)'] - perf['return'] * 100) < 1e-6


def test_old_mapping_bug_would_drop_etfs():
    used = {'069500', 'INVENI'}
    old = {**ci._code_to_name(), **{t: t for t in used}}
    new = {**{t: t for t in used}, **ci._code_to_name()}
    assert old['069500'] == '069500' and new['069500'] == 'KOSPI200' and new['INVENI'] == 'INVENI'


# ── 편집기 100% 상한 ──────────────────────────────────────────────────
def test_cap_value_random():
    rnd = random.Random(0)
    for _ in range(3000):
        n = rnd.randint(1, 12)
        vals = {str(i): rnd.uniform(0, 100) / n for i in range(n)}
        t = str(rnd.randrange(n))
        vals[t] = rnd.uniform(0, 100)
        vals[t] = cap_value(t, vals)
        assert sum(vals.values()) <= 100 + 1e-9 or sum(v for k, v in vals.items() if k != t) > 100
        assert vals[t] >= 0


# ── 기업 재무 단위 ────────────────────────────────────────────────────
def test_financial_units_and_ratios():
    d = cf.load_financials(cf.CSV_PATH)
    assert cf.to_eok(100_000) == 1.0                    # 10만 천원 = 1억원
    raw = pd.read_csv(cf.CSV_PATH, dtype=str)
    r = raw[(raw['종목코드'] == 'A005930') & (raw['회계연도'] == '2025')].iloc[0]
    t = cf.company_table(d, '005930')
    last = t.iloc[-1]
    assert int(last['사업연도']) == 2025
    assert abs(last['매출액'] - float(r['매출액']) / 1e5) < 1e-6
    assert abs(last['부채비율(%)'] - float(r['부채총계']) / float(r['자본총계']) * 100) < 1e-6
    assert len(t) == cf.YEARS
    assert cf.company_table(d, 'NVDA') is None          # 미국 기업 재무 없음 → 지어내지 않음
    assert cf.fmt(np.nan) == '자료 없음'


# ── 화면 흐름 (AppTest) ───────────────────────────────────────────────
EDU_WORDS = ['강의', '수업', '과제', '공분산', 'SLSQP', 'scipy', '교육용', '구현']
BANMAL = re.compile(r'(해 줘|이야\.|했어\.|있어\.|없어\.|넘었어|줘\.)')


def _texts(at):
    out = [m.value for m in at.markdown] + [c.value for c in at.caption] + [b.label for b in at.button]
    out += [e.label for e in at.expander] + [w.value for w in at.warning] + [i.value for i in at.info]
    return '\n'.join(out)


@pytest.fixture
def app():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=120)
    at.run()
    return at


def test_flow_quiz_result_build_company(app):
    at = app
    assert not at.exception
    at.button(key='home_start').click().run()
    assert at.session_state['page'] == 'quiz' and at.session_state['step'] == 0
    at.number_input(key='budget_w').set_value(100_000).run()
    at.button(key='quiz_next').click().run()
    for i in range(7):                                  # 한 화면 한 질문, 고르면 다음으로
        assert len(at.radio) == 1
        at.radio(key=f'q{i}_w').set_value(2).run()
    assert at.session_state['page'] == 'result' and not at.exception
    text = _texts(at)
    assert '위험 중립형 투자자' in text and '성장형' in text   # 2점 × 7 = 14점 → 안정성장형 배분
    assert '나만의 포트폴리오 제작하기' in text and '직접 바꿔보며' not in text
    assert '2026.11.13 종가 기준' in text
    for w in EDU_WORDS:
        assert w not in text, w
    assert not BANMAL.search(text)
    at.button(key='to_mock_top').click().run()
    assert at.session_state['page'] == 'mock' and not at.exception
    text = _texts(at)
    assert not at.error and '과거 성과를 계산하지 못했어요' not in text
    assert any('class="mtab"' in m.value for m in at.markdown)   # 성과 비교 지표 표
    for w in EDU_WORDS:
        assert w not in text, w
    assert not BANMAL.search(text)
    at.button(key='nav_company').click().run()
    assert at.session_state['page'] == 'company' and not at.exception
    assert '단위 억원' in _texts(at)


EK = 'existing_recommendation_c'


def _mock(at, score=26, budget=10_000_000):
    at.session_state['ans'] = answers_for(score)
    at.session_state['budget'] = budget
    at.session_state['page'] = 'mock'
    at.run()
    assert not at.exception
    return at


def _model(at):
    return at.session_state[f'{EK}_model']['w']


def _rows(at):
    """지금 화면에 그려진 편집 행: 코드 → (슬라이더, 숫자 입력)"""
    sl = {s.key[len(f'{EK}_s_'):]: s for s in at.slider if s.key.startswith(f'{EK}_s_')}
    nb = {n.key[len(f'{EK}_n_'):]: n for n in at.number_input if n.key and n.key.startswith(f'{EK}_n_')}
    assert set(sl) == set(nb)
    return {t: (sl[t], nb[t]) for t in sl}


def _show(at, t):
    """상품 t 의 행이 보이도록 그 자산 종류 필터로 가고, 필요하면 '더 보기'를 눌러요"""
    _filter(at, rc.ETF_INFO[t]['group'] if t in rc.ETF_INFO else '주식')
    while t not in _rows(at):
        at.button(key=f'{EK}_more').click().run()
    return _rows(at)[t]


def _filter(at, f):
    at.segmented_control(key=f'{EK}_filter').set_value(f).run()
    assert not at.exception


def test_editor_multi_rows_and_filters(app):
    at = _mock(app)                                       # 공격형 1,000만원: 추천 상품 20개
    rows = _rows(at)
    assert len(rows) == 5                                 # 한 번에 5행 (슬라이더 + 숫자 입력)
    assert not any(s.key.endswith('_pick') for s in at.selectbox)   # 드롭다운 1종목 방식 아님
    w = _model(at)
    n_listed = sum(1 for v in w.values() if v > 0)
    at.button(key=f'{EK}_more').click().run()
    assert len(_rows(at)) == 10
    group = lambda t: rc.ETF_INFO[t]['group'] if t in rc.ETF_INFO else '주식'   # noqa: E731
    for f in ['채권·예금', '주식', '대안투자', '자산배분']:   # 자산 종류 필터: 그 종류만, 추천 상품 수만큼
        _filter(at, f)
        rows = _rows(at)
        assert rows and all(group(t) == f for t in rows), f
        assert len(rows) == min(5, sum(1 for t, v in w.items() if v > 0 and group(t) == f))
    assert n_listed >= 15


def test_editor_slider_number_sync_and_live_compare(app):
    at = _mock(app)
    t, (sl, nb) = next(iter(_rows(at).items()))
    nb.set_value(12.34).run()                             # 숫자 입력 → 슬라이더·model 동기화
    assert _model(at)[t] == pytest.approx(12.34)
    assert _rows(at)[t][0].value == pytest.approx(12.34)
    _rows(at)[t][0].set_value(7.5).run()                 # 슬라이더 → 숫자 입력 동기화
    assert _model(at)[t] == pytest.approx(7.5) and _rows(at)[t][1].value == pytest.approx(7.5)
    # 비교 패널(구성 차이 목록·과거 성과 표)이 같은 실행에서 바로 바뀌어요
    md = '\n'.join(m.value for m in at.markdown)
    assert 'class="changes one"' in md and 'class="mtab"' in md
    assert not any('과거 성과를 계산하지 못했어요' in w.value for w in at.warning)


def test_editor_multi_edit_persists_across_filters_and_pages(app):
    at = _mock(app)
    rows = list(_rows(at))
    a_, b_ = rows[0], rows[1]
    _rows(at)[a_][1].set_value(1.5).run()
    _rows(at)[b_][1].set_value(2.25).run()               # 여러 행을 이어서 편집
    w0 = dict(_model(at))
    _filter(at, '대안투자')                                 # 다른 필터로 가면 위 행 위젯은 지워져요
    _filter(at, '전체')
    assert _rows(at)[a_][1].value == pytest.approx(1.5) and _rows(at)[b_][0].value == pytest.approx(2.25)
    at.session_state['page'] = 'result'
    at.run()
    at.session_state['page'] = 'mock'
    at.run()
    assert _model(at) == w0                                # 페이지 왕복 뒤에도 그대로
    assert _rows(at)[a_][1].value == pytest.approx(1.5)


def test_editor_cap_reset_extra_budget(app):
    at = _mock(app)
    rec = dict(_model(at))
    t = max(rec, key=rec.get)
    others = sum(v for k, v in rec.items() if k != t)
    before = dict(_model(at))
    _show(at, t)[1].set_value(100.0).run()               # 남은 한도까지만, 다른 상품은 그대로
    w = _model(at)
    assert w[t] == pytest.approx(100 - others) and sum(w.values()) <= 100 + 1e-6
    assert all(w[k] == before[k] for k in w if k != t)
    assert _rows(at)[t][0].value == pytest.approx(100 - others)
    assert any('100%를 넘지 않도록' in i.value for i in at.info)
    # 추천에 없던 ETF 더하기 → 0%로 목록에 들어오고, 다른 상품을 줄여야 담을 수 있어요
    new = next(k for k, v in rec.items() if v == 0)
    at.multiselect(key=f'{EK}_extra').set_value([new]).run()
    assert new in at.session_state[f'{EK}_model']['extra'] and _model(at)[new] == 0
    _show(at, t)[1].set_value(0.0).run()
    _show(at, new)[1].set_value(5.0).run()
    assert _model(at)[new] == pytest.approx(5.0) and sum(_model(at).values()) <= 100 + 1e-6
    at.number_input(key=f'{EK}_budget').set_value(3_000_000).run()      # 예산 바꿔도 비중 유지
    assert _model(at)[new] == pytest.approx(5.0)
    at.button(key=f'{EK}_reset').click().run()
    assert _model(at) == rec and at.session_state[f'{EK}_model']['extra'] == []


def _won(text):
    """'1억 2,300만 50원' → 123000050"""
    m = re.fullmatch(r'(?:(\d[\d,]*)억\s*)?(?:(\d[\d,]*)만\s*)?(?:(\d[\d,]*)원)?', text.strip())
    assert m, text
    eok, man, one = (int((g or '0').replace(',', '')) for g in m.groups())
    return eok * 100_000_000 + man * 10_000 + one


def _budget_shown(at):
    """예산 입력값 · model 예산 · 요약 카드(실제로 사는 돈 + 남는 현금)로 거꾸로 계산한 예산"""
    md = '\n'.join(m.value for m in at.markdown)
    spent = _won(re.search(r'<span>실제로 사는 돈</span><b>([^<]+)</b>', md).group(1))
    cash = _won(re.search(r'<span>남는 현금</span><b>([^<]+)</b>', md).group(1))
    return at.number_input(key=f'{EK}_budget').value, at.session_state[f'{EK}_model']['budget'], spent + cash


def test_editor_budget_persists_across_pages(app):
    at = _mock(app, score=0)                               # 기본 생성: 설문 예산 1,000만원
    assert _budget_shown(at) == (10_000_000,) * 3
    at.number_input(key=f'{EK}_budget').set_value(12_300_000).run()
    assert _budget_shown(at) == (12_300_000,) * 3
    t = next(iter(_rows(at)))
    _rows(at)[t][1].set_value(1.25).run()
    w0 = dict(_model(at))
    for page in ['company', 'result']:                     # 다른 페이지에 다녀와도 입력값·계산 모두 유지
        at.session_state['page'] = page
        at.run()
        at.session_state['page'] = 'mock'
        at.run()
        assert not at.exception
        assert _budget_shown(at) == (12_300_000,) * 3, page
        assert _model(at) == w0
    at.number_input(key=f'{EK}_budget').increment().run()  # +/− 버튼도 같은 값으로 계산
    assert _budget_shown(at) == (12_310_000,) * 3
    md = '\n'.join(m.value for m in at.markdown)          # 모바일 하단 요약: 변경 1개 + 같은 페이지 비교 패널 링크
    assert 'class="mob-sum"' in md and '변경 <b>1개</b>' in md and 'href="#cmp-view"' in md and 'id="cmp-view"' in md
    at.button(key=f'{EK}_reset').click().run()             # 되돌리기는 비중만, 직접 정한 예산은 유지
    assert _budget_shown(at) == (12_310_000,) * 3
    at.session_state['budget'] = 5_000_000                 # 설문 예산(기본 예산)이 바뀌면 새 기본 예산으로
    at.run()
    assert _budget_shown(at) == (5_000_000,) * 3


# ── 비교 그래프: 원래 추천안(고정 기준선) vs 내 수정안 ─────────────────────
def test_compare_figures_pure():
    idx = pd.date_range('2024-01-01', periods=4)
    nav = pd.DataFrame({'추천안': [100, 101, 99.5, 102], '내 구성': [100, 103, 98, 104.25]}, index=idx)
    fig = nav_compare_figure(nav)
    rec, mine = fig.data
    assert (rec.name, mine.name) == ('원래 추천안', '내 수정안')
    assert rec.line.dash == 'dot' and mine.line.dash is None and rec.line.color != mine.line.color
    assert list(rec.y) == [100, 101, 99.5, 102] and list(mine.y) == [100, 103, 98, 104.25]   # 값은 그대로 옮기기만
    same = nav_compare_figure(nav.assign(**{'내 구성': nav['추천안']}))
    assert list(same.data[0].y) == list(same.data[1].y)
    g = group_compare_figure(pd.Series({'주식': 60.0, '유동성': 40.0}), pd.Series({'주식': 30.0, '채권·예금': 70.0}))
    bars = {b.name: list(b.x) for b in g.data}
    assert list(g.data[0].y) == ['내 수정안', '원래 추천안']
    assert bars['주식'] == [30.0, 60.0] and bars['채권'] == [70.0, 0.0] and bars['현금'] == [0.0, 40.0]


def _charts(at):
    """비교 패널 그래프 두 개: (선 그래프 {이름: y}, 막대 {자산 종류: [내 수정안, 원래 추천안]})"""
    import json
    nav, bar = None, None
    for c in at.get('plotly_chart'):
        data = json.loads(c.proto.spec)['data']
        names = [d.get('name') for d in data]
        if names == ['원래 추천안', '내 수정안'] and data[0].get('mode') == 'lines':
            nav = {d['name']: d['y'] for d in data}
        elif data and data[0].get('type') == 'bar' and data[0].get('y') == ['내 수정안', '원래 추천안']:
            bar = {d['name']: d['x'] for d in data}
    assert nav is not None and bar is not None, '비교 그래프 두 개가 탭 없이 그려져야 해요'
    return nav, bar


def test_compare_chart_baseline_fixed_and_mine_moves(app):
    at = _mock(app)
    nav0, bar0 = _charts(at)
    assert nav0['원래 추천안'] == nav0['내 수정안']                 # 처음에는 같은 비중 → 두 선이 겹쳐요
    assert all(v[0] == v[1] for v in bar0.values())
    assert '두 선이 겹쳐 보여요' in '\n'.join(m.value for m in at.markdown)
    rec = dict(_model(at))
    t = max(rec, key=rec.get)
    _show(at, t)[1].set_value(0.0).run()                          # 실제 수치를 크게 바꿔요
    nav1, bar1 = _charts(at)
    assert nav1['원래 추천안'] == nav0['원래 추천안']              # 기준선(원래 추천안)은 그대로
    assert [v[1] for v in bar1.values()] == [v[1] for v in bar0.values()]
    assert nav1['내 수정안'] != nav0['내 수정안']                  # 내 수정안 선만 바뀌어요
    assert max(abs(a - b) for a, b in zip(nav1['내 수정안'], nav1['원래 추천안'])) > 0.01
    _show(at, t)[1].set_value(100.0).run()                        # 100% 한도로 잘려도 기준선은 그대로
    others = sum(v for k, v in rec.items() if k != t)
    assert _model(at)[t] == pytest.approx(100 - others) and sum(_model(at).values()) <= 100 + 1e-6
    assert _charts(at)[0]['원래 추천안'] == nav0['원래 추천안']
    at.number_input(key=f'{EK}_budget').set_value(12_300_000).run()   # 예산을 바꿔도 비중 기준 선은 그대로
    assert _charts(at)[0]['원래 추천안'] == nav0['원래 추천안']
    at.session_state['page'] = 'result'                           # 페이지 왕복 뒤에도 같은 기준선
    at.run()
    at.session_state['page'] = 'mock'
    at.run()
    assert _charts(at)[0]['원래 추천안'] == nav0['원래 추천안']
    assert at.number_input(key=f'{EK}_budget').value == 12_300_000
    at.button(key=f'{EK}_reset').click().run()                    # 되돌리면 다시 같은 선
    nav2, _ = _charts(at)
    assert nav2['원래 추천안'] == nav0['원래 추천안'] == nav2['내 수정안']


def test_editor_signature_change_resets(app):
    at = _mock(app, score=26)
    t = next(iter(_rows(at)))
    _rows(at)[t][1].set_value(0.0).run()
    at = _mock(at, score=5)                                # 성향이 바뀌면 새 추천으로 다시 시작
    w = _model(at)
    assert sum(w.values()) == pytest.approx(90, abs=1e-6)  # 현금 10% 제외 전부 추천 비중


def test_product_donut_includes_cash(app):
    import json
    at = app
    at.session_state['ans'] = answers_for(0)
    at.session_state['budget'] = 1_000_000
    at.session_state['page'] = 'result'
    at.run()
    spec = json.loads(at.get('plotly_chart')[0].proto.spec)['data'][0]
    assert '현금' in spec['labels']
    assert sum(spec['values']) == pytest.approx(100, abs=0.5)
    i = spec['labels'].index('현금')
    assert spec['marker']['colors'][i] == rc.GROUP_BASE['유동성']
    text = _texts(at)
    assert '개별 종목 없이 ETF만' in text and '하나만 남으면' in text   # 안정형: 성향 조건 + 3% 예외 설명


def test_no_picks_due_to_budget_explained(app):
    at = app
    at.session_state['ans'] = answers_for(28)
    at.session_state['budget'] = 100_000
    at.session_state['page'] = 'result'
    at.run()
    text = _texts(at)
    prices = rc.load_prices(with_stocks=True, with_candidates=True)
    picks = rc.choose_picks('공격형', prices, 100_000)
    slots = min(rc.MAX_STOCKS, int(0.44 * rc.STOCK_SHARE / rc.MIN_WEIGHT + 1e-9))   # 공격형 7개
    if not picks:
        assert '1주 가격보다 작아 개별 종목을 담지 못했어요' in text
    else:
        assert f'개별 종목 {len(picks)}개' in text
        if len(picks) < slots:                             # 소액이라 일부만: 성향 탓이 아니라 예산 탓이라고 설명
            assert f'{slots}개 대신 {len(picks)}개만' in text
    assert '이 성향은 주식 비중' not in text


def _biz(at):
    return [m.value for m in at.markdown if 'class="biz' in m.value]


def test_company_us_stock_profile_without_financials(app):
    at = app
    at.session_state['ans'] = answers_for(28)
    at.session_state['budget'] = 10_000_000
    at.session_state['company_pick'] = 'NVDA'
    at.session_state['page'] = 'company'
    for _ in range(2):                                     # 다시 그려도 국내 다른 회사로 바뀌지 않아요
        at.run()
        assert not at.exception
        assert at.selectbox(key='company_financials_ticker').value == 'NVDA'
        assert any('엔비디아' in m.value and 'fin-head' in m.value for m in at.markdown)
        biz = _biz(at)
        assert biz and 'GPU' in biz[0] and 'nvidia.com' in biz[0] and '2026-11-14' in biz[0]
        assert any('재무 자료가 아직 없어요' in i.value for i in at.info)
        assert not at.get('plotly_chart')                  # 미국 재무를 만들지 않아요
    text = _texts(at)
    assert '천원' not in text and 'data/' not in text


def test_company_unknown_code_stays_no_data(app):
    at = app
    at.session_state['company_pick'] = '없는종목'
    at.session_state['page'] = 'company'
    for _ in range(2):
        at.run()
        assert any('기업 소개와 재무 자료가 없어요' in w.value for w in at.warning)
        assert not at.selectbox and not at.get('plotly_chart')
    at.button(key='company_clear').click().run()           # 사용자가 직접 다른 기업 검색을 고를 때만
    assert at.selectbox(key='company_financials_ticker') is not None and at.get('plotly_chart')


def test_company_search_covers_kr_and_us(app):
    at = app
    at.session_state['page'] = 'company'
    at.run()
    opts = at.selectbox(key='company_financials_ticker').options
    assert len(opts) == 806 + 20
    assert any('Nvidia' in o or '엔비디아' in o for o in opts) and any('테슬라' in o and '미국' in o for o in opts)
    at.selectbox(key='company_financials_ticker').set_value('TSLA').run()
    assert '전기차' in _biz(at)[0] and not at.get('plotly_chart')
    at.selectbox(key='company_financials_ticker').set_value('000040').run()   # 이름이 달라 소개 미확보인 회사
    b = _biz(at)[0]
    assert '기업 소개 미확보' in b and '이름' in b and at.get('plotly_chart')   # 재무는 그대로 보여요
    at.selectbox(key='company_financials_ticker').set_value('005930').run()
    b = _biz(at)[0]
    assert '메모리 반도체' in b and 'kind.krx.co.kr' in b and '수집일 2026-11-14' in b and '최신 사업과 다를 수' in b
    assert any(e.label.startswith('상장법인목록 원문') for e in at.expander)
    at.selectbox(key='company_financials_ticker').set_value('034020').run()   # 공식 최신 자료로 보완한 회사
    b = _biz(at)[0]
    assert '원자력' in b and '가스터빈' in b and '선박용 엔진' not in b
    assert 'https://www.doosanenerbility.com/kr' in b and '2025_report_kr.pdf' in b and 'kind.krx.co.kr' not in b
    assert '선박용엔진' in '\n'.join(m.value for m in at.markdown)         # KIND 원문은 펼침에 그대로


def test_company_profile_files_coverage():
    kr = pd.read_csv(ROOT / 'data' / 'company_profiles_kr.csv', dtype=str, keep_default_na=False)
    fin = cf.load_financials(cf.CSV_PATH)
    assert len(kr) == 806 and set(kr['code']) == set(fin['종목코드']) and kr['code'].str.fullmatch(r'[0-9A-Z]{6}').all()  # 0120G0 같은 새 코드 포함
    ok = kr[kr.status == 'ok']
    assert len(ok) >= 790 and (ok.summary != '').all()
    assert (kr[kr.status != 'ok'].summary == '').all()       # 이름 불일치·누락은 설명을 만들지 않아요
    names = fin.drop_duplicates('종목코드', keep='last').set_index('종목코드')['기업명']
    assert all(names[r.code] == r.kind_name for r in ok.itertuples())   # 같은 이름일 때만 붙였어요
    assert set(kr.status) <= {'ok', 'name_mismatch', 'missing'}
    assert (kr.collected_at == '2026-11-14').all()
    official = kr[kr.written == 'official'].set_index('code')
    assert set(official.index) == {'034020', '009830'}       # 공식 최신 자료로 보완한 회사만 출처가 KIND 가 아니에요
    assert (kr[kr.written != 'official'].source_url.str.startswith('https://kind.krx.co.kr')).all()
    assert official.at['034020', 'source_url'] == 'https://www.doosanenerbility.com/kr'
    assert official.at['034020', 'ref_url'].endswith('/2025_report_kr.pdf') and '원자력' in official.at['034020', 'summary']
    assert official.at['009830', 'source_url'] == 'https://www.hanwhasolutions.com/ko/'
    assert official.at['009830', 'ref_url'].endswith('Sustainability_Report_2025.pdf') and '태양광' in official.at['009830', 'tags']
    assert '선박용엔진' in official.at['034020', 'products'] and '합성수지' in official.at['009830', 'products']  # KIND 원문 보존
    assert not ok.tags.str.split('|').apply(lambda l: '수출입' in l).any()   # 동사 '수출입'은 제품 태그가 아니에요
    assert '수출입' not in kr.set_index('code').at['000020', 'summary']     # 동화약품
    import build_company_profiles as bcp                    # 다시 만들어도 공식 보완 문구·출처가 유지돼요
    assert set(bcp.OFFICIAL) == set(official.index) and not set(bcp.OFFICIAL) & set(bcp.MANUAL)
    assert all(bcp.OFFICIAL[c]['source_url'] == official.at[c, 'source_url'] for c in bcp.OFFICIAL)
    core = set(rc.STOCK_CATALOG[rc.STOCK_CATALOG.currency == 'KRW'].code)
    assert core <= set(ok.code) and ok[ok.code.isin(core)].written.isin(['manual', 'official']).all()
    us = pd.read_csv(ROOT / 'data' / 'company_profiles_us.csv', dtype=str, keep_default_na=False)
    want = set(pd.read_csv(ROOT / 'data' / 'stock_us.csv', nrows=1, index_col=0).columns)
    assert set(us.ticker) == want and len(us) == 20
    assert (us.summary.str.len() > 20).all() and us.summary.is_unique and (us.tags.str.count(r'\|') >= 1).all()
    assert us.source_url.str.startswith('https://').all() and (us.checked_at == '2026-11-14').all()
    off = us.source_url.str.contains('sec.gov') | us.apply(lambda r: r.ticker.lower()[:3] in r.source_url
                                                           or any(d in r.source_url for d in ['about.google', 'meta.com',
                                                                  'aboutamazon', 'modernatx', 'micron', 'intel', 'broadcom',
                                                                  'oracle', 'lumentum', 'bloomenergy', 'seagate', 'microsoft', 'nvidia']), axis=1)
    assert off.all()                                       # 공식 사이트 또는 회사 제출 SEC 보고서


def test_result_company_link(app):
    at = app
    at.session_state['ans'] = answers_for(28)
    at.session_state['budget'] = 10_000_000
    at.session_state['page'] = 'result'
    at.run()
    sb = at.selectbox(key='res_company_pick')
    cat = rc.STOCK_CATALOG
    us = next(n for n in rc.choose_picks('공격형', rc.load_prices(with_stocks=True, with_candidates=True), 10_000_000)
              if n in cat.index and cat.at[n, 'currency'] == 'USD')        # 추천에 담긴 미국 종목
    sb.set_value(us).run()
    at.button(key='res_company_go').click().run()
    assert at.session_state['page'] == 'company' and not at.exception
    assert _biz(at) and not at.get('plotly_chart')


def test_company_domestic_preselect(app):
    at = app
    at.session_state['company_pick'] = 'SB성보'
    at.session_state['page'] = 'company'
    at.run()
    assert at.selectbox(key='company_financials_ticker').value == '003080'
    assert any('SB성보' in m.value and 'fin-head' in m.value for m in at.markdown)


def test_footer_user_facing(app):
    text = _texts(app)
    assert 'FinanceDataReader' in text and '국내 상장사 연간 자료' in text and 'data/' not in text


@pytest.mark.parametrize('score', [5, 14, 21, 27])
@pytest.mark.parametrize('budget', BUDGETS)
def test_result_pages_all_profiles(app, score, budget):
    at = app
    at.session_state['ans'] = answers_for(score)
    at.session_state['budget'] = budget
    at.session_state['page'] = 'result'
    at.run()
    assert not at.exception
    at.session_state['page'] = 'mock'
    at.run()
    assert not at.exception and not at.error
    assert '과거 성과를 계산하지 못했어요' not in _texts(at)
