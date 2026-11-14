"""투자상품 목록(거래대금 순위)과 종목 분석 화면

- 개별 기업: 매출액·영업이익·부채비율 차트 (국내: 재무_2026.csv, 미국: SEC EDGAR 10-K)
- ETF: 여러 종목을 묶은 상품이라 기업 재무제표 대신 무엇을 담는 상품인지와 가격 흐름을 보여줘요
- 값이 없는 연도·항목은 0으로 채우지 않고 '자료 없음'으로 표시해요
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import recommender as rc
import service as svc
from ui import html, esc, won, card_title, dot

KR_PREFIX = 'KRFIN:'
ETF_ABOUT = {   # ETF가 담는 것 (상품 이름·운용사 공개 정보 기준의 일반 설명)
    'KOSPI200': '한국 유가증권시장 대표 200개 기업(KOSPI 200 지수)을 따라가요.',
    'SP500': '미국 대형주 500개(S&P 500) 선물을 따라가고, 환율 영향을 줄인(환헤지) 상품이에요.',
    'TOPIX': '일본 도쿄증권거래소 전체 지수(TOPIX)를 따라가요(환헤지).',
    'CSI300': '중국 상하이·선전 대표 300개 기업(CSI 300)을 따라가요.',
    'EUROSTOXX50': '유로존 대표 50개 기업(EURO STOXX 50)을 따라가요(환헤지).',
    'KBOND': '만기 1년 안팎의 통화안정증권(한국은행 발행 채권)에 투자해요. 가격 변동이 작아요.',
    'OIL': 'WTI 원유 선물 가격을 따라가요(환헤지). 가격 변동이 매우 커요.',
    'USD': '미국 달러 선물을 따라가요. 원/달러 환율이 오르면 가격이 올라요.',
    'SPY': '미국 대형주 500개(S&P 500 지수)를 따라가는 세계에서 가장 거래가 많은 ETF예요.',
    'VOO': 'S&P 500 지수를 따라가는 ETF예요.', 'IVV': 'S&P 500 지수를 따라가는 ETF예요.',
    'QQQ': '미국 나스닥 상장 비금융 대형주 100개(나스닥100)를 따라가요. 기술주 비중이 커요.',
    'IWM': '미국 중소형주 2,000개(Russell 2000)를 따라가요.',
    'SMH': '미국에 상장된 대표 반도체 기업들을 묶어 담아요.',
    'HYG': '미국 하이일드(신용등급이 낮은 대신 이자가 높은) 회사채에 투자해요.',
    'LQD': '미국 투자등급(신용도가 좋은) 회사채에 투자해요.',
    'TLT': '만기 20년 이상 미국 국채에 투자해요. 금리 변화에 가격이 크게 움직여요.',
    'IEF': '만기 7~10년 미국 국채에 투자해요.',
    'SGOV': '만기 0~3개월 미국 국채에 투자해요. 현금과 비슷하게 가격 변동이 매우 작아요.',
    'SOXL': '반도체 지수 하루 수익률의 3배를 따라가는 레버리지 ETF예요. 오래 들고 있으면 손실이 커질 수 있어요.',
    'TQQQ': '나스닥100 하루 수익률의 3배를 따라가는 레버리지 ETF예요. 오래 들고 있으면 손실이 커질 수 있어요.',
    '132030': '금 선물 가격을 따라가고, 환율 영향을 줄인(환헤지) 상품이에요.',
    '133690': '미국 나스닥100 지수를 원화로 사고팔 수 있게 만든 국내 상장 ETF예요. 기술주 비중이 커요.',
    '161510': '배당을 많이 주는 국내 상장 기업들을 묶어 담아요.',
    '284430': '국내 KOSPI 200 주식과 미국 국채를 함께 담는 주식·채권 혼합 ETF예요.',
    '251600': '국내 고배당주와 채권을 함께 담는 주식·채권 혼합 ETF예요.',
    '114260': '만기 3년 안팎의 한국 국고채에 투자해요.',
    '153130': '만기가 짧은 국내 채권에 투자해요. 가격 변동이 작은 편이에요.',
    '136340': '신용도가 좋은 국내 회사채(중기)에 투자해요.',
    '148070': '만기 10년 안팎의 한국 국고채에 투자해요. 금리 변화에 가격이 크게 움직여요.',
}


@st.cache_data(show_spinner=False)
def _fin_kr():
    return svc.load_fin_kr()


@st.cache_data(show_spinner=False)
def _all_candidates():
    f = rc.UNIVERSE_DIR / 'ranking_all_candidates.csv'
    return pd.read_csv(f, dtype={'ticker': str}) if f.exists() else None


def _fmt(v, unit='', digits=0):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '자료 없음'
    return f'{v:,.{digits}f}{unit}'


# ── 투자상품 목록 ───────────────────────────────────────────────────────
def render_products(data, ss, go_page, open_detail, has_wide=True):
    products = data['products']
    html("""<div class="section-title left"><div class="k">투자상품</div><h2>어떤 상품을 고를 수 있나요?</h2></div>
         <p class="cd">행을 누른 뒤 <b>분석 보기</b>를 누르면 회사의 재무제표(매출·영업이익·부채비율)나 ETF 설명을 볼 수 있어요.</p>""")
    u = data.get('universe')
    if has_wide and u is not None:
        r, meta = u['ranking'], u['meta']
        ranked = r[~r.list.str.startswith('국내 추가')]          # 순위 목록(통합 상위·채권 상위)만
        kr = ranked[ranked.market == 'KR']
        us = ranked[ranked.market == 'US']
        win = []
        if not us.empty:
            win.append(f"미국 {us.window_start.min()} ~ {us.window_end.max()} (평균 환율 {us.avg_usdkrw.mean():,.1f}원)")
        if not kr.empty:
            win.append(f"국내 {kr.window_start.min()} ~ {kr.window_end.max()}")
        allc = _all_candidates()
        kr_note = ''
        if allc is not None:
            kr_all = allc[~allc.ticker.str.match(r'^[A-Z]+$')]
            if not kr_all.empty and kr.empty:
                k0 = kr_all.iloc[0]
                kr_note = (f' 이번 기준으로는 국내 종목이 30위 안에 없어요. 국내 1위 {esc(k0["name"])}는 '
                           f'통합 {int(k0["rank"])}위({k0["avg_value_krw"] / 1e12:,.2f}조원)예요.')
        top = r[r.list.str.startswith('통합')]
        bonds = r[r.list.str.startswith('채권')]
        kr_extra = r[r.list.str.startswith('국내 추가')]
        with st.container(border=True):
            card_title(f'거래대금 상위 {len(top)}종목 · 국내·미국 통합',
                       f'비교 통화 <b>원화(KRW)</b> · 거래대금 = 종가×거래량의 <b>최근 {meta["window_days"]}거래일 평균</b>'
                       f' (각 시장의 장 마감일 기준: {" / ".join(win) or "-"}) · 미국은 같은 날 원/달러 환율로 환산했어요.{kr_note}')
            _rank_table(top, products, open_detail, 'rank_top')
        with st.container(border=True):
            card_title(f'채권 ETF 거래대금 상위 {len(bonds)}',
                       '통합 30위 안에 채권 상품이 없어서, 채권 ETF끼리 같은 기준(원화 평균 거래대금)으로 순위를 매겨 더했어요. '
                       '추천 계산의 채권·예금 몫에 함께 들어가요.')
            _rank_table(bonds, products, open_detail, 'rank_bond')
        if not kr_extra.empty:
            with st.container(border=True):
                card_title(f'국내 추가 ETF {len(kr_extra)}종 · 순위와 별도',
                           '거래대금 순위에 국내 상품이 없어서, 원화로 소액 투자할 수 있는 국내 채권·금·혼합·주식 ETF를 따로 더했어요. '
                           '순위를 바꾸지 않고 별도 목록으로 추천 계산(각 자산군 몫)에 함께 넣어요. '
                           f'거래대금은 같은 기준(국내 {kr_extra.window_end.max()}까지 최근 {meta["window_days"]}거래일 평균)이에요.')
                _rank_table(kr_extra, products, open_detail, 'rank_kr')
        with st.expander('순위를 만든 방법과 한계'):
            st.markdown(f"""
- **후보**: 국내 주식(KRX 전체)·국내 ETF는 최근 거래일 거래대금 상위 {meta['pool_per_market']}개씩, 미국 주식(NASDAQ·NYSE·AMEX 전체)은 공개 스크리너의 종가×거래량 상위 {meta['pool_per_market']}개를 후보로 골랐어요. 국내 채권 ETF는 거래대금 상위 20개를 후보에 더했어요.
- **미국 ETF 후보의 한계**: 무료 공개 스크리너가 ETF 거래량을 주지 않아서 대표 미국 ETF 목록(SPY·QQQ·TLT 등 40여 개)을 후보로 썼어요. 목록 밖의 미국 ETF는 순위에 없을 수 있어요.
- **거래대금 계산**: 실제 체결 금액의 합이 아니라 '종가 × 거래량'으로 근사했어요. 두 시장에 같은 방식을 썼어요.
- **기준일**: 국내 {meta['kr_last_session']}, 미국 {meta['us_last_session']} 장 마감까지(장중 데이터는 쓰지 않아요). 수집 시각 {meta['run_at_kst']}.
- **국내 추가 ETF**: 순위와 별개로, 팀이 미리 골라 둔 국내 ETF 목록(`data/extra_data/products.csv`, 기본 8종 제외)을 같은 날짜까지의 실제 가격으로 받아 추천 계산에 더했어요. 이 상품들이 순위에 끼어들지는 않아요.
- **추천 계산에서 빼는 종목**: 레버리지·인버스·변동성 상품, 가격 기록이 3년이 안 되는 종목(최근 상장), 같은 지수·같은 회사를 중복으로 담는 종목. 순위는 그대로 보여 드려요.
- **가격과 환율**: 미국 상품은 미국 종가 × 그날 원/달러 환율로 원화 환산하고, 한국 장 마감 때 이미 알려진 전날 미국 종가만 써요(미래 데이터 방지). 분배금은 반영하지 않은 가격이에요.
- **출처**: {', '.join(meta['sources'].values())}
- 새로 받으려면 `python update_universe.py`를 실행하세요.
""")
            fails = meta.get('failures') or []
            if fails:
                st.warning(f'수집 중 실패 {len(fails)}건: ' + ', '.join(f"{f['symbol']}({f['step']})" for f in fails[:10]))
    else:
        st.info('거래대금 상위 종목 자료(data/universe)가 없어 국내 ETF 8종만 보여 드려요. '
                '`python update_universe.py`를 실행하면 추가돼요.')

    with st.container(border=True):
        card_title('기본 국내 ETF 8종', '원화로 바로 살 수 있는 국내 상장 ETF예요. 모든 추천에 기본으로 들어가요.')
        cols = st.columns(4)
        for i, n in enumerate(rc.ETF_NAMES):
            p = products[n]
            cols[i % 4].button(f'{p["short"]}', key=f'base_{n}', width='stretch', on_click=open_detail, args=(n, 'products'),
                               help=f'{p["desc"]} · {p["group"]}')

    with st.container(border=True):
        card_title('국내 기업 재무 찾아보기', '국내 상장사 806곳의 연간 재무(매출·영업이익·부채비율)를 볼 수 있어요.')
        fin = _fin_kr()
        names = fin.drop_duplicates('종목코드').sort_values('종목명')
        opts = [f'{KR_PREFIX}{c}' for c in names['종목코드']]
        label = dict(zip(opts, names['종목명'] + ' (' + names['종목코드'] + ')'))
        c1, c2 = st.columns([2, 1], vertical_alignment='bottom')
        pick = c1.selectbox('기업 이름', opts, index=None, format_func=lambda k: label.get(k, k), key='kr_fin_pick',
                            placeholder='예: 삼성전자')
        c2.button('분석 보기', key='kr_fin_go', width='stretch', disabled=pick is None,
                  on_click=open_detail, args=(pick, 'products'))


def _short_reason(r):
    """표에 들어가게 짧게 (전체 사유는 종목 분석 화면에 그대로 보여요)"""
    if not r:
        return ''
    out = []
    for part in r.split(' · '):
        if part.startswith('레버리지'):
            out.append('레버리지·인버스')
        elif part.startswith('가격 기록 3년 미만'):
            out.append('상장 3년 미만' + part[len('가격 기록 3년 미만'):].replace('부터', '~'))
        elif '중복' in part:
            out.append(f'중복({part.split("와")[0]}와 같음)')
        else:
            out.append(part)
    return ' · '.join(out)


def _rank_table(df, products, open_detail, key):
    show = pd.DataFrame({
        '순위': (df['rank'].astype(int) if key == 'rank_top' else df['bond_rank'].astype(int) if key == 'rank_bond'
                 else df['rank'].map(lambda v: f'{int(v)}위' if pd.notna(v) else '후보 밖')),
        '종목': [products.get(n, {}).get('short', n) if m == 'KR' else f'{t} · {nm}'
                 for n, t, nm, m in zip(df.name_key, df.ticker, df.name, df.market)],
        '시장': df.market.map({'KR': '국내', 'US': '미국'}),
        '종류': df.kind.map({'주식': '개별주식', 'ETF': 'ETF'}),
        '자산군': df.asset_class.map(rc.GROUP_SHORT),
        '평균 거래대금(억원)': (df.avg_value_krw / 1e8).round(0),
        '추천 계산': np.where(df.eligible, '사용', '제외'),
        '제외 사유': df.exclude_reason.map(_short_reason),
    })
    if key == 'rank_bond':
        show.insert(1, '통합 순위', df['rank'].astype(int).values)
    if key == 'rank_kr':
        show = show.rename(columns={'순위': '통합 순위'})
    ev = st.dataframe(show, hide_index=True, width='stretch', on_select='rerun', selection_mode='single-row', key=key,
                      column_config={'평균 거래대금(억원)': st.column_config.NumberColumn(format='%,.0f', width='medium'),
                                     '종목': st.column_config.TextColumn(width='medium'),
                                     '시장': st.column_config.TextColumn(width='small'),
                                     '종류': st.column_config.TextColumn(width='small'),
                                     '자산군': st.column_config.TextColumn(width='small'),
                                     '추천 계산': st.column_config.TextColumn(width='small'),
                                     '제외 사유': st.column_config.TextColumn(width='medium')},
                      height=min(35 * (len(show) + 1) + 3, 420))
    rows = ev.selection.rows if ev is not None else []
    if rows:
        name = df.iloc[rows[0]]['name_key']
        st.button(f'{show.iloc[rows[0]]["종목"]} 분석 보기', type='primary', key=f'{key}_go',
                  on_click=open_detail, args=(name, 'products'))


# ── 종목 분석 ──────────────────────────────────────────────────────────
def render_detail(name, data, ss, go_page):
    back = ss.get('detail_from', 'products')
    back_label = {'result': '추천 결과로', 'mock': '모의 포트폴리오로', 'products': '투자상품 목록으로'}.get(back, '뒤로')
    st.button(f'← {back_label} 돌아가기', key='detail_back', on_click=go_page, args=(back,))
    if not name:
        st.info('분석할 종목을 먼저 골라 주세요.')
        return
    if str(name).startswith(KR_PREFIX):
        _detail_kr_company(name[len(KR_PREFIX):])
        return
    p = data['products'].get(name)
    if p is None:
        st.warning('이 상품 정보를 찾을 수 없어요. 투자상품 목록에서 다시 골라 주세요.')
        return
    market = {'KR': '국내', 'US': '미국'}.get(p['market'], '')
    kind = '개별주식' if p['kind'] == '주식' else p['kind']
    tags = [market, kind, rc.GROUP_SHORT.get(p['group'], p['group']), p['currency']]
    if p.get('list') == '국내 추가 ETF':
        tags.append('국내 추가 ETF')
    elif p.get('rank') and pd.notna(p.get('rank')):
        tags.append(f'거래대금 {p["list"]} · {int(p["rank"])}위')
    html(f"""<div class="res-hero detail-hero"><div class="tags">{''.join(f'<span>{esc(t)}</span>' for t in tags if t)}</div>
      <div class="who">{esc(p['code'])}</div><h2>{esc(p['short'] if p['market'] != 'US' else p['desc'])}</h2>
      <div class="desc">{esc(ETF_ABOUT.get(name, p['label']) if p['kind'] == 'ETF' else
                              f"{market} 상장 개별주식이에요. 회사의 연간 실적과 가격 흐름을 함께 볼 수 있어요.")}</div></div>""")
    if p.get('reason'):
        st.info(f'추천 계산에서는 빠져 있어요: {p["reason"]}')

    _price_card(name, p, data)
    if p['kind'] == 'ETF':
        with st.container(border=True):
            card_title('ETF는 재무제표 대신 이렇게 봐요',
                       'ETF는 여러 회사(또는 채권·원자재)를 한 번에 담은 펀드라 한 회사의 매출·부채 같은 재무제표가 없어요.')
            html(f"""<ul class="changes">
              <li><b>무엇을 담나요?</b> {esc(ETF_ABOUT.get(name, f"{p['label']} — 상품 이름이 따라가는 지수·자산을 확인해 주세요."))}</li>
              <li><b>자산군</b> {esc(rc.GROUP_SHORT.get(p['group'], p['group']))} — 서비스에서는 {dot(rc.GROUP_BASE.get(p['group'], '#98a2b3'))}색으로 표시해요.</li>
              <li><b>확인할 것</b> 총보수(1년 운용 비용), 추종 오차, 분배금 지급 여부는 운용사 홈페이지의 상품 설명서에서 확인할 수 있어요.</li>
            </ul>""")
    elif p['market'] == 'US':
        _fin_card(svc.financials_us(data['universe']['fin_us'] if data.get('universe') else None, p['code']),
                  '억 달러', 'SEC EDGAR 10-K 연간 보고서(companyfacts API) · 미국 회계기준(US GAAP) · 단위 억 달러(USD)',
                  p['code'])
    else:
        _fin_card(svc.financials_kr(_fin_kr(), p['code']), '억원', '재무_2026.csv(국내 상장사 연간 재무 자료) · 단위 억원(KRW)',
                  p['code'])


def _detail_kr_company(code):
    fin = _fin_kr()
    row = fin[fin['종목코드'] == code]
    if row.empty:
        st.warning('이 기업의 재무 자료를 찾을 수 없어요.')
        return
    nm = row['종목명'].iloc[-1]
    html(f"""<div class="res-hero detail-hero"><div class="tags"><span>국내</span><span>개별주식</span><span>KRW</span></div>
      <div class="who">{esc(code)}</div><h2>{esc(nm)}</h2>
      <div class="desc">추천 상품 목록 밖의 기업이라 가격 차트 없이 연간 재무만 보여 드려요.</div></div>""")
    _fin_card(svc.financials_kr(fin, code), '억원', '재무_2026.csv(국내 상장사 연간 재무 자료) · 단위 억원(KRW)', code)


def _price_card(name, p, data):
    u = data.get('universe')
    local = None
    if p['currency'] == 'USD' and u is not None and name in u['local']:
        local = u['local'][name]
    krw = data['prices'][name] if name in data['prices'] else None
    with st.container(border=True):
        if krw is None or krw.dropna().empty:
            card_title('가격 흐름', '')
            st.warning('가격 자료를 받지 못해 차트를 그릴 수 없어요.')
            return
        recent = krw.loc[krw.index[-1] - pd.DateOffset(years=rc.LOOKBACK_YEARS):]
        stats = svc.price_stats(recent)
        cur = '원'
        series = recent
        if local is not None:
            series = local.loc[recent.index[0]:]
            cur = '달러'
        if local is not None:
            # 미국 가격은 한국 달력에 맞춰 하루 밀어 둔 값이라, 날짜 대신 실제 미국 종가 기준일을 적어요
            rng = f'최근 {rc.LOOKBACK_YEARS}년 · 마지막 값은 {data.get("us_as_of") or "-"} 미국 현지 종가'
        else:
            rng = f'{series.dropna().index[0]:%Y.%m.%d} ~ {series.dropna().index[-1]:%Y.%m.%d}'
        card_title('최근 3년 가격 흐름', f'{rng} · 종가({cur}) · 분배금 미반영'
                   + (' · 아래 수익률은 원/달러 환율을 반영한 원화 기준이에요' if local is not None else ''))
        fig = go.Figure(go.Scatter(x=series.index, y=series, line=dict(color=rc.GROUP_BASE.get(p['group'], '#2563eb'), width=2),
                                   hovertemplate=('$%{y:,.2f}' if local is not None else '%{y:,.0f}원') + '<extra></extra>'))
        fig.update_layout(height=260, margin=dict(t=10, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)',
                          plot_bgcolor='rgba(0,0,0,0)', font=dict(family='Pretendard', color='#475467'),
                          yaxis=dict(gridcolor='#f2f4f7'), xaxis=dict(showgrid=False))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        if stats is None:
            st.info('가격 기록이 60거래일보다 짧아 수익률·변동성을 계산하지 않았어요.')
        else:
            last_krw = krw.dropna().iloc[-1]
            html(f"""<div class="compare">
              <div><span>현재가 (원화)</span><b>{last_krw:,.0f}원</b><em>{'$' + format(local.dropna().iloc[-1], ',.2f') if local is not None else ''}</em></div>
              <div><span>연환산 수익률 · 변동성</span><b>{stats['return']:+.1%} · {stats['vol']:.1%}</b><em>최근 {rc.LOOKBACK_YEARS}년</em></div>
              <div><span>최대 낙폭</span><b>{stats['mdd']:.1%}</b><em class="down">고점 대비</em></div></div>""")


def _fin_card(table, unit, source, code):
    with st.container(border=True):
        card_title('기업 재무 한눈에 보기', f'출처: {source}')
        if table is None or table.empty:
            st.info('이 종목의 재무 자료를 확보하지 못했어요. (예: 미국 외 기업이 내는 20-F 보고서, 자료가 없는 기업) '
                    '빈 값을 0으로 채우지 않았어요.')
            return
        x = table['연도']
        c1, c2 = st.columns(2, gap='medium')
        fig = go.Figure()
        fig.add_bar(x=x, y=table['매출액'], name='매출액', marker_color='#93c5fd',
                    hovertemplate='%{x}<br>매출액 %{y:,.0f}' + unit + '<extra></extra>')
        fig.add_bar(x=x, y=table['영업이익'], name='영업이익', marker_color='#2563eb',
                    hovertemplate='%{x}<br>영업이익 %{y:,.0f}' + unit + '<extra></extra>')
        fig.update_layout(barmode='group', height=280, margin=dict(t=30, b=0, l=0, r=0), title=dict(text=f'매출액·영업이익 ({unit})', font=dict(size=14)),
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation='h', y=-0.2),
                          font=dict(family='Pretendard', color='#475467'), yaxis=dict(gridcolor='#f2f4f7', tickformat=',.0f'))
        c1.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        fig2 = go.Figure()
        fig2.add_scatter(x=x, y=table['부채비율(%)'], name='부채비율', mode='lines+markers', line=dict(color='#f04438', width=3),
                         connectgaps=False, hovertemplate='%{x}<br>부채비율 %{y:,.0f}%<extra></extra>')
        fig2.add_scatter(x=x, y=table['영업이익률(%)'], name='영업이익률', mode='lines+markers', line=dict(color='#16a34a', width=2, dash='dot'),
                         connectgaps=False, hovertemplate='%{x}<br>영업이익률 %{y:,.1f}%<extra></extra>')
        fig2.update_layout(height=280, margin=dict(t=30, b=0, l=0, r=0), title=dict(text='부채비율·영업이익률 (%)', font=dict(size=14)),
                           paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation='h', y=-0.2),
                           font=dict(family='Pretendard', color='#475467'), yaxis=dict(gridcolor='#f2f4f7', ticksuffix='%'))
        c2.plotly_chart(fig2, width='stretch', config={'displayModeBar': False})
        cols = ['매출액', '영업이익', '당기순이익', '부채총계', '자본총계']
        disp = pd.DataFrame({'연도': table['연도']})
        for c in cols:
            disp[f'{c}({unit})'] = [_fmt(v) for v in table[c]]
        disp['부채비율'] = [_fmt(v, '%') for v in table['부채비율(%)']]
        disp['영업이익률'] = [_fmt(v, '%', 1) for v in table['영업이익률(%)']]
        st.dataframe(disp, hide_index=True, width='stretch')
        missing = int(table[cols].isna().sum().sum())
        notes = ['부채비율 = 부채총계 ÷ 자본총계 × 100 (자본이 0 이하이면 계산하지 않아요)', '영업이익률 = 영업이익 ÷ 매출액 × 100']
        if missing:
            notes.append(f'빈 칸 {missing}개는 원자료에 값이 없는 항목이에요. 0으로 채우지 않았어요.')
        if '부채 출처' in table and table['부채 출처'].str.contains('계산').any():
            notes.append('일부 연도의 부채총계는 보고서에 따로 없어 "부채와 자본 총계 − 자본총계"로 계산했어요.')
        st.caption(' · '.join(notes))
        st.caption('재무 수치는 공시 자료 기준이며, 회사가 나중에 고친 값(정정 공시)과 다를 수 있어요.')
