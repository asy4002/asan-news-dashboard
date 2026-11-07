"""뉴스토어(한국언론진흥재단) 뉴스검색 API 수집.

공식 매뉴얼: https://www.newstore.or.kr/store/prodct/license-news-search/license-api-list.do
- 엔드포인트: https://www.newstore.or.kr/api-newstore/v1/search/newsAllList.json
- 요청 인자: apiKey, query, from/until(yyyy-MM-dd, until 은 그 전날까지), sort, return_from, return_size, fields
- 응답: {"return_object": {"total_hits": n, "documents": [{news_id, title, content, published_at,
         provider, byline, category, provider_link_page, ...}]}}

매뉴얼에 HTTP 메서드와 키 위치가 명시되어 있지 않아 POST(JSON) → GET(쿼리) 순으로 시도하고,
성공한 방식을 기억해 이후 요청에 사용한다. 엔드포인트는 NEWSTORE_ENDPOINT 로 바꿀 수 있다.

매일 실행 시에는 마지막으로 수집한 날짜 3일 전부터 오늘까지만 조회한다(증분 수집).
처음 실행하거나 기간을 지정하면 그 기간 전체를 조회한다.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from . import config, db, text

DEFAULT_ENDPOINT = "https://www.newstore.or.kr/api-newstore/v1/search/newsAllList.json"
PAGE = 500                # 한 번에 받을 기사 수 (API 최대 10,000)
MAX_FROM = 20000          # return_from 최대값
FIELDS = ["news_id", "title", "content", "published_at", "dateline", "provider",
          "byline", "category", "provider_link_page"]
KST = timezone(timedelta(hours=9))

_mode = None  # "post" | "get" (처음 성공한 방식)


class NewstoreError(Exception):
    pass


def _body(key, query, since, until_excl, start):
    return {
        "apiKey": key,
        "access_key": key,
        "query": query,
        "from": since,
        "until": until_excl,
        "published_at": {"from": since, "until": until_excl},
        "sort": {"date": "desc"},
        "return_from": start,
        "return_size": PAGE,
        "fields": FIELDS,
    }


def _open(req):
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def _call(endpoint, body):
    """POST(JSON) 또는 GET(쿼리스트링)으로 호출. 응답 JSON 반환."""
    global _mode
    headers = {"User-Agent": "news-dashboard/1.0", "Accept": "application/json"}
    tries = [_mode] if _mode else ["post", "get"]
    last = None
    for mode in tries:
        if mode == "post":
            req = urllib.request.Request(
                endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers=dict(headers, **{"Content-Type": "application/json"}), method="POST")
        else:
            flat = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                    for k, v in body.items() if k != "published_at"}
            req = urllib.request.Request(endpoint + "?" + urllib.parse.urlencode(flat), headers=headers)
        for attempt in range(4):
            try:
                res = _open(req)
                if "return_object" not in res:
                    raise NewstoreError("응답 형식 오류: " + json.dumps(res, ensure_ascii=False)[:300])
                _mode = mode
                return res
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")[:300]
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 ** (attempt + 1))
                    last = NewstoreError(f"HTTP {e.code}: {msg}")
                    continue
                last = NewstoreError(f"HTTP {e.code}: {msg}")
                break  # 다른 방식으로 재시도
            except (urllib.error.URLError, TimeoutError) as e:
                time.sleep(2 ** (attempt + 1))
                last = NewstoreError(f"네트워크 오류: {e}")
            except (ValueError, NewstoreError) as e:
                last = e if isinstance(e, NewstoreError) else NewstoreError(f"JSON 해석 실패: {e}")
                break
    raise last or NewstoreError("알 수 없는 오류")


def _to_kst(s):
    """'2021-01-14T00:00:00.000+09:00' 또는 UTC 문자열 → (YYYY-MM-DD, YYYY-MM-DD HH:MM:SS) KST."""
    if not s:
        return None, None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(KST)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return s[:10], None


def _default_since(conn):
    row = conn.execute("SELECT MAX(pub_date) FROM articles WHERE source='newstore'").fetchone()
    if row and row[0]:
        d = (date.fromisoformat(row[0]) - timedelta(days=3)).isoformat()
        return max(d, config.START_DATE)
    return config.START_DATE


def run(conn, since=None, until=None):
    key = config.env("NEWSTORE_API_KEY")
    if not key:
        print("뉴스토어: NEWSTORE_API_KEY 가 없어 건너뜀")
        return 0
    endpoint = config.env("NEWSTORE_ENDPOINT", DEFAULT_ENDPOINT)
    since = since or _default_since(conn)
    until = until or date.today().isoformat()
    until_excl = (date.fromisoformat(until) + timedelta(days=1)).isoformat()  # until 은 전날까지 검색
    print(f"뉴스토어 수집: {since} ~ {until}")
    total_new = total_seen = total_irrelevant = 0
    per_query = {}
    errors = 0
    for q in config.QUERIES:
        new = seen = irrelevant = 0
        start = 0
        while start <= MAX_FROM:
            try:
                res = _call(endpoint, _body(key, q, since, until_excl, start))
            except NewstoreError as e:
                print(f"  [{q}] 오류: {e}")
                errors += 1
                break
            ro = res.get("return_object") or {}
            docs = ro.get("documents") or []
            for d in docs:
                seen += 1
                title = text.clean(d.get("title"))
                desc = text.clean((d.get("content") or "")[:300])
                if not title or not text.is_relevant(title, desc):
                    irrelevant += 1
                    continue
                pd, pdt = _to_kst(d.get("published_at") or d.get("dateline"))
                _, dlt = _to_kst(d.get("dateline"))
                if not pd or pd < config.START_DATE:
                    continue
                link = (d.get("provider_link_page") or "").strip()
                url = link if link.startswith("http") else f"newstore://{d.get('news_id') or title}"
                dom = text.domain_of(url) if link.startswith("http") else ""
                press = (d.get("provider") or "").strip() or text.press_from_domain(dom) or "(매체 미상)"
                cur = conn.execute(
                    """INSERT OR IGNORE INTO articles
                       (url, title, description, pub_date, pub_datetime, press, domain,
                        source, query, topic, collected_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (url, title, desc, pd, dlt or pdt, press, dom, "newstore", q,
                     text.classify_topic(title, desc), db.now()),
                )
                new += cur.rowcount
            conn.commit()
            total_hits = ro.get("total_hits") or 0
            start += PAGE
            if len(docs) < PAGE or start >= total_hits:
                break
            time.sleep(0.3)
        per_query[q] = {"seen": seen, "new": new, "irrelevant": irrelevant}
        print(f"  [{q}] 확인 {seen}건 · 신규 {new}건 · 무관 {irrelevant}건")
        total_new += new
        total_seen += seen
        total_irrelevant += irrelevant
        if errors >= 3 and total_seen == 0:
            print("  연속 오류로 뉴스토어 수집을 중단함 (키·엔드포인트 확인 필요)")
            break
    db.log_run(conn, "newstore", {"new": total_new, "seen": total_seen, "irrelevant": total_irrelevant,
                                  "since": since, "until": until, "mode": _mode, "errors": errors,
                                  "queries": per_query})
    print(f"뉴스토어 수집 완료: 신규 {total_new}건 (확인 {total_seen}, 무관 제외 {total_irrelevant}, 오류 {errors})")
    if errors and total_seen == 0:
        raise NewstoreError("뉴스토어 수집 실패")
    return total_new
