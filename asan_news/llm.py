"""Gemini 해석. 수치를 만들지 않고, stats.py 가 계산한 JSON 만 해석한다."""
import copy
import json
import urllib.error
import urllib.request

from . import config

PROMPT = """너는 지방자치단체 홍보 성과를 분석하는 통계 전문가다.
아래 JSON은 {region} 관련 온라인 뉴스 보도를 통계 분석한 결과다.

[규칙]
1. JSON에 있는 수치만 사용하고, 새로운 수치를 계산하거나 만들지 말 것.
2. 유의성 판단은 Holm 보정 p값(p_holm)을 기준으로 하고, p<0.05일 때만 '유의함'이라 쓸 것.
3. 인과관계를 단정하지 말 것("~때문에" 금지, "~와 함께 변동함" 등으로 표현).
4. 추세 문장에는 수집 편향 가능성을 반드시 함께 명시할 것.
5. 표본이 작거나(available=false, small_sample=true, 주 수 12 미만) 근거가 약하면 결론을 유보할 것.
6. 문장은 공무원 보고서 개조식으로 쓸 것(문장 끝 "~함", "~임", "~됨").
7. p값이 0.001 미만이면 "p<0.001"로 쓸 것.

[출력 형식] 다음 키를 가진 JSON 하나만 출력:
{{"headline": "한 문장 요약",
 "key_findings": ["핵심 발견 3~5개"],
 "sections": {{"trend": "", "correlation": "", "weekday": "", "topic_spread": "", "topic_month": "", "budget": ""}},
 "recommendations": ["제언 3~5개"],
 "caveats": ["유의사항 2~4개"]}}

[분석 결과 JSON]
{data}
"""


def _strip(obj):
    """차트용 원자료(points, series 등)는 보내지 않는다."""
    o = copy.deepcopy(obj)

    def walk(x):
        if isinstance(x, dict):
            for k in list(x.keys()):
                if k in ("points", "series", "counts", "shares", "months_detail"):
                    del x[k]
                else:
                    walk(x[k])
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(o)
    return o


def interpret(stats_result):
    key = config.env("GEMINI_API_KEY")
    model = config.env("GEMINI_TEXT_MODEL")
    if not key or not model:
        print("AI 해석: GEMINI_API_KEY 또는 GEMINI_TEXT_MODEL 이 없어 건너뜀")
        return None
    base = config.env("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
    body = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT.format(
            region=config.REGION,
            data=json.dumps(_strip(stats_result), ensure_ascii=False))}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        f"{base}/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read().decode("utf-8"))
        txt = res["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(txt)
        if not isinstance(out, dict) or "headline" not in out:
            raise ValueError("응답 형식 오류")
        out.setdefault("sections", {})
        for k in ("key_findings", "recommendations", "caveats"):
            out.setdefault(k, [])
        return out
    except urllib.error.HTTPError as e:
        print(f"AI 해석 실패: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
    except Exception as e:  # 네트워크·파싱 오류 모두 None
        print(f"AI 해석 실패: {type(e).__name__}: {e}")
    return None
