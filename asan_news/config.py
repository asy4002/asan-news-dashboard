"""지역 설정값. 다른 지역으로 바꿀 때는 이 파일만 수정한다."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DASHBOARD_DIR = ROOT / "dashboard"
DB_PATH = DATA_DIR / "asan_news.db"
SAMPLE_DB_PATH = DATA_DIR / "sample.db"
REPORT_JSON = DATA_DIR / "report.json"
BUDGET_CSV = DATA_DIR / "budget.csv"
DATA_JS = DASHBOARD_DIR / "data.js"

# ── 지역 ──────────────────────────────────────────
REGION = "아산시"
REGION_SHORT = "아산"
PARENT_REGION = "충청남도"
START_DATE = "2026-01-01"
SYSTEM_NAME = f"{REGION} 홍보 사업 성과 분석 시스템"
OPERATOR = "사단법인 도시공동체본부"
POWERED_BY = "YILOWOON"
REFRESH_TIME_TEXT = "오전 8시"

QUERIES = [
    "아산시", "아산시장", "아산시의회", "아산시청", "아산 온양온천",
    "아산 배방", "아산 탕정", "아산 이순신축제", "아산 곡교천", "아산 신정호",
]

LOCAL_TERMS = [
    "온양", "배방", "탕정", "음봉", "둔포", "곡교천", "신정호",
    "외암마을", "현충사", "이순신축제", "인주", "영인", "염치", "송악", "도고", "선장", "신창",
]

# 지역명이 들어가지만 무관한 고유명사 (관련성 판단 전에 지운다)
EXCLUDE_TERMS = [
    "서울아산병원", "울산대학교병원", "강릉아산병원", "현대아산", "아산나눔재단",
    "아산정책연구원", "아산사회복지재단", "아산병원", "아산상", "아산의학상",
]

TOPICS = {
    "행정·시정": ["시정", "행정", "시장", "공무원", "조직", "예산", "민원", "시청", "협약", "업무협약", "간담회", "정책"],
    "경제·산업·일자리": ["경제", "산업", "기업", "일자리", "고용", "투자", "반도체", "디스플레이", "산단", "산업단지", "소상공인", "창업", "수출"],
    "관광·문화·축제": ["관광", "문화", "축제", "공연", "전시", "온천", "이순신", "외암", "현충사", "여행", "예술", "박물관"],
    "복지·보건": ["복지", "보건", "건강", "의료", "돌봄", "어르신", "노인", "장애인", "출산", "보육", "감염"],
    "교육·청년": ["교육", "학교", "학생", "청년", "대학", "장학", "도서관", "학습", "아동"],
    "도시·교통·개발": ["도시", "교통", "개발", "도로", "철도", "버스", "주택", "아파트", "재개발", "건설", "택지", "공원"],
    "환경·안전": ["환경", "안전", "재난", "화재", "사고", "폭우", "미세먼지", "탄소", "하천", "쓰레기", "방역"],
    "의회·정치": ["의회", "의원", "의장", "선거", "국회의원", "정당", "조례", "행정사무감사", "본회의"],
    "체육": ["체육", "스포츠", "축구", "야구", "마라톤", "대회", "선수", "경기장", "FC"],
}
OTHER_TOPIC = "기타"
TOPIC_NAMES = list(TOPICS.keys()) + [OTHER_TOPIC]

# ── 임계값 ────────────────────────────────────────
CLUSTER_SIM = 0.45          # 자카드 유사도
CLUSTER_WINDOW_DAYS = 3     # 비교 대상 기간
CLUSTER_MAX_SPAN_DAYS = 7   # 한 이슈의 최대 기간
BIG_ISSUE_PRESS = 5         # 대형 확산 이슈 기준 매체 수
VIEWS_RECHECK_DAYS = 14
VIEWS_THREADS = 6
VIEWS_TIMEOUT = 12
VIEWS_MAX_PER_RUN = 800
# 조회수 패턴이 검증된 도메인만 조회수로 인정한다.
VIEWS_TRUSTED_DOMAINS = [
    "newsis.com", "news1.kr", "yna.co.kr", "ccdailynews.com", "daejonilbo.com",
    "cctoday.co.kr", "joongdo.co.kr", "ggilbo.com", "dynews.co.kr", "inews365.com",
]

# ── 주요 언론사 도메인 → 매체명 ───────────────────
PRESS_BY_DOMAIN = {
    "yna.co.kr": "연합뉴스", "newsis.com": "뉴시스", "news1.kr": "뉴스1",
    "chosun.com": "조선일보", "joongang.co.kr": "중앙일보", "donga.com": "동아일보",
    "hani.co.kr": "한겨레", "khan.co.kr": "경향신문", "hankookilbo.com": "한국일보",
    "kmib.co.kr": "국민일보", "seoul.co.kr": "서울신문", "segye.com": "세계일보",
    "mk.co.kr": "매일경제", "hankyung.com": "한국경제", "sedaily.com": "서울경제",
    "mt.co.kr": "머니투데이", "edaily.co.kr": "이데일리", "asiae.co.kr": "아시아경제",
    "fnnews.com": "파이낸셜뉴스", "heraldcorp.com": "헤럴드경제", "nocutnews.co.kr": "노컷뉴스",
    "ohmynews.com": "오마이뉴스", "kbs.co.kr": "KBS", "imbc.com": "MBC", "sbs.co.kr": "SBS",
    "ytn.co.kr": "YTN", "jtbc.co.kr": "JTBC", "tjb.co.kr": "TJB대전방송",
    "daejonilbo.com": "대전일보", "cctoday.co.kr": "충청투데이", "joongdo.co.kr": "중도일보",
    "ggilbo.com": "금강일보", "dynews.co.kr": "동양일보", "ccdailynews.com": "충청일보",
    "inews365.com": "충북일보", "cnbnews.com": "CNB뉴스", "newspim.com": "뉴스핌",
    "dt.co.kr": "디지털타임스", "etnews.com": "전자신문", "ajunews.com": "아주경제",
    "pressian.com": "프레시안", "breaknews.com": "브레이크뉴스", "dailian.co.kr": "데일리안",
    "nspna.com": "NSP통신", "kyeongin.com": "경인일보", "sisajournal.com": "시사저널",
}


def load_env(path=None):
    """간단한 .env 로더 (외부 라이브러리 없이)."""
    p = Path(path) if path else ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def env(name, default=""):
    return os.environ.get(name, default) or default
