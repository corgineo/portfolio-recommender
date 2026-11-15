# 주식 초보를 위한 포트폴리오 추천 서비스 (초안)

**사이트: https://first-portfolio.streamlit.app**

예산 → 투자성향 설문 7문항(투자 기간은 2번 문항) → 투자성향 판정 → 자산배분 추천(ETF 20종 + 개별 종목) → 결과 화면 → 나만의 포트폴리오 제작하기 · 기업 분석

통합 변경 내역과 검증 결과: `docs/팀원통합_456_변경사항.md`

## 폴더 구성

| 파일 | 하는 일 |
|---|---|
| `app.py` | 웹 화면 (Streamlit). 첫 화면 → 진단(예산 + 7문항) → 결과 → 나만의 포트폴리오 제작하기 · 기업 분석 |
| `assets/style.css`, `ui.py`, `.streamlit/config.toml` | 화면 디자인 (아이보리·네이비, 자산군 색 규칙, 공통 그래프 스타일) |
| `c_integration.py`, `portfolio_editor.py`, `portfolio_core.py` | 나만의 포트폴리오 제작하기 (추천 비중 연결, 100% 상한, 1주 단위 금액·수량, 과거 성과 비교) |
| `company_financials.py` | 기업 분석 (재무_2026.csv, 천원 → 억원, 매출·영업이익·부채비율 차트) |
| `collect_data.py`, `select_universe.py` | ETF 20종·국내/미국 개별주 가격과 `data/products.csv` 생성 |
| `recommender.py` | 추천 로직 전부 (성향 판정, 성향표, 최소분산·위험균형 최적화, 성과 지표) |
| `factor.py` | 주식 몫 일부를 개별 종목으로: 저PER·저PBR·고ROE 순위합 상위 5종목 |
| `backtest.py` | 연 1회(4월) 리밸런싱 백테스팅과 성과 지표 (CAGR·변동성·샤프·소르티노·MDD·연도별 수익률) |
| `update_data.py` | (예전 8종용) ETF 8종 가격만 받아 `data/etf_prices.csv`를 덮어써요. 지금은 20종 파일이라 `collect_data.py`로 갱신하세요 |
| `update_stock_data.py` | 연도별 팩터 종목 선정 → `data/factor_picks.csv`, 선정 종목 가격 → `data/stock_prices.csv` |
| `data/etf_prices.csv`, `data/stock_kr.csv`, `data/stock_us.csv` | ETF 20종 · 국내 23종 · 미국 20종(원화 환산) 가격 (2016-01-04 ~ 2026-11-13) |
| `data/products.csv` | 상품 정보 (종목코드는 문자열로 읽어요: `dtype=str`) |
| `data/재무_2026.csv` | 국내 상장사 재무 데이터 (806종목, 2000~2025 회계연도, 금액 단위 천원) |
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
python collect_data.py
```

## 팩터 종목 · 백테스팅 (선택)

`data/factor_picks.csv`, `data/stock_prices.csv`가 이미 있어요. 다시 만들 때만 강의 `실습데이터/KOSPI_PRICE_SAMPLE.csv`를 `data/raw/`에 복사하고 실행하세요 (용량이 커서 git에는 안 올려요).

```bash
python update_stock_data.py
python backtest.py              # 성향별 성과표 출력
```

계산 방법, 결과, 검증, 한계는 [docs/백테스팅_팩터_계산정리.md](docs/백테스팅_팩터_계산정리.md)에 정리했어요.

화면에서 쓰는 법: `rc.build_portfolio(profile, cov_mat, picks=rc.current_picks())`로 주식 몫의 50%를 팩터 종목으로 나누고, `backtest.compare(profile)`로 누적가치·성과표·연도별 수익률을 받아요.

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
