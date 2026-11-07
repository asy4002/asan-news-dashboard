"""통계 + AI 해석 묶기. AI 실패 시 직전 해석을 재사용한다."""
import json
import re
from datetime import datetime

from . import config, llm, stats


def _previous_ai():
    p = config.REPORT_JSON
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("ai"):
                return d["ai"], d.get("ai_generated")
        except ValueError:
            pass
    js = config.DATA_JS
    if js.exists():
        m = re.search(r"window\.ASAN_REPORT\s*=\s*(\{.*?\});\s*$", js.read_text(encoding="utf-8"), re.S | re.M)
        if m:
            try:
                d = json.loads(m.group(1))
                if d.get("ai"):
                    return d["ai"], d.get("ai_generated")
            except ValueError:
                pass
    return None, None


def build(conn, use_ai=False, sample=False):
    result = stats.analyze(conn)
    ai, ai_at, ai_status = None, None, "none"
    if use_ai and not sample:
        ai = llm.interpret(result)
        if ai:
            ai_at, ai_status = datetime.now().strftime("%Y-%m-%d %H:%M"), "fresh"
    if not ai and not sample:
        ai, ai_at = _previous_ai()
        if ai:
            ai_status = "reused"
    rep = {"stats": result, "ai": ai, "ai_generated": ai_at, "ai_status": ai_status,
           "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "sample": sample}
    if not sample:
        config.DATA_DIR.mkdir(exist_ok=True)
        config.REPORT_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    label = {"fresh": "AI 해석 포함", "reused": "AI 해석 포함(직전 해석 재사용)", "none": "AI 해석 없음(통계만)"}
    print(f"보고서 생성: {label[ai_status]}")
    return rep
