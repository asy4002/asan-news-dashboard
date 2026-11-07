"""NAVER API HUB 뉴스 검색 수집."""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime

from . import config, db, text

ENDPOINT = "https://naverapihub.apigw.ntruss.com/search/v1/news"
DISPLAY = 100
MAX_START = 901


def _keys():
    cid = config.env("NAVER_CLIENT_ID")
    sec = config.env("NAVER_CLIENT_SECRET")
    if not cid or not sec:
        print(".env 파일에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 을 입력하세요.")
        sys.exit(1)
    return cid, sec


def _request(query, start, cid, sec):
    params = urllib.parse.urlencode(
        {"query": query, "display": DISPLAY, "start": start, "sort": "date"}
    )
    req = urllib.request.Request(
        f"{ENDPOINT}?{params}",
        headers={
            "X-NCP-APIGW-API-KEY-ID": cid,
            "X-NCP-APIGW-API-KEY": sec,
            "User-Agent": "news-dashboard/1.0",
        },
    )
    wait = 2
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 429 and attempt < 5:
                print(f"  429 요청 한도 초과 → {wait}초 대기 후 재시도")
                time.sleep(wait)
                wait *= 2
                continue
            print(f"API 오류 {e.code}: {body[:500]}")
            sys.exit(1)
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(wait)
                wait *= 2
                continue
            print(f"네트워크 오류: {e}")
            sys.exit(1)
    return {}


def _parse_date(s):
    try:
        dt = parsedate_to_datetime(s)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None, None


def run(conn):
    cid, sec = _keys()
    total_new = total_seen = total_irrelevant = 0
    per_query = {}
    for q in config.QUERIES:
        new = seen = irrelevant = 0
        stop = False
        for start in range(1, MAX_START + 1, DISPLAY):
            data = _request(q, start, cid, sec)
            items = data.get("items") or []
            if not items:
                break
            for it in items:
                d, dt = _parse_date(it.get("pubDate"))
                if not d:
                    continue
                if d < config.START_DATE:
                    stop = True
                    continue
                seen += 1
                title = text.clean(it.get("title"))
                desc = text.clean(it.get("description"))
                if not text.is_relevant(title, desc):
                    irrelevant += 1
                    continue
                url = it.get("originallink") or it.get("link")
                if not url:
                    continue
                dom = text.domain_of(url)
                cur = conn.execute(
                    """INSERT OR IGNORE INTO articles
                       (url, naver_link, title, description, pub_date, pub_datetime,
                        press, domain, source, query, topic, collected_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (url, it.get("link"), title, desc, d, dt,
                     text.press_from_domain(dom), dom, "naver", q,
                     text.classify_topic(title, desc), db.now()),
                )
                new += cur.rowcount
            conn.commit()
            if stop or len(items) < DISPLAY:
                break
            time.sleep(0.15)
        per_query[q] = {"seen": seen, "new": new, "irrelevant": irrelevant}
        print(f"  [{q}] 확인 {seen}건 · 신규 {new}건 · 무관 {irrelevant}건")
        total_new += new
        total_seen += seen
        total_irrelevant += irrelevant
    db.log_run(conn, "collect", {"new": total_new, "seen": total_seen,
                                 "irrelevant": total_irrelevant, "queries": per_query})
    print(f"수집 완료: 신규 {total_new}건 (확인 {total_seen}, 무관 제외 {total_irrelevant})")
    return total_new
