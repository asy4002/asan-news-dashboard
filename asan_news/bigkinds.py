"""빅카인즈 웹사이트에서 내려받은 엑셀(.xlsx) 가져오기.

사용: python run.py bigkinds 파일.xlsx
열 이름(일자, 언론사, 제목, 본문/키워드, URL)을 자동으로 찾는다.
"""
import hashlib

from . import db, text


def _find(headers, *cands):
    for i, h in enumerate(headers):
        h = str(h or "").strip()
        if any(c in h for c in cands):
            return i
    return None


def run(conn, path):
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    headers = list(next(rows))
    i_date = _find(headers, "일자", "날짜")
    i_press = _find(headers, "언론사")
    i_title = _find(headers, "제목")
    i_body = _find(headers, "본문", "키워드")
    i_url = _find(headers, "URL", "url")
    if i_date is None or i_title is None:
        print("엑셀에서 '일자'와 '제목' 열을 찾지 못했습니다.")
        return 0
    new = 0
    for r in rows:
        title = text.clean(str(r[i_title] or ""))
        desc = text.clean(str(r[i_body] or ""))[:300] if i_body is not None else ""
        raw = str(r[i_date] or "").replace(".", "-")
        d = raw[:10] if "-" in raw else f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        if not title or len(d) != 10 or not text.is_relevant(title, desc):
            continue
        url = (str(r[i_url]).strip() if i_url is not None and r[i_url] else "") or f"bigkinds://{d}/{hashlib.sha1(title.encode()).hexdigest()[:16]}"
        dom = text.domain_of(url)
        press = str(r[i_press]).strip() if i_press is not None and r[i_press] else text.press_from_domain(dom)
        cur = conn.execute(
            """INSERT OR IGNORE INTO articles
               (url, title, description, pub_date, press, domain, source, topic, collected_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (url, title, desc, d, press, dom, "bigkinds", text.classify_topic(title, desc), db.now()),
        )
        new += cur.rowcount
    conn.commit()
    db.log_run(conn, "bigkinds", {"new": new, "file": str(path)})
    print(f"빅카인즈 엑셀 가져오기: 신규 {new}건")
    return new
