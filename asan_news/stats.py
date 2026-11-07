"""통계 분석. 화면·보고서의 모든 수치는 여기서만 만든다 (결정적 계산).

진행 중인 마지막 주(오늘이 속한 주)와 오늘은 제외한다.
"""
import csv
import math
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np
from scipy import stats as st

from . import config


def sig(x, digits=3):
    """유효숫자 보존 (p값이 0으로 뭉개지지 않게)."""
    if x is None:
        return None
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        return None
    if x == 0:
        return 0.0
    return float(f"{x:.{digits}g}")


def r4(x):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else round(x, 4)


def describe(arr):
    a = np.asarray(arr, dtype=float)
    if a.size == 0:
        return {"n": 0}
    mean = a.mean()
    sd = a.std(ddof=1) if a.size > 1 else 0.0
    return {
        "n": int(a.size), "mean": r4(mean), "sd": r4(sd), "median": r4(np.median(a)),
        "min": r4(a.min()), "max": r4(a.max()), "cv": r4(sd / mean) if mean else None,
        "sum": r4(a.sum()),
    }


def strength(r):
    if r is None:
        return "-"
    a = abs(r)
    if a < 0.1:
        return "거의 없음"
    if a < 0.3:
        return "약함"
    if a < 0.5:
        return "중간"
    if a < 0.7:
        return "강함"
    return "매우 강함"


def holm(pvals):
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    order = sorted(idx, key=lambda i: pvals[i])
    adj = [None] * len(pvals)
    running = 0.0
    for rank, i in enumerate(order):
        v = min(1.0, (m - rank) * pvals[i])
        running = max(running, v)
        adj[i] = running
    return adj


def fisher_ci(r, n):
    if r is None or n <= 3 or abs(r) >= 1:
        return None, None
    z = math.atanh(r)
    se = 1 / math.sqrt(n - 3)
    return math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)


def _week_start(d):
    return d - timedelta(days=d.weekday())


def load(conn):
    arts = conn.execute(
        "SELECT pub_date, press, cluster_id, views, topic FROM articles WHERE pub_date >= ?",
        (config.START_DATE,),
    ).fetchall()
    clus = conn.execute(
        "SELECT id, first_date, press_cnt, article_cnt, topic FROM clusters WHERE first_date >= ?",
        (config.START_DATE,),
    ).fetchall()
    return arts, clus


def weekly_frame(arts, clus, today):
    cur_week = _week_start(today)
    w_art = Counter()
    w_issue = defaultdict(set)
    w_press = defaultdict(set)
    w_views = Counter()
    w_vcnt = Counter()
    for a in arts:
        d = date.fromisoformat(a["pub_date"])
        ws = _week_start(d)
        if ws >= cur_week:
            continue
        w_art[ws] += 1
        if a["cluster_id"] is not None:
            w_issue[ws].add(a["cluster_id"])
        if a["press"]:
            w_press[ws].add(a["press"])
        if a["views"] is not None:
            w_views[ws] += a["views"]
            w_vcnt[ws] += 1
    w_big = Counter()
    for c in clus:
        ws = _week_start(date.fromisoformat(c["first_date"]))
        if ws < cur_week and (c["press_cnt"] or 0) >= config.BIG_ISSUE_PRESS:
            w_big[ws] += 1
    if not w_art:
        return []
    first = min(w_art)
    weeks = []
    ws = first
    while ws < cur_week:
        n = w_art[ws]
        iss = len(w_issue[ws])
        weeks.append({
            "week": ws.isoformat(), "articles": n, "issues": iss, "press": len(w_press[ws]),
            "big": w_big[ws], "per_issue": (n / iss) if iss else 0.0,
            "views": w_views[ws], "views_cnt": w_vcnt[ws],
        })
        ws += timedelta(days=7)
    return weeks


def daily_frame(arts, today):
    c = Counter(a["pub_date"] for a in arts)
    start = date.fromisoformat(config.START_DATE)
    out = []
    d = start
    while d < today:
        out.append((d, c.get(d.isoformat(), 0)))
        d += timedelta(days=1)
    return out


def corr_pair(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    if n < 4 or np.std(x) == 0 or np.std(y) == 0:
        return {"n": n, "r": None, "p": None, "ci": [None, None], "rho": None, "rho_p": None}
    r, p = st.pearsonr(x, y)
    rho, rp = st.spearmanr(x, y)
    lo, hi = fisher_ci(r, n)
    return {"n": n, "r": r4(r), "p": sig(p), "ci": [r4(lo), r4(hi)], "rho": r4(rho), "rho_p": sig(rp)}


def analyze(conn, today=None):
    today = today or date.today()
    arts, clus = load(conn)
    weeks = weekly_frame(arts, clus, today)
    days = daily_frame(arts, today)
    out = {"generated_for": today.isoformat(), "start": config.START_DATE,
           "n_articles": len(arts), "n_issues": len(clus), "weeks_n": len(weeks)}

    # ── 기술통계 ──
    wa = [w["articles"] for w in weeks]
    da = [c for _, c in days]
    out["descriptive"] = {
        "weekly": describe(wa), "daily": describe(da),
        "weekly_issues": describe([w["issues"] for w in weeks]),
        "weekly_press": describe([w["press"] for w in weeks]),
        "issue_press": describe([c["press_cnt"] or 0 for c in clus]),
    }

    # ── 추세 ──
    trend = {"available": len(weeks) >= 4, "points": [{"week": w["week"], "y": w["articles"]} for w in weeks]}
    if trend["available"]:
        x = np.arange(len(weeks))
        lr = st.linregress(x, wa)
        rho, rp = st.spearmanr(x, wa)
        trend.update({
            "slope": r4(lr.slope), "intercept": r4(lr.intercept), "r2": r4(lr.rvalue ** 2),
            "p": sig(lr.pvalue), "rho": r4(rho), "rho_p": sig(rp),
            "pct_per_week": r4(lr.slope / np.mean(wa) * 100) if np.mean(wa) else None,
        })
    out["trend"] = trend

    # ── 상관 ──
    views_ok = sum(1 for w in weeks if w["views_cnt"] > 0) >= 5
    variables = [
        ("issues", "이슈 수", "보도 건수 = 이슈 수 × 이슈당 보도 건수이므로 구조적 상관이 존재함"),
        ("press", "보도 매체 수", None),
        ("big", "대형 확산 이슈 수", None),
        ("per_issue", "이슈당 보도 건수", "보도 건수의 구성 요소로 구조적 상관 가능성 있음"),
    ]
    if views_ok:
        variables.append(("views", "확인 조회수", "조회수는 공개 매체 일부만 확인된 표본임"))
    corrs = []
    for key, label, note in variables:
        xs = [w[key] for w in weeks]
        c = corr_pair(xs, wa)
        c.update({"key": key, "label": label, "note": note,
                  "points": [[r4(a), b] for a, b in zip(xs, wa)]})
        corrs.append(c)
    adj = holm([c["p"] for c in corrs])
    for c, a in zip(corrs, adj):
        c["p_holm"] = sig(a)
        c["strength"] = strength(c["r"])
    out["correlation"] = {"target": "주간 보도 건수", "views_included": views_ok, "items": corrs}

    # ── 상관행렬 ──
    mkeys = [("articles", "보도 건수"), ("issues", "이슈 수"), ("press", "매체 수"),
             ("big", "대형 확산"), ("per_issue", "이슈당 보도")]
    mat = []
    for k1, _ in mkeys:
        row = []
        for k2, _ in mkeys:
            if k1 == k2:
                row.append(1.0)
            else:
                row.append(corr_pair([w[k1] for w in weeks], [w[k2] for w in weeks])["r"])
        mat.append(row)
    out["matrix"] = {"labels": [l for _, l in mkeys], "values": mat}

    # ── 요일 효과 ──
    names = ["월", "화", "수", "목", "금", "토", "일"]
    by_wd = defaultdict(list)
    for d, c in days:
        by_wd[d.weekday()].append(c)
    wk = {"available": len(days) >= 14,
          "means": [r4(np.mean(by_wd[i])) if by_wd[i] else None for i in range(7)], "labels": names}
    if wk["available"]:
        wkday = [c for d, c in days if d.weekday() < 5]
        wkend = [c for d, c in days if d.weekday() >= 5]
        u, p = st.mannwhitneyu(wkday, wkend, alternative="two-sided")
        n1, n2 = len(wkday), len(wkend)
        mu, sd = n1 * n2 / 2, math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
        z = (u - mu) / sd if sd else 0
        groups = [by_wd[i] for i in range(7) if len(by_wd[i]) > 1]
        varied = len({v for g in groups for v in g}) > 1
        h, kp = st.kruskal(*groups) if len(groups) >= 2 and varied else (None, None)
        wk.update({
            "weekday_mean": r4(np.mean(wkday)), "weekend_mean": r4(np.mean(wkend)),
            "weekday_median": r4(np.median(wkday)), "weekend_median": r4(np.median(wkend)),
            "u": r4(u), "p": sig(p), "z": r4(z), "effect_r": r4(abs(z) / math.sqrt(n1 + n2)),
            "kruskal_h": r4(h), "kruskal_p": sig(kp),
        })
    out["weekday"] = wk

    # ── 주제별 확산력 ──
    by_t = defaultdict(list)
    for c in clus:
        by_t[c["topic"] or config.OTHER_TOPIC].append(c["press_cnt"] or 0)
    eligible = {t: v for t, v in by_t.items() if len(v) >= 20}
    ts = {"min_issues": 20, "topics": []}
    for t in config.TOPIC_NAMES:
        v = by_t.get(t, [])
        if v:
            ts["topics"].append({"topic": t, "issues": len(v), "mean": r4(np.mean(v)),
                                 "median": r4(np.median(v)), "big": sum(1 for x in v if x >= config.BIG_ISSUE_PRESS),
                                 "included": t in eligible})
    if len(eligible) >= 2:
        h, p = st.kruskal(*eligible.values())
        n = sum(len(v) for v in eligible.values())
        ts.update({"available": True, "h": r4(h), "p": sig(p), "k": len(eligible),
                   "epsilon2": r4(h * (n + 1) / (n * n - 1)) if n > 1 else None, "n": n})
    else:
        ts["available"] = False
    out["topic_spread"] = ts

    # ── 주제 구성 변화 (주제 × 월) ──
    months = sorted({a["pub_date"][:7] for a in arts})
    tab = defaultdict(Counter)
    for a in arts:
        tab[a["topic"] or config.OTHER_TOPIC][a["pub_date"][:7]] += 1
    topics = [t for t in config.TOPIC_NAMES if sum(tab[t].values()) > 0]
    table = [[tab[t][m] for m in months] for t in topics]
    tm = {"months": months, "topics": topics, "counts": table, "available": False}
    if len(topics) >= 2 and len(months) >= 2:
        arr = np.array(table, dtype=float)
        colsum = arr.sum(axis=0)
        tm["shares"] = [[r4(arr[i, j] / colsum[j]) if colsum[j] else 0 for j in range(len(months))]
                        for i in range(len(topics))]
        chi2, p, dof, _ = st.chi2_contingency(arr)
        n = arr.sum()
        v = math.sqrt(chi2 / (n * (min(arr.shape) - 1))) if n else None
        tm.update({"available": True, "chi2": r4(chi2), "p": sig(p), "dof": int(dof), "cramers_v": r4(v), "n": int(n)})
    out["topic_month"] = tm

    # ── 홍보비 연계 ──
    out["budget"] = budget_analysis(arts, today)

    # ── 조회수 공개율 ──
    vcnt = sum(1 for a in arts if a["views"] is not None)
    out["views_coverage"] = {"checked": vcnt, "total": len(arts),
                             "rate": r4(vcnt / len(arts)) if arts else 0}

    out["limitations"] = limitations(out)
    out["summary"] = {
        "weekly_mean": out["descriptive"]["weekly"].get("mean"),
        "trend_pct": trend.get("pct_per_week"), "trend_p": trend.get("p"),
        "top_corr": max((c for c in corrs if c["r"] is not None), key=lambda c: abs(c["r"]), default=None),
        "weekday_ratio": r4(wk["weekday_mean"] / wk["weekend_mean"]) if wk.get("weekend_mean") else None,
    }
    if out["summary"]["top_corr"]:
        tc = out["summary"]["top_corr"]
        out["summary"]["top_corr"] = {"label": tc["label"], "r": tc["r"], "p_holm": tc["p_holm"]}
    return out


def budget_analysis(arts, today):
    p = config.BUDGET_CSV
    if not p.exists():
        return {"available": False, "reason": "data/budget.csv 없음"}
    amounts = {}
    with open(p, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                amounts[row["month"].strip()[:7]] = float(str(row["amount"]).replace(",", ""))
            except (KeyError, ValueError):
                continue
    cnt = Counter(a["pub_date"][:7] for a in arts)
    cur = today.isoformat()[:7]
    months = sorted(m for m in amounts if m < cur)
    rows = [{"month": m, "amount": amounts[m], "articles": cnt.get(m, 0),
             "per_article": r4(amounts[m] / cnt[m]) if cnt.get(m) else None} for m in months]
    res = {"available": True, "months": rows, "n": len(rows)}
    if len(rows) >= 4:
        res.update(corr_pair([r["amount"] for r in rows], [r["articles"] for r in rows]))
    total_a = sum(r["amount"] for r in rows)
    total_n = sum(r["articles"] for r in rows)
    res["total_amount"] = total_a
    res["total_articles"] = total_n
    res["cost_per_article"] = r4(total_a / total_n) if total_n else None
    res["small_sample"] = len(rows) < 12
    return res


def limitations(o):
    L = ["수집 편향: 네이버 뉴스 검색(검색어당 최대 1,000건)과 선택적 뉴스토어 수집에 의존하므로 "
         "전체 보도를 포괄하지 못함. 검색어·수집 범위 변경 시 추세가 인위적으로 달라질 수 있음",
         "상관≠인과: 제시된 상관계수는 동시 변동을 나타낼 뿐 홍보 활동의 인과 효과를 의미하지 않음",
         "자기상관: 주간 시계열은 서로 독립이 아니므로 p값이 실제보다 작게 추정될 수 있음"]
    vc = o["views_coverage"]
    if vc["rate"] < 0.5:
        L.append(f"조회수 표본 부족: 조회수가 확인된 기사는 전체의 {vc['rate'] * 100:.1f}%에 불과하여 "
                 "도달 규모 판단에 한계가 있음")
    if o["weeks_n"] < 12:
        L.append(f"분석 기간이 {o['weeks_n']}주로 짧아 통계적 결론을 유보함")
    b = o["budget"]
    if b.get("available") and b.get("small_sample"):
        L.append(f"홍보비 자료가 {b['n']}개월로 적어 홍보비-보도량 관계에 대한 결론을 유보함")
    return L
