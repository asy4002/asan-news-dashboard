"""API 키 없이 화면을 확인하기 위한 샘플 데이터 (data/sample.db).

매체명은 '샘플매체 01' 형식이며 실제 언론사명은 쓰지 않는다. 화면에는 '샘플' 배너가 뜬다.
"""
import random
from datetime import date, timedelta

from . import config, db, text

TEMPLATES = {
    "행정·시정": ["{r}, {p} 시민 소통 간담회 개최", "{r}장, {p} 현장 방문해 민원 청취", "{r}, 내년도 예산안 {n}억원 편성"],
    "경제·산업·일자리": ["{r}, {p} 기업과 투자협약 체결", "{r} 탕정 산업단지 일자리 {n}개 창출 기대", "{r}, 소상공인 지원 사업 확대"],
    "관광·문화·축제": ["{r} 이순신축제 {p} 관람객 몰려", "{r} 온양온천 관광객 {n}만명 돌파", "{r} 외암마을 가을 문화행사 개최"],
    "복지·보건": ["{r}, 어르신 돌봄 서비스 확대 시행", "{r}, 출산 지원금 {n}만원으로 상향", "{r} 보건소, 감염병 예방 캠페인"],
    "교육·청년": ["{r}, 청년 창업 지원 {p} 공모", "{r}, 장학금 {n}명에게 전달", "{r} 도서관 독서 프로그램 운영"],
    "도시·교통·개발": ["{r} 배방 도로 확장 공사 착공", "{r}, 시내버스 노선 개편 {p} 시행", "{r} 신정호 공원 조성 사업 속도"],
    "환경·안전": ["{r}, 곡교천 하천 정화 활동", "{r}, 폭우 대비 재난 안전 점검", "{r}, 탄소중립 실천 {p} 캠페인"],
    "의회·정치": ["{r}의회, 행정사무감사 돌입", "{r}의회 의원, 조례 개정안 대표 발의", "{r}의회 본회의서 {n}건 의결"],
    "체육": ["{r}, 전국 마라톤 대회 개최", "{r} FC, 홈 경기서 승리", "{r} 체육대회 {p} 성황리 마무리"],
}
PLACES = ["온양", "배방", "탕정", "음봉", "둔포", "신창", "도고", "송악"]


def run():
    rng = random.Random(20260101)
    db.use_sample(True)
    if config.SAMPLE_DB_PATH.exists():
        config.SAMPLE_DB_PATH.unlink()
    conn = db.connect()
    press = [f"샘플매체 {i:02d}" for i in range(1, 41)]
    weights = [1 / (i + 1) ** 0.7 for i in range(len(press))]
    start = date.fromisoformat(config.START_DATE)
    today = date.today()
    topics = list(TEMPLATES.keys())
    tweights = [5, 4, 4, 3, 2, 3, 2, 3, 1]
    seq = 0
    d = start
    while d <= today:
        weekend = d.weekday() >= 5
        n_issue = rng.randint(1, 3) if weekend else rng.randint(4, 9)
        trend = 1 + (d - start).days / 600
        for _ in range(int(n_issue * trend)):
            topic = rng.choices(topics, tweights)[0]
            title = rng.choice(TEMPLATES[topic]).format(
                r=config.REGION, p=rng.choice(PLACES), n=rng.randint(2, 300))
            k = min(len(press), max(1, int(rng.paretovariate(1.3))))
            chosen = set()
            while len(chosen) < k:
                chosen.add(rng.choices(range(len(press)), weights)[0])
            for pi in chosen:
                seq += 1
                pd = d + timedelta(days=rng.choice([0, 0, 0, 1, 2]))
                if pd > today:
                    pd = today
                variant = title if rng.random() < 0.6 else f"[포토] {title}" if rng.random() < 0.5 else title + " 눈길"
                views = rng.randint(80, 6000) if rng.random() < 0.35 else None
                conn.execute(
                    """INSERT INTO articles
                       (url, title, description, pub_date, pub_datetime, press, domain, source,
                        query, topic, views, views_checked, views_status, collected_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"https://sample.invalid/{seq}", variant,
                     f"{config.REGION} {rng.choice(PLACES)} 관련 샘플 기사 본문입니다.",
                     pd.isoformat(), f"{pd.isoformat()} {rng.randint(6, 22):02d}:{rng.randint(0, 59):02d}:00",
                     press[pi], f"sample{pi + 1:02d}.invalid", "sample", config.REGION,
                     text.classify_topic(variant) if rng.random() < 0.3 else topic,
                     views, db.now() if views else None, "ok" if views else None, db.now()),
                )
        d += timedelta(days=1)
    conn.commit()
    db.log_run(conn, "sample", {"articles": seq})
    print(f"샘플 데이터 생성: 기사 {seq}건 → {config.SAMPLE_DB_PATH.name}")
    return conn
