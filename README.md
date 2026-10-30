# 주식 초보를 위한 포트폴리오 추천 서비스 (초안)

**사이트: https://first-portfolio.streamlit.app**

예산 · 투자 기간 · 설문 5문항 → 투자성향 판정 → 자산배분 추천 → 결과 화면

## 폴더 구성

| 파일 | 하는 일 |
|---|---|
| `app.py` | 웹 화면 (Streamlit). 첫 화면 → 진단 → 결과 3개 화면 |
| `assets/style.css` | 화면 디자인 (색, 글꼴, 카드 모양) |
| `recommender.py` | 추천 로직 전부 (성향 판정, 성향표, 최소분산·위험균형 최적화, 성과 지표) |
| `update_data.py` | ETF 8종 가격을 FinanceDataReader로 받아 `data/etf_prices.csv` 저장 |
| `data/etf_prices.csv` | 이미 받아 둔 가격 데이터 (2016-01-04 ~ 2026-10-29) |
| `requirements.txt` | 설치할 패키지 목록 |

## 처음 한 번만: 설치

Python 3.10 이상이 필요해요. 이 폴더에서 터미널(Windows는 명령 프롬프트)을 열고 실행하세요.

**Mac**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows**
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 실행

```bash
streamlit run app.py
```

브라우저가 자동으로 열려요(안 열리면 http://localhost:8501). 끄려면 터미널에서 `Ctrl + C`.

## 가격 데이터 최신화 (선택)

`data/etf_prices.csv`가 이미 있어서 인터넷 없이도 돌아가요. 최신 가격으로 바꾸고 싶을 때만:

```bash
python update_data.py
```

## 공유할 때

`.venv` 폴더는 각자 컴퓨터에서 새로 만들어야 해서 빼고 압축해 주세요.

> 교육용 시뮬레이션이며 투자 권유가 아닙니다.

## 팀원 협업 방법

코드를 고쳐서 GitHub에 올리면 위 사이트에 1~2분 안에 자동으로 반영돼요.

```bash
git pull                       # 작업 전에 최신 코드 받기
git add .
git commit -m "무엇을 바꿨는지"
git push
```

같은 파일을 동시에 고치면 충돌이 나기 쉬워요. 역할을 나눠서 작업하세요.
(예: 로직 `recommender.py`, 화면 `app.py`, 디자인 `assets/style.css`, 발표 자료)

> 사이트는 한동안 아무도 안 쓰면 잠들어요. 발표 전에 먼저 한 번 열어 두세요.
