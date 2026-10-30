"""ETF 가격 데이터 받기 (한 번만 실행하면 data/etf_prices.csv 가 생겨요)

강의 '자산배분모형_종합_2026.ipynb' 의 ETF 자산배분 사례에서 쓴
국내 상장 ETF 8종을 FinanceDataReader 로 받아 CSV 로 저장합니다.
웹사이트는 이 CSV 를 읽기 때문에 발표·시연 중 인터넷이 끊겨도 동작해요.

실행: python update_data.py
"""
import pandas as pd
import FinanceDataReader as fdr

from recommender import ETF_INFO, DATA_FILE

START = '2016-01-01'


def main():
    prices = {}
    for code, info in ETF_INFO.items():
        df = fdr.DataReader(code, START)          # 강의: fdr.DataReader(티커, 시작일)
        prices[info['name']] = df['Close']
        print(f"{info['name']:<12} {code}  {df.index[0].date()} ~ {df.index[-1].date()}  {len(df)}일")

    price_df = pd.DataFrame(prices).dropna()      # 8종 모두 가격이 있는 날만 사용
    price_df.index.name = 'Date'
    DATA_FILE.parent.mkdir(exist_ok=True)
    price_df.to_csv(DATA_FILE, encoding='utf-8-sig')
    print(f"\n저장: data/etf_prices.csv  ({price_df.index[0].date()} ~ {price_df.index[-1].date()}, {len(price_df)}일)")


if __name__ == '__main__':
    main()
