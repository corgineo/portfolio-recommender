"""계산 로직 테스트: 설문 원문 대조, 점수 경계, 추천·예산 경계, 상품 확대 데이터, 모의 포트폴리오 상한, 재무 빈값

실행 (프로젝트 폴더에서):
    uv run --no-project --python .venv/bin/python --with pytest --with python-pptx pytest -q tests
"""
import importlib.util
import random
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import recommender as rc   # noqa: E402
import service as svc      # noqa: E402

PPTX = ROOT.parents[1] / '강의자료' / '투자성향_자산배분.pptx'


def answers_for(score):
    """합계가 score 가 되는 답(0=①4점 … 4=⑤0점)"""
    pts, left = [], score
    for _ in range(len(rc.QUESTIONS)):
        p = min(4, left)
        pts.append(p)
        left -= p
    assert left == 0
    return [rc.POINTS.index(p) for p in pts]


# ── 설문: 원문과 글자 그대로 일치 ──────────────────────────────────────
def _norm(s):
    return re.sub(r'\s+', '', s)


@pytest.mark.skipif(not PPTX.exists(), reason='강의자료 pptx 없음')
def test_questions_match_source_pptx():
    pptx = pytest.importorskip('pptx')
    text = []
    for slide in pptx.Presentation(str(PPTX)).slides:
        for sh in slide.shapes:
            if sh.has_text_frame:
                text.append(sh.text_frame.text)
    src = _norm('\n'.join(text))
    assert len(rc.QUESTIONS) == 7
    for q, opts in rc.QUESTIONS:
        assert _norm(q) in src, q
        assert len(opts) == 5
        for o in opts:
            assert _norm(o) in src, o


def test_score_range_and_types():
    assert rc.MAX_SCORE == 28
    top = rc.judge_profile([0] * 7)
    assert (top['score'], top['type'], top['profile']) == (28, '공격 추구형', '공격형')
    low = rc.judge_profile([4] * 7)
    assert (low['score'], low['type'], low['profile']) == (0, '안정 추구형', '안정형')


@pytest.mark.parametrize('score,typ,profile', [
    (10, '안정 추구형', '안정형'), (11, '위험 중립형', '안정성장형'), (17, '위험 중립형', '안정성장형'),
    (18, '위험 중립형', '성장형'), (24, '위험 중립형', '성장형'), (25, '공격 추구형', '공격형')])
def test_score_boundaries(score, typ, profile):
    j = rc.judge_profile(answers_for(score))
    assert (j['score'], j['type'], j['profile']) == (score, typ, profile)
    assert sum(j['points']) == score


@pytest.mark.parametrize('bad', [[0] * 6, [0] * 6 + [None], [0] * 6 + [5], [0] * 6 + [-1]])
def test_judge_rejects_incomplete(bad):
    with pytest.raises(ValueError):
        rc.judge_profile(bad)


def test_period_from_question2():
    a = [2] * 7
    a[1] = 4
    j = rc.judge_profile(a)
    assert j['period'] == '1년 이내' and j['short_term']
    a[1] = 0
    assert rc.judge_profile(a)['period'] == '20년 이상'


# ── 기존 기능 회귀: 기본 범위 비중은 원래 코드와 같아요 ──────────────────────
def test_base_weights_same_as_original():
    try:
        src = subprocess.run(['git', 'show', 'main:recommender.py'], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout
    except Exception:
        pytest.skip('git main 없음')
    path = ROOT / 'tests' / '_orig_recommender_tmp.py'
    path.write_text(src, encoding='utf-8')
    try:
        spec = importlib.util.spec_from_file_location('orig_rc', path)
        orig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(orig)
        prices = rc.load_prices()
        _, _, cov = rc.model_inputs(prices)
        for prof in rc.PROFILES:
            new_w, _, _ = rc.build_portfolio(prof, cov)
            old_w, _, _ = orig.build_portfolio(prof, cov)
            pd.testing.assert_series_equal(new_w.sort_index(), old_w.sort_index(), atol=1e-6)
    finally:
        path.unlink(missing_ok=True)


# ── 추천: 성향 × 상품 범위 × 예산 경계 ────────────────────────────────────
@pytest.fixture(scope='module')
def scopes():
    return {s: svc.load_scope(s) for s in ['base', 'wide']}


@pytest.mark.parametrize('score', [0, 14, 21, 28])
@pytest.mark.parametrize('budget', [100_000, 1_000_000, 10_000_000, 1_000_000_000])
@pytest.mark.parametrize('scope', ['base', 'wide'])
def test_recommend_runs_and_is_consistent(scopes, score, budget, scope):
    data = scopes[scope]
    res = svc.recommend(answers_for(score), budget, data)
    w = res['weights']
    assert abs(w.sum() - 1) < 1e-9 and (w >= 0).all()
    alloc = res['alloc']
    spent = alloc.loc[alloc.name != rc.CASH, '금액(원)'].sum()
    cash = alloc.loc[alloc.name == rc.CASH, '금액(원)'].iloc[0]
    assert spent <= budget + 1e-6 and cash >= -1e-6
    assert abs(spent + cash - budget) < 1e-3
    q = alloc.loc[alloc.name != rc.CASH, '수량(주)']
    assert (q >= 0).all() and (q == q.round()).all()
    # 색: 상품 색이 모두 자기 자산군 팔레트 안에 있어요
    for n, c in res['colors'].items():
        assert c in rc.GROUP_SHADES[data['products'][n]['group']]
    for k in ['return', 'vol', 'mdd']:
        assert np.isfinite(res['perf'][k])
    if scope == 'wide':
        # 1주도 못 사는 상품은 (자산군에 혼자 남은 경우 말고는) 추천에서 빠져 있어요
        members = {g: len(s) for g, s in res['sleeves'].items()}
        zero = alloc[(alloc.name != rc.CASH) & (alloc['수량(주)'] == 0)]
        for n in zero.name:
            grp = data['products'][n]['group']
            assert members.get(grp, 1) == 1 or n in rc.ETF_NAMES, (n, budget)


def test_zero_budget_rejected(scopes):
    with pytest.raises(ValueError):
        svc.recommend([2] * 7, 0, scopes['base'])


def test_wide_falls_back_when_universe_missing(monkeypatch):
    monkeypatch.setattr(rc, 'load_universe', lambda *a, **k: None)
    data = svc.load_scope('wide')
    assert data['scope'] == 'base' and data['extra'] == {}


def test_load_universe_missing_dir(tmp_path):
    assert rc.load_universe(tmp_path) is None


# ── 상품 확대 데이터: 순위·환율·미래 데이터·상장 시점 ─────────────────────────
@pytest.fixture(scope='module')
def uni():
    u = rc.load_universe()
    if u is None:
        pytest.skip('data/universe 없음')
    return u


def test_ranking_is_sorted_and_documented(uni):
    r = uni['ranking']
    top = r[r.list.str.startswith('통합')]
    assert 20 <= len(top) <= 30
    assert list(top['rank']) == list(range(1, len(top) + 1))
    assert top['avg_value_krw'].is_monotonic_decreasing
    assert (r.loc[r.list.str.startswith('채권'), 'asset_class'] == '채권·예금').all()
    m = uni['meta']
    assert '20거래일' in m['value_definition'] and '원화' in m['value_definition']
    assert pd.Timestamp(r.loc[r.market == 'US', 'window_end'].max()) <= pd.Timestamp(m['us_last_session'])


def test_exclusion_rules(uni):
    r = uni['ranking']
    lev = r[r.name.str.contains('3X|레버리지|인버스|Ultra', case=False, regex=True)]
    assert not lev['eligible'].any()
    px = uni['prices']
    for row in r[r.eligible].itertuples():
        s = px[row.name_key]
        assert s.first_valid_index() <= px.index[-1] - pd.DateOffset(years=3) + pd.Timedelta(days=10), row.ticker
        assert pd.notna(s.iloc[-1])
    for row in r[~r.eligible].itertuples():
        assert row.exclude_reason, row.ticker


def test_us_prices_use_previous_us_close_and_fx(uni):
    """한국 t일의 미국 상품 원화가격 = t일보다 앞선 마지막 미국 종가 × 그날 환율 (미래 데이터 없음)"""
    r = uni['ranking']
    us = r[(r.market == 'US') & r.eligible].ticker.tolist()[:5]
    assert us
    fx = uni['fx']
    for t in us:
        krw, loc = uni['prices'][t].dropna(), uni['local'][t].dropna()
        last_day = krw.index[-1]
        us_session = pd.Timestamp(uni['meta']['us_last_session'])
        assert us_session < last_day                       # 미국 마지막 종가일 < 한국 기준일
        rate = fx.loc[:us_session].iloc[-1]
        assert krw.iloc[-1] == pytest.approx(loc.iloc[-1] * rate, rel=1e-6)


def test_fx_is_plausible(uni):
    fx = uni['fx'].dropna()
    assert fx.between(900, 2000).all()                     # 원/달러 환율 단위 오류(예: 1/환율) 방지
    assert fx.index.is_monotonic_increasing


def test_base_etfs_match_original_csv(uni):
    """새로 받은 기존 ETF 8종 가격이 원래 CSV와 겹치는 기간에 같은지"""
    orig = rc.load_prices()
    new = uni['prices'][rc.ETF_NAMES]
    common = orig.index.intersection(new.index)
    common = common[common >= new.index[0]]
    diff = (orig.loc[common] - new.loc[common]).abs() / orig.loc[common]
    assert len(common) > 500
    assert (diff.max() < 1e-9).all(), diff.max()


def test_kr_extra_etfs_linked_and_match_extra_data(uni):
    """순위와 별도인 '국내 추가 ETF'가 실제 가격으로 들어오고, 기존 extra_data 가격과 겹치는 날 값이 같은지"""
    r = uni['ranking']
    kr = r[r.list == '국내 추가 ETF']
    assert len(kr) == 9 and (kr.market == 'KR').all() and (kr.currency == 'KRW').all()
    assert {'채권·예금', '대안투자', '자산배분', '주식'} <= set(kr.asset_class)
    top = r[r.list.str.startswith('통합')]
    assert list(top['rank']) == list(range(1, len(top) + 1))           # 순위는 그대로
    ext = pd.read_csv(ROOT / 'data' / 'extra_data' / 'etf_prices_ext.csv', index_col=0, parse_dates=True)
    prod = pd.read_csv(ROOT / 'data' / 'extra_data' / 'products.csv', dtype={'code': str}, encoding='utf-8-sig')
    abbr = dict(zip(['132030', '133690', '161510', '284430', '251600', '114260', '153130', '136340', '148070'],
                    ['GOLD', 'NASDAQ100', 'DIVIDEND', 'MIX_K200_UST', 'MIX_DIVIDEND', 'KTB3Y', 'SHORTBOND', 'CORPBOND', 'KTB10Y']))
    assert set(kr.ticker) == set(abbr) and set(abbr) <= set(prod.code)
    px = uni['prices']
    for code, col in abbr.items():
        common = ext.index.intersection(px.index)
        rel = ((ext.loc[common, col] - px.loc[common, code]).abs() / ext.loc[common, col]).dropna()
        assert len(rel) > 1000 and (rel < 0.01).mean() > 0.995, code   # 수정주가 반영 차이 몇 건만 허용
        assert pd.notna(px[code].iloc[-1])


def test_wide_stable_pool_has_domestic_bonds(scopes):
    """넓은 범위에서 채권 몫 후보에 국내 채권 ETF가 들어가고, 소액 예산에서도 원화 채권 ETF로 채권 몫을 담는지"""
    d = scopes['wide']
    assert {'114260', '153130', '136340', '148070'} <= set(d['extra']['채권·예금'])
    res = svc.recommend(answers_for(0), 1_000_000, d)
    a = res['alloc']
    bonds = a[a.name.map(lambda n: d['products'].get(n, {}).get('group')) == '채권·예금']
    assert (bonds['수량(주)'] > 0).any()
    assert a['금액(원)'].sum() == pytest.approx(1_000_000)
    assert (a.loc[a.name != rc.CASH, '수량(주)'] % 1 == 0).all()


# ── 모의 포트폴리오: 합계 100% 상한 ───────────────────────────────────────
def test_clamp_never_exceeds_100_random_sequence():
    rng = random.Random(7)
    names = [f'A{i}' for i in range(12)]
    w = {n: 0.0 for n in names}
    for _ in range(3000):
        n = rng.choice(names)
        want = rng.choice([0, 0.5, rng.uniform(0, 100), 100, 150, -5])
        w[n] = svc.clamp_weight(n, want, w)
        assert sum(w.values()) <= 100 + 1e-9
        assert 0 <= w[n] <= 100


def test_clamp_examples():
    cur = {'A': 60.0, 'B': 30.0, 'C': 0.0}
    assert svc.clamp_weight('C', 50, cur) == 10.0
    assert svc.clamp_weight('A', 80, cur) == 70.0
    assert svc.clamp_weight('B', 10, cur) == 10.0


def test_floor_pct_sum_le_100(scopes):
    for score in [0, 14, 21, 28]:
        res = svc.recommend(answers_for(score), 10_000_000, scopes['wide'])
        pct = svc.floor_pct(res['weights'])
        assert sum(pct.values()) <= 100 and rc.CASH not in pct
        assert all(v % 0.5 == 0 for v in pct.values())


def test_compare_weights(scopes):
    px = scopes['base']['prices']
    out = svc.compare_weights(px, {'KOSPI200': 50, 'KBOND': 50}, {})
    assert (out['nav']['내 구성'] == 100).all()           # 전액 현금
    assert out['metrics'].loc['추천안', '변동성(%)'] > 0
    with pytest.raises(ValueError):
        svc.compare_weights(px, {'NOT_EXIST': 100}, {})    # 가격 없는 상품
    with pytest.raises(ValueError):
        svc.compare_weights(px.tail(20), {'KOSPI200': 100}, {})   # 데이터 부족


# ── 기업 분석: 재무 단위·빈값 ──────────────────────────────────────────
def test_kr_financials_units_and_nan():
    fin = svc.load_fin_kr()
    t = svc.financials_kr(fin, '005930')
    y24 = t[t['연도'] == '2024년'].iloc[0]
    assert y24['매출액'] == pytest.approx(3_008_710, rel=1e-3)   # 300.9조원 = 3,008,710억원
    assert svc.financials_kr(fin, '999999') is None
    # 영업이익이 비어 있는 기업-연도는 NaN 그대로여야 해요(0으로 채우지 않음)
    miss = fin[fin['영업이익'].isna() & fin['매출액'].notna()]
    if not miss.empty:
        code, year = miss.iloc[-1]['종목코드'], int(miss.iloc[-1]['회계연도'])
        tt = svc.financials_kr(fin, code, years=50)
        row = tt[tt['연도'] == f'{year}년'].iloc[0]
        assert np.isnan(row['영업이익']) and np.isnan(row['영업이익률(%)'])


def test_us_financials(uni):
    fin = uni['fin_us']
    t = svc.financials_us(fin, 'NVDA')
    fy = t[t['결산'] == '2025-01-26'].iloc[0]
    assert fy['매출액'] == pytest.approx(1304.97, rel=1e-4)          # NVIDIA FY2025 매출 $130.497B
    assert fy['부채비율(%)'] == pytest.approx(32274 / 79327 * 100, rel=1e-3)
    lly = svc.financials_us(fin, 'LLY')
    assert lly['영업이익'].isna().all()                               # 태그 없음 → 빈값 유지
    assert svc.financials_us(fin, 'TSM') is None                      # 20-F 기업 → 자료 없음
    assert svc.financials_us(pd.DataFrame(), 'NVDA') is None


def test_price_stats_short_series():
    s = pd.Series(np.linspace(100, 110, 30), index=pd.bdate_range('2026-01-01', periods=30))
    assert svc.price_stats(s) is None
    s2 = pd.Series(np.linspace(100, 110, 300), index=pd.bdate_range('2025-01-01', periods=300))
    st = svc.price_stats(s2)
    assert st['mdd'] == 0 and st['return'] > 0
