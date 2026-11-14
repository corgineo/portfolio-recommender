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
    # 아래 12종은 data/extra_data 의 collect_data.py 로 추가한 상품 (열 이름 = etf_prices.csv 열 이름)
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

# ── 3. 설문 ─────────────────────────────────────────────────────────────
QUESTIONS = [
    ('주식이나 펀드에 투자해 본 경험이 있나요?',
     ['전혀 없어요', '1년 미만이에요', '1~3년이에요', '3년 이상이에요']),
    ('이 돈을 투자하는 가장 큰 목적은 무엇인가요?',
     ['원금을 꼭 지키고 싶어요', '예금보다 조금 더 벌고 싶어요',
      '시장 평균만큼 벌고 싶어요', '손실을 감수하고 높은 수익을 원해요']),
    ('투자한 돈이 한 달 만에 10% 떨어졌다면?',
     ['바로 전부 팔래요', '일부만 팔래요', '그대로 기다릴래요', '싸졌으니 더 살래요']),
    ('1년 동안 견딜 수 있는 최대 손실은 어느 정도인가요?',
     ['-5%까지', '-10%까지', '-20%까지', '-30% 이상도 괜찮아요']),
    ('이 투자금은 내 전체 재산 중 어느 정도인가요?',
     ['절반 이상이에요', '30~50%예요', '10~30%예요', '10% 미만이에요']),
]
PERIODS = ['1년 미만', '1~3년', '3년 이상']


def judge_profile(answers, period):
    """설문 답(각 0~3) → 점수(5~20) → 성향. 투자기간이 1년 미만이면 한 단계 보수적으로."""
    score = sum(a + 1 for a in answers)
    level = 0 if score <= 8 else 1 if score <= 12 else 2 if score <= 16 else 3
    adjusted = level
    if period == '1년 미만':
        adjusted = max(level - 1, 0)
    return {'score': score, 'base': PROFILES[level], 'profile': PROFILES[adjusted],
            'adjusted': adjusted != level}


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
    tags = ['#주식초보맞춤']
    tags.append({'안정형': '#원금방어', '안정성장형': '#안정속성장', '성장형': '#균형성장', '공격형': '#적극투자'}[profile])
    g = detail.groupby('group')['weight'].sum()
    if g.get('채권·예금', 0) >= 0.5:
        tags.append('#채권중심')
    if g.get('주식', 0) >= 0.4:
        tags.append('#주식중심')
    overseas = sum(weights.get(n, 0) for n in ['SP500', 'TOPIX', 'CSI300', 'EUROSTOXX50', 'NASDAQ100', 'UST10Y', 'UST30Y_H'])
    if overseas > weights.get('KOSPI200', 0):
        tags.append('#글로벌분산')
    tags.append('#' + MODEL_NAME[MODEL_BY_PROFILE[profile]].split('(')[0].replace(' ', ''))
    tags.append({'1년 미만': '#단기', '1~3년': '#중기', '3년 이상': '#장기'}[period] + '투자')
    return tags
