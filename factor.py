"""팩터 종목 선정 (주식 몫 일부를 개별 종목으로)

강의 '종목선정_포트폴리오_2026.ipynb' 의 순위합 방식:
저PER · 저PBR (가치) + 고ROE (수익성) 각각의 순위를 더해 다시 순위를 매기고, 상위 N종목을 같은 비중으로 담아요.
재무제표는 발표 시차가 있어서 (회계연도 + 1)년 4월 1일부터 쓸 수 있다고 봐요 (강의와 같은 가정).
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / 'data'
FIN_FILE = DATA_DIR / '재무_2026.csv'
PICKS_FILE = DATA_DIR / 'factor_picks.csv'
N_STOCKS = 5          # 담을 종목 수
REBAL_MONTH = 4       # 매년 4월 리밸런싱 (재무 발표 시차)


def load_financials(path=FIN_FILE):
    """재무 데이터 → 종목코드 정리 + ROE 계산 + 주당 지표를 현재 주식 수 기준으로 환산

    주가는 수정주가(이후 액면분할·무상증자를 반영해 과거 가격을 낮춘 값)인데 EPS·BPS 는 그해 주식 수 기준이라,
    그대로 나누면 나중에 분할한 종목의 과거 PER 이 터무니없이 낮게 나와요 (예: 삼성전자 2017년 PER ≈ 0.2).
    주식 수 = 자본총계 ÷ BPS 로 구해서 EPS·BPS × (그해 주식 수 ÷ 최근 주식 수) 로 맞춰요. 최근 연도는 그대로예요.
    """
    fin = pd.read_csv(path, dtype={'종목코드': str})
    fin['종목코드'] = fin['종목코드'].str.replace('A', '')
    fin['ROE'] = np.where(fin['자본총계'] > 0, fin['당기순이익'] / fin['자본총계'], np.nan)  # 자본잠식이면 제외

    fin = fin.sort_values(['종목코드', '회계연도'])
    shares = pd.Series(np.where(fin['BPS'] > 0, fin['자본총계'] / fin['BPS'], np.nan), index=fin.index)
    latest = shares.groupby(fin['종목코드']).transform('last')                   # 가장 최근 유효한 주식 수
    ratio = shares / latest
    fin['EPS_adj'] = fin['EPS'] * ratio
    fin['BPS_adj'] = fin['BPS'] * ratio
    return fin


def factor_rank(fin, price_on_date, fy):
    """특정 날짜 주가 + 직전 회계연도 재무 → PER · PBR · ROE 와 합산순위

    price_on_date: 종목명 → 그날 종가 (Series)
    fy: 쓸 회계연도 (예: 2026년 4월이면 2025)
    """
    df = fin.query('회계연도 == @fy')[['종목코드', '종목명', 'EPS_adj', 'BPS_adj', 'ROE']].copy()
    df['종가'] = df['종목명'].map(price_on_date)
    df = df.dropna(subset=['종가'])                                            # 주가가 있는 종목만
    df['PER'] = np.where(df['EPS_adj'] > 0, df['종가'] / df['EPS_adj'], np.nan)   # 적자 기업 제외
    df['PBR'] = np.where(df['BPS_adj'] > 0, df['종가'] / df['BPS_adj'], np.nan)

    rank = pd.DataFrame({'PER': df['PER'].rank(),                           # 낮을수록 1위
                         'PBR': df['PBR'].rank(),
                         'ROE': df['ROE'].rank(ascending=False)})           # 높을수록 1위
    df['합산순위'] = rank.sum(axis=1, skipna=False).rank(method='first')     # 하나라도 없으면 제외
    return df.dropna(subset=['합산순위']).sort_values('합산순위')


def pick_stocks(fin, price_on_date, fy, n=N_STOCKS):
    """합산순위 상위 n종목"""
    return factor_rank(fin, price_on_date, fy).head(n)


def rebalance_dates(index, first_year):
    """매년 4월 1일 이후 첫 거래일 (index: 거래일 DatetimeIndex)"""
    dates = []
    for year in range(first_year, index[-1].year + 1):
        after = index[index >= pd.Timestamp(year, REBAL_MONTH, 1)]
        if len(after):
            dates.append(after[0])
    return pd.DatetimeIndex(dates)


def load_picks(path=PICKS_FILE):
    """update_stock_data.py 가 저장한 연도별 선정 종목"""
    picks = pd.read_csv(path, dtype={'종목코드': str}, parse_dates=['리밸런싱일'])
    return picks


def picks_on(picks, date):
    """date 시점에 들고 있어야 할 종목명 리스트 (그 이전 마지막 리밸런싱의 선정 종목)"""
    past = picks[picks['리밸런싱일'] <= pd.Timestamp(date)]
    if past.empty:
        return []
    last = past['리밸런싱일'].max()
    return past.loc[past['리밸런싱일'] == last, '종목명'].tolist()
