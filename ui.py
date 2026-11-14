"""여러 화면에서 같이 쓰는 작은 도구 (HTML 출력, 금액 표시, 카드 제목)"""
import html as _html
import math

import streamlit as st


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


def card_title(title, desc=''):
    html(f'<h3 class="ct">{title}</h3><p class="cd">{desc}</p>')


def dot(color):
    return f'<span class="dot" style="background:{color}"></span>'
