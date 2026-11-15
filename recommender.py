"""포트폴리오 추천 로직

흐름: 설문 점수 → 투자성향 → 자산군 배분(성향표) → 자산군 안 ETF 비중(수업 모형) → 예산 환산 → 성과 지표
화면(app.py)과 분리해 두어서 팀원이 로직만 따로 고치거나 테스트할 수 있어요.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.optimize as sco

DAYS = 240  # 1년 거래일 수 (강의 기준: 연율화할 때 × 240, 변동성은 × √240)
LOOKBACK_YEARS = 3  # 기대수익률·공분산을 계산할 최근 기간

# ── 1. 투자 상품: 강의 ETF 자산배분 사례의 8종 + 빈틈을 채운 12종 (총 20종) ─────────────────────────────
ETF_INFO = {
    '069500': {'name': 'KOSPI200', 'label': 'KODEX 200 (국내 대형주)', 'group': '주식'},
    '143850': {'name': 'SP500', 'label': 'TIGER 미국S&P500선물 (미국 주식)', 'group': '주식'},
    '195920': {'name': 'TOPIX', 'label': 'TIGER 일본TOPIX (일본 주식)', 'group': '주식'},
    '192090': {'name': 'CSI300', 'label': 'TIGER 차이나CSI300 (중국 주식)', 'group': '주식'},
    '195930': {'name': 'EUROSTOXX50', 'label': 'TIGER 유로스탁스50 (유럽 주식)', 'group': '주식'},
    '122260': {'name': 'KBOND', 'label': 'KIWOOM 통안채1년 (국내 단기채권)', 'group': '채권·예금'},
    '130680': {'name': 'OIL', 'label': 'TIGER 원유선물 (원유)', 'group': '대안투자'},
    '138230': {'name': 'USD', 'label': 'KIWOOM 미국달러선물 (달러)', 'group': '대안투자'},
    # 아래 12종은 collect_data.py 로 추가한 상품 (data/etf_prices.csv 열 이름, 상품 정보는 data/products.csv)
    '132030': {'name': 'GOLD', 'label': 'KODEX 골드선물(H) (금)', 'group': '대안투자'},
    '329200': {'name': 'REIT', 'label': 'TIGER 리츠부동산인프라 (리츠·부동산)', 'group': '대안투자'},
    '133690': {'name': 'NASDAQ100', 'label': 'TIGER 미국나스닥100 (미국 성장주)', 'group': '주식'},
    '161510': {'name': 'DIVIDEND', 'label': 'PLUS 고배당주 (국내 배당주)', 'group': '주식'},
    '114260': {'name': 'KTB3Y', 'label': 'KODEX 국고채3년 (국내 국고채)', 'group': '채권·예금'},
    '153130': {'name': 'SHORTBOND', 'label': 'KODEX 단기채권 (국내 단기채권)', 'group': '채권·예금'},
    '136340': {'name': 'CORPBOND', 'label': 'RISE 중기우량회사채 (국내 회사채)', 'group': '채권·예금'},
    '148070': {'name': 'KTB10Y', 'label': 'KIWOOM 국고채10년 (국내 장기채권)', 'group': '채권·예금'},
    '305080': {'name': 'UST10Y', 'label': 'TIGER 미국채10년선물 (미국 장기국채)', 'group': '채권·예금'},
    '304660': {'name': 'UST30Y_H', 'label': 'KODEX 미국30년국채울트라선물(H) (미국 장기국채)', 'group': '채권·예금'},
    '284430': {'name': 'MIX_K200_UST', 'label': 'KODEX 200미국채혼합50 (주식·채권 혼합)', 'group': '자산배분'},
    '251600': {'name': 'MIX_DIVIDEND', 'label': 'PLUS 고배당주채권혼합 (주식·채권 혼합)', 'group': '자산배분'},
}
NAME_TO_LABEL = {v['name']: v['label'] for v in ETF_INFO.values()}
NAME_TO_LABEL['CASH'] = '현금 (CMA·예금)'
CASH = 'CASH'
ETF_NAMES = [v['name'] for v in ETF_INFO.values()]
DATA_FILE = Path(__file__).parent / 'data' / 'etf_prices.csv'
STOCK_FILE = Path(__file__).parent / 'data' / 'stock_prices.csv'   # update_stock_data.py 가 만든 팩터 종목 가격
STOCK_SHARE = 0.5   # 주식 몫 중 개별 종목으로 담는 비율
EXTRA_DIR = Path(__file__).parent / 'data'    # collect_data.py 결과 (개별주 가격·상품정보)
MIN_WEIGHT = 0.03   # 상품 하나의 최소 비중. 이보다 작은 상품은 빼고 같은 자산군의 나머지에 다시 나눠요
MAX_STOCKS = 10     # 개별 종목 최대 개수 (종목 하나당 최소 비중 MIN_WEIGHT 를 지키도록 개수는 비중에서 계산)

# ── 자산군 색: 주식 빨강/주황 · 채권 파랑 · 대안투자 초록 · 자산배분 보라 · 현금 회색 (도넛·막대·표 모두 같은 규칙) ──
GROUP_SHADES = {
    '채권·예금': ['#1d4ed8', '#3b82f6', '#60a5fa', '#1e40af', '#93c5fd', '#2563eb', '#bfdbfe'],
    '주식': ['#dc2626', '#f97316', '#ef4444', '#fb923c', '#b91c1c', '#ea580c', '#f87171', '#fdba74',
             '#991b1b', '#c2410c', '#fca5a5', '#fed7aa', '#e11d48', '#d97706', '#be123c', '#f59e0b'],
    '대안투자': ['#16a34a', '#4ade80', '#15803d', '#86efac', '#22c55e', '#166534'],
    '자산배분': ['#7c3aed', '#a78bfa', '#6d28d9', '#c4b5fd'],
    '유동성': ['#98a2b3'],
}
GROUP_BASE = {'채권·예금': '#2563eb', '주식': '#ef4444', '대안투자': '#16a34a', '자산배분': '#8b5cf6', '유동성': '#98a2b3'}


def group_of(name):
    """상품 이름(열 이름) → 자산군. 개별 종목(팩터·거래대금 상위)은 주식, CASH 는 유동성"""
    if name == CASH:
        return '유동성'
    for v in ETF_INFO.values():
        if v['name'] == name:
            return v['group']
    return '주식'


def color_map(names, group_of=group_of):
    """상품 이름 목록(보통 비중 큰 순) → 색. 같은 자산군 안에서는 순서대로 진한 색부터 써요."""
    used, out = {}, {}
    for n in names:
        g = group_of(n)
        shades = GROUP_SHADES.get(g, ['#98a2b3'])
        i = used.get(g, 0)
        out[n] = shades[i % len(shades)]
        used[g] = i + 1
    return out


# ── 2. 투자성향별 자산군 배분 (법률신문 기사 〈그림 1〉 수치, 팀 논의 후 수정 예정) ──
PROFILES = ['안정형', '안정성장형', '성장형', '공격형']
PROFILE_TABLE = {
    #            채권·예금 주식  대안투자 자산배분 유동성 | 기사 속 목표수익률 / 위험
    '안정형':     {'채권·예금': 73, '주식': 5,  '대안투자': 2,  '자산배분': 10, '유동성': 10, 'target': (7, 3.2)},
    '안정성장형': {'채권·예금': 39, '주식': 9,  '대안투자': 26, '자산배분': 16, '유동성': 10, 'target': (9, 7.4)},
    '성장형':     {'채권·예금': 24, '주식': 26, '대안투자': 30, '자산배분': 10, '유동성': 10, 'target': (11, 12)},
    '공격형':     {'채권·예금': 10, '주식': 44, '대안투자': 26, '자산배분': 10, '유동성': 10, 'target': (13, 17)},
}
GROUPS = ['채권·예금', '주식', '대안투자', '자산배분', '유동성']

# 성향별로 자산군 안에서 쓸 수업 모형
MODEL_BY_PROFILE = {'안정형': 'MVP', '안정성장형': 'MVP', '성장형': 'RP', '공격형': 'RP'}
MODEL_NAME = {'MVP': '최소분산 포트폴리오', 'RP': '위험균형(리스크 패리티)'}

# ── 3. 설문: 투자성향 파악 설문 7문항 (투자성향_자산배분 자료의 문항·선택지를 그대로 사용) ──
QUESTIONS = [
    ('당신의 나이는?', ['~ 44세', '45 – 55', '56 – 65', '66 – 75', '76세 ~']),
    ('당신의 투자 기간은?', ['20년 이상', '11 – 19년', '6 – 10년', '1 – 5년', '1년 이내']),
    ('당신이 우선 고려 하는 투자는?',
     ['무조건 수익률 우선', '원금보전 고려하나 수익률 우선', '수익률과 원금보전 동일하게 고려',
      '수익률 고려하나 원금보전 우선', '어떤 경우라도 원금보전 우선']),
    ('정상적인 주식시장상황에서 이번 투자에서 기대하는 수익은?',
     ['시장 수익률은 상회해야 한다', '시장수익률 수준은 따라가야 한다', '시장 수익률 하회해도 평균적인 수익은 내야',
      '어느 정도의 안정성과 평균적인 수익은 내야', '안정성이 확보되면서 약간의 수익은 내야']),
    ('향후 10년간 주식시장 침체가 예상될 때 나의 투자성과는?',
     ['부진할 수 있다', '원금 수준은 유지해야 한다', '약간의 수익은 나야 한다', '꽤 괜찮은 수익을 기대한다',
      '어떤 경우라도 수익이 나야 한다']),
    ('향후 3년 투자시 투자성과에 대한 당신의 생각은?',
     ['원금 손실가능성 인정', '대부분의 손실은 감내 가능', '약간의 손실은 감내 가능', '어떤 손실도 감내 어려움',
      '약간의 수익이라도 내야']),
    ('향후 3개월 투자시 투자손실에 대한 당신의 생각은?',
     ['시장변화에 크게 신경 쓰지 않는다.', '20% 이상 손실발생시 걱정한다.', '10% 이상 손실발생시 걱정한다.',
      '작은 시장변화는 감내한다.', '어떤 투자손실도 견디기 힘들다.']),
]
TOPICS = ['나이', '투자 기간', '우선 고려', '기대 수익', '10년 침체 시', '3년 투자 성과', '3개월 손실']
# 원 자료에는 선택지별 점수가 없어요. 모든 문항이 ①이 가장 공격적, ⑤가 가장 보수적인 순서라 ①4점 … ⑤0점으로 둬요.
POINTS = [4, 3, 2, 1, 0]
MAX_SCORE = POINTS[0] * len(QUESTIONS)          # 28점
# 스코어링 기준(원 자료 그대로): 25점 이상 공격 추구형 · 11~24점 위험 중립형 · 10점 이하 안정 추구형
TYPES = [  # (최저점, 최고점, 투자성향, 주요 특징)
    (0, 10, '안정 추구형', '약간의 리스크만을 허용하고, 물가수준 이상의 수익을 추구하는 투자자'),
    (11, 24, '위험 중립형', '적당한 리스크를 허용하여 장기적으로 완만한 수익을 추구하는 투자자'),
    (25, MAX_SCORE, '공격 추구형', '금융시장의 큰 변동성을 감수하면서 고수익을 기대하는 투자자'),
]
# 투자성향 → 자산배분표(법률신문 4단계). 위험 중립형은 범위(11~24점)가 넓어 가운데(17/18점)에서 둘로 나눠요.
ALLOC_BANDS = [  # (최저점, 최고점, 자산배분표 이름)
    (0, 10, '안정형'), (11, 17, '안정성장형'), (18, 24, '성장형'), (25, MAX_SCORE, '공격형'),
]
PERIOD_LABEL = ['20년 이상', '11~19년', '6~10년', '1~5년', '1년 이내']   # 2번 문항 답 → 투자 기간


def judge_profile(answers):
    """설문 답(각 0~4, ①=0) → 점수(0~28) → 투자성향(3단계) + 자산배분표(4단계)"""
    if len(answers) != len(QUESTIONS) or any(a is None or not 0 <= a < len(POINTS) for a in answers):
        raise ValueError('7문항에 모두 답해야 해요.')
    points = [POINTS[a] for a in answers]
    score = sum(points)
    kind = next(t for t in TYPES if t[0] <= score <= t[1])
    band = next(b for b in ALLOC_BANDS if b[0] <= score <= b[1])
    return {'score': score, 'points': points, 'type': kind[2], 'type_desc': kind[3],
            'type_range': (kind[0], kind[1]), 'profile': band[2], 'band_range': (band[0], band[1]),
            'period': PERIOD_LABEL[answers[1]], 'short_term': answers[1] == 4}



# ── 4. 입력값: 기대수익률과 공분산 (강의: 일간수익률 평균 × 240, 공분산 × 240) ──
def load_prices(path=DATA_FILE, with_stocks=False, with_candidates=False):
    """ETF 20종 가격. with_stocks=True 면 팩터 종목 가격, with_candidates=True 면 거래대금 상위 개별주(국내·해외 원화환산)
    가격도 옆에 붙여요 (상장 전 날짜는 NaN)"""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if with_stocks:
        stock = pd.read_csv(STOCK_FILE, index_col=0, parse_dates=True)
        df = df.join(stock)
    if with_candidates and STOCK_CATALOG is not None:
        for fname in ('stock_kr.csv', 'stock_us.csv'):
            df = df.join(pd.read_csv(EXTRA_DIR / fname, index_col=0, parse_dates=True))
    return df


def load_stock_catalog():
    """products.csv 의 개별 주식 (열 이름 → 종목코드·이름·세부군·평균거래대금). 파일이 없으면 None"""
    try:
        p = pd.read_csv(EXTRA_DIR / 'products.csv', dtype={'code': str})
    except FileNotFoundError:
        return None
    return p[p['type'] == '주식'].set_index('price_column')[['code', 'name', 'sub_class', 'currency', 'avg_amount_krw']]


STOCK_CATALOG = load_stock_catalog()
if STOCK_CATALOG is not None:                      # 화면·표에 쓸 이름 (ETF 와 같은 NAME_TO_LABEL 에 합침)
    for _col, _r in STOCK_CATALOG.iterrows():
        NAME_TO_LABEL[_col] = _r['name'] + ' (' + _r['sub_class'] + ')'


def model_inputs(prices, end=None):
    """end 를 주면 그날까지의 데이터만 써요 (백테스팅에서 과거 시점마다 다시 계산할 때)"""
    if end is not None:
        prices = prices.loc[:end]
    recent = prices.loc[prices.index[-1] - pd.DateOffset(years=LOOKBACK_YEARS):]
    # 최근 기간 내내 가격이 있는 ETF 만 사용 (상장이 늦어 그 시점에 3년이 안 되는 ETF 는 그 시점 계산에서 제외. 백테스트 과거 시점용)
    etfs = [c for c in ETF_NAMES if c in recent.columns and recent[c].notna().all()]
    rets = recent.pct_change().dropna(subset=etfs)  # 일간수익률 (개별 종목은 상장 전이면 NaN)
    avg_returns = rets[etfs].mean() * DAYS         # 연율화 기대수익률
    cov_mat = rets[etfs].cov() * DAYS              # 연율화 공분산 행렬 (최적화는 ETF 끼리만)
    return rets, avg_returns, cov_mat


# ── 5. 수업 모형 (자산배분모형_종합_2026.ipynb 함수와 같은 방식) ──────────────
def get_portf_vol(weight, cov_mat):
    """포트폴리오 변동성 = √(wᵀ Σ w)"""
    return np.sqrt(weight.T @ cov_mat @ weight)


def minimum_variance(cov_mat):
    """최소분산 포트폴리오: 변동성을 가장 작게 만드는 비중 (비중합 1, 0~1)"""
    n = cov_mat.shape[0]
    res = sco.minimize(get_portf_vol, n * [1. / n], args=(cov_mat,), method='SLSQP',
                       bounds=[(0, 1)] * n,
                       constraints={'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
    return res.x


def risk_contribution(weight, cov_mat):
    """자산별 위험기여도 RC = w × (Σw / σp)"""
    std = np.sqrt(weight.T @ cov_mat @ weight)
    mrc = (cov_mat @ weight) / std                 # 한계 위험기여도
    return weight * mrc, std


def risk_parity(cov_mat):
    """위험균형 포트폴리오: 모든 자산의 위험기여도가 σp / n 으로 같아지는 비중"""
    n = cov_mat.shape[0]

    def target(weight):
        rc, std = risk_contribution(weight, cov_mat)
        return np.sum(np.square(rc - std / n))

    res = sco.minimize(target, n * [1. / n], method='SLSQP', bounds=[(0, 1)] * n,
                       constraints={'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
                       tol=1e-20)
    return res.x


def optimize(names, cov_mat, model):
    """자산군 안의 상품들에 모형을 적용해 비중(합 1)을 돌려줘요"""
    if len(names) == 1:
        return pd.Series(1.0, index=names)
    sub = cov_mat.loc[names, names].values
    w = minimum_variance(sub) if model == 'MVP' else risk_parity(sub)
    w = np.clip(w, 0, None)
    return pd.Series(w / w.sum(), index=names)


# ── 6. 추천 비중 만들기 ─────────────────────────────────────────────────
def stock_sleeve(etf_names, cov_mat, model, picks, group_pct=None):
    """주식 몫 = ETF 최적화 비중 × (1 − STOCK_SHARE) + 팩터 종목 같은 비중 × STOCK_SHARE"""
    etf_w = optimize(etf_names, cov_mat, model)
    if group_pct:                                      # ETF 쪽만 최소 비중 정리 (개별 종목이 ETF 몫을 다 가져가지 않게)
        etf_w = apply_min_weight(etf_w, group_pct * (1 - STOCK_SHARE if picks else 1))
    if not picks:
        return etf_w
    stock_w = pd.Series(1 / len(picks), index=picks)
    return pd.concat([etf_w * (1 - STOCK_SHARE), stock_w * STOCK_SHARE])


def choose_picks(profile, prices, budget, factor_names=None):
    """개별 종목 고르기: 반은 팩터 종목(factor.py), 반은 거래대금 상위 종목 (products.csv 의 avg_amount_krw 순).
    - 개수 = (성향표 주식 비중 × STOCK_SHARE) ÷ MIN_WEIGHT 의 몫 (최대 MAX_STOCKS). 0개면 ETF 만 써요.
    - 최근 LOOKBACK_YEARS 년 내내 가격이 있고, 예산으로 1주 이상 살 수 있는 종목만 (못 사면 다음 순위로)
    """
    total = PROFILE_TABLE[profile]['주식'] / 100 * STOCK_SHARE
    n = min(MAX_STOCKS, int(total / MIN_WEIGHT + 1e-9))
    if n == 0:
        return []
    per_amount = budget * total / n                               # 종목 하나에 배정되는 금액
    px = prices.ffill()
    start = px.index[-1] - pd.DateOffset(years=LOOKBACK_YEARS)

    def ok(name):
        return name in px.columns and px.loc[start:, name].notna().all() and px[name].iloc[-1] <= per_amount

    if factor_names is None:
        try:
            factor_names = current_picks()
        except Exception:
            factor_names = []
    ranked = [] if STOCK_CATALOG is None else \
        list(STOCK_CATALOG.dropna(subset=['avg_amount_krw']).sort_values('avg_amount_krw', ascending=False).index)
    chosen = []
    for source, k in ((factor_names, n // 2), (ranked, n - n // 2)):
        for name in source:
            if k == 0:
                break
            if name not in chosen and ok(name):
                chosen.append(name)
                k -= 1
    for name in list(factor_names) + ranked:                      # 한쪽이 모자라면 남은 후보로 채움
        if len(chosen) >= n:
            break
        if name not in chosen and ok(name):
            chosen.append(name)
    return chosen


def apply_min_weight(sleeve, group_pct):
    """자산군 안 비중(합 1)에서 가장 작은 상품부터 하나씩 빼며 다시 합 1로 맞춰요.
    남은 상품의 최종 비중(자산군 비중 × 안 비중)이 모두 MIN_WEIGHT 이상이 되거나 하나만 남으면 멈춰요."""
    w = sleeve[sleeve > 0]
    w = w / w.sum()
    while len(w) > 1 and (w * group_pct / 100).min() < MIN_WEIGHT:
        w = w.drop(w.idxmin())
        w = w / w.sum()
    return w


def build_portfolio(profile, cov_mat, picks=None):
    """성향표의 자산군 비중 × 자산군 안 비중 = 최종 상품별 비중

    picks: 팩터 종목명 리스트 (factor.py). 주면 주식 몫의 STOCK_SHARE 만큼을 이 종목들로 나눠 담아요.
           안 주면(None) 지금처럼 ETF 만 써요.
    """
    table = PROFILE_TABLE[profile]
    model = MODEL_BY_PROFILE[profile]
    usable = set(cov_mat.index)                       # 그 시점에 3년 데이터가 있는 ETF 만
    by_group = {g: [v['name'] for v in ETF_INFO.values() if v['group'] == g and v['name'] in usable]
                for g in ['채권·예금', '주식', '대안투자', '자산배분']}
    if not by_group['자산배분']:                       # 혼합형 ETF 가 아직 3년이 안 된 과거 시점: 쓸 수 있는 ETF 전체를 위험균형으로
        by_group['자산배분'] = [v['name'] for v in ETF_INFO.values() if v['name'] in usable]

    sleeves = {
        '채권·예금': optimize(by_group['채권·예금'], cov_mat, model),
        '주식': stock_sleeve(by_group['주식'], cov_mat, model, picks, table['주식']),
        '대안투자': optimize(by_group['대안투자'], cov_mat, model),
        '자산배분': optimize(by_group['자산배분'], cov_mat, 'RP'),      # 주식·채권 혼합형 ETF 를 위험균형으로 섞은 묶음
        '유동성': pd.Series(1.0, index=[CASH]),
    }
    for g in ['채권·예금', '대안투자', '자산배분']:                  # 너무 작은 비중은 정리 (주식은 stock_sleeve 안에서)
        if table[g] > 0:
            sleeves[g] = apply_min_weight(sleeves[g], table[g])
    rows = []
    for g in GROUPS:
        for name, w in sleeves[g].items():
            rows.append({'group': g, 'name': name, 'weight': table[g] / 100 * w})
    detail = pd.DataFrame(rows)
    weights = detail.groupby('name')['weight'].sum()
    weights = weights[weights > 0.0005].sort_values(ascending=False)
    return weights / weights.sum(), detail, sleeves


def current_picks(date=None):
    """지금(또는 date 시점) 들고 있어야 할 팩터 종목명 리스트 → build_portfolio(..., picks=) 에 넣어요"""
    import factor
    picks = factor.load_picks()
    return factor.picks_on(picks, date if date is not None else picks['리밸런싱일'].max())


# ── 7. 예산 → 금액·수량 ────────────────────────────────────────────────
def allocate_budget(weights, prices, budget):
    last = prices.ffill().iloc[-1]                  # 개별 종목은 마지막 날 가격이 비어 있으면 직전 가격
    rows, spent = [], 0
    for name, w in weights.items():
        if name == CASH:
            continue
        price = last[name]
        qty = int(budget * w // price)             # 1주 단위로 살 수 있는 수량
        cost = qty * price
        spent += cost
        rows.append({'상품': NAME_TO_LABEL.get(name, name), '비중(%)': w * 100, '금액(원)': cost,
                     '현재가(원)': price, '수량(주)': qty})
    rows.append({'상품': NAME_TO_LABEL[CASH], '비중(%)': weights.get(CASH, 0) * 100,
                 '금액(원)': budget - spent, '현재가(원)': None, '수량(주)': None})
    return pd.DataFrame(rows)


# ── 8. 성과 지표 (강의: 연율화 수익률·변동성, 샤프비율, MDD) ────────────────
def performance(weights, rets):
    r = rets.fillna(0)                             # 개별 종목 상장 전 날짜는 0
    r[CASH] = 0.0                                  # 초안: 현금 수익률 0으로 가정
    port = r[weights.index] @ weights.values       # 매일 같은 비중을 유지한다고 가정
    ann_ret = port.mean() * DAYS
    ann_vol = port.std() * np.sqrt(DAYS)
    index_100 = (1 + port).cumprod() * 100         # 강의 index_100 함수와 같은 누적성과
    peak = index_100.cummax()
    mdd = (index_100 / peak - 1).min()
    return {'return': ann_ret, 'vol': ann_vol, 'sharpe': ann_ret / ann_vol if ann_vol else 0,
            'mdd': mdd, 'index': index_100}


def benchmark_index(rets, name='KOSPI200'):
    return (1 + rets[name]).cumprod() * 100


def safe_index(rets):
    """비교 기준: 예금처럼 안전한 단기채권(통안채 ETF)에만 넣었을 때의 누적성과"""
    return benchmark_index(rets, 'KBOND')


# ── 9. 해시태그 ───────────────────────────────────────────────────────
def hashtags(profile, period, weights, detail):
    """period: judge_profile()['period'] (설문 2번 문항 답, 예: '6~10년')"""
    tags = ['#주식초보맞춤']
    tags.append({'안정형': '#원금방어', '안정성장형': '#안정속성장', '성장형': '#균형성장', '공격형': '#적극투자'}[profile])
    g = detail.groupby('group')['weight'].sum()
    if g.get('채권·예금', 0) >= 0.5:
        tags.append('#채권중심')
    if g.get('주식', 0) >= 0.4:
        tags.append('#주식중심')
    us = set() if STOCK_CATALOG is None else set(STOCK_CATALOG.index[STOCK_CATALOG['currency'] == 'USD'])
    overseas = sum(v for n, v in weights.items()
                   if n in us or n in ['SP500', 'TOPIX', 'CSI300', 'EUROSTOXX50', 'NASDAQ100', 'UST10Y', 'UST30Y_H'])
    if overseas > weights.get('KOSPI200', 0):
        tags.append('#글로벌분산')
    tags.append('#' + MODEL_NAME[MODEL_BY_PROFILE[profile]].split('(')[0].replace(' ', ''))
    tags.append('#단기투자' if period == '1년 이내' else '#중기투자' if period == '1~5년' else '#장기투자')
    return tags
