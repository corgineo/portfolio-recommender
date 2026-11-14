"""팀프로젝트 데이터 수집·정리 스크립트
- 강의 7주차(자산배분모형_종합_2026)의 ETF 티커/수집 방식, 2주차 FinanceDataReader 사용법을 그대로 활용
- 결과물(data 폴더): 가격 파일 3개 + 상품정보 1개, 모두 Date 열 + 상품별 열, utf-8-sig, LF
  etf_prices.csv  : ETF 20종 (앞 8종은 팀원 초안 앱과 같은 열 이름·순서, 영문 약칭). 상장 전 구간은 빈 칸
  stock_kr.csv    : 국내 개별주 23종 (열 이름 = 종목명, 원화)
  stock_us.csv    : 해외 개별주 20종 (열 이름 = 티커, 원/달러 환율로 원화 환산한 가격)
  products.csv    : 상품정보 (price_file·price_column으로 가격이 어느 파일·열에 있는지 안내)
  ※ 저장소의 data/stock_prices.csv는 팩터 종목용(update_stock_data.py)이라 이름이 겹치지 않게 stock_kr/us로 정함
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
    # 국내 상장 해외 채권·리츠 (상장 3년 이상 확인: 2018-08, 2018-09, 2019-07)
    '305080': ['TIGER 미국채10년선물',          '채권', '채권·예금', '미국 장기국채'],
    '304660': ['KODEX 미국30년국채울트라선물(H)', '채권', '채권·예금', '미국 장기국채'],
    '329200': ['TIGER 리츠부동산인프라',         'ETF', '대안투자',  '리츠·부동산'],
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
    '305080': 'UST10Y', '304660': 'UST30Y_H', '329200': 'REIT',
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


CANDIDATES = os.path.join(OUT_DIR, '후보종목_거래대금상위.csv')       # select_universe.py 가 data 폴더에 저장한 후보 목록


def collect_candidates(market='국내', fname='stock_prices_kr20.csv'):
    """select_universe.py가 뽑은 후보 중 해당 구분(국내/해외) 종목의 종가를 받아 저장 (열 이름 = 종목명)
    상장 전 구간은 NaN, 휴장일 결측만 앞날 값으로 채움. 해외는 달러 가격이라 원화 환산이 따로 필요함"""
    if not os.path.exists(CANDIDATES):
        print(f'  [참고] {os.path.basename(CANDIDATES)}가 없어 후보 종목 수집을 건너뜁니다. select_universe.py를 먼저 실행하세요.')
        return
    cand = pd.read_csv(CANDIDATES, dtype={'code': str})
    cand = cand[cand['구분'] == market]
    closes = {}
    for code, name in zip(cand['code'], cand['name']):
        s = load_close(code)
        if s is not None:
            closes[name] = s.rename(name)
    df = clean(pd.concat(closes.values(), axis=1))
    df.index.name = 'Date'
    if fname:
        save_csv(df, fname, 'utf-8-sig')
    print(f'\n[{market} 후보 {len(df.columns)}/{len(cand)}종목] {df.index.min().date()} ~ {df.index.max().date()} / 행수 {len(df)}')
    print('상장 전 결측:', df.isna().sum()[df.isna().sum() > 0].to_dict())
    return df


def collect_candidates_krw(market='해외', fname='stock_prices_us20_krw.csv'):
    """후보 중 해외 종목의 달러 종가를 받아 '그날 원/달러 환율'을 곱한 원화 환산 가격으로 저장 (열 이름 = 티커)
    - 날짜는 한국 거래일(삼성전자 거래일) 기준. 미국 휴장일에는 앞날 미국 종가를 그대로 씀(최대 5일)
    - 같은 날짜의 미국 종가와 환율을 곱하는 단순 환산 (미국 종가는 한국 장 마감 뒤라 하루 시차는 무시)
    - 원화 환산이라 수익률에 환율 변동이 반영됨. 앱은 이 가격을 국내 종목처럼 다루면 됨"""
    if not os.path.exists(CANDIDATES):
        print(f'  [참고] {os.path.basename(CANDIDATES)}가 없어 건너뜁니다. select_universe.py를 먼저 실행하세요.')
        return
    cand = pd.read_csv(CANDIDATES, dtype={'code': str})
    codes = cand.loc[cand['구분'] == market, 'code']
    usd = pd.concat([s for s in (load_close(c) for c in codes) if s is not None], axis=1)
    usd.index = pd.to_datetime(usd.index)
    usd = usd[~usd.index.duplicated(keep='last')].sort_index()
    fx = fdr.DataReader('USD/KRW', START, END)['Close']                  # 원/달러
    fx.index = pd.to_datetime(fx.index)
    kr_days = pd.to_datetime(fdr.DataReader('005930', START, END).index)  # 한국 거래일 달력

    usd_kr = usd.reindex(usd.index.union(kr_days)).ffill(limit=5).reindex(kr_days)
    fx_kr = fx.reindex(fx.index.union(kr_days)).ffill(limit=5).reindex(kr_days)
    krw = usd_kr.mul(fx_kr, axis=0).dropna(how='all').round(2)
    krw.index.name = 'Date'
    if fname:
        save_csv(krw, fname, 'utf-8-sig')
    print(f'\n[{market} 후보 {len(krw.columns)}/{len(codes)}종목, 원화 환산] {krw.index.min().date()} ~ {krw.index.max().date()} / 행수 {len(krw)}'
          f' / 마지막 환율 {fx_kr.dropna().iloc[-1]:,.1f}원')
    print('상장 전 결측:', krw.isna().sum()[krw.isna().sum() > 0].to_dict())
    return krw


def candidate_products(cand, kr, us):
    """후보 종목(국내·해외)의 상품정보 행. 가격은 이미 받은 kr/us 가격표에서 찾고, 데이터 기간도 거기서 계산
    - 해외는 sub_class에 반도체·AI 구분을 담음(열을 따로 만들지 않음). 가격 파일은 원화 환산 가격이고 currency는 원래 통화
    - 같은 코드가 이미 있는 종목은 호출하는 쪽에서 미리 제외"""
    from select_universe import tech_tag          # 반도체·AI 분류 기준을 한 곳에서 관리
    rows = []
    for _, r in cand.iterrows():
        domestic = r['구분'] == '국내'
        prices, col = (kr, r['name']) if domestic else (us, r['code'])
        if prices is None or col not in prices.columns:
            continue
        tag = '' if domestic else tech_tag(r['code'], r['세부업종'])
        rows.append({'code': r['code'], 'name': r['name'], 'type': '주식', 'asset_class': '주식',
                     'sub_class': '국내 개별주' if domestic else (f'해외 {tag}' if tag else '해외 개별주'),
                     'first_date': prices[col].first_valid_index().date(),
                     'last_date': prices[col].last_valid_index().date(),
                     'Market': r['market'], 'sector': r['섹터'], 'currency': 'KRW' if domestic else 'USD',
                     'price_file': 'stock_kr.csv' if domestic else 'stock_us.csv',
                     'price_column': col})
    return pd.DataFrame(rows).set_index('code')


PRODUCT_COLUMNS = ['name', 'type', 'asset_class', 'sub_class', 'first_date', 'last_date', 'Market', 'Marcap',
                   'sector', 'currency', 'price_file', 'price_column', 'avg_amount_krw']


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    catalog = {**PRODUCTS, **GAP_PRODUCTS, **EXTRA_PRODUCTS}
    closes = {}
    for code in catalog:
        s = load_close(code)
        if s is not None:
            closes[code] = s
    price = clean(pd.concat(closes.values(), axis=1))

    # 상품정보: 수동 분류 + 실제 데이터 기간 + 가격 파일 위치(price_file, price_column)
    app_codes = list(APP_COLUMNS)[:8]
    products = pd.DataFrame(
        [[c] + catalog[c] for c in price.columns],
        columns=['code', 'name', 'type', 'asset_class', 'sub_class'],
    ).set_index('code')
    products['first_date'] = price.apply(lambda s: s.first_valid_index()).dt.date
    products['last_date'] = price.apply(lambda s: s.last_valid_index()).dt.date
    products['Market'], products['sector'], products['currency'] = None, '', 'KRW'
    products['avg_amount_krw'] = None
    where = {c: ('etf_prices.csv', APP_COLUMNS[c]) if c in APP_COLUMNS
             else ('stock_kr.csv', catalog[c][0]) for c in products.index}      # 초안의 개별주 7종은 국내 종목 파일(열 이름 = 종목명)
    products['price_file'] = [where[c][0] for c in products.index]
    products['price_column'] = [where[c][1] for c in products.index]

    # 후보 종목(국내·해외 거래대금 상위): 가격표를 받아 상품정보에 합침 (파일 저장은 아래에서 한 번에)
    kr = collect_candidates('국내', None)
    us = collect_candidates_krw('해외', None)
    if os.path.exists(CANDIDATES):
        cand = pd.read_csv(CANDIDATES, dtype={'code': str})
        cand[['섹터', '세부업종']] = cand[['섹터', '세부업종']].fillna('')
        kr_names = cand.loc[cand['구분'] == '국내'].set_index('code')['name']
        for code in products.index.intersection(kr_names.index):       # 이미 있는 국내 종목은 후보 목록의 종목명으로 통일
            products.loc[code, ['price_file', 'price_column']] = ['stock_kr.csv', kr_names[code]]
        products = pd.concat([products, candidate_products(cand[~cand['code'].isin(products.index)], kr, us)])
        # 최근 20거래일 평균 거래대금(원). 해외는 달러 값에 마지막 원/달러 환율을 곱함 (개별주 선택 순위용)
        fx_last = float(fdr.DataReader('USD/KRW', START, END)['Close'].dropna().iloc[-1])
        amt = cand.set_index('code')
        products['avg_amount_krw'] = [round(amt.at[c, 'avg_amount'] * (fx_last if amt.at[c, '통화'] == 'USD' else 1))
                                      if c in amt.index else None for c in products.index]

    # 시가총액 등 KRX 상장 정보 병합 (2주차 StockListing 활용, 실패해도 진행). ETF·해외 종목은 빈 칸
    try:
        krx = fdr.StockListing('KRX').set_index('Code')
        products['Marcap'] = krx['Marcap'].reindex(products.index)
        products['Market'] = products['Market'].fillna(krx['Market'].reindex(products.index))
    except Exception as e:
        products['Marcap'] = None
        print(f'  [참고] StockListing 병합 생략: {e}')
    products = products[PRODUCT_COLUMNS]

    # 가격 파일 3개 (utf-8-sig, LF, Date 오름차순)
    #  - etf_prices.csv : ETF 20종 (앞 8종은 recommender.ETF_INFO와 같은 열·순서). 앱은 ETF_NAMES 열만 골라 쓰므로 추가 열은 영향 없음
    #                     혼합형 2종은 상장 전 구간이 빈 칸이라 dropna()를 걸지 않음 (앱은 최근 3년만 사용)
    #  - stock_kr.csv   : 국내 개별주 (후보 20종 + 초안 개별주 중 후보에 없는 종목)
    #  - stock_us.csv   : 해외 개별주 20종 (원화 환산)
    etf = price[list(APP_COLUMNS)].rename(columns=APP_COLUMNS)
    extra_kr = [c for c in APP_STOCK_COLUMNS if catalog[c][0] not in (kr.columns if kr is not None else [])]
    stock_kr = pd.concat([kr, price[extra_kr].rename(columns={c: catalog[c][0] for c in extra_kr})], axis=1) if kr is not None \
        else price[list(APP_STOCK_COLUMNS)].rename(columns={c: catalog[c][0] for c in APP_STOCK_COLUMNS})
    for df, fname in [(etf, 'etf_prices.csv'), (stock_kr, 'stock_kr.csv'), (us, 'stock_us.csv')]:
        if df is not None:
            df = df.copy()
            df.index.name = 'Date'
            save_csv(df, fname, 'utf-8-sig')

    save_csv(products, 'products.csv', 'utf-8-sig')

    # 점검 출력
    print('\n[수집 결과]')
    print(products[['name', 'type', 'asset_class', 'first_date', 'last_date']])
    print('\n기간:', price.index.min().date(), '~', price.index.max().date(), '/ 행수', len(price))
    print('날짜 오름차순:', price.index.is_monotonic_increasing, '/ 중복 날짜:', price.index.duplicated().sum())
    print('남은 결측(상장 전 구간 포함):\n', price.isna().sum()[price.isna().sum() > 0])


if __name__ == '__main__':
    main()
