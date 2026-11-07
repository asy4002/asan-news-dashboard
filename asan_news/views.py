"""원문 페이지 확인: og:site_name 으로 매체명 보정, 조회수 읽기.

- robots.txt 가 허용할 때만 접속
- 검증된 도메인(VIEWS_TRUSTED_DOMAINS)에서 읽은 값만 조회수로 인정
- 최근 14일 기사는 매일 재확인
"""
import re
import threading
import urllib.error
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import urlparse

from . import config, db

UA = "Mozilla/5.0 (compatible; RegionNewsResearchBot/1.0)"
_OG = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:site_name["\'][^>]*content=["\']([^"\']{1,60})["\']'
    r'|<meta[^>]+content=["\']([^"\']{1,60})["\'][^>]*(?:property|name)=["\']og:site_name["\']',
    re.I,
)
_CHARSET = re.compile(rb'charset=["\']?([A-Za-z0-9_\-]+)', re.I)
# "조회수 1,234" / "조회 1234" / "조회수 : 1,234회". 바로 뒤가 날짜 구분자(. - /)이면 무시
_VIEWS = re.compile(r"조회(?:수)?\s*[:：]?\s*</?[^>]{0,40}>?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,7})(?![0-9.\-/:])\s*(?:회)?")

_robots = {}
_robots_lock = threading.Lock()


def _allowed(url):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    with _robots_lock:
        rp = _robots.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=config.VIEWS_TIMEOUT) as r:
                rp.parse(r.read().decode("utf-8", "replace").splitlines())
        except urllib.error.HTTPError as e:
            rp.parse([] if e.code in (404, 410) else ["User-agent: *", "Disallow: /"])
        except Exception:
            rp.parse(["User-agent: *", "Disallow: /"])
        with _robots_lock:
            _robots[base] = rp
    return rp.can_fetch(UA, url)


def _decode(raw, ctype):
    m = re.search(r"charset=([\w\-]+)", ctype or "", re.I) or _CHARSET.search(raw[:4000])
    enc = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)) if m else "utf-8"
    enc = enc.lower()
    if enc in ("ks_c_5601-1987", "euc_kr", "ksc5601"):
        enc = "euc-kr"
    for e in (enc, "utf-8", "cp949"):
        try:
            return raw.decode(e)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def _trusted(domain):
    return any(domain == d or domain.endswith("." + d) for d in config.VIEWS_TRUSTED_DOMAINS)


def check(row):
    url, domain = row["url"], row["domain"] or ""
    if not url.startswith("http"):
        return row["id"], None, None, "skip"
    try:
        if not _allowed(url):
            return row["id"], None, None, "robots"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=config.VIEWS_TIMEOUT) as r:
            html = _decode(r.read(1_500_000), r.headers.get("Content-Type"))
    except Exception as e:
        return row["id"], None, None, f"error:{type(e).__name__}"
    m = _OG.search(html)
    site = (m.group(1) or m.group(2)).strip() if m else None
    views = None
    if _trusted(domain):
        vm = _VIEWS.search(html)
        if vm:
            views = int(vm.group(1).replace(",", ""))
    return row["id"], site, views, "ok" if views is not None else "no_views"


def run(conn, limit=None):
    limit = limit or config.VIEWS_MAX_PER_RUN
    recent = (date.today() - timedelta(days=config.VIEWS_RECHECK_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT id, url, domain FROM articles
           WHERE source != 'sample' AND (views_checked IS NULL OR pub_date >= ?)
           ORDER BY views_checked IS NOT NULL, pub_date DESC LIMIT ?""",
        (recent, limit),
    ).fetchall()
    if not rows:
        print("원문 확인: 대상 없음")
        return 0
    with ThreadPoolExecutor(max_workers=config.VIEWS_THREADS) as ex:
        results = list(ex.map(check, rows))
    ok = fixed = 0
    for aid, site, views, status in results:
        if site and not re.fullmatch(r"[\w.\-]+\.[a-z]{2,}", site, re.I):
            conn.execute("UPDATE articles SET press=? WHERE id=? AND (press IS NULL OR press = domain)", (site, aid))
            fixed += 1
        if views is not None:
            ok += 1
            conn.execute("UPDATE articles SET views=? WHERE id=?", (views, aid))
        conn.execute("UPDATE articles SET views_checked=?, views_status=? WHERE id=?", (db.now(), status, aid))
    conn.commit()
    db.log_run(conn, "views", {"checked": len(rows), "views_found": ok, "press_fixed": fixed})
    print(f"원문 확인: {len(rows)}건 확인 · 조회수 {ok}건 · 매체명 보정 {fixed}건")
    return ok
