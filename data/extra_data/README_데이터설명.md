# 데이터 설명 (팀프로젝트 · 포트폴리오 추천 서비스)

> **저장소 위치**: 앱이 읽는 파일은 `data/etf_prices.csv`(8종) 하나뿐이고, 이 문서와 나머지 파일은 `extra_data/` 폴더에 있습니다. `extra_data/collect_data.py`를 실행하면 결과가 `extra_data/data/`에 저장되므로 앱의 `data/`를 덮어쓰지 않습니다.

FinanceDataReader로 수집해 정리한 CSV입니다. 수집 코드는 `collect_data.py`이고, 실행하면 이 파일들이 다시 만들어집니다.
가격 파일은 모두 초안 앱에서 쓰던 `etf_prices.csv`와 같은 형식(`Date` + 영문 약칭 열, `utf-8-sig`)입니다.

## 파일 목록
| 파일 | 내용 | 종목 수 | 앱 사용 |
|---|---|---|---|
| `etf_prices.csv` | **초안 앱이 읽는 ETF 8종** (팀원 `update_data.py` 결과와 같은 열·순서) | 8 | 사용 |
| `etf_prices_ext.csv` | 위 8종 + 보강한 ETF·채권 ETF 9종 | 17 | 미사용 (아래 참고) |
| `stock_prices.csv` | 개별주식 종가 | 7 | 미사용 |
| `products.csv` | 상품정보 (이름, 유형, 자산군, 데이터 기간) | 24 | 미사용 |

- `etf_prices.csv`는 앱에 그대로 넣어도 동작합니다. 기존 파일과 겹치는 기간은 값이 완전히 같고, 새 파일은 10/30까지 하루 더 있습니다.
- `etf_prices_ext.csv`의 앞 8열은 `etf_prices.csv`와 같습니다. 뒤 9열을 앱에서 쓰려면 `recommender.py`의 `ETF_INFO`에 항목(코드, `name`, `label`, `group`)을 추가해야 합니다. 열을 추가만 해 두면 앱 결과는 달라지지 않습니다.

- 기간: 2016-01-04 ~ 2026-10-30, 일별 데이터
- 가격은 모두 **종가**입니다. 단위는 원입니다.

## 가격 파일 구조
- 첫 열 `Date`는 날짜이고 **오름차순**으로 정렬돼 있습니다. 중복 날짜는 없습니다.
- 나머지 열은 **영문 약칭**입니다. 약칭과 종목코드의 대응은 아래 표를 보세요.
- 휴장일 결측은 앞날 값으로 채웠습니다. 최대 5일까지만 채웠습니다.
- 상장 전 구간은 빈 값(NaN)입니다. 24종목 중 **2종목만** 해당합니다.
  - `MIX_K200_UST`(`284430`): 2017-11-30부터 데이터가 있습니다.
  - `MIX_DIVIDEND`(`251600`): 2016-08-11부터 데이터가 있습니다.
  - 나머지 22종목은 2016-01-04부터 결측이 없습니다.

### etf_prices_ext.csv 열 (앞 8개가 `etf_prices.csv`, 팀원 초안 앱과 같은 이름·순서)
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

### stock_prices.csv 열
| 열 | 코드 | 종목 |
|---|---|---|
| `SAMSUNG` | 005930 | 삼성전자 |
| `HYNIX` | 000660 | SK하이닉스 |
| `HYUNDAI` | 005380 | 현대차 |
| `NAVER` | 035420 | NAVER |
| `SAMSUNGCT` | 028260 | 삼성물산 |
| `SKT` | 017670 | SK텔레콤 |
| `KTNG` | 033780 | KT&G |

## products.csv 컬럼
| 컬럼 | 설명 |
|---|---|
| `code` | 종목코드 (앞자리 0 포함, 문자열) |
| `name` | 상품명 |
| `type` | ETF / 채권 / 주식 (채권은 채권 ETF) |
| `asset_class` | **채권·예금 / 주식 / 대안투자 / 자산배분** → 추천 로직의 자산군 |
| `sub_class` | 세부군 (국내 단기채권, 미국 주식, 원유, 미국 달러, 금, 주식·채권 혼합 등) |
| `first_date`, `last_date` | 데이터 시작일과 마지막 날짜 |
| `Market`, `Marcap` | 시장과 시가총액. 개별주식만 값이 있고 ETF는 비어 있습니다. |

`products.csv`에는 영문 약칭 열이 없고 종목코드(`code`)만 있습니다. 가격 파일의 열 이름(약칭)과 연결하려면 위 표를 쓰세요.

`asset_class`는 직접 분류한 값입니다. 법률신문 자산배분 표(채권·예금/주식/대안투자/자산배분/유동성)와 맞는지 확인해 주세요.

- "자산배분"에는 주식·채권 혼합형 ETF 2종(`MIX_K200_UST`, `MIX_DIVIDEND`)을 넣었습니다. 기사의 "자산배분펀드"에 해당합니다.
- "유동성"은 현금(CMA·예금)이라 ETF 데이터가 없습니다. 앱에서 비중만 계산하세요.
- 달러(`USD`)를 대안투자로 둔 것은 팀의 선택이고 기사에는 근거가 없습니다.
- 상품명은 현재 상장명 기준입니다. 초안 앱의 KOSEF 표기는 KIWOOM으로 바뀌었습니다.

## 읽는 방법
```python
import pandas as pd

etf = pd.read_csv('data/etf_prices.csv', index_col=0, parse_dates=True)          # 앱용 8종
etf_ext = pd.read_csv('extra_data/etf_prices_ext.csv', index_col=0, parse_dates=True)  # 보강 포함 17종
stock = pd.read_csv('extra_data/stock_prices.csv', index_col=0, parse_dates=True)
products = pd.read_csv('extra_data/products.csv', dtype={'code': str}, index_col='code')

# 예: 일간 수익률 (7주차 강의 방식)
daily_ret = etf.pct_change(1).dropna()   # 주의: 아래 설명 참고
```

`etf_prices.csv`(8종)는 결측이 없어 그대로 써도 됩니다. `etf_prices_ext.csv`에는 상장이 늦은 `MIX_K200_UST`가 있어, 위처럼 `dropna()`를 쓰면 2017-11-30 이전 행이 모두 사라집니다. 길게 쓰려면 해당 열을 빼거나, 계산에 필요한 기간으로 자르세요. 앱은 최근 3년(`LOOKBACK_YEARS = 3`)만 쓰므로 이 문제가 생기지 않습니다.

```python
# 상장이 늦은 자산배분 ETF를 빼고 전체 기간 사용
daily_ret = etf_ext.drop(columns=['MIX_K200_UST', 'MIX_DIVIDEND']).pct_change(1).dropna()

# 또는 최근 3년만 사용 (앱의 백테스트 방식)
daily_ret = etf_ext.loc['2023-10-31':].pct_change(1).dropna()
```

## 주의
- **`products.csv`는 반드시 `dtype={'code': str}`로 읽으세요.** 안 그러면 `069500`이 `69500`이 됩니다.
- **Excel로 열고 저장하지 마세요.** 코드 앞자리 0이 사라질 수 있습니다. 열어서 보기만 하세요.
- `collect_data.py`를 실행할 때 data 폴더의 CSV가 Excel 등에서 열려 있으면 그 파일은 저장되지 않고 경고만 나옵니다. 닫고 다시 실행하세요.
- 모든 CSV는 `utf-8-sig`로 저장돼 있습니다(앱의 `update_data.py`와 같음).
- 팀원이 `update_data.py`를 실행하면 `etf_prices.csv`가 같은 8종으로 다시 만들어집니다. `etf_prices_ext.csv`는 덮어써지지 않습니다.
- 교육용 데이터이며 투자 권유가 아닙니다.

