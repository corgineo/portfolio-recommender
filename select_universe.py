"""추가 종목 후보 선정: 국내·해외 각각 최근 20거래일 평균 거래대금 상위 N종목
- 국내: fdr.StockListing('KRX') 상위 후보를 다시 20일 평균 거래대금으로 정렬 (우선주·스팩 제외)
- 해외: fdr.StockListing('S&P500') 전체를 20일 평균 거래대금(종가 × 거래량, 달러)으로 정렬
- 결과: 후보종목_거래대금상위.csv  (3년 이상 가격 이력이 있는지도 함께 표시)
실행: py select_universe.py   (저장소 맨 위 폴더에서. 결과는 data 폴더에 저장)
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import FinanceDataReader as fdr
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

TOP_N = 20
WINDOW = 20                       # 평균에 쓸 최근 거래일 수
HISTORY_START = '2016-01-01'      # 이력 확인용 (앱은 최근 3년만 사용)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', '후보종목_거래대금상위.csv')
OUT_XLSX = OUT.replace('.csv', '.xlsx')       # 반도체·AI 종목 이름 셀에 색을 입힌 엑셀

# 같은 회사의 중복 종목은 하나만 남김 (제외 종목: 사유)
EXCLUDE = {'GOOG': '알파벳 C주 (GOOGL과 같은 회사)'}

# 해외 종목 표시용. 반도체는 S&P500 업종(Industry)에 'Semiconductor'가 들어간 종목을 자동 표시.
# AI는 업종 필드가 없어서 AI 인프라·플랫폼이 사업의 핵심 서사인 종목을 직접 지정 (팀에서 고쳐도 됨).
# 빅테크(MSFT·GOOGL·META·AMZN 등)는 AI 투자가 크지만 사업이 다양해 표시하지 않음.
AI_PICKS = {'PLTR': 'AI 데이터 분석 플랫폼', 'ORCL': 'AI 클라우드 인프라', 'LITE': 'AI 데이터센터 광통신',
            'STX': 'AI 데이터센터 저장장치', 'BE': 'AI 데이터센터 전력(연료전지)'}


def tech_tag(code, industry):
    if isinstance(industry, str) and 'Semiconductor' in industry:
        return '반도체'
    return 'AI' if code in AI_PICKS else ''


def avg_trading_value(code):
    """최근 WINDOW 거래일 평균 거래대금 (종가 × 거래량). 실패하면 None"""
    try:
        df = fdr.DataReader(code, (pd.Timestamp.today() - pd.Timedelta(days=60)).strftime('%Y-%m-%d'))
        df = df.dropna(subset=['Close', 'Volume']).tail(WINDOW)
        if len(df) < WINDOW // 2:
            return None
        return {'code': code, 'avg_amount': float((df['Close'] * df['Volume']).mean()),
                'last_price': float(df['Close'].iloc[-1]), 'last_date': df.index[-1].date()}
    except Exception:
        return None


def first_date(code):
    try:
        return fdr.DataReader(code, HISTORY_START).index[0].date()
    except Exception:
        return None


def rank(codes, workers=12):
    with ThreadPoolExecutor(workers) as ex:
        rows = [r for r in ex.map(avg_trading_value, codes) if r]
    return pd.DataFrame(rows).sort_values('avg_amount', ascending=False)


def keep_long_history(ranked):
    """거래대금 순위대로 보면서 3년 미만 이력 종목은 건너뛰고 TOP_N개를 채움 (제외 종목은 따로 반환)"""
    pool = ranked.head(TOP_N * 2).copy()                      # 제외분을 메울 여유분까지 확인
    with ThreadPoolExecutor(8) as ex:
        pool['first_date'] = list(ex.map(first_date, pool['code']))
    pool['이력3년이상'] = pd.to_datetime(pool['first_date']) <= pd.Timestamp.today() - pd.DateOffset(years=3)
    pool['원래순위'] = range(1, len(pool) + 1)
    return pool[pool['이력3년이상']].head(TOP_N), pool[~pool['이력3년이상']]


def domestic():
    krx = fdr.StockListing('KRX')
    krx = krx[krx['Market'].isin(['KOSPI', 'KOSDAQ'])]
    krx = krx[~krx['Name'].str.contains(r'우[A-Z]?$|우\(|스팩|제\d+호', regex=True, na=False)]
    cand = krx.sort_values('Amount', ascending=False).head(100)        # 당일 거래대금 상위 100개를 후보로
    ranked = rank(cand['Code']).merge(cand[['Code', 'Name', 'Market']], left_on='code', right_on='Code')
    kept, dropped = keep_long_history(ranked.sort_values('avg_amount', ascending=False))
    kept['구분'], kept['통화'], kept['섹터'] = '국내', 'KRW', ''
    return kept.rename(columns={'Name': 'name', 'Market': 'market'}), dropped.rename(columns={'Name': 'name'})


def foreign():
    sp = fdr.StockListing('S&P500')
    ranked = rank(sp['Symbol']).merge(sp, left_on='code', right_on='Symbol')
    ranked = ranked[~ranked['code'].isin(EXCLUDE)].sort_values('avg_amount', ascending=False)
    kept, dropped = keep_long_history(ranked)
    kept['구분'], kept['통화'], kept['market'] = '해외', 'USD', 'S&P500'
    kept['반도체·AI'] = [tech_tag(c, i) for c, i in zip(kept['code'], kept['Industry'])]
    return kept.rename(columns={'Name': 'name', 'Sector': '섹터', 'Industry': '세부업종'}), \
        dropped.rename(columns={'Name': 'name'})


COLUMNS = ['구분', 'rank', 'code', 'name', 'market', '섹터', '세부업종', 'avg_amount', '통화',
           'last_price', 'last_date', 'first_date', '원래순위']

# 엑셀 표시: 반도체·AI는 열을 따로 만들지 않고 종목 이름(name) 셀 색으로만 구분
FILL = {'반도체': PatternFill('solid', fgColor='BDD7EE'), 'AI': PatternFill('solid', fgColor='FFE699')}
WIDTH = {'구분': 7, 'rank': 6, 'code': 9, 'name': 26, 'market': 9, '섹터': 24, '세부업종': 36,
         'avg_amount': 16, '통화': 6, 'last_price': 14, 'last_date': 12, 'first_date': 12, '원래순위': 9}


def save_xlsx(df, tags, path):
    wb = Workbook()
    ws = wb.active
    ws.title = '후보종목'
    ws.append(list(df.columns))
    for cell in ws[1]:
        cell.font, cell.fill = Font(bold=True), PatternFill('solid', fgColor='F2F2F2')
    name_col = list(df.columns).index('name') + 1
    for r, (row, tag) in enumerate(zip(df.astype(object).where(df.notna(), None).itertuples(index=False), tags), start=2):
        ws.append(list(row))
        if tag in FILL:
            ws.cell(r, name_col).fill = FILL[tag]
    for i, col in enumerate(df.columns, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = WIDTH.get(col, 12)
    for col in ('avg_amount', 'last_price'):
        for cell in ws[ws.cell(1, list(df.columns).index(col) + 1).column_letter][1:]:
            cell.number_format = '#,##0'
    ws.freeze_panes = 'A2'

    legend = wb.create_sheet('범례')
    legend.append(['색', '의미'])
    legend.append(['반도체', 'S&P500 업종(Industry)에 Semiconductor가 들어간 종목 (자동 분류)'])
    legend.append(['AI', '직접 지정한 AI 관련 종목 (아래 목록, 팀에서 수정 가능)'])
    legend['A2'].fill, legend['A3'].fill = FILL['반도체'], FILL['AI']
    legend.append([])
    legend.append(['AI 지정 종목', '사유'])
    for code, why in AI_PICKS.items():
        legend.append([code, why])
    legend.column_dimensions['A'].width, legend.column_dimensions['B'].width = 14, 60
    wb.save(path)


def main():
    (d_kept, d_drop), (f_kept, f_drop) = domestic(), foreign()
    result = pd.concat([d_kept, f_kept], ignore_index=True)
    result[['세부업종', '반도체·AI']] = result[['세부업종', '반도체·AI']].fillna('')     # 국내는 빈 칸
    result.insert(1, 'rank', result.groupby('구분').cumcount() + 1)       # 제외 후 다시 매긴 순위
    print('[중복으로 제외]', ', '.join(f'{k}: {v}' for k, v in EXCLUDE.items()))
    try:
        result[COLUMNS].to_csv(OUT, index=False, encoding='utf-8-sig', lineterminator='\n')
    except PermissionError:
        print('  [경고] CSV가 열려 있어 저장하지 못했습니다. 닫고 다시 실행하세요.')
    try:
        save_xlsx(result[COLUMNS], result['반도체·AI'], OUT_XLSX)
    except PermissionError:
        print('  [경고] 엑셀 파일이 열려 있어 저장하지 못했습니다. 닫고 다시 실행하세요.')
    pd.set_option('display.width', 200, 'display.unicode.east_asian_width', True)
    print(result[COLUMNS].to_string(index=False))
    print('\n[3년 미만 이력으로 제외]')
    dropped = pd.concat([d_drop.assign(구분='국내'), f_drop.assign(구분='해외')])
    print(dropped[['구분', 'code', 'name', 'first_date', '원래순위']].to_string(index=False))


if __name__ == '__main__':
    main()
