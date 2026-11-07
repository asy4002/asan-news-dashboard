"""정제 · 관련성 판단 · 주제 분류 · 매체명."""
import html
import re
from urllib.parse import urlparse

from . import config

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# 제목 앞 말머리: [포토], 【단독】, <속보>, (아산=뉴스1) 기자명 = 등
_PREFIX = re.compile(
    r"^\s*(?:"
    r"\[[^\]]{0,20}\]|【[^】]{0,20}】|<[^>]{0,20}>|〈[^〉]{0,20}〉|"
    r"\([^)]{0,25}=[^)]{0,25}\)|\([^)]{0,6}\)"
    r"|[가-힣]{2,4}\s*(?:기자|특파원|통신원)\s*[=:]"
    r")\s*"
)


def clean(s):
    if not s:
        return ""
    s = _TAG.sub("", s)
    s = html.unescape(html.unescape(s))
    return _WS.sub(" ", s).strip()


def strip_prefix(title):
    t = title or ""
    for _ in range(4):
        new = _PREFIX.sub("", t, count=1)
        if new == t:
            break
        t = new
    return t.strip()


def _remove_excluded(s):
    for term in config.EXCLUDE_TERMS:
        s = s.replace(term, " ")
    return s


def is_relevant(title, desc):
    t = _remove_excluded(title or "")
    d = _remove_excluded(desc or "")
    whole = t + " " + d
    if config.REGION_SHORT not in whole:
        return False
    if config.REGION_SHORT in t:
        return True
    return any(term in d for term in config.LOCAL_TERMS)


def classify_topic(title, desc=""):
    best, best_score = config.OTHER_TOPIC, 0
    for topic, kws in config.TOPICS.items():
        score = 0
        for kw in kws:
            score += 2 * (title or "").count(kw) + (desc or "").count(kw)
        if score > best_score:
            best, best_score = topic, score
    return best


def domain_of(url):
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    host = host.lower()
    for pre in ("www.", "m.", "news.", "mobile."):
        if host.startswith(pre):
            host = host[len(pre):]
    return host


def press_from_domain(domain):
    if not domain:
        return ""
    if domain in config.PRESS_BY_DOMAIN:
        return config.PRESS_BY_DOMAIN[domain]
    for d, name in config.PRESS_BY_DOMAIN.items():
        if domain.endswith("." + d):
            return name
    return domain
