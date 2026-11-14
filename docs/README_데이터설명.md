# 데이터 설명 (팀프로젝트 · 포트폴리오 추천 서비스)

FinanceDataReader로 수집해 정리한 CSV입니다. 데이터는 `data/` 폴더에, 수집 코드(`collect_data.py`, `select_universe.py`)는 저장소 맨 위 폴더에 있고, 실행하면 이 파일들이 다시 만들어집니다.
가격 파일은 모두 `Date` 열 + 상품별 열 형식이고, `utf-8-sig`, LF 줄바꿈입니다.

## 파일 목록
| 파일 | 내용 | 열 수 | 열 이름 |
|---|---|---|---|
| `etf_prices.csv` | ETF 20종 (초안 앱 8종 + 보강 12종) | 20 | 영문 약칭 |
| `stock_kr.csv` | 국내 개별주 | 23 | 종목명 |
| `stock_us.csv` | 해외 개별주 (**원화 환산 가격**) | 20 | 티커 |
| `products.csv` | 상품정보 (63행). 가격이 어느 파일·열에 있는지 안내 | - | - |

- 기간: 2016-01-04 ~ 2026-11-13, 일별 데이터(2,664행). 세 파일의 날짜가 같아서 날짜로 바로 합칠 수 있습니다.
- 가격은 모두 **종가**이고 단위는 **원**입니다. 해외 종목도 원화로 환산돼 있습니다.
- 첫 열 `Date`는 **오름차순**이고 중복 날짜는 없습니다. 날짜는 한국 거래일 기준입니다.
- 휴장일 결측은 앞날 값으로 채웠고, 최대 5일까지만 채웠습니다.
- 저장소의 `data/stock_prices.csv`는 팩터 종목용(`update_stock_data.py`)이라 이름이 겹치지 않게 `stock_kr.csv`, `stock_us.csv`로 정했습니다.

## 상장 전 결측
상장 전 구간은 빈 값(NaN)입니다. 앱은 최근 3년(`LOOKBACK_YEARS = 3`)만 쓰므로 아래 결측은 앱에 영향이 없습니다.

| 파일 | 열 | 값이 있는 시작일 |
|---|---|---|
| `etf_prices.csv` | `MIX_K200_UST` | 2017-11-30 |
| | `MIX_DIVIDEND` | 2016-08-11 |
| | `UST10Y` | 2018-08-30 |
| | `UST30Y_H` | 2018-09-12 |
| | `REIT` | 2019-07-19 |
| `stock_kr.csv` | 삼성바이오로직스 | 2016-11-10 |
| | 대덕전자 | 2020-05-21 |
| | SK스퀘어 | 2021-11-29 |
| | LG에너지솔루션 | 2022-01-27 |
| `stock_us.csv` | BE | 2018-07-25 |
| | MRNA | 2018-12-07 |
| | PLTR | 2020-10-05 |

나머지 열은 2016-01-04부터 결측이 없습니다. 3년 미만 이력 종목은 후보에서 제외하고 다음 순위로 채웠습니다.

## etf_prices.csv 열 (앞 8개는 팀원 초안 앱과 같은 이름·순서)
| 열              | 코드     | 상품                    | 자산군   |
| -------------- | ------ | --------------------- | ----- |
| `KOSPI200`     | 069500 | KODEX 200             | 주식    |
| `SP500`        | 143850 | TIGER 미국S&P500선물(H)   | 주식    |
| `TOPIX`        | 195920 | TIGER 일본TOPIX(합성 H)   | 주식    |
| `CSI300`       | 192090 | TIGER 차이나CSI300       | 주식    |
| `EUROSTOXX50`  | 195930 | TIGER 유로스탁스50(합성 H)   | 주식    |
| `KBOND`        | 122260 | KIWOOM 통안채1년          | 채권·예금 |
| `OIL`          | 130680 | TIGER 원유선물Enhanced(H) | 대안투자  |
| `USD`          | 138230 | KIWOOM 미국달러선물         | 대안투자  |
| `GOLD`         | 132030 | KODEX 골드선물(H)         | 대안투자  |
| `NASDAQ100`    | 133690 | TIGER 미국나스닥100        | 주식    |
| `DIVIDEND`     | 161510 | PLUS 고배당주             | 주식    |
| `MIX_K200_UST` | 284430 | KODEX 200미국채혼합50      | 자산배분  |
| `MIX_DIVIDEND` | 251600 | PLUS 고배당주채권혼합         | 자산배분  |
| `KTB3Y`        | 114260 | KODEX 국고채3년           | 채권·예금 |
| `SHORTBOND`    | 153130 | KODEX 단기채권            | 채권·예금 |
| `CORPBOND`     | 136340 | RISE 중기우량회사채          | 채권·예금 |
| `KTB10Y`       | 148070 | KIWOOM 국고채10년         | 채권·예금 |
| `UST10Y`       | 305080 | TIGER 미국채10년선물        | 채권·예금 |
| `UST30Y_H`     | 304660 | KODEX 미국30년국채울트라선물(H) | 채권·예금 |
| `REIT`         | 329200 | TIGER 리츠부동산인프라        | 대안투자  |

앱(`recommender.py`)은 `ETF_NAMES`에 있는 열만 골라 쓰므로, 뒤 12열은 `ETF_INFO`에 항목을 추가하기 전까지 앱 결과에 영향을 주지 않습니다.

## stock_kr.csv (국내 개별주 23종, 열 이름 = 종목명)
- 국내 거래대금 상위 20종목(최근 20거래일 평균 거래대금, 우선주·스팩 제외)과 초안 앱의 개별주 7종을 합쳤습니다. 4종이 겹쳐서 23열입니다.
- 거래대금 상위 20종: SK하이닉스, 삼성전자, 삼성전기, SK스퀘어, 삼성SDI, 삼성E&A, 대덕전자, LG에너지솔루션, 현대차, NAVER, 한화솔루션, 두산에너빌리티, KB금융, 한화에어로스페이스, 한화오션, 셀트리온, SK, 한미반도체, 한진칼, 삼성바이오로직스
- 초안 개별주 중 후보에 없던 3종: 삼성물산, SK텔레콤, KT&G
- 초안 앱의 영문 약칭(`SAMSUNG` 등)은 쓰지 않습니다. 약칭과 종목명의 대응은 `products.csv`의 `price_column`을 보세요.

## stock_us.csv (해외 개별주 20종, 열 이름 = 티커, 원화 환산)
- S&P500 구성종목 중 거래대금 상위 20종목입니다. 같은 회사의 중복 종목(GOOG)은 GOOGL만 남겼습니다.
- 반도체 7: NVDA, MU, AMD, INTC, AVGO, MRVL, AMAT
- AI 5 (직접 지정): ORCL, LITE, PLTR, BE, STX
- 그 외 8: AAPL, TSLA, META, MSFT, AMZN, GOOGL, LLY, MRNA
- **환산 방식**: 달러 종가 × 그날 원/달러 환율. 한국 거래일 기준으로 맞추고, 미국 휴장일은 앞날 종가를 씁니다(최대 5일). 미국 종가는 한국 장 마감 뒤에 나오지만 하루 시차는 무시했습니다.
- 환율 변동이 수익률에 반영됩니다. 앱에서는 국내 종목처럼 다루면 됩니다.
- 수수료·세금은 반영하지 않았습니다. 1주 가격이 커서(예: LLY 약 190만원) 소액 예산에서는 비중이 작으면 0주가 될 수 있습니다.

## products.csv 컬럼
| 컬럼 | 설명 |
|---|---|
| `code` | 종목코드 (앞자리 0 포함, 문자열). 해외는 티커 |
| `name` | 상품명 |
| `type` | ETF / 채권 / 주식 (채권은 채권 ETF) |
| `asset_class` | **채권·예금 / 주식 / 대안투자 / 자산배분** → 추천 로직의 자산군 |
| `sub_class` | 세부군 (국내 단기채권, 미국 주식, 원유, 금, 주식·채권 혼합, 국내 개별주, 해외 반도체, 해외 AI, 해외 개별주 등) |
| `first_date`, `last_date` | 데이터 시작일과 마지막 날짜 |
| `Market`, `Marcap` | 시장과 시가총액. 국내 개별주만 값이 있고(해외는 시장 S&P500), ETF는 비어 있습니다 |
| `sector` | 해외 개별주의 업종 (그 외는 빈 칸) |
| `currency` | 원래 통화 (KRW / USD). 가격 파일은 모두 원화입니다 |
| `price_file` | 이 상품의 가격이 있는 파일 (`etf_prices.csv` / `stock_kr.csv` / `stock_us.csv`) |
| `price_column` | 그 파일에서의 열 이름 |
| `avg_amount_krw` | 최근 20거래일 평균 거래대금(원). 거래대금 상위 후보 종목 40개만 값이 있고(해외는 마지막 원/달러 환율로 환산), 그 외는 빈 칸. 개별주를 거래대금 순으로 고를 때 씁니다 |

구성: ETF 20종 + 개별 주식 43종(국내 23, 해외 반도체 7, 해외 AI 5, 해외 개별주 8) = 63행.

`asset_class`는 직접 분류한 값입니다. 법률신문 자산배분 표(채권·예금/주식/대안투자/자산배분/유동성)와 맞는지 확인해 주세요.

- "자산배분"에는 주식·채권 혼합형 ETF 2종(`MIX_K200_UST`, `MIX_DIVIDEND`)을 넣었습니다. 기사의 "자산배분펀드"에 해당합니다.
- 미국 장기국채 2종(`UST10Y`는 환노출, `UST30Y_H`는 환헤지)과 리츠 1종(`REIT`)은 초안 앱의 빈틈(미국 채권, 부동산)을 채우려고 추가했습니다. 리츠는 법률신문 표의 대안투자에 해당한다고 보고 대안투자로 분류했습니다.
- "유동성"은 현금(CMA·예금)이라 데이터가 없습니다. 앱에서 비중만 계산하세요.
- 달러(`USD`)를 대안투자로 둔 것은 팀의 선택이고 기사에는 근거가 없습니다.
- 상품명은 현재 상장명 기준입니다. 초안 앱의 KOSEF 표기는 KIWOOM으로 바뀌었습니다.
- 개별 주식의 `asset_class`는 모두 "주식"입니다. 추천에 쓸 때 ETF와 어떻게 섞을지는 팀에서 정해야 합니다.

## 읽는 방법
```python
import pandas as pd

etf = pd.read_csv('data/etf_prices.csv', index_col=0, parse_dates=True)
kr = pd.read_csv('data/stock_kr.csv', index_col=0, parse_dates=True)
us = pd.read_csv('data/stock_us.csv', index_col=0, parse_dates=True)
products = pd.read_csv('data/products.csv', dtype={'code': str}, index_col='code')

# 상품의 가격 찾기: products의 price_file, price_column 사용
files = {'etf_prices.csv': etf, 'stock_kr.csv': kr, 'stock_us.csv': us}
r = products.loc['005930']
samsung = files[r['price_file']][r['price_column']]

# 일간 수익률 (7주차 강의 방식)
daily_ret = etf.loc['2023-11-13':].pct_change(1).dropna()   # 최근 3년 (앱의 방식)
```

`etf_prices.csv`에는 상장이 늦은 `MIX_K200_UST`, `MIX_DIVIDEND`, `UST10Y`, `UST30Y_H`, `REIT`가 있어서, 전체 기간에 `dropna()`를 쓰면 2019-07-19 이전 행이 모두 사라집니다. 길게 쓰려면 해당 열을 빼거나 필요한 기간으로 자르세요. `stock_kr.csv`, `stock_us.csv`도 상장이 늦은 종목이 있어 같습니다.

```python
# 상장이 늦은 ETF를 빼고 전체 기간 사용
daily_ret = etf.drop(columns=['MIX_K200_UST', 'MIX_DIVIDEND', 'UST10Y', 'UST30Y_H', 'REIT']).pct_change(1).dropna()
```

## 주의
- **`products.csv`는 반드시 `dtype={'code': str}`로 읽으세요.** 안 그러면 `069500`이 `69500`이 됩니다.
- **Excel로 열고 저장하지 마세요.** 코드 앞자리 0이 사라질 수 있습니다. 열어서 보기만 하세요.
- `collect_data.py`를 실행할 때 data 폴더의 CSV가 Excel 등에서 열려 있으면 그 파일은 저장되지 않고 경고만 나옵니다. 닫고 다시 실행하세요. 후보 종목 목록(`후보종목_거래대금상위.csv`)은 `select_universe.py`로 먼저 만들어야 합니다.
- **팀원의 `update_data.py`는 같은 `etf_prices.csv`를 8종으로 덮어쓰고 `dropna()`도 합니다.** 20열 파일과 같이 쓰지 말고, 갱신은 `collect_data.py`로 하세요.
- 모든 CSV는 `utf-8-sig`로 저장돼 있습니다(앱의 `update_data.py`와 같음).
- 교육용 데이터이며 투자 권유가 아닙니다.
