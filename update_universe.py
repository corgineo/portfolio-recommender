"""거래대금 상위 종목(국내·미국 통합) 수집 → data/universe/

실행: python update_universe.py        (인터넷 필요, 3~6분)

하는 일
1. 후보 모으기
   - 국내 주식: KRX 전체 종목 목록(FinanceDataReader)의 최근 거래일 거래대금 상위 50
   - 국내 ETF: 국내 ETF 목록(FinanceDataReader, 네이버 금융)의 거래대금 상위 50
   - 미국 주식: Nasdaq 공개 스크리너(NASDAQ·NYSE·AMEX 전체)의 최근 거래일 '종가×거래량' 상위 50
   - 미국 ETF: 공개 스크리너가 ETF 거래량을 주지 않아서, 아래 US_ETF_SEED 목록(대표 ETF)으로 후보를 정해요 (한계로 표시)
2. 후보마다 최근 일봉을 받아 '최근 20거래일 평균 거래대금(원)'을 계산해요.
   - 거래대금 ≈ 종가 × 거래량 (두 시장에 같은 방식). 미국은 그날 USD/KRW 종가로 원화 환산.
   - 각 시장에서 장이 끝난 날만 써요 (실행 시점에 장이 열려 있으면 그날 데이터는 빼요).
3. 원화 기준으로 국내·미국을 한 줄로 세워 상위 30개를 저장해요. 순위는 손대지 않고,
   추천 계산에 넣지 않는 종목(레버리지·인버스, 가격 기록 3년 미만 등)은 사유를 같이 적어요.
4. 상위 30 + 기존 ETF 8종의 가격(현지 통화·원화)을 저장해요.
   - 미국 종가는 '한국 장 마감 시점에 이미 알려진 값'만 쓰도록 하루 밀어서(미국 t일 종가 → 한국 t+1일 이후) 맞춰요.
5. 미국 개별주식의 연간 재무(매출·영업이익·부채·자본)를 SEC EDGAR(무료 공개 API)에서 받아요.

모든 단계에서 실패한 종목은 meta.json 의 failures 에 남기고, 값을 지어내지 않아요.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

import FinanceDataReader as fdr

OUT = Path(__file__).parent / 'data' / 'universe'
TOP_N = 30
BOND_N = 5                  # 통합 상위 30에 채권이 없을 때 따로 더할 채권 ETF 수
WINDOW = 20                 # 평균 거래대금을 낼 거래일 수
POOL = 50                   # 시장별 후보 수
HISTORY_START = '2021-01-01'
UA = {'User-Agent': 'Mozilla/5.0 (first-portfolio local educational app)'}
SEC_UA = {'User-Agent': 'first-portfolio-edu research@example.com', 'Accept-Encoding': 'gzip, deflate'}  # SEC 요청 형식(이름+연락처)의 일반 표기

# 기존 앱의 ETF 8종 (recommender.ETF_INFO 와 같은 코드)
BASE = {'069500': 'KOSPI200', '143850': 'SP500', '195920': 'TOPIX', '192090': 'CSI300',
        '195930': 'EUROSTOXX50', '122260': 'KBOND', '130680': 'OIL', '138230': 'USD'}

# 미국 ETF 후보 (공개 스크리너에 ETF 거래량이 없어서 대표 ETF를 직접 적음) → 자산군
US_ETF_SEED = {
    'SPY': ('SPDR S&P 500 ETF', '주식'), 'QQQ': ('Invesco QQQ Trust', '주식'), 'IWM': ('iShares Russell 2000 ETF', '주식'),
    'VOO': ('Vanguard S&P 500 ETF', '주식'), 'IVV': ('iShares Core S&P 500 ETF', '주식'),
    'VTI': ('Vanguard Total Stock Market ETF', '주식'), 'DIA': ('SPDR Dow Jones Industrial Average ETF', '주식'),
    'SMH': ('VanEck Semiconductor ETF', '주식'), 'XLF': ('Financial Select Sector SPDR', '주식'),
    'XLK': ('Technology Select Sector SPDR', '주식'), 'XLE': ('Energy Select Sector SPDR', '주식'),
    'EEM': ('iShares MSCI Emerging Markets ETF', '주식'), 'EFA': ('iShares MSCI EAFE ETF', '주식'),
    'FXI': ('iShares China Large-Cap ETF', '주식'), 'ARKK': ('ARK Innovation ETF', '주식'),
    'TLT': ('iShares 20+ Year Treasury Bond ETF', '채권·예금'), 'IEF': ('iShares 7-10 Year Treasury Bond ETF', '채권·예금'),
    'SHY': ('iShares 1-3 Year Treasury Bond ETF', '채권·예금'), 'SGOV': ('iShares 0-3 Month Treasury Bond ETF', '채권·예금'),
    'BIL': ('SPDR Bloomberg 1-3 Month T-Bill ETF', '채권·예금'), 'HYG': ('iShares iBoxx High Yield Corporate Bond ETF', '채권·예금'),
    'LQD': ('iShares iBoxx Investment Grade Corporate Bond ETF', '채권·예금'), 'AGG': ('iShares Core U.S. Aggregate Bond ETF', '채권·예금'),
    'BND': ('Vanguard Total Bond Market ETF', '채권·예금'), 'GLD': ('SPDR Gold Shares', '대안투자'),
    'SLV': ('iShares Silver Trust', '대안투자'), 'USO': ('United States Oil Fund', '대안투자'),
    'TQQQ': ('ProShares UltraPro QQQ (3배 레버리지)', '주식'), 'SQQQ': ('ProShares UltraPro Short QQQ (-3배 인버스)', '주식'),
    'SOXL': ('Direxion Daily Semiconductor Bull 3X', '주식'), 'UVXY': ('ProShares Ultra VIX Short-Term Futures', '대안투자'),
    'VCIT': ('Vanguard Intermediate-Term Corporate Bond ETF', '채권·예금'), 'JNK': ('SPDR Bloomberg High Yield Bond ETF', '채권·예금'),
    'GOVT': ('iShares U.S. Treasury Bond ETF', '채권·예금'), 'SHV': ('iShares Short Treasury Bond ETF', '채권·예금'),
    'TLH': ('iShares 10-20 Year Treasury Bond ETF', '채권·예금'), 'EMB': ('iShares J.P. Morgan USD Emerging Markets Bond ETF', '채권·예금'),
    'MUB': ('iShares National Muni Bond ETF', '채권·예금'), 'BNDX': ('Vanguard Total International Bond ETF', '채권·예금'),
    'JPST': ('JPMorgan Ultra-Short Income ETF', '채권·예금'), 'USFR': ('WisdomTree Floating Rate Treasury Fund', '채권·예금'),
    'TBIL': ('US Treasury 3 Month Bill ETF', '채권·예금'), 'VGSH': ('Vanguard Short-Term Treasury ETF', '채권·예금'),
}
# 같은 지수·같은 회사를 중복으로 담지 않게: 앞의 것이 더 거래대금이 많을 때만 뒤의 것을 추천 계산에서 빼요
SAME_AS = {'VOO': 'SPY', 'IVV': 'SPY', 'GOOG': 'GOOGL', 'GOOGL': 'GOOG'}

LEVERAGE_WORDS = ['레버리지', '인버스', '2X', '3X', '울트라', 'ULTRA', ' BULL', ' BEAR', 'SHORT', 'VIX', '선물인버스']
BOND_WORDS = ['채권', '국고채', '국채', '회사채', '통안채', '단기채', 'KOFR', 'CD금리', '머니마켓', '금리', 'TREASURY', 'BOND', 'T-BILL']
ALT_WORDS = ['골드', '금현물', '금선물', '은선물', '원유', 'WTI', '구리', '원자재', '달러', 'GOLD', 'SILVER', 'OIL']
MIX_WORDS = ['혼합', 'TDF', 'TRF']

failures = []


def log(*a):
    print(datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def classify(name, kind):
    """이름 키워드로 자산군 분류 (개별주식은 모두 주식)"""
    if kind == '주식':
        return '주식'
    up = name.upper()
    if any(w in up for w in [w.upper() for w in MIX_WORDS]):
        return '자산배분'
    if any(w.upper() in up for w in BOND_WORDS):
        return '채권·예금'
    if any(w.upper() in up for w in ALT_WORDS):
        return '대안투자'
    return '주식'


def is_leveraged(name):
    up = f' {name.upper()}'
    return any(w.upper() in up for w in LEVERAGE_WORDS)


def completed(df, market):
    """장이 아직 안 끝난 오늘 데이터는 빼요"""
    if df.empty:
        return df
    tz, close_hm = (ZoneInfo('Asia/Seoul'), (15, 45)) if market == 'KR' else (ZoneInfo('America/New_York'), (16, 15))
    now = datetime.now(tz)
    last = df.index[-1].date()
    if last > now.date() or (last == now.date() and (now.hour, now.minute) < close_hm):
        return df.iloc[:-1]
    return df


def fetch(symbol, start, market, tries=3):
    for i in range(tries):
        try:
            d = fdr.DataReader(symbol, start)
            if d is None or d.empty or 'Close' not in d:
                raise ValueError('빈 데이터')
            d = d[['Close', 'Volume']].astype(float)
            d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
            d = d[~d.index.duplicated(keep='last')].sort_index()
            d = d[d['Close'] > 0]
            return completed(d, market)
        except Exception as e:     # noqa: BLE001 - 실패는 기록하고 다음 종목으로
            err = e
            time.sleep(1.5 * (i + 1))
    failures.append({'symbol': symbol, 'step': f'가격 조회({start}~)', 'error': repr(err)[:200]})
    return None


# ── 1. 후보 ─────────────────────────────────────────────────────────────
def candidates():
    rows = []
    krx = fdr.StockListing('KRX')
    krx = krx.dropna(subset=['Amount']).sort_values('Amount', ascending=False).head(POOL)
    for r in krx.itertuples():
        rows.append(dict(ticker=r.Code, name=r.Name, market='KR', kind='주식', exchange=r.Market))
    etf = fdr.StockListing('ETF/KR')
    etf = etf.dropna(subset=['Amount']).sort_values('Amount', ascending=False)
    bond_etf = etf[[classify(n, 'ETF') == '채권·예금' and not is_leveraged(n) for n in etf['Name']]].head(20)
    for r in pd.concat([etf.head(POOL), bond_etf]).drop_duplicates('Symbol').itertuples():
        rows.append(dict(ticker=r.Symbol, name=r.Name, market='KR', kind='ETF', exchange='KRX ETF'))
    res = requests.get('https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true', headers=UA, timeout=60)
    us = pd.DataFrame(res.json()['data']['rows'])
    us['price'] = pd.to_numeric(us['lastsale'].str.replace('$', '').str.replace(',', ''), errors='coerce')
    us['vol'] = pd.to_numeric(us['volume'], errors='coerce')
    us['value'] = us['price'] * us['vol']
    us = us[~us['symbol'].str.contains(r'[\^/ ]', regex=True)]          # 우선주·워런트 표기 제외
    for r in us.sort_values('value', ascending=False).head(POOL).itertuples():
        rows.append(dict(ticker=r.symbol, name=r.name, market='US', kind='주식', exchange='US'))
    for t, (n, _) in US_ETF_SEED.items():
        rows.append(dict(ticker=t, name=n, market='US', kind='ETF', exchange='US ETF'))
    df = pd.DataFrame(rows).drop_duplicates('ticker')
    return df


# ── 2. 평균 거래대금 ─────────────────────────────────────────────────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    run_at = datetime.now(ZoneInfo('Asia/Seoul'))
    log('후보 모으기')
    cand = candidates()
    log('후보', len(cand))

    fx = fetch('USD/KRW', HISTORY_START, 'FX')['Close'].rename('USDKRW')
    fx = fx[fx.index.day_of_week < 5]

    short_start = (run_at - timedelta(days=50)).strftime('%Y-%m-%d')
    stats = []
    for c in cand.itertuples():
        d = fetch(c.ticker, short_start, c.market)
        if d is None or len(d) < WINDOW:
            if d is not None:
                failures.append({'symbol': c.ticker, 'step': '거래대금', 'error': f'거래일 {len(d)}일 < {WINDOW}일'})
            continue
        d = d.tail(WINDOW).copy()
        if c.market == 'US':
            rate = fx.reindex(d.index, method='ffill')
            if rate.isna().any():
                failures.append({'symbol': c.ticker, 'step': '환율', 'error': '해당 날짜 환율 없음'})
                continue
            d['value_krw'] = d['Close'] * d['Volume'] * rate
            avg_fx = float(rate.mean())
        else:
            d['value_krw'] = d['Close'] * d['Volume']
            avg_fx = np.nan
        stats.append(dict(ticker=c.ticker, avg_value_krw=float(d['value_krw'].mean()), window_start=d.index[0].date(),
                          window_end=d.index[-1].date(), days=len(d), avg_usdkrw=avg_fx))
    stats = pd.DataFrame(stats)
    rank = cand.merge(stats, on='ticker').sort_values('avg_value_krw', ascending=False).reset_index(drop=True)
    rank['rank'] = rank.index + 1
    def asset_class(r):
        if r.market == 'US' and r.kind == 'ETF':
            return US_ETF_SEED[r.ticker][1]
        return classify(r.name, r.kind)
    rank['asset_class'] = [asset_class(r) for r in rank.itertuples()]
    top = rank.head(TOP_N).copy()
    top['list'] = f'통합 상위 {TOP_N}'
    # 통합 상위 30에 채권이 없으면, 채권 ETF끼리 같은 기준(원화 평균 거래대금)으로 매긴 상위 BOND_N 개를 따로 더해요
    bonds = rank[(rank.asset_class == '채권·예금') & ~rank.ticker.isin(top.ticker)].copy()
    bonds = bonds[[not is_leveraged(n) for n in bonds['name']]].head(BOND_N)
    bonds['list'] = f'채권 상위 {BOND_N}'
    bonds['bond_rank'] = range(1, len(bonds) + 1)
    top = pd.concat([top, bonds], ignore_index=True)
    log('상위', TOP_N, '+ 채권', len(bonds), '확정')
    top['currency'] = np.where(top['market'] == 'US', 'USD', 'KRW')

    # ── 4. 긴 가격 기록 ─────────────────────────────────────────────────
    kr_cal = fetch('069500', HISTORY_START, 'KR')
    cal = kr_cal.index
    local, krw, first_dates = {}, {}, {}
    for t in list(BASE) + top['ticker'].tolist():
        if t in local:
            continue
        mkt = 'US' if t in set(top.loc[top.market == 'US', 'ticker']) else 'KR'
        d = fetch(t, HISTORY_START, mkt)
        if d is None:
            continue
        close = d['Close']
        first_dates[t] = close.index[0].date()
        if mkt == 'US':
            rate = fx.reindex(close.index, method='ffill')
            usd_krw = (close * rate).dropna()
            # 미국 t일 종가는 한국 시각으로 t+1일 새벽에 나와요 → 한국 t+1일 장 마감부터 아는 값으로 둬요
            shifted = usd_krw.copy()
            shifted.index = shifted.index + pd.Timedelta(days=1)
            krw[t] = shifted.reindex(cal, method='ffill', tolerance=pd.Timedelta(days=7))
            loc = close.copy()
            loc.index = loc.index + pd.Timedelta(days=1)
            local[t] = loc.reindex(cal, method='ffill', tolerance=pd.Timedelta(days=7))
        else:
            s = close.reindex(cal)
            s = s.ffill(limit=5).where(s.index >= close.index[0])      # 상장 전은 비워 둬요
            krw[t] = s
            local[t] = s
    px_krw = pd.DataFrame(krw)
    px_local = pd.DataFrame(local)
    # 마지막 날(한국 기준)에 값이 없는 종목은 현재가를 모르는 것 → 추천 계산 제외
    end = cal[-1]
    need_from = end - pd.DateOffset(years=3)

    reasons = []
    for r in top.itertuples():
        why = []
        if is_leveraged(r.name):
            why.append('레버리지·인버스·변동성 상품(초보자 장기 보유에 부적합)')
        twin = SAME_AS.get(r.ticker)
        if twin in set(top.ticker) and top.loc[top.ticker == twin, 'avg_value_krw'].iloc[0] > r.avg_value_krw:
            why.append(f'{twin}와 같은 지수·같은 회사라 중복 제외')
        if r.ticker not in px_krw or px_krw[r.ticker].isna().all():
            why.append('가격 기록을 받지 못함')
        else:
            s = px_krw[r.ticker]
            if s.first_valid_index() is None or s.first_valid_index() > need_from + pd.Timedelta(days=10):
                why.append(f'가격 기록 3년 미만({first_dates.get(r.ticker)}부터)')
            elif s.loc[need_from:].isna().mean() > 0.02:
                why.append('최근 3년 가격 빈칸이 2% 초과')
            if pd.isna(s.iloc[-1]):
                why.append('최근 가격 없음')
        reasons.append(' · '.join(why))
    top['exclude_reason'] = reasons
    top['eligible'] = top['exclude_reason'] == ''
    top['first_date'] = top['ticker'].map(first_dates)
    top['name'] = top['name'].str.replace(r'\s+(Common Stock|Class A Common Stock|Class A Ordinary Shares|Ordinary Shares|'
                                           r'Class C Capital Stock|Class A Capital Stock|Common Shares).*$', '', regex=True)

    # ── 5. 미국 개별주식 재무 (SEC EDGAR companyfacts) ───────────────────
    fin_rows = []
    us_stocks = top[(top.market == 'US') & (top.kind == '주식')]['ticker'].tolist()
    if us_stocks:
        try:
            tick = requests.get('https://www.sec.gov/files/company_tickers.json', headers=SEC_UA, timeout=60).json()
            cik = {v['ticker'].upper(): int(v['cik_str']) for v in tick.values()}
        except Exception as e:     # noqa: BLE001
            cik = {}
            failures.append({'symbol': 'SEC', 'step': 'CIK 목록', 'error': repr(e)[:200]})
        for t in us_stocks:
            if t.upper() not in cik:
                failures.append({'symbol': t, 'step': 'SEC 재무', 'error': 'CIK 없음'})
                continue
            try:
                time.sleep(0.2)
                facts = requests.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik[t.upper()]:010d}.json',
                                     headers=SEC_UA, timeout=60).json()
                fin_rows += sec_annual(t, facts)
            except Exception as e:  # noqa: BLE001
                failures.append({'symbol': t, 'step': 'SEC 재무', 'error': repr(e)[:200]})
    fin = pd.DataFrame(fin_rows)

    # ── 저장 ──────────────────────────────────────────────────────────
    cols = ['list', 'rank', 'bond_rank', 'ticker', 'name', 'market', 'kind', 'asset_class', 'currency', 'avg_value_krw', 'window_start',
            'window_end', 'days', 'avg_usdkrw', 'first_date', 'eligible', 'exclude_reason']
    top[cols].to_csv(OUT / 'ranking.csv', index=False, encoding='utf-8-sig')
    rank[['rank', 'ticker', 'name', 'market', 'kind', 'avg_value_krw', 'window_start', 'window_end']].to_csv(
        OUT / 'ranking_all_candidates.csv', index=False, encoding='utf-8-sig')
    px_krw.round(4).to_csv(OUT / 'prices_krw.csv', encoding='utf-8-sig')
    px_local.round(4).to_csv(OUT / 'prices_local.csv', encoding='utf-8-sig')
    fx.to_frame().to_csv(OUT / 'usdkrw.csv', encoding='utf-8-sig')
    if not fin.empty:
        fin.to_csv(OUT / 'financials_us.csv', index=False, encoding='utf-8-sig')
    meta = {
        'run_at_kst': run_at.isoformat(timespec='minutes'),
        'kr_last_session': str(kr_cal.index[-1].date()),
        'us_last_session': str(top.loc[top.market == 'US', 'window_end'].max()) if (top.market == 'US').any() else None,
        'price_end_kr_calendar': str(end.date()),
        'window_days': WINDOW, 'top_n': TOP_N, 'bond_n': BOND_N, 'pool_per_market': POOL,
        'value_definition': '최근 20거래일(각 시장의 장 마감일) 일별 종가×거래량의 평균, 미국은 같은 날 USD/KRW 종가로 원화 환산',
        'sources': {
            'kr_list': 'FinanceDataReader StockListing("KRX"), StockListing("ETF/KR")',
            'us_list': 'Nasdaq 공개 스크리너 api.nasdaq.com/api/screener/stocks (NASDAQ·NYSE·AMEX 전체)',
            'us_etf': f'공개 스크리너에 ETF 거래량이 없어 대표 ETF {len(US_ETF_SEED)}종(US_ETF_SEED)을 후보로 사용',
            'kr_bond_etf': '국내 ETF 목록에서 이름에 채권·국고채·KOFR·CD금리 등이 들어간 ETF 중 거래대금 상위 20을 후보에 추가',
            'prices': 'FinanceDataReader DataReader (국내: KRX/네이버, 미국·환율: Yahoo Finance)',
            'fx': 'FinanceDataReader DataReader("USD/KRW")',
            'us_financials': 'SEC EDGAR companyfacts API (10-K 연간)',
        },
        'failures': failures,
    }
    (OUT / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    log('저장 완료', OUT, '실패', len(failures))
    print(top[['list', 'rank', 'ticker', 'name', 'market', 'asset_class', 'avg_value_krw', 'eligible', 'exclude_reason']].to_string())


SEC_TAGS = {
    'revenue': ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet',
                'RevenueFromContractWithCustomerIncludingAssessedTax'],
    'operating_income': ['OperatingIncomeLoss'],
    'net_income': ['NetIncomeLoss'],
    'liabilities': ['Liabilities'],
    'equity': ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
    'liab_and_equity': ['LiabilitiesAndStockholdersEquity'],
}


def sec_annual(ticker, facts):
    """10-K 의 연간(약 1년 기간) 값만 골라 결산일별로 정리. 없는 값은 비워 둬요."""
    gaap = facts.get('facts', {}).get('us-gaap', {})

    def series(tags, duration):
        best = {}
        for tag in tags:
            for unit, items in gaap.get(tag, {}).get('units', {}).items():
                if unit != 'USD':
                    continue
                for it in items:
                    if it.get('form') not in ('10-K', '10-K/A'):
                        continue
                    end = pd.Timestamp(it['end'])
                    if duration:
                        if 'start' not in it:
                            continue
                        days = (end - pd.Timestamp(it['start'])).days
                        if not 350 <= days <= 380:
                            continue
                    key = end
                    # 같은 결산일이면 먼저 나온 태그(우선순위)를, 같은 태그면 나중에 제출된 값을 써요
                    prev = best.get(key)
                    if prev is None or (prev[0] == tag and it['filed'] >= prev[2]):
                        best[key] = (tag, it['val'], it['filed'])
            # 앞 순위 태그에 값이 있으면 그 연도는 그대로 두고, 빈 연도만 다음 태그로 채워요
        return {k: v for k, v in best.items()}

    rev = series(SEC_TAGS['revenue'], True)
    ends = sorted(rev)[-6:]
    if not ends:
        return []
    op = series(SEC_TAGS['operating_income'], True)
    ni = series(SEC_TAGS['net_income'], True)
    li = series(SEC_TAGS['liabilities'], False)
    eq = series(SEC_TAGS['equity'], False)
    le = series(SEC_TAGS['liab_and_equity'], False)
    rows = []
    for e in ends:
        liab, liab_note = (li[e][1], 'Liabilities') if e in li else (None, '')
        if liab is None and e in le and e in eq:
            liab, liab_note = le[e][1] - eq[e][1], '부채및자본총계−자본총계로 계산'
        rows.append({'ticker': ticker, 'fiscal_end': e.date(), 'currency': 'USD',
                     'revenue': rev[e][1], 'revenue_tag': rev[e][0],
                     'operating_income': op[e][1] if e in op else None,
                     'net_income': ni[e][1] if e in ni else None,
                     'liabilities': liab, 'liabilities_note': liab_note,
                     'equity': eq[e][1] if e in eq else None,
                     'filed': rev[e][2]})
    return rows


# ── 6. 국내 추가 ETF (data/extra_data/products.csv) ────────────────────────
# 통합 상위 30이 미국 종목만으로 채워질 수 있어서, 팀이 미리 골라 둔 국내 ETF(기본 8종 제외)를
# 순위와 별개 목록으로 추천 계산에 더해요. 원화로 1주 가격이 낮아 소액 예산에서도 채권·금·혼합 비중을 담을 수 있어요.
EXTRA_PRODUCTS = Path(__file__).parent / 'data' / 'extra_data' / 'products.csv'
KR_EXTRA_LIST = '국내 추가 ETF'


def add_kr_extra():
    """기존 data/universe 결과에 '국내 추가 ETF' 행과 가격 열을 더해요 (다시 실행하면 그 부분만 새로 받아요)."""
    ranking = pd.read_csv(OUT / 'ranking.csv', dtype={'ticker': str})
    px_krw = pd.read_csv(OUT / 'prices_krw.csv', index_col=0, parse_dates=True)
    px_local = pd.read_csv(OUT / 'prices_local.csv', index_col=0, parse_dates=True)
    meta = json.loads((OUT / 'meta.json').read_text(encoding='utf-8'))
    allc_f = OUT / 'ranking_all_candidates.csv'
    allc = pd.read_csv(allc_f, dtype={'ticker': str}) if allc_f.exists() else pd.DataFrame(columns=['ticker', 'rank'])
    cand_rank = dict(zip(allc['ticker'], allc['rank']))

    ranking = ranking[ranking['list'] != KR_EXTRA_LIST]
    prod = pd.read_csv(EXTRA_PRODUCTS, dtype={'code': str}, encoding='utf-8-sig')
    prod = prod[(prod['type'].isin(['ETF', '채권'])) & ~prod['code'].isin(BASE) & ~prod['code'].isin(ranking['ticker'])]
    kr_end = pd.Timestamp(meta['kr_last_session'])
    cal = px_krw.index
    need_from = cal[-1] - pd.DateOffset(years=3)
    rows = []
    for p in prod.itertuples():
        d = fetch(p.code, HISTORY_START, 'KR')
        if d is None:
            continue
        d = d.loc[:kr_end]
        win = d.tail(WINDOW)
        close = d['Close']
        s = close.reindex(cal).ffill(limit=5).where(cal >= close.index[0])
        px_krw[p.code] = s
        px_local[p.code] = s
        why = []
        if is_leveraged(p.name):
            why.append('레버리지·인버스·변동성 상품(초보자 장기 보유에 부적합)')
        if s.first_valid_index() is None or s.first_valid_index() > need_from + pd.Timedelta(days=10):
            why.append(f'가격 기록 3년 미만({close.index[0].date()}부터)')
        elif s.loc[need_from:].isna().mean() > 0.02:
            why.append('최근 3년 가격 빈칸이 2% 초과')
        if pd.isna(s.iloc[-1]):
            why.append('최근 가격 없음')
        rows.append(dict(list=KR_EXTRA_LIST, rank=cand_rank.get(p.code, np.nan), bond_rank=np.nan, ticker=p.code, name=p.name,
                         market='KR', kind='ETF', asset_class=p.asset_class, currency='KRW',
                         avg_value_krw=float((win['Close'] * win['Volume']).mean()) if len(win) == WINDOW else np.nan,
                         window_start=win.index[0].date(), window_end=win.index[-1].date(), days=len(win), avg_usdkrw=np.nan,
                         first_date=close.index[0].date(), eligible=not why, exclude_reason=' · '.join(why)))
    ranking = pd.concat([ranking, pd.DataFrame(rows)], ignore_index=True)
    ranking.to_csv(OUT / 'ranking.csv', index=False, encoding='utf-8-sig')
    px_krw.round(4).to_csv(OUT / 'prices_krw.csv', encoding='utf-8-sig')
    px_local.round(4).to_csv(OUT / 'prices_local.csv', encoding='utf-8-sig')
    meta['kr_extra'] = {
        'run_at_kst': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='minutes'),
        'source': 'data/extra_data/products.csv 의 국내 ETF(기본 8종 제외) · 가격·거래량 FinanceDataReader DataReader',
        'count': len(rows),
        'note': '거래대금 순위와 별개 목록. rank 는 통합 후보 안에 있을 때만 그 순위, 후보 밖이면 비움',
    }
    meta['failures'] = failures if failures else meta.get('failures', [])
    (OUT / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    log('국내 추가 ETF', len(rows), '저장')
    print(pd.DataFrame(rows)[['ticker', 'name', 'asset_class', 'rank', 'avg_value_krw', 'eligible', 'exclude_reason']].to_string())


if __name__ == '__main__':
    import sys
    if '--kr-extra-only' not in sys.argv:
        main()
    add_kr_extra()
