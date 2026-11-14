"""팀이 준비한 data/재무_2026.csv를 표시하는 Streamlit 화면."""
from pathlib import Path

import pandas as pd
import streamlit as st

CSV_PATH = Path(__file__).resolve().parent / "data" / "재무_2026.csv"
METRICS = ["매출액", "영업이익", "당기순이익"]
COLUMNS = ["종목코드", "기업명", "사업연도", *METRICS]
EXAMPLE = "종목코드,기업명,사업연도,매출액,영업이익,당기순이익\n005930,삼성전자,2025,1000,150,100"


def load_financials(path):
    for encoding in ("utf-8-sig", "cp949"):
        try:
            data = pd.read_csv(path, dtype=str, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV를 UTF-8 또는 CP949로 저장해 줘.")
    data.columns = data.columns.str.strip()
    data = data.rename(columns={"종목명": "기업명", "회계연도": "사업연도"})
    missing = [column for column in COLUMNS if column not in data]
    if missing:
        raise ValueError("필수 열이 빠졌어. " + ", ".join(missing))
    if data.empty:
        raise ValueError("CSV에 재무 데이터 행을 추가해 줘.")
    for column in COLUMNS:
        data[column] = data[column].str.strip()
    codes = data["종목코드"].str.upper().str.replace(r"^A(?=[0-9A-Z]{6}$)", "", regex=True)
    if not codes.str.fullmatch(r"(?:[0-9]{1,6}|[0-9A-Z]{6})", na=False).all():
        raise ValueError("종목코드 형식을 확인해 줘. 예: A005930, 005930")
    data["종목코드"] = codes.str.zfill(6)
    if not data["사업연도"].str.fullmatch(r"[0-9]{4}", na=False).all():
        raise ValueError("사업연도는 네 자리 숫자로 넣어 줘.")
    if data["기업명"].fillna("").eq("").any():
        raise ValueError("기업명이 비어 있는 행이 있어.")
    data["사업연도"] = data["사업연도"].astype(int)
    if data.duplicated(["종목코드", "사업연도"]).any():
        raise ValueError("같은 종목코드와 사업연도가 두 번 이상 있어. 기준을 통일해 한 행만 남겨 줘.")
    for column in [*METRICS, *(c for c in ("자산총계", "부채총계", "자본총계") if c in data)]:
        raw = data[column].str.replace(",", "", regex=False).replace("", None)
        values = pd.to_numeric(raw, errors="coerce")
        if ((raw.notna() & values.isna()) | values.isin([float("inf"), float("-inf")])).any():
            raise ValueError(f"{column}에는 숫자나 빈칸을 넣어 줘.")
        data[column] = values
    return data.sort_values(["종목코드", "사업연도"])


def render_company_financials():
    st.title("기업 재무 분석")
    st.caption("출처 재무_2026.csv · 금액은 원본 수치 그대로 표시")
    try:
        data = load_financials(CSV_PATH)
    except FileNotFoundError:
        st.info("프로젝트의 data/재무_2026.csv에 팀의 재무 데이터를 넣어 줘.")
        st.caption("아래는 열 형식을 보여주는 가상 수치 예시야.")
        st.code(EXAMPLE, language="text")
        return
    except (ValueError, OSError) as exc:
        st.error(f"재무 CSV를 읽지 못했어. {exc}")
        return

    names = data.drop_duplicates("종목코드", keep="last").set_index("종목코드")["기업명"]
    code = st.selectbox("기업 선택", names.index.tolist(),
                        format_func=lambda ticker: f"{names[ticker]} ({ticker})",
                        key="company_financials_ticker")
    company = data.loc[data["종목코드"].eq(code)]
    fields = [*METRICS, *(c for c in ("자산총계", "부채총계", "자본총계") if c in company)]
    st.dataframe(company[["사업연도", *fields]], hide_index=True)
    chart = company.set_index("사업연도")[METRICS].dropna(how="all")
    if not chart.empty:
        chart.index = chart.index.astype(str)
        st.bar_chart(chart, stack=False)
    st.caption("빈칸은 해당 연도에 입력된 값이 없는 항목이야.")


if __name__ == "__main__":
    st.set_page_config(page_title="기업 재무 분석", layout="wide")
    render_company_financials()
