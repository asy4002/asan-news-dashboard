"""뉴스토어(빅카인즈) 뉴스검색 API 기간 수집 (선택).

NEWSTORE_API_KEY 가 없으면 건너뛴다. 엔드포인트·필드명은 발급 기관 문서에 맞게
NEWSTORE_ENDPOINT 환경변수로 바꿀 수 있다.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import date

from . import config, db, text

DEFAULT_ENDPOINT = "https://tools.kinds.or.kr/search/news"
PAGE = 100


def _post(endpoint, payload):
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "news-dashboard/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def run(conn, since=None, until=None):
    key = config.env("NEWSTORE_API_KEY")
    if not key:
        print("뉴스토어: NEWSTORE_API_KEY 가 없어 건너뜀")
        return 0
    endpoint = config.env("NEWSTORE_ENDPOINT", DEFAULT_ENDPOINT)
    since = since or config.START_DATE
    until = until or date.today().isoformat()
    new = 0
    for q in config.QUERIES:
        page = 0
        while True:
            payload = {
                "access_key": key,
                "argument": {
                    "query": q,
                    "published_at": {"from": since, "until": until},
                    "sort": {"date": "desc"},
                    "return_from": page * PAGE,
                    "return_size": PAGE,
                    "fields": ["title", "content", "published_at", "provider", "provider_link_page"],
                },
            }
            try:
                res = _post(endpoint, payload)
            except (urllib.error.URLError, ValueError) as e:
                print(f"뉴스토어 오류({q}): {e}")
                break
            docs = ((res.get("return_object") or {}).get("documents")) or []
            for d in docs:
                title = text.clean(d.get("title"))
                desc = text.clean((d.get("content") or "")[:300])
                url = d.get("provider_link_page")
                pd = (d.get("published_at") or "")[:10]
                if not url or not pd or not text.is_relevant(title, desc):
                    continue
                dom = text.domain_of(url)
                cur = conn.execute(
                    """INSERT OR IGNORE INTO articles
                       (url, title, description, pub_date, pub_datetime, press, domain,
                        source, query, topic, collected_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (url, title, desc, pd, (d.get("published_at") or "")[:19].replace("T", " "),
                     d.get("provider") or text.press_from_domain(dom), dom, "newstore", q,
                     text.classify_topic(title, desc), db.now()),
                )
                new += cur.rowcount
            conn.commit()
            if len(docs) < PAGE or page >= 50:
                break
            page += 1
            time.sleep(0.2)
    db.log_run(conn, "newstore", {"new": new, "since": since, "until": until})
    print(f"뉴스토어 수집: 신규 {new}건")
    return new
