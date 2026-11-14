"""Streamlit AppTest: 실제 app.py 를 돌려 화면 흐름·상태 유지·슬라이더 상한·빈 자료 처리를 확인해요."""
import re
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import recommender as rc   # noqa: E402

BANNED = ['수업', '강의', '교수', '과제', '기말', '팀 프로젝트', 'B 담당']


def new_app():
    return AppTest.from_file(str(ROOT / 'app.py'), default_timeout=120).run()


def texts(at):
    return '\n'.join([m.value for m in at.markdown if not m.value.lstrip().startswith('<style>')] + [c.value for c in at.caption])


def finish_quiz(at, ans, budget=None, scope=None):
    at.button(key='home_start').click().run()
    if budget is not None:
        at.number_input(key='budget_w').set_value(budget).run()
    if scope is not None:
        at.radio(key='scope_w').set_value(scope).run()
    at.button(key='quiz_next').click().run()
    for i, a in enumerate(ans):
        at.radio(key=f'q{i}_w').set_value(a).run()
        assert not at.exception, at.exception
    return at


@pytest.mark.parametrize('ans,typ', [([4] * 7, '안정 추구형'), ([2] * 7, '위험 중립형'),
                                     ([1] * 7, '위험 중립형'), ([0] * 7, '공격 추구형')])
@pytest.mark.parametrize('scope', ['wide', 'base'])
def test_each_profile_reaches_result(ans, typ, scope):
    at = finish_quiz(new_app(), ans, scope=scope)
    assert at.session_state.page == 'result'
    t = texts(at)
    assert f'당신은 {typ} 투자자예요' in t
    assert '이렇게 사면 돼요' in t and not at.error
    assert not any(w in t for w in BANNED), [w for w in BANNED if w in t]


@pytest.mark.parametrize('budget', [100_000, 1_000_000_000])
def test_budget_boundaries(budget):
    at = finish_quiz(new_app(), [1] * 7, budget=budget)
    assert at.session_state.budget == budget
    assert not at.exception and not at.error
    assert '이렇게 사면 돼요' in texts(at)


def test_short_period_note():
    ans = [2] * 7
    ans[1] = 4                         # 투자 기간 1년 이내
    t = texts(finish_quiz(new_app(), ans))
    assert '투자 기간 1년 이내' in t and '손실을 회복할 시간이 부족' in t


def set_mock_weight(at, name, value):
    """나만의 포트폴리오 화면: 상품 하나를 고른 뒤 그 상품 슬라이더를 움직여요 (한 번에 한 상품만 조절)"""
    at.selectbox(key='mock_pick').set_value(name).run()
    at.slider(key=f'mw_{name}').set_value(value).run()


def test_mock_page_cap_and_roundtrip():
    at = finish_quiz(new_app(), [1] * 7)
    at.button(key='to_mock_top').click().run()
    assert at.session_state.page == 'mock' and not at.exception
    names = list(at.selectbox(key='mock_pick').options)
    assert len(names) >= 3
    assert len(at.slider) == 1                     # 한 번에 슬라이더 하나만 보여요
    # 연속 조작: 여러 상품을 차례로 100%로 → 합계는 100%를 넘지 않아요
    items = [n for n in at.session_state.mock['w']][:4]
    for n in items:
        set_mock_weight(at, n, 100.0)
        total = sum(at.session_state.mock['w'].values())
        assert total <= 100 + 1e-9, total
        assert not at.exception
    assert any('100%를 넘지 않도록' in i.value for i in at.info)
    snapshot = dict(at.session_state.mock['w'])
    picked = at.session_state.mock_pick
    # 페이지 왕복: 결과 → 상품 둘러보기 → 상세 → 나만의 포트폴리오
    at.button(key='nav_result').click().run()
    at.button(key='nav_products').click().run()
    at.button(key='base_KBOND').click().run()
    assert at.session_state.page == 'detail'
    at.button(key='nav_mock').click().run()
    assert at.session_state.mock['w'] == snapshot
    assert at.slider(key=f'mw_{picked}').value == pytest.approx(snapshot[picked])
    # 다른 상품을 골라도 저장된 값이 그대로 보여요
    for n in items:
        at.selectbox(key='mock_pick').set_value(n).run()
        assert at.slider(key=f'mw_{n}').value == pytest.approx(snapshot[n])
    # 되돌리기
    at.button(key='mock_reset').click().run()
    assert at.session_state.mock['w'] == at.session_state.mock['rec']
    assert sum(at.session_state.mock['w'].values()) <= 100


def test_mock_add_item_and_budget():
    """상품 더하기 → 0%에서 시작해 바로 조절 대상으로 골라짐, 제작 예산 바꾸기"""
    at = finish_quiz(new_app(), [1] * 7)
    at.button(key='to_mock_top').click().run()
    ms = at.multiselect(key='mock_items_w')
    cur = list(ms.value)
    import service as svc
    data = svc.load_scope(at.session_state.scope)
    last = data['prices'].ffill().iloc[-1]
    cands = list(rc.ETF_NAMES) + [n for v in data['extra'].values() for n in v]
    new = next(n for n in cands if n not in cur and n in last and last[n] == last[n])
    ms.set_value(cur + [new]).run()
    assert not at.exception
    assert at.session_state.mock['w'][new] == 0.0
    assert at.session_state.mock_pick == new
    set_mock_weight(at, new, 5.0)
    assert sum(at.session_state.mock['w'].values()) <= 100 + 1e-9
    at.number_input(key='mock_budget_w').set_value(3_000_000).run()
    assert at.session_state.mock['budget'] == 3_000_000 and not at.exception


def test_mock_remove_all_items_is_all_cash():
    at = finish_quiz(new_app(), [2] * 7)
    at.button(key='to_mock_top').click().run()
    at.multiselect(key='mock_items_w').set_value([]).run()
    assert not at.exception
    assert any('전액 현금' in i.value or '담은 상품이 없어요' in i.value for i in at.info)


def test_mock_resets_when_conditions_change():
    at = finish_quiz(new_app(), [1] * 7)
    at.button(key='to_mock_top').click().run()
    first = at.session_state.mock_pick
    set_mock_weight(at, first, 0.0)
    assert at.session_state.mock['w'][first] == 0.0
    at.button(key='nav_result').click().run()
    at.button(key='to_cond_top').click().run()
    assert at.session_state.page == 'quiz' and at.session_state.step == 0
    at.number_input(key='budget_w').set_value(5_000_000).run()
    at.button(key='nav_mock').click().run()
    assert at.session_state.mock['budget'] == 5_000_000
    assert at.session_state.mock['w'] == at.session_state.mock['rec']


def test_holdings_more_toggle():
    at = finish_quiz(new_app(), [0] * 7, budget=1_000_000_000)
    before = texts(at).count('<tr>')
    at.button(key='more_hold').click().run()
    after = texts(at).count('<tr>')
    assert after > before


@pytest.mark.parametrize('name,expect', [
    ('NVDA', 'SEC EDGAR'), ('TSM', '재무 자료를 확보하지 못했어요'), ('SPY', 'ETF는 재무제표 대신'),
    ('KOSPI200', 'ETF는 재무제표 대신'), ('KRFIN:005930', '부채비율'), ('UNKNOWN_X', '상품 정보를 찾을 수 없어요'),
    ('SPCX', '추천 계산에서는 빠져 있어요')])
def test_detail_pages(name, expect):
    if rc.load_universe() is None and name in ('NVDA', 'TSM', 'SPY', 'SPCX'):
        pytest.skip('universe 없음')
    at = new_app()
    at.session_state['detail'] = name
    at.session_state['page'] = 'detail'
    at.run()
    assert not at.exception, at.exception
    t = texts(at) + '\n'.join(x.value for x in list(at.info) + list(at.warning))
    assert expect in t
    if name in ('SPY', 'KOSPI200'):
        assert '매출액·영업이익' not in t


def test_products_page_criteria():
    at = new_app()
    at.button(key='nav_products').click().run()
    t = texts(at)
    assert not at.exception
    if rc.load_universe() is not None:
        assert '원화(KRW)' in t and '최근 20거래일 평균' in t
        assert re.search(r'국내 1위 .+ 통합 \d+위', t)


# ── Codex 검수 보완 (UX 1차) ─────────────────────────────────────────────
@pytest.mark.parametrize('name', ['KRFIN:005930', 'NVDA'])
def test_fin_year_label_not_doubled(name):
    if name == 'NVDA' and rc.load_universe() is None:
        pytest.skip('universe 없음')
    at = new_app()
    at.session_state['detail'] = name
    at.session_state['page'] = 'detail'
    at.run()
    t = texts(at)
    assert not at.exception and '매출액 · ' in t
    assert '년년' not in t and '결산년' not in t


def test_result_mdd_is_percent_not_money():
    t = texts(finish_quiz(new_app(), [1] * 7))
    assert '당시 최고점에서' in t and '처음 넣은 돈 기준 손실액이 아니에요' in t
    assert '줄어듦' not in t and '다섯 곳' not in t


def test_mock_pick_line_shows_amount_and_zero_share():
    at = finish_quiz(new_app(), [1] * 7)
    at.button(key='to_mock_top').click().run()
    pick = at.session_state.mock_pick
    t = texts(at)
    assert '목표 금액' in t and '어치 사요' in t and '남는 현금이에요' in t
    # 예산을 아주 작게 → 1주도 못 사는 상품은 한 주 금액 부족 안내
    at.number_input(key='mock_budget_w').set_value(10_000).run()
    set_mock_weight(at, pick, 1.0)
    assert '한 주를 살 돈이 부족해요' in texts(at)
    # 0%로 내리면 사지 않는다고 안내
    set_mock_weight(at, pick, 0.0)
    assert '0%라 이 상품은 사지 않아요' in texts(at)


def test_products_page_has_no_developer_paths():
    at = new_app()
    at.button(key='nav_products').click().run()
    t = texts(at) + '\n'.join(i.value for i in at.info)
    for bad in ['update_universe', 'data/universe', 'data/extra_data', '.py']:
        assert bad not in t, bad
    assert '살펴볼 수 있는 상품' in t


# ── 시각 개편 2차: 나만의 포트폴리오 전용 페이지 · 계산 방법 섹션 제거 · 실시간 연결 ───────────────
def all_text(at):
    return texts(at) + '\n'.join(x.label for x in at.button) + '\n'.join(x.label for x in at.expander)


def test_build_menu_always_visible_and_no_practice_wording():
    at = new_app()
    assert at.button(key='nav_mock').label == '나만의 포트폴리오'
    assert at.button(key='home_build').proto.type == 'primary'           # 홈의 가장 강조된 버튼
    assert '연습' not in all_text(at)
    finish_quiz(at, [1] * 7)
    assert at.button(key='nav_mock').label == '나만의 포트폴리오'
    assert '나만의 포트폴리오' in at.button(key='to_mock_top').label and at.button(key='to_mock_top').proto.type == 'primary'
    assert '연습' not in all_text(at)
    at.button(key='to_mock_top').click().run()
    assert '연습' not in all_text(at) and '제작 예산' in all_text(at)


def test_build_intro_before_quiz_then_returns_to_workbench():
    at = new_app()
    at.button(key='nav_mock').click().run()
    assert at.session_state.page == 'mock' and not at.exception
    t = texts(at)
    assert '7문항 성향 진단' in t and '화면 예시' in t and '맞춤 구성이 아니에요' in t
    assert len(at.slider) == 0 and 'mock' not in at.session_state      # 진단 전에는 가짜 맞춤 구성을 만들지 않아요
    at.button(key='build_start').click().run()
    assert at.session_state.page == 'quiz' and at.session_state.after_quiz == 'mock'
    assert '제작 화면으로 바로 이어져요' in texts(at)
    at.button(key='quiz_next').click().run()
    for i in range(7):
        at.radio(key=f'q{i}_w').set_value(1).run()
    assert at.session_state.page == 'mock' and at.session_state.after_quiz is None
    assert len(at.slider) == 1 and at.session_state.mock['w'] == at.session_state.mock['rec']


def test_build_intro_resumes_partial_quiz():
    at = new_app()
    at.button(key='home_start').click().run()
    at.button(key='quiz_next').click().run()
    at.radio(key='q0_w').set_value(2).run()
    at.radio(key='q1_w').set_value(2).run()
    at.button(key='nav_mock').click().run()
    assert '질문 3 / 7' in at.button(key='build_start').label
    at.button(key='build_start').click().run()
    assert at.session_state.step == 3 and at.session_state.ans[:2] == [2, 2]


def test_general_quiz_still_goes_to_result():
    at = new_app()
    at.button(key='nav_mock').click().run()
    at.button(key='nav_quiz').click().run()          # 메뉴의 성향 진단은 그대로 진단 (after_quiz 는 소개 화면 시작 때만)
    at.button(key='nav_logo').click().run()
    at.button(key='home_start').click().run()         # 홈에서 처음부터 진단 → 결과로
    at.button(key='quiz_next').click().run()
    for i in range(7):
        at.radio(key=f'q{i}_w').set_value(1).run()
    assert at.session_state.page == 'result'


@pytest.mark.parametrize('ans', [[4] * 7, [0] * 7])
def test_result_has_no_calc_method_section(ans):
    at = finish_quiz(new_app(), ans)
    t = all_text(at)
    for bad in ['계산 방법과 자료 기준', '공분산', 'wᵀΣw', '위험기여도', '× 240', '종류 안 비중']:
        assert bad not in t, bad
    # 해석에 필요한 짧은 캡션(기준일·원화)은 표 옆에 남아 있어요
    assert '종가 기준 · 원화' in t
    assert '돈을 이렇게 나눠요' in t and 'class="donut"' in t


def test_result_targets_vs_actual_amounts():
    at = finish_quiz(new_app(), [1] * 7)
    t = texts(at)
    assert '실제로 사는 돈' in t and '남는 현금' in t and '목표 비율로 나눈 값' in t


def _donut_total(at):
    """제작 화면 도넛의 상품 조각 합계 (현금 조각 제외) — 도넛 aria-label 에 적힌 값을 읽어요"""
    m = re.search(r'aria-label="내 구성 상품별 목표 비율: ([^"]*)"', texts(at))
    if not m:
        return None
    parts = [x.rsplit(' ', 1) for x in m.group(1).split(', ')]
    return sum(float(v.rstrip('%')) for n, v in parts if not n.startswith('현금'))


def test_workbench_preview_updates_live():
    at = finish_quiz(new_app(), [1] * 7)
    at.button(key='to_mock_top').click().run()
    before_total = _donut_total(at)
    assert before_total == pytest.approx(sum(at.session_state.mock['w'].values()), abs=0.2)
    pick = at.session_state.mock_pick
    before = texts(at)
    set_mock_weight(at, pick, 0.0)
    after = texts(at)
    w0 = at.session_state.mock['rec'][pick]
    assert _donut_total(at) == pytest.approx(before_total - w0, abs=0.2)     # 도넛 = 슬라이더 값
    assert f'<b>{sum(at.session_state.mock["w"].values()):.1f}%</b>' in after                            # 도넛 가운데 합계
    spent = lambda t: re.search(r'실제로 사는 돈</span><b>[^<]+</b><em>([\d,]+)원', t).group(1)
    assert spent(before) != spent(after)                                 # KPI 금액도 같이 바뀌어요


# ── Codex 검수 보완 (시각 개편 2차) ─────────────────────────────────────
def test_won_exact_readable_and_exact():
    from ui import won_exact
    assert won_exact(9_999_600_192) == '99억 9,960만 192원'
    assert won_exact(678_140) == '67만 8,140원'
    assert won_exact(10_000_000_000) == '100억원' and won_exact(0) == '0원'


def test_cta_wording_and_big_budget_kpi_exact():
    at = new_app()
    assert at.button(key='home_build').label == '나만의 포트폴리오 제작하기'
    finish_quiz(at, [1] * 7)
    assert at.button(key='to_mock_top').label == '나만의 포트폴리오 제작하기'
    t = texts(at)
    assert '추천 상품</span>' in t and '그중 1주 이상 사는 상품' in t and '5가지에' not in t
    assert '안정 추구형 0~10점' in t and '공격 추구형 25~28점' in t      # 점수 막대 전체 이름
    at.button(key='to_mock_top').click().run()
    assert '<h1>나만의 포트폴리오</h1>' in texts(at)
    at.number_input(key='mock_budget_w').set_value(10_000_000_000).run()
    t = texts(at)
    from ui import won_exact
    m = re.search(r'실제로 사는 돈</span><b>([^<]+)</b><em>([\d,]+)원', t)
    exact = int(m.group(2).replace(',', ''))
    assert m.group(1) == won_exact(exact) and exact > 5_000_000_000     # 큰 표시와 정확한 금액이 둘 다 보여요
    assert '<b>100억원</b><em>10,000,000,000원</em>' in t
    for short in ['>채권<', '>다른 자산<', '>현금<']:
        assert short in t, short
