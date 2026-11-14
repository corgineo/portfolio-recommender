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
from ui import html, esc, won, card_title, dot, easy_group, plot_style, GROUP_EASY, INK, MUTED

KR_PREFIX = 'KRFIN:'
ETF_ABOUT = {   # ETF가 담는 것 (상품 이름·운용사 공개 정보 기준의 일반 설명)
    'KOSPI200': '한국 유가증권시장 대표 200개 기업(KOSPI 200 지수)을 따라가요.',
    'SP500': '미국 대형주 500개(S&P 500) 선물을 따라가고, 환율 영향을 줄인(환헤지) 상품이에요.',
    'TOPIX': '일본 도쿄증권거래소 전체 지수(TOPIX)를 따라가요(환헤지).',
    'CSI300': '중국 상하이·선전 대표 300개 기업(CSI 300)을 따라가요.',
    'EUROSTOXX50': '유로존 대표 50개 기업(EURO STOXX 50)을 따라가요(환헤지).',
    'KBOND': '만기 1년 안팎의 통화안정증권(한국은행 발행 채권)에 투자해요. 가격 변동이 작은 편이지만 원금이 보장되지는 않아요.',
    'OIL': 'WTI 원유 선물 가격을 따라가요(환헤지). 가격 변동이 매우 커요.',
    'USD': '미국 달러 선물을 따라가요. 원/달러 환율이 오르면 가격이 올라요.',
    'SPY': '미국 대형주 500개(S&P 500 지수)를 따라가는 ETF예요.',
    'VOO': 'S&P 500 지수를 따라가는 ETF예요.', 'IVV': 'S&P 500 지수를 따라가는 ETF예요.',
    'QQQ': '미국 나스닥 상장 비금융 대형주 100개(나스닥100)를 따라가요. 기술주 비중이 커요.',
    'IWM': '미국 중소형주 2,000개(Russell 2000)를 따라가요.',
    'SMH': '미국에 상장된 대표 반도체 기업들을 묶어 담아요.',
    'HYG': '미국 하이일드(신용등급이 낮은 대신 이자가 높은) 회사채에 투자해요.',
    'LQD': '미국 투자등급(신용도가 좋은) 회사채에 투자해요.',
    'TLT': '만기 20년 이상 미국 국채에 투자해요. 금리 변화에 가격이 크게 움직여요.',
    'IEF': '만기 7~10년 미국 국채에 투자해요.',
    'SGOV': '만기 0~3개월 미국 국채에 투자해요. 가격 변동이 매우 작은 편이지만 원금이 보장되지는 않아요.',
    'SOXL': '반도체 지수 하루 수익률의 3배를 따라가는 레버리지 ETF예요. 오래 들고 있으면 손실이 커질 수 있어요.',
    'TQQQ': '나스닥100 하루 수익률의 3배를 따라가는 레버리지 ETF예요. 오래 들고 있으면 손실이 커질 수 있어요.',
    '132030': '금 선물 가격을 따라가고, 환율 영향을 줄인(환헤지) 상품이에요.',
    '133690': '미국 나스닥100 지수를 원화로 사고팔 수 있게 만든 국내 상장 ETF예요. 기술주 비중이 커요.',
    '161510': '배당을 많이 주는 국내 상장 기업들을 묶어 담아요.',
    '284430': '국내 KOSPI 200 주식과 미국 국채를 함께 담는 주식·채권 혼합 ETF예요.',
    '251600': '국내 고배당주와 채권을 함께 담는 주식·채권 혼합 ETF예요.',
    '114260': '만기 3년 안팎의 한국 국고채에 투자해요.',
    '153130': '만기가 짧은 국내 채권에 투자해요. 가격 변동이 작은 편이지만 원금이 보장되지는 않아요.',
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


# ── 상품 둘러보기 ───────────────────────────────────────────────────────
CATS = ['처음 보기 좋은 기본 8개', '채권', '주식', '다른 자산', '섞은 상품']
CAT_GROUP = {'채권': '채권·예금', '주식': '주식', '다른 자산': '대안투자', '섞은 상품': '자산배분'}
CAT_NOTE = {
    '처음 보기 좋은 기본 8개': '원화로 바로 살 수 있는 국내 상장 ETF예요. 추천의 기본 후보 상품이에요.',
    '채권': GROUP_EASY['채권·예금'][1],
    '주식': GROUP_EASY['주식'][1] + ' 아래 순서는 최근 거래가 많았던 순서일 뿐, 좋은 상품 순서가 아니에요.',
    '다른 자산': GROUP_EASY['대안투자'][1],
    '섞은 상품': '주식과 채권 등을 한 상품 안에 미리 섞어 둔 ETF예요.',
}


def _kind_word(p):
    return 'ETF' if p['kind'] == 'ETF' else ('개별주식' if p['kind'] == '주식' else p['kind'])


def _cat_items(products, cat):
    if cat == CATS[0]:
        return list(rc.ETF_NAMES)
    g = CAT_GROUP[cat]
    names = [n for n, p in products.items() if p['group'] == g and n != rc.CASH]
    def order(n):
        p = products[n]
        base = 0 if n in rc.ETF_NAMES else (1 if p.get('list') == '국내 추가 ETF' else 2)
        r = p.get('rank')
        return (base, r if r is not None and pd.notna(r) else 9999)
    return sorted(names, key=order)


def render_products(data, ss, go_page, open_detail, has_wide=True):
    products = data['products']
    legend = ''.join(f'<span>{dot(rc.GROUP_BASE[g])}{easy_group(g).split(" (")[0]}</span>' for g in CAT_GROUP.values())
    html(f"""<div class="page-h"><span class="eyebrow">상품 둘러보기</span><h1>어떤 상품인지 먼저 알아봐요</h1>
         <p>이름으로 찾거나 종류별로 둘러보고, 궁금한 상품의 <b>가격 흐름과 회사 실적</b>을 확인해 보세요. 여기서 고른다고 주문되지는 않아요.</p>
         <div class="glegend">{legend}<em>색은 자산 종류예요</em></div></div>""")

    # ① 이름으로 찾기 (추천 후보 상품 + 국내 상장사 806곳)
    fin = _fin_kr()
    names = fin.drop_duplicates('종목코드').sort_values('종목명')
    opts = [n for n in products if n != rc.CASH]
    label = {n: f'{products[n]["short"]}' + (f' · {products[n]["desc"]}' if products[n]['desc'] != products[n]['short'] else '')
                + f' ({_kind_word(products[n])})' for n in opts}
    kr_opts = [f'{KR_PREFIX}{c}' for c in names['종목코드']]
    label.update(dict(zip(kr_opts, names['종목명'] + ' (' + names['종목코드'] + ') · 국내 기업 재무')))
    with st.container(border=True, key='prod_find'):
        card_title('이름으로 찾기', f'살펴볼 수 있는 상품 {len(opts)}개와 국내 상장사 {len(kr_opts)}곳의 재무를 찾아볼 수 있어요.')
        c1, c2 = st.columns([2.2, 1], vertical_alignment='bottom')
        pick = c1.selectbox('상품·회사 이름', opts + kr_opts, index=None, format_func=lambda k: label.get(k, k),
                            key='prod_search', placeholder='예: 삼성전자, KODEX 200, SPY')
        c2.button('설명 보기', key='prod_search_go', type='primary', width='stretch', disabled=pick is None,
                  on_click=open_detail, args=(pick, 'products'))

    # ② 종류별로 둘러보기
    with st.container(border=True, key='prod_browse'):
        card_title('종류별로 둘러보기', '')
        cat = st.pills('종류', CATS, default=CATS[0], key='prod_cat', label_visibility='collapsed') or CATS[0]
        html(f'<p class="cd">{esc(CAT_NOTE[cat])}</p>')
        items = [n for n in _cat_items(products, cat) if n in products]
        more_key = f'prod_more_{cat}'
        show = items if ss.get(more_key) else items[:8]
        css = ''.join(f'.st-key-{("base_" if cat == CATS[0] else "cat_")}{n} button{{--gc:{rc.GROUP_BASE.get(products[n]["group"], "#98a2b3")}}}'
                      f'.st-key-{("base_" if cat == CATS[0] else "cat_")}{n} button::after{{content:"{easy_group(products[n]["group"]).split(" (")[0]} · {_kind_word(products[n])}"}}'
                      for n in show if str(n).replace('_', '').isalnum())
        html(f'<style>{css}</style>')
        cols = st.columns(2)
        for i, n in enumerate(show):
            p = products[n]
            desc = rc.BASE_DESC.get(n) or (p['desc'] if p['desc'] != p['short'] else easy_group(p['group']))
            key = f'base_{n}' if cat == CATS[0] else f'cat_{n}'
            cols[i % 2].button(f'{p["short"]} · {desc}', key=key, width='stretch', on_click=open_detail,
                               args=(n, 'products'), help=f'{_kind_word(p)} · {easy_group(p["group"])}')
        if len(items) > 8:
            st.button('접기' if ss.get(more_key) else f'{len(items) - 8}개 더 보기', key=f'more_{cat}',
                      on_click=lambda: ss.update({more_key: not ss.get(more_key)}))

    html('<div class="more-h">더 알아보기 <span>필요할 때만 펼쳐 보세요</span></div>')
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
        with st.expander('거래대금 순위표 전체 보기 (많이 사고판 순서 · 좋은 상품 순서 아님)'):
            html('<p class="warnline">거래대금은 하루에 얼마나 많이 사고팔렸는지예요. 순위가 높다고 수익이 좋거나 안전한 상품이라는 뜻은 아니에요. '
                 '표에서 행을 누르면 그 상품 설명으로 갈 수 있는 버튼이 나와요.</p>')
            card_title(f'거래대금 상위 {len(top)}종목 · 국내·미국 통합',
                       f'비교 통화 <b>원화(KRW)</b> · 거래대금 = 종가×거래량의 <b>최근 {meta["window_days"]}거래일 평균</b>'
                       f' (각 시장의 장 마감일 기준: {" / ".join(win) or "-"}) · 미국은 같은 날 원/달러 환율로 환산했어요.{kr_note}')
            _rank_table(top, products, open_detail, 'rank_top')
            card_title(f'채권 ETF 거래대금 상위 {len(bonds)}',
                       '통합 30위 안에 채권 상품이 없어서, 채권 ETF끼리 같은 기준(원화 평균 거래대금)으로 순위를 매겨 더했어요. '
                       '추천 계산의 채권 몫에 함께 들어가요.')
            _rank_table(bonds, products, open_detail, 'rank_bond')
            if not kr_extra.empty:
                card_title(f'국내 추가 ETF {len(kr_extra)}종 · 순위와 별도',
                           '거래대금 순위에 국내 상품이 없어서, 원화로 소액 투자할 수 있는 국내 채권·금·혼합·주식 ETF를 따로 더했어요. '
                           '순위를 바꾸지 않고 별도 목록으로 추천 계산(각 자산 종류 몫)에 함께 넣어요. '
                           f'거래대금은 같은 기준(국내 {kr_extra.window_end.max()}까지 최근 {meta["window_days"]}거래일 평균)이에요.')
                _rank_table(kr_extra, products, open_detail, 'rank_kr')
        with st.expander('순위를 만든 방법과 한계'):
            st.markdown(f"""
- **후보**: 국내 주식(KRX 전체)·국내 ETF는 최근 거래일 거래대금 상위 {meta['pool_per_market']}개씩, 미국 주식(NASDAQ·NYSE·AMEX 전체)은 공개 스크리너의 종가×거래량 상위 {meta['pool_per_market']}개를 후보로 골랐어요. 국내 채권 ETF는 거래대금 상위 20개를 후보에 더했어요.
- **미국 ETF 후보의 한계**: 무료 공개 스크리너가 ETF 거래량을 주지 않아서 대표 미국 ETF 목록(SPY·QQQ·TLT 등 40여 개)을 후보로 썼어요. 목록 밖의 미국 ETF는 순위에 없을 수 있어요.
- **거래대금 계산**: 실제 체결 금액의 합이 아니라 '종가 × 거래량'으로 근사했어요. 두 시장에 같은 방식을 썼어요.
- **기준일**: 국내 {meta['kr_last_session']}, 미국 {meta['us_last_session']} 장 마감까지(장중 데이터는 쓰지 않아요). 수집 시각 {meta['run_at_kst']}.
- **국내 추가 ETF**: 순위와 별개로, 미리 골라 둔 국내 ETF 목록(기본 8종 제외)을 같은 날짜까지의 실제 가격으로 받아 추천 계산에 더했어요. 이 상품들이 순위에 끼어들지는 않아요.
- **추천 계산에서 빼는 종목**: 레버리지·인버스·변동성 상품, 가격 기록이 3년이 안 되는 종목(최근 상장), 같은 지수·같은 회사를 중복으로 담는 종목. 순위는 그대로 보여 드려요.
- **가격과 환율**: 미국 상품은 미국 종가 × 그날 원/달러 환율로 원화 환산하고, 한국 장 마감 때 이미 알려진 전날 미국 종가만 써요(미래 데이터 방지). 분배금은 반영하지 않은 가격이에요.
- **출처**: {', '.join(meta['sources'].values())}
""")
            fails = meta.get('failures') or []
            if fails:
                st.warning(f'수집 중 실패 {len(fails)}건: ' + ', '.join(f"{f['symbol']}({f['step']})" for f in fails[:10]))
    else:
        st.info('거래대금 상위 종목 자료를 불러오지 못해 국내 ETF 8종만 보여 드려요. '
                '잠시 뒤 새로고침해 보고, 계속 안 되면 서비스 운영자에게 알려 주세요.')


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


# ── 상품 설명 ──────────────────────────────────────────────────────────
def _what_is(name, p, market):
    """이 상품이 어떤 돈의 묶음 / 어떤 회사인지 한두 문장"""
    if p['kind'] == 'ETF':
        return ('여러 자산을 한 바구니에 담아 주식처럼 1주씩 사고팔 수 있게 만든 상품(ETF)이에요. '
                + ETF_ABOUT.get(name, f"{p['label']} — 상품 이름이 따라가는 지수·자산을 확인해 주세요."))
    return (f'{market}에 상장된 회사({p["desc"] if p["market"] == "US" else p["short"]})의 주식이에요. '
            '1주를 사면 이 회사의 아주 작은 일부를 갖게 돼요.')


def _check_points(p):
    """꼭 알아 둘 점 (2~3개)"""
    pts = []
    if p['kind'] == 'ETF':
        pts.append('여러 자산에 나눠 담겨 한 회사만 살 때보다 덜 쏠리지만, 담고 있는 자산 값이 떨어지면 함께 떨어져요.')
    else:
        pts.append('한 회사에만 투자하는 것이라, 회사 사정에 따라 값이 크게 오르내리고 손실이 날 수 있어요.')
    if p['group'] in GROUP_EASY and p['group'] != '주식':
        pts.append(f'{easy_group(p["group"])}: {GROUP_EASY[p["group"]][1]}')
    if p.get('currency') == 'USD':
        pts.append('달러로 거래되는 미국 상품이라, 환율이 바뀌면 원화로 본 금액도 달라져요.')
    pts.append('이 화면에서는 주문할 수 없어요. 실제로 사려면 증권사에서 상품 설명서와 수수료를 직접 확인해야 해요.')
    return pts


def render_detail(name, data, ss, go_page):
    back = ss.get('detail_from', 'products')
    back_label = {'result': '내 추천으로', 'mock': '나만의 포트폴리오로', 'products': '상품 둘러보기로'}.get(back, '뒤로')
    st.button(f'← {back_label} 돌아가기', key='detail_back', on_click=go_page, args=(back,))
    if not name:
        st.info('설명을 볼 상품을 먼저 골라 주세요.')
        return
    if str(name).startswith(KR_PREFIX):
        _detail_kr_company(name[len(KR_PREFIX):])
        return
    p = data['products'].get(name)
    if p is None:
        st.warning('이 상품 정보를 찾을 수 없어요. 상품 둘러보기에서 다시 골라 주세요.')
        return
    market = {'KR': '국내', 'US': '미국'}.get(p['market'], '')
    kind = '개별주식' if p['kind'] == '주식' else p['kind']
    tags = [market, kind, easy_group(p['group']), p['currency']]
    if p.get('list') == '국내 추가 ETF':
        tags.append('국내 추가 ETF')
    elif p.get('rank') and pd.notna(p.get('rank')):
        tags.append(f'거래대금 {p["list"]} · {int(p["rank"])}위')
    pts = ''.join(f'<li>{esc(t)}</li>' for t in _check_points(p))
    gc = rc.GROUP_BASE.get(p['group'], '#98a2b3')
    html(f"""<div class="res-hero detail-hero" style="--gc:{gc}"><div class="dh-main"><div class="tags light">{''.join(f'<span>{esc(t)}</span>' for t in tags if t)}</div>
      <div class="who">{esc(p['code'])}</div><h2>{esc(p['short'] if p['market'] != 'US' else p['desc'])}</h2>
      <p class="desc">{esc(_what_is(name, p, market))}</p></div>
      <ul class="checks"><li class="h">꼭 알아 둘 점</li>{pts}</ul></div>""")
    if p.get('reason'):
        st.info(f'추천 계산에서는 빠져 있어요: {p["reason"]}')

    _price_card(name, p, data)
    if p['kind'] == 'ETF':
        with st.expander('ETF는 재무제표 대신 이렇게 봐요'):
            html(f"""<p class="cd">ETF는 재무제표 대신 무엇을 담는지와 비용을 봐요. ETF는 여러 회사(또는 채권·원자재)를 한 번에 담은 펀드라 한 회사의 매출·부채 같은 재무제표가 없어요.</p>
            <ul class="changes one">
              <li><b>무엇을 담나요?</b> {esc(ETF_ABOUT.get(name, f"{p['label']} — 상품 이름이 따라가는 지수·자산을 확인해 주세요."))}</li>
              <li><b>자산 종류</b> {esc(easy_group(p['group']))} — 서비스에서는 {dot(rc.GROUP_BASE.get(p['group'], '#98a2b3'))}색으로 표시해요.</li>
              <li><b>확인할 것</b> 총보수(1년 운용 비용), 추종 오차, 분배금 지급 여부는 운용사 홈페이지의 상품 설명서에서 확인할 수 있어요.</li>
            </ul>""")
    elif p['market'] == 'US':
        _fin_card(svc.financials_us(data['universe']['fin_us'] if data.get('universe') else None, p['code']),
                  '억 달러', 'SEC EDGAR 10-K 연간 보고서(companyfacts API) · 미국 회계기준(US GAAP) · 단위 억 달러(USD)',
                  p['code'])
    else:
        _fin_card(svc.financials_kr(_fin_kr(), p['code']), '억원', '국내 상장사 연간 재무 자료(재무_2026) · 단위 억원(KRW)',
                  p['code'])


def _detail_kr_company(code):
    fin = _fin_kr()
    row = fin[fin['종목코드'] == code]
    if row.empty:
        st.warning('이 기업의 재무 자료를 찾을 수 없어요.')
        return
    nm = row['종목명'].iloc[-1]
    html(f"""<div class="res-hero detail-hero" style="--gc:{rc.GROUP_BASE['주식']}"><div class="dh-main"><div class="tags light"><span>국내</span><span>개별주식</span><span>KRW</span></div>
      <div class="who">{esc(code)}</div><h2>{esc(nm)}</h2>
      <p class="desc">국내에 상장된 회사예요. 추천 상품 목록 밖의 기업이라 가격 차트 없이 연간 재무만 보여 드려요.</p></div>
      <ul class="checks"><li class="h">꼭 알아 둘 점</li>
      <li>한 회사에만 투자하는 것이라, 회사 사정에 따라 값이 크게 오르내리고 손실이 날 수 있어요.</li>
      <li>과거 실적이 좋았다고 앞으로도 좋다는 보장은 없어요. 이 화면에서는 주문할 수 없어요.</li></ul></div>""")
    _fin_card(svc.financials_kr(fin, code), '억원', '국내 상장사 연간 재무 자료(재무_2026) · 단위 억원(KRW)', code)


def _price_card(name, p, data):
    u = data.get('universe')
    local = None
    if p['currency'] == 'USD' and u is not None and name in u['local']:
        local = u['local'][name]
    krw = data['prices'][name] if name in data['prices'] else None
    with st.container(border=True, key='price_card'):
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
        gcol = rc.GROUP_BASE.get(p['group'], '#2563eb')
        fig = go.Figure(go.Scatter(x=series.index, y=series, line=dict(color=gcol, width=2.2),
                                   fill='tozeroy', fillcolor='rgba(0,0,0,0)',
                                   hovertemplate=('$%{y:,.2f}' if local is not None else '%{y:,.0f}원') + '<extra></extra>'))
        plot_style(fig, 260, legend=False)
        lo_, hi_ = float(series.min()), float(series.max())
        pad = (hi_ - lo_) * 0.08 or hi_ * 0.05
        fig.update_yaxes(range=[lo_ - pad, hi_ + pad], tickprefix='$' if local is not None else '',
                         ticksuffix='' if local is not None else '원', tickformat=',.2f' if local is not None and hi_ < 100 else ',.0f')
        c1, c2 = st.columns([8, 5], gap='large', vertical_alignment='center')
        with c1:
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        with c2:
            if stats is None:
                st.info('가격 기록이 60거래일보다 짧아 수익률·변동성을 계산하지 않았어요.')
            else:
                last_krw = krw.dropna().iloc[-1]
                html(f"""<div class="stack">
                  <div><span>현재가 (원화)</span><b>{last_krw:,.0f}원</b><em>{'$' + format(local.dropna().iloc[-1], ',.2f') + ' (현지 종가)' if local is not None else '마지막 종가'}</em></div>
                  <div><span>가장 크게 떨어졌던 폭</span><b class="down">{stats['mdd']:.1%}</b><em>최근 {rc.LOOKBACK_YEARS}년 중 고점 대비</em></div>
                  <div><span>1년 평균으로 바꾼 변화 · 흔들림</span><b>{stats['return']:+.1%} · {stats['vol']:.1%}</b><em>과거 값이에요 (연환산 수익률 · 변동성). 앞으로를 보장하지 않아요.</em></div></div>""")


def _fin_card(table, unit, source, code):
    with st.container(border=True, key='fin_card'):
        card_title('이 회사는 얼마나 팔고, 얼마나 남겼나요?', f'출처: {source}')
        if table is None or table.empty:
            st.info('이 종목의 재무 자료를 확보하지 못했어요. (예: 미국 외 기업이 내는 20-F 보고서, 자료가 없는 기업) '
                    '빈 값을 0으로 채우지 않았어요.')
            return
        x = table['연도']
        lastrow = table.iloc[-1]
        yr = str(lastrow['연도'])      # 원자료 표기 그대로 (국내 '2025년', 미국 '2026.01 결산')

        def delta(col):
            if len(table) < 2:
                return ''
            a, b = table[col].iloc[-2], lastrow[col]
            if pd.isna(a) or pd.isna(b):
                return ''
            return '전년보다 늘었어요' if b > a else ('전년보다 줄었어요' if b < a else '전년과 같아요')
        fig = go.Figure()
        fig.add_bar(x=x, y=table['매출액'], name='매출액', marker_color='#C9D3E0',
                    hovertemplate='%{x}<br>매출액 %{y:,.0f}' + unit + '<extra></extra>')
        fig.add_bar(x=x, y=table['영업이익'], name='영업이익', marker_color=INK,
                    hovertemplate='%{x}<br>영업이익 %{y:,.0f}' + unit + '<extra></extra>')
        plot_style(fig, 280, barmode='group', top=36, title=dict(text=f'연도별 매출액·영업이익 ({unit})', font=dict(size=14), x=0))
        fig.update_layout(legend=dict(orientation='h', y=-0.18))
        fig.update_yaxes(tickformat=',.0f')
        c1, c2 = st.columns([8, 5], gap='large', vertical_alignment='center')
        with c1:
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        with c2:
            html(f"""<div class="stack">
              <div><span>매출액 · {esc(yr)}</span><b>{_fmt(lastrow['매출액'], unit)}</b>
                <em>물건·서비스를 팔아 들어온 돈이에요. {delta('매출액')}</em></div>
              <div><span>영업이익 · {esc(yr)}</span><b>{_fmt(lastrow['영업이익'], unit)}</b>
                <em>본업으로 번 돈에서 비용을 빼고 남긴 돈이에요. 마이너스면 손해를 봤다는 뜻이에요. {delta('영업이익')}</em></div>
            </div>""")
        missing = 0
        with st.expander('빚은 얼마나 되나요? (부채비율·영업이익률·연도별 원자료 표)'):
            html('<ul class="terms plain"><li><b>부채비율</b> 회사가 가진 자기 돈(자본) 대비 빚(부채)의 크기예요. 높을수록 빚 부담이 커요.</li>'
                 '<li><b>영업이익률</b> 매출 100원 중 본업으로 남긴 돈이 몇 원인지예요.</li></ul>')
            fig2 = go.Figure()
            fig2.add_scatter(x=x, y=table['부채비율(%)'], name='부채비율', mode='lines+markers', line=dict(color='#B4532A', width=3),
                             connectgaps=False, hovertemplate='%{x}<br>부채비율 %{y:,.0f}%<extra></extra>')
            fig2.add_scatter(x=x, y=table['영업이익률(%)'], name='영업이익률', mode='lines+markers', line=dict(color=MUTED, width=2, dash='dot'),
                             connectgaps=False, hovertemplate='%{x}<br>영업이익률 %{y:,.1f}%<extra></extra>')
            plot_style(fig2, 260, top=36, title=dict(text='부채비율·영업이익률 (%)', font=dict(size=14), x=0))
            fig2.update_layout(legend=dict(orientation='h', y=-0.2))
            fig2.update_yaxes(ticksuffix='%')
            st.plotly_chart(fig2, width='stretch', config={'displayModeBar': False})
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
        st.caption('재무 수치는 공시 자료 기준이며, 회사가 나중에 고친 값(정정 공시)과 다를 수 있어요. '
                   '‘자료 없음’은 원자료에 값이 없다는 뜻이에요.')
