"""DB → dashboard/data.js (window.ASAN_DATA, window.ASAN_REPORT)."""
import json
import os
from datetime import datetime

from . import config


def _dump(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def run(conn, report=None, sample=False):
    rows = conn.execute(
        """SELECT a.id, a.pub_date, a.cluster_id, a.press, a.title, a.url, a.views, a.topic
           FROM articles a WHERE a.pub_date >= ? ORDER BY a.pub_date DESC, a.id DESC""",
        (config.START_DATE,),
    ).fetchall()
    press_idx, topic_idx = {}, {t: i for i, t in enumerate(config.TOPIC_NAMES)}
    press = []
    arts = []
    used_clusters = set()
    for r in rows:
        p = r["press"] or "(매체 미상)"
        if p not in press_idx:
            press_idx[p] = len(press)
            press.append(p)
        t = r["topic"] if r["topic"] in topic_idx else config.OTHER_TOPIC
        cid = r["cluster_id"] if r["cluster_id"] is not None else -r["id"]
        used_clusters.add(cid)
        arts.append([r["id"], r["pub_date"], cid, press_idx[p], r["title"], r["url"], r["views"], topic_idx[t]])
    clusters = {}
    for c in conn.execute("SELECT id, title FROM clusters"):
        if c["id"] in used_clusters:
            clusters[str(c["id"])] = c["title"]
    for a in arts:  # 이슈 통합 전 기사도 표시되도록
        if str(a[2]) not in clusters:
            clusters[str(a[2])] = a[4]
    if not arts and not sample and config.DATA_JS.exists():
        print("내보내기 생략: DB에 기사가 없어 기존 dashboard/data.js 를 유지함")
        return
    dates = [a[1] for a in arts]
    meta = {
        "region": config.REGION, "system": config.SYSTEM_NAME, "operator": config.OPERATOR,
        "powered_by": config.POWERED_BY, "refresh_text": config.REFRESH_TIME_TEXT,
        "start": config.START_DATE, "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "sample": sample,
        "big_issue_press": config.BIG_ISSUE_PRESS, "articles": len(arts),
    }
    data = {"meta": meta, "press": press, "topics": config.TOPIC_NAMES, "clusters": clusters, "articles": arts}
    config.DASHBOARD_DIR.mkdir(exist_ok=True)
    tmp = config.DATA_JS.with_suffix(".js.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("// 자동 생성 파일 - 직접 수정하지 마세요\n")
        f.write("window.ASAN_DATA = " + _dump(data) + ";\n")
        f.write("window.ASAN_REPORT = " + _dump(report or {}) + ";\n")
    os.replace(tmp, config.DATA_JS)  # 원자적 교체: 실패해도 기존 화면 유지
    kb = config.DATA_JS.stat().st_size // 1024
    print(f"내보내기: 기사 {len(arts)}건 · 매체 {len(press)}개 → dashboard/data.js ({kb:,} KB)")
