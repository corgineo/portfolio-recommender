"""팩터 종목 선정 + 선정 종목 가격 받기 (재무 데이터가 바뀌거나 새 리밸런싱 시점이 오면 실행)

1) 매년 4월 리밸런싱일마다 강의 주가 샘플(KOSPI_PRICE_SAMPLE.csv)의 그날 종가와
   직전 회계연도 재무(재무_2026.csv)로 PER · PBR · ROE 순위합 상위 종목을 뽑아요 → data/factor_picks.csv
2) 뽑힌 종목만 FinanceDataReader 로 일간 종가를 받아요 → data/stock_prices.csv
   800여 종목 전체 대신 뽑힌 종목만 저장해서 저장소가 가볍고, 웹사이트는 인터넷 없이 돌아가요.

준비: 강의 '실습데이터/KOSPI_PRICE_SAMPLE.csv' 를 data/raw/ 에 복사 (용량이 커서 git 에는 안 올려요)
실행: python update_stock_data.py
"""
import sys

import pandas as pd
import FinanceDataReader as fdr

import factor
from recommender import DATA_FILE, LOOKBACK_YEARS, load_prices

SAMPLE_FILE = factor.DATA_DIR / 'raw' / 'KOSPI_PRICE_SAMPLE.csv'
STOCK_FILE = factor.DATA_DIR / 'stock_prices.csv'


def load_sample(path=SAMPLE_FILE):
    """강의 주가 샘플: 2번째 줄이 종목명, 숫자에 쉼표, cp949 (종목선정 노트북과 같은 전처리)"""
    df = pd.read_csv(path, index_col=0, header=[1], encoding='cp949', low_memory=False)
    df = df.apply(lambda x: pd.to_numeric(x.astype(str).str.replace(',', ''), errors='coerce'))
    df.index = pd.to_datetime(df.index)
    return df


def main():
    if not SAMPLE_FILE.exists():
        sys.exit(f'{SAMPLE_FILE} 가 없어요. 강의 실습데이터의 KOSPI_PRICE_SAMPLE.csv 를 복사해 주세요.')

    fin = factor.load_financials()
    sample = load_sample()
    etf = load_prices(DATA_FILE)

    # ETF 공분산에 3년치가 필요해서, 첫 리밸런싱은 ETF 시작 + 3년 이후
    first_year = (etf.index[0] + pd.DateOffset(years=LOOKBACK_YEARS)).year
    dates = [d for d in factor.rebalance_dates(etf.index, first_year) if d <= sample.index[-1]]

    rows = []
    for d in dates:
        price_on_date = sample.loc[:d].iloc[-1]          # 그날(휴일이면 직전) 종가
        top = factor.pick_stocks(fin, price_on_date, d.year - 1)
        top.insert(0, '리밸런싱일', d.date())
        top.insert(1, '회계연도', d.year - 1)
        rows.append(top)
        print(f"{d.date()}  {d.year - 1}년 재무  →  {', '.join(top['종목명'])}")
    picks = pd.concat(rows)[['리밸런싱일', '회계연도', '종목코드', '종목명', '종가', 'PER', 'PBR', 'ROE', '합산순위']]
    picks.to_csv(factor.PICKS_FILE, index=False, encoding='utf-8-sig')

    # 뽑힌 종목의 일간 종가 (fdr 은 수정주가라 강의 샘플과 같은 값이에요)
    codes = picks.drop_duplicates('종목코드').set_index('종목코드')['종목명']
    start = (pd.Timestamp(dates[0]) - pd.DateOffset(months=1)).strftime('%Y-%m-%d')
    prices = {}
    for code, name in codes.items():
        try:
            prices[name] = fdr.DataReader(code, start)['Close']
        except Exception as e:                             # 상장폐지 등으로 못 받으면 강의 샘플로 대신
            print(f'  {name}({code}) fdr 실패 → 샘플 사용: {e}')
            prices[name] = sample.loc[start:, name]
    stock = pd.DataFrame(prices).reindex(etf.index).ffill().loc[start:]   # ETF 거래일에 맞춤
    stock.index.name = 'Date'
    stock.to_csv(STOCK_FILE, encoding='utf-8-sig')
    print(f'\n저장: data/factor_picks.csv ({len(dates)}회, {len(codes)}종목) · data/stock_prices.csv '
          f'({stock.index[0].date()} ~ {stock.index[-1].date()})')


if __name__ == '__main__':
    main()
