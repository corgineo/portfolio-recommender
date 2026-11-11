"""팀프로젝트 데이터 수집·정리 스크립트
- 강의 7주차(자산배분모형_종합_2026)의 ETF 티커/수집 방식, 2주차 FinanceDataReader 사용법을 그대로 활용
- 결과물(data 폴더), 가격 파일은 모두 팀원 초안 앱 형식(Date + 영문 약칭 열):
  etf_prices.csv(앱용 8종, 팀원 update_data.py 결과와 동일), etf_prices_ext.csv(보강 포함 17종),
  stock_prices.csv(개별주식 7종), products.csv(상품정보)
"""
import os
import pandas as pd
import FinanceDataReader as fdr

START = '2016-01-01'          # 초안 앱(update_data.py)과 같은 시작일
END = None                    # None이면 오늘까지
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

# (코드: [상품명, 유형, 자산군, 세부군])
# 1) 강의 7주차 ETF 8종 (초안 앱과 동일)
# (상품명은 StockListing('ETF/KR') 기준 현재 이름. 초안 앱의 KOSEF 표기는 KIWOOM으로 바뀜)
PRODUCTS = {
    '069500': ['KODEX 200',                'ETF', '주식',     '국내 대형주 200'],
    '122260': ['KIWOOM 통안채1년',          '채권', '채권·예금', '국내 단기채권'],
    '195920': ['TIGER 일본TOPIX(합성 H)',   'ETF', '주식',     '일본 주식'],
    '143850': ['TIGER 미국S&P500선물(H)',   'ETF', '주식',     '미국 주식'],
    '192090': ['TIGER 차이나CSI300',        'ETF', '주식',     '중국 주식'],
    '195930': ['TIGER 유로스탁스50(합성 H)', 'ETF', '주식',     '유럽 주식'],
    '130680': ['TIGER 원유선물Enhanced(H)', 'ETF', '대안투자',  '원유'],
    '138230': ['KIWOOM 미국달러선물',       'ETF', '대안투자',  '미국 달러'],
}

# 2) 초안 앱의 빈틈 보강 (자산군별 부족한 상품)
#    - 대안투자: 선택지가 원유·달러뿐 → 금 (기사: 대안투자에 귀금속 등 실물자산 포함)
#    - 주식   : 미국 성장주(나스닥100), 배당(결과화면 배당 차트용) 추가
#    - 자산배분: 전용 상품 없음 → 주식+채권 혼합형 ETF (기사의 '자산배분펀드'에 해당)
#    ※ 284430은 2017-11, 251600은 2016-08 상장이라 그 이전 구간은 빈 값(NaN)
GAP_PRODUCTS = {
    '132030': ['KODEX 골드선물(H)',      'ETF', '대안투자',  '금'],
    '133690': ['TIGER 미국나스닥100',     'ETF', '주식',     '미국 성장주'],
    '161510': ['PLUS 고배당주',           'ETF', '주식',     '국내 배당주'],
    '284430': ['KODEX 200미국채혼합50',   'ETF', '자산배분',  '주식·채권 혼합'],
    '251600': ['PLUS 고배당주채권혼합',    'ETF', '자산배분',  '주식·채권 혼합'],
}

# 3) 추가 후보 (채권 선택지 확대, 개별주식). 코드는 실행 시 검증하고 실패하면 자동 제외
EXTRA_PRODUCTS = {
    '114260': ['KODEX 국고채3년',      '채권', '채권·예금', '국내 국고채'],
    '153130': ['KODEX 단기채권',       '채권', '채권·예금', '국내 단기채권'],
    '136340': ['RISE 중기우량회사채',   '채권', '채권·예금', '국내 회사채'],
    '148070': ['KIWOOM 국고채10년',    '채권', '채권·예금', '국내 장기채권'],
    '005930': ['삼성전자',  '주식', '주식', '국내 개별주'],
    '000660': ['SK하이닉스', '주식', '주식', '국내 개별주'],
    '005380': ['현대차',    '주식', '주식', '국내 개별주'],
    '035420': ['NAVER',     '주식', '주식', '국내 개별주'],
    '028260': ['삼성물산',  '주식', '주식', '국내 개별주'],
    '017670': ['SK텔레콤',  '주식', '주식', '국내 개별주'],
    '033780': ['KT&G',      '주식', '주식', '국내 개별주'],
}


# 팀원 초안 앱 형식(etf_prices.csv)용 영문 열 이름. 앞 8개는 초안과 같은 이름·순서, 뒤는 추가분
APP_COLUMNS = {
    '069500': 'KOSPI200', '143850': 'SP500', '195920': 'TOPIX', '192090': 'CSI300',
    '195930': 'EUROSTOXX50', '122260': 'KBOND', '130680': 'OIL', '138230': 'USD',
    '132030': 'GOLD', '133690': 'NASDAQ100', '161510': 'DIVIDEND',
    '284430': 'MIX_K200_UST', '251600': 'MIX_DIVIDEND',
    '114260': 'KTB3Y', '153130': 'SHORTBOND', '136340': 'CORPBOND', '148070': 'KTB10Y',
}


# 개별주식용 영문 열 이름 (stock_prices.csv)
APP_STOCK_COLUMNS = {
    '005930': 'SAMSUNG', '000660': 'HYNIX', '005380': 'HYUNDAI', '035420': 'NAVER',
    '028260': 'SAMSUNGCT', '017670': 'SKT', '033780': 'KTNG',
}


def load_close(code):
    """종목 하나의 종가 Series. 실패/빈 데이터면 None"""
    try:
        raw = fdr.DataReader(code, START, END)
    except Exception as e:
        print(f'  [제외] {code}: {e}')
        return None
    if raw is None or raw.empty:
        print(f'  [제외] {code}: 데이터 없음')
        return None
    return raw['Close'].rename(code)


def clean(df):
    """날짜 정렬, 중복 제거, 비영업일/휴장일 결측 앞값 채움"""
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    df = df[~df.index.duplicated(keep='last')].sort_index()   # 날짜 오름차순
    df = df.ffill(limit=5)                                    # 휴장일 결측만 채움(상장 전 구간은 NaN 유지)
    return df.dropna(how='all')


def save_csv(df, fname, encoding):
    """저장. Excel 등에서 파일이 열려 있으면 경고만 내고 다음 파일로 진행"""
    try:
        df.to_csv(os.path.join(OUT_DIR, fname), encoding=encoding, lineterminator='\n')   # 앱 파일과 같은 LF 줄바꿈
    except PermissionError:
        print(f'  [경고] {fname}이(가) 열려 있어 저장하지 못했습니다. 파일을 닫고 다시 실행하세요.')


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    catalog = {**PRODUCTS, **GAP_PRODUCTS, **EXTRA_PRODUCTS}
    closes = {}
    for code in catalog:
        s = load_close(code)
        if s is not None:
            closes[code] = s
    price = clean(pd.concat(closes.values(), axis=1))

    # 상품정보: 수동 분류 + 실제 데이터 기간
    products = pd.DataFrame(
        [[c] + catalog[c] for c in price.columns],
        columns=['code', 'name', 'type', 'asset_class', 'sub_class'],
    ).set_index('code')
    products['first_date'] = price.apply(lambda s: s.first_valid_index()).dt.date
    products['last_date'] = price.apply(lambda s: s.last_valid_index()).dt.date

    # 시가총액 등 KRX 상장 정보 병합 (2주차 StockListing 활용, 실패해도 진행)
    try:
        krx = fdr.StockListing('KRX').set_index('Code')
        extra = krx[[c for c in ['Market', 'Marcap', 'Sector'] if c in krx.columns]]
        products = products.join(extra)
    except Exception as e:
        print(f'  [참고] StockListing 병합 생략: {e}')

    # 초안 앱 형식: Date + 영문 약칭 열 한 파일, 인코딩은 앱(update_data.py)과 같은 utf-8-sig
    #  - etf_prices.csv     : 앱이 읽는 8종 (recommender.ETF_INFO와 같은 열·순서). update_data.py 결과와 동일
    #  - etf_prices_ext.csv : 보강 종목까지 17종 (앱에서 쓰려면 ETF_INFO에 항목 추가 필요)
    #  - stock_prices.csv   : 개별주식 7종 (앱 미사용)
    app_codes = list(APP_COLUMNS)[:8]
    outputs = [
        (app_codes, APP_COLUMNS, 'etf_prices.csv'),
        (list(APP_COLUMNS), APP_COLUMNS, 'etf_prices_ext.csv'),
        (list(APP_STOCK_COLUMNS), APP_STOCK_COLUMNS, 'stock_prices.csv'),
    ]
    for codes, mapping, fname in outputs:
        app_df = price[[c for c in codes if c in price.columns]].rename(columns=mapping)
        if fname == 'etf_prices.csv':
            app_df = app_df.dropna()          # 앱과 같은 방식: 8종 모두 가격이 있는 날만 사용
        app_df.index.name = 'Date'
        save_csv(app_df, fname, 'utf-8-sig')

    save_csv(products, 'products.csv', 'utf-8-sig')

    # 점검 출력
    print('\n[수집 결과]')
    print(products[['name', 'type', 'asset_class', 'first_date', 'last_date']])
    print('\n기간:', price.index.min().date(), '~', price.index.max().date(), '/ 행수', len(price))
    print('날짜 오름차순:', price.index.is_monotonic_increasing, '/ 중복 날짜:', price.index.duplicated().sum())
    print('남은 결측(상장 전 구간 포함):\n', price.isna().sum()[price.isna().sum() > 0])


if __name__ == '__main__':
    main()
