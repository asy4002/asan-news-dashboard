"""같은 보도자료로 쓴 기사들을 하나의 이슈로 묶는다.

제목 정규화 → 문자 2-gram 집합 → 자카드 유사도 ≥ CLUSTER_SIM 이면 같은 이슈.
3일 이내 기사끼리만, (날짜, 단어) 역색인으로 후보를 줄인다.
union-find로 묶되 한 이슈의 기간은 최대 7일.
"""
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import config, db, text

_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】|<[^>]*>|〈[^〉]*〉|\{[^}]*\}")
_NONWORD = re.compile(r"[^0-9A-Za-z가-힣\s]")
_STOP = {config.REGION, config.REGION_SHORT, f"{config.REGION_SHORT}시", "기자", "뉴스", "포토"}
BUCKET_LIMIT = 400  # 너무 흔한 (날짜,단어) 버킷은 후보 생성에 쓰지 않음


def normalize(title):
    t = text.strip_prefix(title or "")
    t = _BRACKETS.sub(" ", t)
    t = _NONWORD.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def bigrams(norm):
    s = norm.replace(" ", "")
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def words(norm):
    return {w for w in norm.split() if len(w) >= 2 and w not in _STOP}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def _d(s):
    return date.fromisoformat(s)


def run(conn):
    rows = conn.execute(
        "SELECT id, title, pub_date, press, views, topic FROM articles ORDER BY pub_date, id"
    ).fetchall()
    n = len(rows)
    if n == 0:
        print("이슈 통합: 기사가 없습니다.")
        return 0
    ids = [r["id"] for r in rows]
    dates = [_d(r["pub_date"]) for r in rows]
    norms = [normalize(r["title"]) for r in rows]
    grams = [bigrams(x) for x in norms]
    wsets = [words(x) for x in norms]

    index = defaultdict(list)
    for i in range(n):
        for w in wsets[i]:
            index[(dates[i], w)].append(i)

    edges = []
    win = config.CLUSTER_WINDOW_DAYS
    for i in range(n):
        cands = set()
        for k in range(0, win + 1):
            dd = dates[i] + timedelta(days=k)
            for w in wsets[i]:
                b = index.get((dd, w))
                if b and len(b) <= BUCKET_LIMIT:
                    cands.update(j for j in b if j > i)
        for j in cands:
            if abs((dates[j] - dates[i]).days) > win:
                continue
            s = jaccard(grams[i], grams[j])
            if s >= config.CLUSTER_SIM:
                edges.append((s, i, j))
    edges.sort(reverse=True)

    parent = list(range(n))
    lo = dates[:]
    hi = dates[:]

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    max_span = config.CLUSTER_MAX_SPAN_DAYS
    for _, i, j in edges:
        a, b = find(i), find(j)
        if a == b:
            continue
        nlo, nhi = min(lo[a], lo[b]), max(hi[a], hi[b])
        if (nhi - nlo).days > max_span:
            continue  # 연쇄 병합 방지
        parent[b] = a
        lo[a], hi[a] = nlo, nhi

    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    conn.execute("DELETE FROM clusters")
    cluster_rows, assign = [], []
    for members in groups.values():
        cid = min(ids[m] for m in members)
        if len(members) == 1:
            rep = members[0]
        else:
            sample = members if len(members) <= 60 else members[:60]
            best, best_avg = sample[0], -1.0
            for m in sample:
                avg = sum(jaccard(grams[m], grams[o]) for o in sample if o != m) / (len(sample) - 1)
                if avg > best_avg:
                    best, best_avg = m, avg
            rep = best
        presses = {rows[m]["press"] for m in members if rows[m]["press"]}
        vsum = sum(rows[m]["views"] or 0 for m in members)
        topic = Counter(rows[m]["topic"] for m in members).most_common(1)[0][0]
        cluster_rows.append((
            cid, text.strip_prefix(rows[rep]["title"]),
            min(dates[m] for m in members).isoformat(), max(dates[m] for m in members).isoformat(),
            len(members), len(presses), vsum, topic,
        ))
        assign.extend((cid, ids[m]) for m in members)
    conn.executemany("INSERT INTO clusters VALUES (?,?,?,?,?,?,?,?)", cluster_rows)
    conn.executemany("UPDATE articles SET cluster_id=? WHERE id=?", assign)
    conn.commit()
    db.log_run(conn, "cluster", {"articles": n, "clusters": len(cluster_rows), "edges": len(edges)})
    print(f"이슈 통합: 기사 {n}건 → 이슈 {len(cluster_rows)}개")
    return len(cluster_rows)
