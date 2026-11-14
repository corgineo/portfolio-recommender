"""기업 분석 화면: 팀이 준비한 data/재무_2026.csv(국내 상장사 연간 재무, 금액 단위 천원)를 보여 줘요.

- 화면 금액은 억원으로 바꿔 보여 줘요 (천원 ÷ 100,000 = 억원).
- 부채비율 = 부채총계 ÷ 자본총계 × 100 (자본이 0 이하이면 계산하지 않아요), 영업이익률 = 영업이익 ÷ 매출액 × 100.
- 빈 값은 0으로 채우지 않고 '자료 없음'으로 보여 줘요. 미국 기업 재무 자료는 아직 없어서 '자료 없음'으로 안내해요.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import html, esc, plot_style, INK, MUTED

CSV_PATH = Path(__file__).resolve().parent / "data" / "재무_2026.csv"
METRICS = ["매출액", "영업이익", "당기순이익"]
COLUMNS = ["종목코드", "기업명", "사업연도", *METRICS]
EXAMPLE = "종목코드,기업명,사업연도,매출액,영업이익,당기순이익\n005930,삼성전자,2025,1000,150,100"
SOURCE_UNIT = 1_000            # 원본 CSV 금액 단위: 천원
EOK = 100_000_000              # 1억원
YEARS = 10                     # 그래프에 보여 줄 최근 연도 수


def load_financials(path):
    for encoding in ("utf-8-sig", "cp949"):
        try:
            data = pd.read_csv(path, dtype=str, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV를 UTF-8 또는 CP949로 저장해 주세요.")
    data.columns = data.columns.str.strip()
    data = data.rename(columns={"종목명": "기업명", "회계연도": "사업연도"})
    missing = [column for column in COLUMNS if column not in data]
    if missing:
        raise ValueError("필수 열이 빠졌어요. " + ", ".join(missing))
    if data.empty:
        raise ValueError("CSV에 재무 데이터 행이 없어요.")
    for column in COLUMNS:
        data[column] = data[column].str.strip()
    codes = data["종목코드"].str.upper().str.replace(r"^A(?=[0-9A-Z]{6}$)", "", regex=True)
    if not codes.str.fullmatch(r"(?:[0-9]{1,6}|[0-9A-Z]{6})", na=False).all():
        raise ValueError("종목코드 형식을 확인해 주세요. 예: A005930, 005930")
    data["종목코드"] = codes.str.zfill(6)
    if not data["사업연도"].str.fullmatch(r"[0-9]{4}", na=False).all():
        raise ValueError("사업연도는 네 자리 숫자로 넣어 주세요.")
    if data["기업명"].fillna("").eq("").any():
        raise ValueError("기업명이 비어 있는 행이 있어요.")
    data["사업연도"] = data["사업연도"].astype(int)
    if data.duplicated(["종목코드", "사업연도"]).any():
        raise ValueError("같은 종목코드와 사업연도가 두 번 이상 있어요. 한 행만 남겨 주세요.")
    for column in [*METRICS, *(c for c in ("자산총계", "부채총계", "자본총계") if c in data)]:
        raw = data[column].str.replace(",", "", regex=False).replace("", None)
        values = pd.to_numeric(raw, errors="coerce")
        if ((raw.notna() & values.isna()) | values.isin([float("inf"), float("-inf")])).any():
            raise ValueError(f"{column}에는 숫자나 빈칸을 넣어 주세요.")
        data[column] = values
    return data.sort_values(["종목코드", "사업연도"])


def to_eok(thousand_won):
    """원본 천원 값 → 억원 (빈 값은 그대로 NaN)"""
    return thousand_won * SOURCE_UNIT / EOK


def company_table(data, code, years=YEARS):
    """한 기업의 최근 years 개 연도 표 (억원, 부채비율·영업이익률 %). 자료가 없으면 None"""
    d = data[data["종목코드"].eq(code)].sort_values("사업연도")
    if d.empty:
        return None
    d = d.tail(years)
    out = pd.DataFrame({"사업연도": d["사업연도"].astype(int).to_numpy()})
    for c in ["매출액", "영업이익", "당기순이익", "부채총계", "자본총계"]:
        out[c] = to_eok(d[c].to_numpy(dtype=float)) if c in d else np.nan
    out["부채비율(%)"] = np.where(out["자본총계"] > 0, out["부채총계"] / out["자본총계"] * 100, np.nan)
    out["영업이익률(%)"] = np.where(out["매출액"] > 0, out["영업이익"] / out["매출액"] * 100, np.nan)
    return out


def fmt(v, unit="억원", digits=0):
    if v is None or pd.isna(v):
        return "자료 없음"
    return f"{v:,.{digits}f}{unit}"


def _delta(table, col):
    if len(table) < 2:
        return ""
    a, b = table[col].iloc[-2], table[col].iloc[-1]
    if pd.isna(a) or pd.isna(b):
        return ""
    return "전년보다 늘었어요." if b > a else ("전년보다 줄었어요." if b < a else "전년과 같아요.")


PROFILE_KR = Path(__file__).resolve().parent / "data" / "company_profiles_kr.csv"
PROFILE_US = Path(__file__).resolve().parent / "data" / "company_profiles_us.csv"


@st.cache_data(show_spinner=False)
def load_profiles():
    """사업 소개 캐시 (build_company_profiles.py · 미국은 공식 자료 확인본). 파일이 없으면 빈 표"""
    def read(path, key):
        try:
            return pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False).set_index(key)
        except FileNotFoundError:
            return pd.DataFrame()
    return read(PROFILE_KR, "code"), read(PROFILE_US, "ticker")


def render_profile(code, us, kr_prof, us_prof):
    """기업이 하는 일: 1~2문장 + 대표 제품 태그 + 출처. 소개가 없으면 정확히 '미확보'라고만 알려요"""
    prof = us_prof if us else kr_prof
    if code not in prof.index or (not us and prof.at[code, "status"] != "ok"):
        why = ("상장법인목록의 회사 이름이 재무 자료와 달라(이름 변경 등) 같은 회사인지 확인되지 않았어요."
               if not us and code in prof.index and prof.at[code, "status"] == "name_mismatch"
               else "상장법인목록에서 이 회사를 찾지 못했어요.")
        html(f'<div class="biz na"><b>기업 소개 미확보</b><p>{why} 다른 회사 설명을 대신 쓰지 않았어요.</p></div>')
        return
    r = prof.loc[code]
    tags = "".join(f"<span>{esc(t)}</span>" for t in r["tags"].split("|") if t)
    if us:
        src = (f'출처: <a href="{esc(r["source_url"])}" target="_blank" rel="noopener">{esc(r["source"])}</a> · '
               f'확인일 {esc(r["checked_at"])}')
    else:
        hp = (f' · <a href="{esc(r["homepage"])}" target="_blank" rel="noopener">회사 홈페이지</a>' if r["homepage"] else "")
        if r.get("written") == "official":            # 회사 공식 최신 자료로 보완한 소개
            ref = (f' · <a href="{esc(r["ref_url"])}" target="_blank" rel="noopener">{esc(r["ref_label"])}</a>'
                   if r.get("ref_url") else "")
            src = (f'출처: <a href="{esc(r["source_url"])}" target="_blank" rel="noopener">{esc(r["source"])}</a>{ref} · '
                   f'확인일 {esc(r["collected_at"])}')
        else:
            src = (f'출처: <a href="{esc(r["source_url"])}" target="_blank" rel="noopener">{esc(r["source"])}</a> · '
                   f'수집일 {esc(r["collected_at"])} 기준이라 최신 사업과 다를 수 있어요{hp}')
    html(f'<div class="biz"><b>이 회사는 무슨 일을 하나요?</b><p>{esc(r["summary"])}</p>'
         f'<div class="tags light">{tags}</div><p class="src">{src}</p></div>')
    if not us and (r["industry"] or r["products"]):
        with st.expander("상장법인목록 원문 보기 (업종 · 주요 제품)"):
            st.markdown(f"**업종** {r['industry'] or '자료 없음'}  \n**주요 제품** {r['products'] or '자료 없음'}")
            st.caption(f"KIND 상장법인목록(한국거래소) 원문 · 수집일 {r['collected_at']} · 지난 사업이 남아 있을 수 있어요.")


def render_company_financials(focus=None, preselect=None, preselect_name=None, on_clear=None):
    """focus: 내 추천에 담긴 개별 종목 [{'name','code','us'}]
    preselect: 다른 화면에서 고른 종목코드(미국은 티커). 미국 20종목은 사업 소개만 있고 재무는 '자료 없음'이에요.
    목록에 없는 종목이면 다른 회사로 바꿔 보여 주지 않고 '자료 없음' 상태를 유지해요."""
    html("""<div class="page-h"><span class="eyebrow">기업 분석</span><h1>기업 살펴보기</h1>
    <p>회사가 무슨 사업을 하는지, 얼마나 팔고(매출액) 본업으로 얼마나 남기는지(영업이익), 빚은 얼마나 되는지(부채비율)를 보여 드려요.</p></div>""")
    try:
        data = load_financials(CSV_PATH)
    except FileNotFoundError:
        st.info("재무 자료가 아직 준비되지 않았어요.")
        return
    except (ValueError, OSError) as exc:
        st.error(f"재무 자료를 읽지 못했어요. {exc}")
        return
    kr_prof, us_prof = load_profiles()

    names = data.drop_duplicates("종목코드", keep="last").set_index("종목코드")["기업명"].to_dict()
    us_names = {t: f'{r["name_ko"]}' for t, r in us_prof.iterrows()}
    focus = focus or []
    if focus:
        chips = "".join(f"<span>{esc(f['name'])}{' · 미국' if f['us'] else ''}</span>" for f in focus)
        html(f'<div class="tags light"><span class="lbl">내 추천 종목</span>{chips}</div>')

    # 목록에 없는 종목을 골라 들어온 경우: 다른 회사로 대신 보여 주지 않아요
    if preselect and preselect not in names and preselect not in us_names:
        nm = preselect_name or preselect
        html(f"""<div class="fin-head"><span>선택한 기업</span><h2>{esc(nm)} <em>({esc(preselect)})</em></h2></div>""")
        st.warning(f"{nm}: 이 서비스에 기업 소개와 재무 자료가 없어요. 값을 임의로 채우지 않았어요.")
        if on_clear is not None:
            st.button("다른 기업 검색하기", key="company_clear", on_click=on_clear)
        return

    mine = [f["code"] for f in focus if f["code"] in names or f["code"] in us_names]
    options = mine + [c for c in names if c not in mine] + [t for t in us_names if t not in mine]
    key = "company_financials_ticker"
    if preselect in options and st.session_state.get("_company_pre") != preselect:
        st.session_state[key] = preselect
    st.session_state["_company_pre"] = preselect

    def label(t):
        nm = names.get(t) or us_names.get(t, t)
        return f"{nm} ({t})" + (" · 미국" if t in us_names and t not in names else "") + (" · 내 추천" if t in mine else "")
    code = st.selectbox(f"기업 검색 (이름이나 종목코드 · 국내 {len(names)}개 · 미국 {len(us_names)}개)", options,
                        key=key, format_func=label)
    us = code in us_names and code not in names
    nm = us_names[code] if us else names[code]
    html(f"""<div class="fin-head"><span>선택한 기업</span><h2>{esc(nm)} <em>({code}{' · 미국' if us else ''})</em></h2></div>""")
    render_profile(code, us, kr_prof, us_prof)
    if us:
        st.info("미국 기업이라 이 서비스에 재무 자료가 아직 없어요. 매출·영업이익·부채비율은 보여 드리지 않고, 값을 임의로 채우지 않았어요.")
        return
    table = company_table(data, code)
    if table is None or table[["매출액", "영업이익"]].isna().all().all():
        st.info("이 기업은 매출액·영업이익 자료가 없어요.")
        return
    last = table.iloc[-1]
    yr = f"{int(last['사업연도'])}년"
    x = table["사업연도"].astype(str) + "년"

    with st.container(border=True, key="fin_card"):
        c1, c2 = st.columns([1.618, 1], gap="large", vertical_alignment="center")
        with c1:
            fig = go.Figure()
            fig.add_bar(x=x, y=table["매출액"], name="매출액", marker_color="#C9D3E0",
                        hovertemplate="%{x}<br>매출액 %{y:,.0f}억원<extra></extra>")
            fig.add_bar(x=x, y=table["영업이익"], name="영업이익", marker_color=INK,
                        hovertemplate="%{x}<br>영업이익 %{y:,.0f}억원<extra></extra>")
            plot_style(fig, 300, barmode="group", top=36,
                       title=dict(text="연도별 매출액·영업이익 (억원)", font=dict(size=14), x=0))
            fig.update_layout(legend=dict(orientation="h", y=-0.18))
            fig.update_yaxes(tickformat=",.0f")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="fin_bar")
        with c2:
            html(f"""<div class="stack">
              <div><span>매출액 · {yr}</span><b>{fmt(last['매출액'])}</b><em>물건·서비스를 팔아 들어온 돈이에요. {_delta(table, '매출액')}</em></div>
              <div><span>영업이익 · {yr}</span><b>{fmt(last['영업이익'])}</b><em>본업으로 번 돈에서 비용을 빼고 남긴 돈이에요. {_delta(table, '영업이익')}</em></div>
              <div><span>부채비율 · {yr}</span><b>{fmt(last['부채비율(%)'], '%')}</b><em>자기 돈(자본) 대비 빚(부채)의 크기예요. 높을수록 빚 부담이 커요.</em></div>
            </div>""")

        c3, c4 = st.columns([1.618, 1], gap="large", vertical_alignment="center")
        with c3:
            fig2 = go.Figure()
            fig2.add_scatter(x=x, y=table["부채비율(%)"], name="부채비율", mode="lines+markers",
                             line=dict(color="#B4532A", width=3), connectgaps=False,
                             hovertemplate="%{x}<br>부채비율 %{y:,.0f}%<extra></extra>")
            fig2.add_scatter(x=x, y=table["영업이익률(%)"], name="영업이익률", mode="lines+markers",
                             line=dict(color=MUTED, width=2, dash="dot"), connectgaps=False,
                             hovertemplate="%{x}<br>영업이익률 %{y:,.1f}%<extra></extra>")
            plot_style(fig2, 260, top=36, title=dict(text="부채비율·영업이익률 (%)", font=dict(size=14), x=0))
            fig2.update_layout(legend=dict(orientation="h", y=-0.2))
            fig2.update_yaxes(ticksuffix="%")
            st.plotly_chart(fig2, width="stretch", config={"displayModeBar": False}, key="fin_ratio")
        with c4:
            html('<ul class="terms plain"><li><b>부채비율</b> 100%면 빚과 자기 돈이 같다는 뜻이에요. 업종마다 보통 수준이 달라요.</li>'
                 '<li><b>영업이익률</b> 매출 100원 중 본업으로 남긴 돈이 몇 원인지예요.</li></ul>')
        st.caption(f"국내 상장사 연간 재무 자료 · {nm} ({code}) · "
                   f"사업연도 {int(table['사업연도'].iloc[0])}~{int(table['사업연도'].iloc[-1])} · 단위 억원 · "
                   "빈 값은 ‘자료 없음’으로 표시해요.")

    with st.expander("연도별 자료 표"):
        disp = pd.DataFrame({"사업연도": x})
        for c in ["매출액", "영업이익", "당기순이익", "부채총계", "자본총계"]:
            disp[f"{c}(억원)"] = [fmt(v, "") for v in table[c]]
        disp["부채비율"] = [fmt(v, "%") for v in table["부채비율(%)"]]
        disp["영업이익률"] = [fmt(v, "%", 1) for v in table["영업이익률(%)"]]
        st.dataframe(disp, hide_index=True, width="stretch")


if __name__ == "__main__":
    st.set_page_config(page_title="기업 재무 분석", layout="wide")
    render_company_financials()
