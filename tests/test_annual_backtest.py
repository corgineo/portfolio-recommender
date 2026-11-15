"""연 1회 리밸런싱 과거 전략(annual_backtest.py) 회귀 검증

- 팀원(origin/sehui 5948ee3) 8종 ETF 규칙과 목표 비중이 같은지 (tests/data/sehui_annual_targets.json)
- 현재 20종 설정과 분리되어 있는지, 미래 가격·종목을 쓰지 않는지, 비용·현금 이자·연도 수익률·CAGR 계산
"""
import json
import base64
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import annual_backtest as ab                # noqa: E402
import recommender as rc                    # noqa: E402

TWENTY_ONLY = {'GOLD', 'REIT', 'NASDAQ100', 'DIVIDEND', 'KTB3Y', 'SHORTBOND', 'CORPBOND', 'KTB10Y', 'UST10Y',
               'UST30Y_H', 'MIX_K200_UST', 'MIX_DIVIDEND'}


@pytest.fixture(scope='module')
def data():
    return ab.load_data()


def _copy(d):
    return {'etf': d['etf'].astype(float), 'stocks': d['stocks'].astype(float), 'picks': d['picks'].copy()}


# ── 팀원 규칙 · 8종 고정 ──────────────────────────────────────────────
@pytest.mark.parametrize('profile', ab.PROFILES)
@pytest.mark.parametrize('use_factor', [True, False])
def test_targets_match_teammate_source(data, profile, use_factor):
    ref = json.loads((ROOT / 'tests' / 'data' / 'sehui_annual_targets.json').read_text())['weights']
    ref = ref[f'{profile}|{int(use_factor)}']
    W, sch = ab.target_weights(profile, data, use_factor)
    assert list(ref) == [t.strftime('%Y-%m-%d') for t in sch.selection]
    for sel, ex in zip(sch.selection, sch.execution):
        mine = W.loc[ex][W.loc[ex] > 0]
        theirs = pd.Series(ref[sel.strftime('%Y-%m-%d')])
        assert set(mine.index) == set(theirs.index)
        assert np.allclose(mine[theirs.index], theirs, atol=1e-9)


def test_fixed_eight_etf_isolation(data):
    assert len(rc.ETF_NAMES) == 20 and TWENTY_ONLY <= set(rc.ETF_NAMES)      # 현재 서비스는 20종
    assert len(ab.LEGACY_ETFS) == 8 and set(ab.LEGACY_ETFS) <= set(rc.ETF_NAMES)
    assert list(data['etf'].columns) == list(ab.LEGACY_ETFS)
    raw = pd.read_csv(ab.ETF_FILE, index_col=0, nrows=2)
    assert raw.shape[1] == 20                                                # 원본 가격 파일은 그대로
    cov = ab.legacy_cov(data['etf'], data['picks']['리밸런싱일'].iloc[0])
    assert list(cov.index) == list(ab.LEGACY_ETFS)
    before = (list(rc.ETF_NAMES), rc.build_portfolio, rc.MIN_WEIGHT, dict(rc.ETF_INFO))
    for profile in ab.PROFILES:
        W, _ = ab.target_weights(profile, data, True)
        etfs = {c for c in W.columns if c in rc.ETF_NAMES}
        assert etfs == set(ab.LEGACY_ETFS) and not (set(W.columns) & TWENTY_ONLY)
        stocks = set(W.columns) - etfs - {ab.CASH}
        assert stocks <= set(data['picks']['종목명'])                       # 거래대금 상위(오늘 기준) 종목 없음
        if rc.STOCK_CATALOG is not None:
            assert not (stocks & set(rc.STOCK_CATALOG.index) - set(data['picks']['종목명']))
    assert before == (list(rc.ETF_NAMES), rc.build_portfolio, rc.MIN_WEIGHT, dict(rc.ETF_INFO))   # 전역 설정 그대로


@pytest.mark.parametrize('profile', ab.PROFILES)
def test_legacy_allocation_rules(data, profile):
    W, sch = ab.target_weights(profile, data, True)
    table = ab.PROFILE_TABLE[profile]
    for ex, row in W.iterrows():
        assert row.sum() == pytest.approx(1, abs=1e-9)
        assert row[ab.CASH] == pytest.approx(table['유동성'] / 100, abs=2e-3)
        picks = [c for c in row.index if c not in ab.LEGACY_ETFS and c != ab.CASH and row[c] > 0]
        assert len(picks) == 5
        each = table['주식'] / 100 * ab.STOCK_SHARE / 5                    # 주식 몫의 절반을 같은 비중으로
        assert np.allclose(row[picks], each, rtol=5e-3)
    if profile == '안정형':                                                 # 3% 정리 규칙이 없어 작은 비중도 남아요
        assert (W.iloc[0][W.iloc[0] > 0] < rc.MIN_WEIGHT).sum() >= 5
    ef, _ = ab.target_weights(profile, data, False)
    assert set(ef.columns) == set(ab.LEGACY_ETFS) | {ab.CASH}


def test_factor_availability_assumption(data):
    p = data['picks']
    idx = data['etf'].index
    for t, g in p.groupby('리밸런싱일'):
        assert (g['회계연도'] == t.year - 1).all()                         # 직전 회계연도 재무만
        assert t == idx[idx >= pd.Timestamp(t.year, 4, 1)][0]               # 4월 1일 이후 첫 거래일


# ── 시점: 다음 거래일 매매 · 미래 자료 미사용 ────────────────────────────────
def test_execution_is_next_trading_day(data):
    W, sch = ab.target_weights('성장형', data, True)
    idx = data['etf'].index
    for r in sch.itertuples():
        assert r.execution == idx[idx > r.selection][0] and r.execution > r.selection
    assert list(W.index) == list(sch.execution)
    res = ab.run('성장형', data=data)
    assert res['start'] == sch.execution.iloc[0] and res['start'] == pd.Timestamp('2019-04-02')
    h = res['holdings']
    for ex in sch.execution:                 # 매매일 종가 이후의 보유 = 목표 비중
        assert np.allclose(h.loc[ex] / h.loc[ex].sum(), W.loc[ex][h.columns], atol=1e-12)


def test_future_unexecutable_selection_does_not_change_past(data):
    d = _copy(data)
    latest = d['picks']['리밸런싱일'].max()
    future = d['picks'].loc[d['picks']['리밸런싱일'] == latest].copy()
    future['리밸런싱일'] += pd.DateOffset(years=1)
    future['회계연도'] += 1
    d['picks'] = pd.concat([d['picks'], future], ignore_index=True)
    original = ab.run('성장형', data=data)
    altered = ab.run('성장형', data=d)
    pd.testing.assert_frame_equal(original['weights'], altered['weights'])
    pd.testing.assert_frame_equal(original['navs'], altered['navs'])


@pytest.mark.parametrize('before_april', [False, True])
def test_financial_information_not_available_at_selection_is_rejected(data, before_april):
    d = _copy(data)
    first = d['picks']['리밸런싱일'].min()
    mask = d['picks']['리밸런싱일'] == first
    if before_april:
        d['picks'].loc[mask, '리밸런싱일'] = d['etf'].index[d['etf'].index < pd.Timestamp(first.year, 4, 1)][-1]
    else:
        d['picks'].loc[mask, '회계연도'] = first.year
    with pytest.raises(ValueError, match='이용할 수 없는 회계연도'):
        ab.target_weights('성장형', d)


def test_future_price_perturbation_keeps_prior_targets(data):
    W0, sch = ab.target_weights('공격형', data, True)
    k = 3
    t = sch.selection.iloc[k]
    d = _copy(data)
    rng = np.random.default_rng(0)
    after = d['etf'].index > t
    d['etf'].loc[after] *= rng.uniform(0.5, 1.5, size=d['etf'].loc[after].shape)
    d['stocks'].loc[after] *= 3.0
    W1, _ = ab.target_weights('공격형', d, True)
    assert W1.iloc[:k + 1].equals(W0.iloc[:k + 1])                          # 선정일 이후 가격은 그해 목표에 영향 없음
    assert not W1.iloc[k + 1:].equals(W0.iloc[k + 1:])
    d2 = _copy(data)                                                        # 선정일 당일 가격은 쓰여요 (그해만 바뀜)
    d2['etf'].loc[t, 'OIL'] *= 1.8
    W2, _ = ab.target_weights('공격형', d2, True)
    assert W2.iloc[:k].equals(W0.iloc[:k]) and not W2.iloc[k].equals(W0.iloc[k])


def test_selection_perturbation_keeps_prior_targets_and_nav(data):
    base = ab.run('성장형', data=data)
    d = _copy(data)
    last = d['picks']['리밸런싱일'].max()
    d['picks'].loc[d['picks']['리밸런싱일'] == last, '종목명'] = ['세아제강지주', '한일홀딩스', '효성', 'SIMPAC', '케이씨']
    alt = ab.run('성장형', data=d)
    k = len(base['weights']) - 1
    assert alt['weights'].iloc[:k].drop(columns=[c for c in alt['weights'] if c not in base['weights']],
                                         errors='ignore').equals(base['weights'].iloc[:k][
                                             [c for c in base['weights'] if c in alt['weights']]])
    ex = base['schedule'].execution.iloc[-1]
    before = base['navs'].index < ex
    pd.testing.assert_frame_equal(base['navs'][before], alt['navs'][before])
    assert not base['navs'].loc[ex:].equals(alt['navs'].loc[ex:])


def test_missing_held_price_raises(data):
    d = _copy(data)
    W, sch = ab.target_weights('성장형', d, True)
    name = data['picks'][data['picks']['리밸런싱일'] == sch.selection.iloc[2]]['종목명'].iloc[0]
    day = d['stocks'].loc[sch.execution.iloc[2]:].index[10]
    d['stocks'].loc[day, name] = np.nan
    with pytest.raises(ValueError, match='보유 자산 가격'):
        ab.run('성장형', data=d)
    d['stocks'].loc[day, name] = 0.0
    with pytest.raises(ValueError, match='보유 자산 가격'):
        ab.run('성장형', data=d)


# ── 비용 · 현금 이자 · 연도 수익률 · CAGR ───────────────────────────────────
def _synthetic(days, prices):
    idx = pd.DatetimeIndex(days)
    return pd.DataFrame(prices, index=idx)


def test_costs_initial_and_rebalance():
    idx = pd.to_datetime(['2020-01-02', '2020-01-03', '2020-01-06'])
    px = pd.DataFrame({'A': [100.0, 110.0, 110.0], 'B': [100.0, 100.0, 100.0]}, index=idx)
    W = pd.DataFrame({'A': [0.5, 0.0], 'B': [0.4, 0.9], ab.CASH: [0.1, 0.1]}, index=idx[[0, 2]])
    nav, hold, turnover, costs = ab.simulate(W, px, bp=0.001, rf=0.0)
    assert nav.iloc[0] == pytest.approx(100 - 90 * 0.001)                  # 처음 매수 비용: 산 금액 90 × 0.1%
    assert turnover.iloc[0] == pytest.approx(0.9)
    v1 = nav.iloc[0] * (0.5 * 1.1 + 0.4 + 0.1)
    assert nav.iloc[1] == pytest.approx(v1)
    a_val = nav.iloc[0] * 0.5 * 1.1
    b_val = nav.iloc[0] * 0.4
    trade = a_val + abs(0.9 * v1 - b_val)                                   # A 전량 매도 + B 추가 매수 (현금 제외)
    assert costs.iloc[1] == pytest.approx(trade * 0.001)
    assert nav.iloc[2] == pytest.approx(v1 - trade * 0.001)
    nav0, *_ = ab.simulate(W, px, bp=0.0, rf=0.0)
    assert nav0.iloc[0] == 100 and nav0.iloc[2] == pytest.approx(100 * (0.5 * 1.1 + 0.5))


def test_cash_interest_calendar_days():
    idx = pd.to_datetime(['2021-01-04', '2021-07-05', '2022-01-04'])
    px = pd.DataFrame({'A': [1.0, 1.0, 1.0]}, index=idx)
    W = pd.DataFrame({'A': [0.0], ab.CASH: [1.0]}, index=idx[:1])
    nav, *_ = ab.simulate(W, px, bp=0.001, rf=0.03)
    assert nav.iloc[-1] == pytest.approx(100 * 1.03)                       # 365일 → 정확히 3%
    nav0, *_ = ab.simulate(W, px, bp=0.001, rf=0.0)
    assert nav0.iloc[-1] == pytest.approx(100)


def test_bp_rf_pass_through_run(data):
    a = ab.run('안정형', data=data)
    b = ab.run('안정형', bp=0.0, rf=0.0, data=data)
    c = ab.run('안정형', bp=0.01, rf=0.03, data=data)
    assert (a['bp'], a['rf'], b['bp'], b['rf']) == (ab.BP, ab.RF, 0.0, 0.0)
    assert b['costs'].sum() == 0 and a['costs'].sum() > 0 and c['costs'].sum() > a['costs'].sum()
    assert b['navs'].iloc[0, 0] == 100 and a['navs'].iloc[0, 0] < 100
    assert a['navs'].iloc[0, 1] == pytest.approx(100 * (1 - ab.BP)) and b['navs'].iloc[0, 1] == 100   # 비교 기준도 같은 비용
    cash_a = a['holdings'][ab.CASH]
    assert cash_a.iloc[1] / cash_a.iloc[0] > 1 and b['holdings'][ab.CASH].iloc[1] == b['holdings'][ab.CASH].iloc[0]


def test_metrics_cagr_and_yearly():
    idx = pd.to_datetime(['2020-06-30', '2020-12-31', '2021-12-31', '2022-06-30'])
    nav = pd.Series([100.0, 110.0, 99.0, 121.0], index=idx)
    m = ab.metrics(nav)
    years = (idx[-1] - idx[0]).days / 365.25
    assert m['cagr'] == pytest.approx(1.21 ** (1 / years) - 1)
    assert m['cum'] == pytest.approx(0.21) and m['mdd'] == pytest.approx(99 / 110 - 1)
    daily_mean_ann = nav.pct_change().mean() * ab.DAYS
    assert abs(m['cagr'] - daily_mean_ann) > 0.05                           # CAGR ≠ 일평균 × 240
    y = ab.yearly(pd.DataFrame({'s': nav}))
    assert list(y.index) == [2020, 2021, 2022]
    assert y.loc[2020, 's'] == pytest.approx(0.10) and y.loc[2021, 's'] == pytest.approx(-0.10)
    assert y.loc[2022, 's'] == pytest.approx(121 / 99 - 1)
    assert y.loc[2020, '기간'].startswith('06.30') and y.loc[2022, '기간'].endswith('06.30') and y.loc[2021, '기간'] == '연간'
    assert np.prod(1 + y['s']) == pytest.approx(1.21)                       # 연도 수익률을 이으면 전체와 같음


@pytest.mark.parametrize('profile', ab.PROFILES)
def test_all_profiles_end_to_end(data, profile):
    res = ab.run(profile, data=data)
    navs = res['navs']
    assert list(navs.columns) == ['연 1회 리밸런싱 전략', '단기채권 ETF 보유']
    assert np.isfinite(navs.to_numpy()).all() and (navs > 0).all().all()
    assert res['start'] == pd.Timestamp('2019-04-02') and res['end'] == data['etf'].index[-1]
    assert list(res['yearly'].index) == list(range(2019, res['end'].year + 1))
    for m in res['metrics'].values():
        assert np.isfinite([m['cagr'], m['mdd'], m['cum']]).all() and m['mdd'] <= 0
    total = np.prod(1 + res['yearly']['연 1회 리밸런싱 전략']) - 1
    assert total == pytest.approx(res['metrics']['연 1회 리밸런싱 전략']['cum'])
    assert len(res['selections']) == 8 and (res['selections']['매매일'] > res['selections']['선정일']).all()


def test_data_version_changes_with_content(tmp_path):
    files = []
    for name in ('a.csv', 'b.csv'):
        p = tmp_path / name
        p.write_text('x\n1\n')
        files.append(p)
    v1 = ab.data_version(files)
    files[1].write_text('x\n2\n')
    assert ab.data_version(files) != v1 and len(v1) == 16


# ── 결과 화면: 별도 섹션 · 현재 추천 비교는 그대로 ───────────────────────────────
def _answers(score):
    ans, left = [], score
    for _ in range(7):
        p = min(4, left)
        ans.append(4 - p)
        left -= p
    return ans


@pytest.mark.parametrize('score,profile', [(5, '안정형'), (14, '안정성장형'), (21, '성장형'), (27, '공격형')])
def test_result_page_annual_section(data, score, profile):
    from streamlit.testing.v1 import AppTest
    import json as _json
    at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=120)
    at.session_state['ans'] = _answers(score)
    at.session_state['page'] = 'result'
    at.run()
    assert not at.exception and not at.warning
    md = '\n'.join(m.value for m in at.markdown)
    assert '현재 추천 포트폴리오와 별도로 계산한 참고 성과' in md and 'ETF 8종' in md and '가치주 5종' in md
    assert '현재 추천 구성의 최근 3년 성과' in md                         # 고정 비중 비교 섹션 유지
    assert '거래비용 0.1%(첫 매수 포함)' in md and '현금 연 3%' in md and '연평균 성장률(CAGR)' in md
    labels = [e.label for e in at.expander]
    assert {'연도별 수익률', '연도별 편입 종목과 비중', '검증 조건 및 유의사항'} <= set(labels)
    charts = {}
    for c in at.get('plotly_chart'):
        spec = _json.loads(c.proto.spec)
        charts[tuple(d.get('name') for d in spec['data'])] = spec['data']
    assert ('단기채권 ETF', '추천 구성') in charts                         # 현재 추천(고정 비중) 그래프
    annual = charts[('단기채권 ETF', '연 1회 리밸런싱 전략')]
    res = ab.run(profile, data=data)
    def values(v):
        # Plotly supports both JSON arrays and typed binary arrays.
        return np.frombuffer(base64.b64decode(v['bdata']), dtype=v['dtype']) if isinstance(v, dict) else np.asarray(v)
    assert np.allclose(values(annual[1]['y']), res['navs']['연 1회 리밸런싱 전략'].to_numpy())
    assert np.allclose(values(annual[0]['y']), res['navs']['단기채권 ETF 보유'].to_numpy())
    assert f"{res['start']:%Y.%m.%d} ~ {res['end']:%Y.%m.%d}" in md and f'{profile} 배분 규칙' in md


def test_annual_cache_key_includes_profile_version_costs():
    import ast
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'annual_strategy')
    assert [a.arg for a in fn.args.args] == ['profile', 'version', 'bp', 'rf']
    assert any(isinstance(d, ast.Call) and ast.unparse(d.func) == 'st.cache_data' for d in fn.decorator_list)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == 'annual_strategy']
    assert calls and all(ast.unparse(c) == 'annual_strategy(profile, ab.data_version(), ab.BP, ab.RF)' for c in calls)
    assert 'bp=bp, rf=rf' in ast.unparse(fn)
