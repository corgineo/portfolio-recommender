"""여러 화면에서 같이 쓰는 작은 도구 (HTML 출력, 금액 표시, 도넛·그래프 스타일)와 초보자용 공통 문구"""
import html as _html
import math

import streamlit as st

# ── 브랜드 색 (화면 틀). 자산 종류 색(recommender.GROUP_BASE)과 섞지 않아요 ──
INK = '#16213B'
INK2 = '#3B4762'
MUTED = '#5E667C'
BRAND = '#2E5B7F'
LINE = '#E4DED3'
GRID = '#ECE7DD'


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def esc(s):
    return _html.escape(str(s))


def won(v):
    """원 → '1,234만원' / '1.2억원'. 값이 없으면 '-'"""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return '-'
    sign = '-' if v < 0 else ''
    v = abs(v)
    if v >= 1e8:
        return f'{sign}{v / 1e8:,.1f}억원'
    if v >= 1e4:
        return f'{sign}{v / 1e4:,.0f}만원'
    return f'{sign}{v:,.0f}원'


def won_exact(v):
    """정확한 원화 금액을 억·만 단위로 끊어 읽기 쉽게: 9999600192 → '99억 9,960만 192원' (반올림하지 않아요)"""
    v = int(round(v))
    if v == 0:
        return '0원'
    sign, v = ('-' if v < 0 else ''), abs(v)
    eok, rest = divmod(v, 100_000_000)
    man, one = divmod(rest, 10_000)
    parts = ([f'{eok:,}억'] if eok else []) + ([f'{man:,}만'] if man else []) + ([f'{one:,}'] if one else [])
    return sign + ' '.join(parts) + '원'


GROUP_TINY = {'채권·예금': '채권', '주식': '주식', '대안투자': '다른 자산', '자산배분': '자산배분', '유동성': '현금'}


def card_title(title, desc=''):
    html(f'<h3 class="ct">{title}</h3>' + (f'<p class="cd">{desc}</p>' if desc else ''))


def section(num, title, desc=''):
    """섹션 머리: 번호 + 큰 제목 + 한 줄 설명"""
    n = f'<span class="sn">{num}</span>' if num else ''
    html(f'<div class="sec-h">{n}<div><h3>{title}</h3>' + (f'<p>{desc}</p>' if desc else '') + '</div></div>')


def dot(color):
    return f'<span class="dot" style="background:{color}"></span>'


def donut_svg(segs, top='', main='', sub='', size=240, thick=30, label='구성 도넛 그래프'):
    """segs: [(이름, 비율%, 색)] → 도넛 SVG 문자열. 비율 합이 100보다 작으면 나머지는 빈 칸(옅은 회색)으로 남겨요.
    색만으로 구분하지 않도록 화면에서는 항상 옆에 이름·%·금액 범례를 함께 둬요."""
    r = (size - thick) / 2
    c = 2 * math.pi * r
    cx = size / 2
    parts = [f'<circle cx="{cx}" cy="{cx}" r="{r:.2f}" fill="none" stroke="#EDE8DF" stroke-width="{thick}"/>']
    start = 0.0
    total = sum(max(0.0, float(v)) for _, v, _ in segs)
    gap = 1.2 if len([s for s in segs if s[1] > 0]) > 1 else 0
    for name, v, color in segs:
        v = max(0.0, float(v))
        if v <= 0:
            continue
        ln = c * v / 100
        draw = max(ln - gap, 0.6)
        parts.append(f'<circle cx="{cx}" cy="{cx}" r="{r:.2f}" fill="none" stroke="{color}" stroke-width="{thick}" '
                     f'stroke-dasharray="{draw:.2f} {c - draw:.2f}" stroke-dashoffset="{-start:.2f}" '
                     f'transform="rotate(-90 {cx} {cx})"><title>{esc(name)} {v:.1f}%</title></circle>')
        start += ln
    aria = esc(label + ': ' + ', '.join(f'{n} {v:.1f}%' for n, v, _ in segs if v > 0))
    center = (f'<div class="dn-c"><span>{top}</span><b>{main}</b><em>{sub}</em></div>' if (top or main or sub) else '')
    return (f'<div class="donut" data-total="{total:.1f}" style="width:{size}px;max-width:100%">'
            f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="{aria}">{"".join(parts)}</svg>{center}</div>')


def plot_style(fig, height, legend=True, **kw):
    """Plotly 그래프 공통 모양: 투명 바탕, 얇은 격자, 같은 글꼴"""
    fig.update_layout(height=height, margin=dict(t=kw.pop('top', 8), b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)', font=dict(family='Pretendard', color=INK2, size=13),
                      showlegend=legend, legend=dict(orientation='h', y=1.1, x=0, font=dict(size=13)),
                      hoverlabel=dict(font=dict(family='Pretendard')), **kw)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    fig.update_xaxes(showgrid=False, linecolor=LINE)
    return fig


# ── 초보자용 자산 종류 이름·설명 (recommender 의 자산군 이름은 그대로 두고 화면 표시만 바꿔요) ──
GROUP_ORDER = ['채권·예금', '주식', '대안투자', '자산배분', '유동성']
GROUP_EASY = {   # 자산군 → (쉬운 이름, 한 줄 설명)
    '채권·예금': ('채권', '나라·회사에 돈을 빌려주고 이자를 받는 상품이에요. 보통 주식보다 덜 흔들리지만, '
                       '금리가 오르거나 빌려 간 곳이 어려워지면 값이 떨어질 수 있어요.'),
    '주식': ('주식', '회사의 일부를 사는 거예요. 회사가 성장하면 함께 오를 수 있지만, 오르내림이 크고 손실이 날 수 있어요.'),
    '대안투자': ('다른 자산 (금·원유·달러·리츠)', '주식·채권과 다르게 움직일 때가 많아, 섞어 두면 전체가 덜 흔들리는 데 도움이 될 수 있어요. '
                                     '이것만 보면 값이 크게 변하기도 해요.'),
    '자산배분': ('자산배분 (혼합형 ETF)', '주식과 채권을 한 상품 안에 섞어 담은 혼합형 ETF예요. '
                                 '하나만 사도 주식·채권에 나눠 투자하는 효과가 있지만, 손실이 날 수 있어요.'),
    '유동성': ('남겨 둘 돈 (현금)', '급할 때 바로 꺼내 쓸 수 있게 CMA·예금 등에 두는 돈이에요. '
                            '1주 단위로 사고 남은 잔돈도 여기에 더해져요.'),
}


GROUP_ONE = {   # 결과 화면 기본용 짧은 한 문장 (손실 가능성 포함). 긴 설명은 GROUP_EASY
    '채권·예금': '빌려주고 이자를 받아요. 값이 내려갈 수도 있어요.',
    '주식': '회사의 일부를 사요. 값이 크게 오르내려요.',
    '대안투자': '금·원유·달러·리츠예요. 이것도 손실이 날 수 있어요.',
    '자산배분': '주식과 채권을 한 상품에 섞은 혼합형 ETF예요.',
    '유동성': '쓰지 않고 남겨 둘 돈이에요. 1주를 못 사서 남는 돈도 더해져요.',
}


def easy_group(g):
    return GROUP_EASY.get(g, (g, ''))[0]


TERMS = {   # 여러 화면에서 쓰는 낱말 풀이
    '포트폴리오': '내가 돈을 여러 상품에 나눠 담은 투자 구성이에요.',
    '비중': '전체 돈에서 한 상품(또는 한 종류)이 차지하는 몫이에요. 100만원 중 30만원이면 30%예요.',
    'ETF': '여러 회사 주식이나 채권을 한 바구니에 담아, 주식처럼 1주씩 사고팔 수 있게 만든 상품이에요.',
    '최대 낙폭': '살펴본 기간 중 가장 높았던 때보다 가장 많이 떨어졌던 비율이에요. 앞으로의 최대 손실 한도는 아니에요.',
    '변동성': '값이 얼마나 크게 오르내렸는지를 나타내요. 클수록 짧은 기간에 많이 오르거나 떨어졌다는 뜻이에요.',
    '연환산 수익률': '기간 전체의 평균을 1년 기준으로 바꾼 수익률이에요. 해마다 그만큼 벌었다는 뜻은 아니에요.',
}
