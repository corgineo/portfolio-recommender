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
    at.button(key='cta2').click().run()
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
    assert '매년 이 방식으로 추천받았다면?' in t                      # 과거 성과 = 연 1회 리밸런싱 백테스트
    assert ('저평가 우량주 5종목' in t) == (scope == 'wide')          # 팩터 종목은 넓은 범위에서만


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


def test_mock_page_cap_and_roundtrip():
    at = finish_quiz(new_app(), [1] * 7)
    at.button(key='to_mock_top').click().run()
    assert at.session_state.page == 'mock' and not at.exception
    sliders = at.slider
    assert len(sliders) >= 3
    # 연속 조작: 여러 슬라이더를 100%로 → 합계는 100%를 넘지 않아요
    for k in range(4):
        at.slider[k].set_value(100.0).run()
        total = sum(at.session_state.mock['w'].values())
        assert total <= 100 + 1e-9, total
    assert any('100%를 넘지 않도록' in i.value for i in at.info)
    snapshot = dict(at.session_state.mock['w'])
    # 페이지 왕복: 결과 → 투자상품 → 상세 → 모의
    at.button(key='nav_result').click().run()
    at.button(key='nav_products').click().run()
    at.button(key='base_KBOND').click().run()
    at.button(key='nav_mock').click().run()
    assert at.session_state.mock['w'] == snapshot
    vals = {s.key: s.value for s in at.slider}
    for n, v in snapshot.items():
        assert vals[f'mw_{n}'] == pytest.approx(v)
    # 되돌리기
    at.button(key='mock_reset').click().run()
    assert sum(at.session_state.mock['w'].values()) <= 100


def test_mock_remove_all_items_is_all_cash():
    at = finish_quiz(new_app(), [2] * 7)
    at.button(key='to_mock_top').click().run()
    at.multiselect(key='mock_items_w').set_value([]).run()
    assert not at.exception
    assert any('전액 현금' in i.value or '담은 상품이 없어요' in i.value for i in at.info)


def test_mock_resets_when_conditions_change():
    at = finish_quiz(new_app(), [1] * 7)
    at.button(key='to_mock_top').click().run()
    at.slider[0].set_value(0.0).run()
    at.button(key='nav_quiz').click().run()
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
