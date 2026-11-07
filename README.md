# 아산시 홍보 사업 성과 분석 시스템

아산시가 보도자료로 홍보한 효과를 **데이터로 증명**하기 위한 시스템입니다.
아산시 관련 온라인 뉴스를 매일 자동으로 수집합니다. 같은 보도자료에서 나온 기사는 하나의 **이슈**로 묶고, 보도량·확산·매체·주제를 일/주/월 단위로 통계 분석합니다. 그 결과를 AI(Gemini)가 공무원 보고서체로 해석해 웹 대시보드로 공개합니다.

- **공개 페이지** `/` — 시의회·시민용 대시보드
- **성과 보고서** `/report.html` — 통계 분석 + AI 해석
- **관리자 페이지** `/admin` — 로그인 후 [최신 데이터로 갱신] 버튼

> 📘 처음부터 다시 설치·배포하려면 **[docs/실행절차.md](docs/실행절차.md)** 를 순서대로 따라 하세요.

> ⚠️ API 키·비밀번호·토큰은 **절대** 코드, README, 커밋에 넣지 마세요. 로컬은 `.env`, GitHub Actions는 **Secrets**, Render는 **Environment**에 넣습니다.

---

## 1. 아키텍처

```mermaid
flowchart LR
  subgraph GH[GitHub]
    A[Actions<br/>매일 07:07·07:37·08:07 KST] -->|python run.py daily| P[수집 → 이슈 통합 → 원문 확인<br/>→ 통계(scipy) → AI 해석(Gemini)]
    P -->|커밋| R[(저장소<br/>data/asan_news.db<br/>dashboard/data.js)]
  end
  N[NAVER API HUB<br/>뉴스 검색] --> P
  K[뉴스토어 API<br/>(선택)] --> P
  G[Gemini API] --> P
  R -->|푸시 시 자동 재배포| W[Render 웹서비스<br/>server.js]
  W --> U1[시민·시의회<br/>/ , /report.html]
  W --> U2[관리자 /admin]
  U2 -->|workflow_dispatch| A
```

- 무거운 작업(수집·분석·AI)은 **GitHub Actions**가 하루 한 번 실행합니다.
- 결과는 `data/asan_news.db`와 `dashboard/data.js` 두 파일로 저장소에 커밋됩니다.
- **Render**는 의존성 없는 `server.js`로 `dashboard/` 폴더를 제공합니다. 저장소에 푸시되면 자동으로 재배포합니다.
- 어떤 단계가 실패해도 기존 `data.js`가 유지되므로 화면은 그대로 남습니다.

## 2. 폴더 구조

```
run.py                       CLI 진입점 (daily|collect|newstore|bigkinds|cluster|views|build|report|sample)
asan_news/config.py          검색어·제외어·지역어·주제 키워드·임계값 ← 지역 교체 시 이 파일만 수정
asan_news/db.py              SQLite 스키마 (articles, clusters, runs)
asan_news/collect.py         NAVER API HUB 뉴스 수집
asan_news/newstore.py        뉴스토어(빅카인즈) API 기간 수집 (선택)
asan_news/bigkinds.py        빅카인즈 엑셀 가져오기
asan_news/text.py            정제·관련성·주제 분류·매체명
asan_news/cluster.py         유사 제목 → 이슈 (자카드 2-gram ≥ 0.45)
asan_news/views.py           원문 페이지: og:site_name 매체명 보정, 조회수
asan_news/stats.py           통계 분석 (숫자는 여기서만 만든다)
asan_news/llm.py             Gemini 해석 (숫자를 만들지 않는다)
asan_news/report.py          통계 + AI 묶기, 실패 시 직전 해석 재사용
asan_news/export.py          DB → dashboard/data.js
asan_news/sample.py          키 없이 화면 확인용 샘플 데이터
dashboard/index.html         공개 대시보드 + 관리자 모드
dashboard/report.html        성과 통계 보고서
dashboard/assets/            로고, 파비콘, og-image.png(1200×630), 공통 CSS
tools/og-image.html          OG 이미지 원본 (Edge/Chrome headless 로 PNG 생성)
server.js, package.json      Render 웹서비스 (npm start)
render.yaml                  Render Blueprint
.github/workflows/daily.yml  매일 자동 실행
```

## 3. API 키 발급

| 키 | 발급처 | 비고 |
|---|---|---|
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | **NAVER API HUB** (네이버 클라우드 플랫폼 콘솔 → API HUB → 검색 > 뉴스) | 기존 네이버 개발자센터 검색 API는 API HUB로 **이관**되었습니다. 엔드포인트 `https://naverapihub.apigw.ntruss.com/search/v1/news`, 헤더 `X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY` |
| `NEWSTORE_API_KEY` | 한국언론진흥재단 [뉴스토어](https://www.newstore.or.kr) → 뉴스검색 API 구매·승인 후 발급 | 네이버 대신(또는 함께) 사용 가능. 엔드포인트 기본값 `https://www.newstore.or.kr/api-newstore/v1/search/newsAllList.json`, 다르면 Actions Variable `NEWSTORE_ENDPOINT` 로 지정 |
| `GEMINI_API_KEY` | Google AI Studio | `GEMINI_TEXT_MODEL`(예: `gemini-2.5-flash`)도 함께 지정 |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → Fine-grained tokens | 이 저장소만, **Actions: Read and write** 권한 |

## 4. 로컬 실행

```bash
pip install -r requirements.txt
```

```bash
python run.py sample
```

```bash
npm start
```

브라우저에서 `http://localhost:10000` 을 엽니다. 샘플 데이터일 때는 화면 맨 위에 주황색 **샘플 배너**가 뜹니다.

실제 데이터로 실행하려면 `.env.example`을 `.env`로 복사하고 키를 **직접** 입력한 뒤 아래를 실행합니다.

```bash
python run.py daily
```

| 명령 | 하는 일 |
|---|---|
| `python run.py daily` | 수집 → 뉴스토어 → 이슈 통합 → 원문 확인 → 보고서(AI) → 내보내기 |
| `python run.py collect` | 네이버 뉴스 수집 (검색어별 최대 1,000건, 시작일 이전이면 중단) |
| `python run.py newstore 2026-01-01 2026-03-31` | 뉴스토어 기간 수집 |
| `python run.py bigkinds 파일.xlsx` | 빅카인즈에서 내려받은 엑셀 가져오기 |
| `python run.py cluster` | 이슈 통합만 |
| `python run.py views 300` | 원문 확인(최대 300건) |
| `python run.py build` | 이슈 통합 + 통계(직전 AI 해석 재사용) + 내보내기 |
| `python run.py report` | 통계 + **AI 해석** + 내보내기 |

## 5. 기능 상세

**대시보드 (`/`)**
- 고정 필터 바: 기간 프리셋(7일/30일/이번 달/3개월/전체)과 날짜 직접 입력, 집계 단위(일/주/월), 주제
- KPI 6개: 보도 건수, 통합 이슈, 보도 매체, 확인 조회수(+공개율), 이슈당 평균 보도, 대형 확산 이슈(5개 매체 이상). 모두 직전 동기간 대비 증감 표시
- 차트: 보도 추이, 조회수 추이, 주제별 분포, 매체별 보도 TOP15, 매체별 조회수 TOP15 (이중 축 없음)
- 홍보 성과 요약: 자동 요약 문장과 6개 지표(노출·확산·도달·지속·매체 다양성·이슈 집중도)
- 통계 분석 요약: AI 헤드라인, 핵심 수치 4칸, 주요 발견 3개, [성과 보고내용 보기 →]
- 기간별 성과표, 주요 이슈 표(정렬·검색·행 클릭 시 기사 펼침·CSV), 기사 목록(검색·페이지·CSV)
- 라이트/다크 모드, 지표 정의 및 데이터 한계 안내

**성과 보고서 (`/report.html`)**
분석 요약 → 기술통계 → 추세(막대+회귀선) → 상관(표, 산점도+회귀선, 발산형 히트맵) → 요일 효과 → 주제별 확산력 → 주제 구성(월×주제 히트맵) → 홍보비 → 제언·데이터 한계·분석 방법. 각 장마다 **AI 해석** 박스가 있고, 유의성 배지(*, **, ***)를 붙이며 p값은 `<0.001` 형식으로 표시합니다.

**통계 방법** (`stats.py`, scipy로 결정적으로 계산하며 진행 중인 마지막 주는 제외)
- 추세: 주차↔주간 보도량 선형회귀(기울기, R², p)와 Spearman
- 상관: 주간 [이슈 수, 매체 수, 대형 확산 이슈 수, 이슈당 보도, 조회수] ↔ 보도 건수. Pearson r, 95% CI(Fisher z), Spearman ρ, Holm 보정을 계산
- 요일: 평일 vs 주말 Mann-Whitney U(r = |Z|/√N), 7요일 Kruskal-Wallis
- 주제별 확산력: 이슈당 매체 수 Kruskal-Wallis(ε²). 이슈가 20개 이상인 주제만 포함
- 주제 구성 변화: 주제×월 카이제곱(Cramér's V)
- 홍보비: `data/budget.csv`(열: `month,amount`)가 있을 때만 계산. 12개월 미만이면 결론을 유보

**AI 해석** (`llm.py`): 통계 결과 JSON만 Gemini에 보냅니다(차트용 원자료는 제외). 새 수치 생성과 인과 단정을 금지하고, Holm p로 판단하며, 공무원 개조식으로 씁니다. 실패하거나 키가 없으면 직전 해석을 재사용합니다.

## 6. API 연동 코드 (요지)

```python
# NAVER API HUB 뉴스 검색 (collect.py)
req = urllib.request.Request(
    "https://naverapihub.apigw.ntruss.com/search/v1/news?" +
    urllib.parse.urlencode({"query": q, "display": 100, "start": start, "sort": "date"}),
    headers={"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": secret})

# Gemini (llm.py)
POST {GEMINI_BASE_URL}/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent
headers: x-goog-api-key: <키>
body: {"contents": [...], "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
```

## 7. 배포 설정

### GitHub
1. 저장소를 만들고 이 폴더를 푸시합니다(`.env`는 `.gitignore`에 있어 올라가지 않습니다).
2. **Settings → Secrets and variables → Actions**
   - Secrets: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `GEMINI_API_KEY`, `NEWSTORE_API_KEY`(선택)
   - Variables: `GEMINI_TEXT_MODEL` (없으면 `gemini-2.5-flash`)
3. **Settings → Actions → General → Workflow permissions** 를 *Read and write* 로 설정합니다.
4. **Actions → 매일 데이터 갱신 → Run workflow** 로 수동 실행해 봅니다.

> ℹ️ AI 도구의 Git 인증에 `workflow` 권한이 없으면 `.github/workflows/` 파일 푸시가 거부됩니다. 그때는 GitHub 웹에서 파일을 직접 만들어 붙여 넣으세요.

### Render
1. **New → Blueprint** 에서 저장소를 연결하면 `render.yaml` 대로 웹서비스가 만들어집니다.
2. **Environment** 에 `ADMIN_ID`, `ADMIN_PASSWORD`, `GITHUB_TOKEN`, `GITHUB_REPO`(계정명/저장소명)를 입력합니다.
3. (선택) 공유 미리보기 주소를 고정하려면 `PUBLIC_URL` 을 입력합니다(예: `https://xxx.onrender.com`).

### 관리자 보안
- 비밀번호는 `timingSafeEqual` 로 비교하고, 세션은 HMAC 서명 쿠키(HttpOnly, SameSite=Strict, https에서는 Secure, 8시간)로 관리합니다.
- IP별 5회 실패 시 15분 잠금, 전체 1시간 20회 실패 시 1시간 잠금
- 갱신 요청은 실행 중이면 거절하고, 10분 쿨다운이 있습니다.

## 8. 지역 바꾸기

`asan_news/config.py` 의 `REGION`, `REGION_SHORT`, `QUERIES`, `LOCAL_TERMS`, `EXCLUDE_TERMS`, `START_DATE`, `OPERATOR` 를 바꿉니다.
그다음 `dashboard/index.html`·`report.html` 의 제목·OG 문구, `tools/og-image.html` 을 바꾸고 OG 이미지를 다시 만듭니다.

```bash
msedge --headless --screenshot=dashboard/assets/og-image.png --window-size=1200,630 tools/og-image.html
```

동명 지명(예: '중구', '동구')은 제외어와 지역어로 오수집을 막으세요.

## 9. FAQ

- **화면에 '샘플' 배너가 떠요** → `python run.py sample` 로 만든 data.js 입니다. 실제 키로 `daily` 를 한 번 실행하면 사라집니다.
- **AI 해석이 없어요** → `GEMINI_API_KEY`, `GEMINI_TEXT_MODEL` 을 확인하고 `python run.py report` 를 실행합니다.
- **갱신 버튼이 비활성이에요** → Render 에 `GITHUB_TOKEN`, `GITHUB_REPO` 가 없습니다.
- **조회수가 적어요** → 조회수를 공개하는 매체가 일부뿐이고, 검증된 도메인(`VIEWS_TRUSTED_DOMAINS`)만 인정하기 때문입니다.
- **Render 무료 플랜이 느려요** → 15분간 접속이 없으면 잠들었다가, 첫 접속 때 수십 초 걸려 깨어납니다.

## 10. 데이터 한계

- **수집 편향**: 네이버 검색(검색어당 최대 1,000건)에 의존하므로 모든 보도를 포괄하지 못합니다. 검색어를 바꾸면 추세가 인위적으로 달라질 수 있습니다.
- **조회수 공개율**: 일부 매체만 조회수를 공개하므로 실제 도달 규모보다 작게 나타납니다.
- **상관 ≠ 인과**: 지표 간 상관은 함께 움직였다는 뜻일 뿐 홍보의 효과를 증명하지 않습니다.
- **자기상관**: 주간 시계열은 서로 독립이 아니므로 p값이 낙관적으로 나올 수 있습니다.
- **주제 분류**: 키워드 기반 자동 분류이므로 오분류가 있을 수 있습니다.

---

<p align="center"><sub>Powered By <b>YILOWOON</b> · © 2026 사단법인 도시공동체본부</sub></p>
