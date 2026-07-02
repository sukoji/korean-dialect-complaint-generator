# -*- coding: utf-8 -*-
"""추출 결과 채점용 정규화. 모델(Opus/Qwen 등) 무관하게 출력 형태 차이를
흡수해서 실제 의미 일치 여부를 비교하기 위함. 프롬프트에 후보 리스트는
안 넣고(합의), 여기서 후처리로만 156종 냄새풀에 매칭한다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ODOR_POOL_PATH = Path(__file__).resolve().parents[1] / "data" / "odor_smell.json"
# complaint_metadata 는 같은 pipeline/ 폴더에 있음
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import complaint_metadata as _cm  # noqa: E402

_SUFFIX_RE = re.compile(r"(냄새|악취)$")
_ODOR_POOL: list[dict] | None = None


def _load_pool() -> list[dict]:
    global _ODOR_POOL
    if _ODOR_POOL is None:
        _ODOR_POOL = json.loads(_ODOR_POOL_PATH.read_text(encoding="utf-8"))
    return _ODOR_POOL


def _core(s: str) -> str:
    return _SUFFIX_RE.sub("", (s or "").strip()).strip()


def normalize_smell(text: str) -> str:
    """자유서술 냄새 표현 → odor_smell.json 156종 중 가장 가까운 원표현.
    매칭 실패 시 원문 그대로(오분류가 그대로 드러나야 채점이 정확함)."""
    t = (text or "").strip()
    if not t:
        return ""
    pool = _load_pool()
    for e in pool:
        if e["odor_keywords"] == t:
            return e["odor_keywords"]
    core = _core(t)
    if not core:
        return t
    for e in pool:
        if _core(e["odor_keywords"]) == core:
            return e["odor_keywords"]
    best = None
    for e in pool:
        kw_core = _core(e["odor_keywords"])
        if kw_core and (kw_core in core or core in kw_core):
            if best is None or len(kw_core) > len(best[0]):
                best = (kw_core, e["odor_keywords"])
    return best[1] if best else t


_INTENSITY_GAP_PATTERNS = [
    (re.compile(r"진하게|짙어짐|강해짐"), "심해짐"),
    (re.compile(r"차이\s*없"), "변화없음"),
]


def normalize_intensity(text: str) -> str:
    """자유서술/카테고리 → 심해짐|약해짐|변화없음|새로발생 (기존 vendor 규칙 재사용).
    카테고리 라벨 자체는 vendor 정규식 어휘와 안 겹칠 수 있어 먼저 identity 체크.
    풀(odor_intensity_200.json) 실측 갭 2건 보강 — 순수 변동(들쭉날쭉 등)은
    분류 안 하는 게 맞아 그대로 둠(강제로 채우면 오분류)."""
    t = (text or "").strip()
    if not t:
        return ""
    if t in _cm.INTENSITY_KEYWORDS:
        return t
    hit = _cm._normalize_intensity_keyword(t, t)
    if hit:
        return hit
    for pat, label in _INTENSITY_GAP_PATTERNS:
        if pat.search(t):
            return label
    return ""


_DURATION_GAP_PATTERNS = [
    (re.compile(r"보름"), "1주이상"),
    (re.compile(r"수\s*개월|몇\s*개월"), "1개월이상"),
    (re.compile(r"수\s*년|몇\s*년"), "1개월이상"),
    (re.compile(r"하루\s*종일|오전\s*내내|낮\s*내내|밤\s*내내|하루\s*내내|하루\s*꼬박"), "당일"),
    (re.compile(r"어젯"), "1~3일"),  # "어젯밤" 사이시옷 표기라 "어제" 패턴에 안 걸림
]


def normalize_duration(text: str) -> str:
    """자유서술/카테고리 → 당일|1~3일|1주이상|1개월이상|매일반복 (기존 vendor 규칙 재사용).
    카테고리 라벨 자체는 vendor 정규식 어휘와 안 겹칠 수 있어 먼저 identity 체크.
    풀(odor_duration_300.json) 실측 갭 보강 — 순수 간격·빈도 묘사(지속기간
    정보 자체가 없는 서술)는 분류 안 하는 게 맞아 그대로 둠."""
    t = (text or "").strip()
    if not t:
        return ""
    if t in _cm.DURATION_KEYWORDS:
        return t
    hit = _cm._normalize_duration_keyword(t, t)
    if hit:
        return hit
    for pat, label in _DURATION_GAP_PATTERNS:
        if pat.search(t):
            return label
    return ""


_LOC_SUFFIX_RE = re.compile(r"(근처|인근|앞|맞은편|옆|부근)\s*$")
_LOC_STRIP_RE = re.compile(r"[\s,，_]+")


def normalize_location(text: str) -> str:
    """공백·구두점·위치접미사 차이 흡수(핵심 지명 비교용)."""
    t = (text or "").strip()
    if not t:
        return ""
    t = _LOC_SUFFIX_RE.sub("", t).strip()
    return _LOC_STRIP_RE.sub("", t)


_ENUM_FIELDS = {
    "냄새강도의변화": _cm.INTENSITY_KEYWORDS,
    "지속시간": _cm.DURATION_KEYWORDS,
}


def validate_extraction(pred: dict) -> tuple[dict, list[str]]:
    """추출 결과 스키마 검증(모델 무관 안전장치). 강도/지속시간은 프롬프트가
    지정한 닫힌 카테고리만 허용 — 다른 필드값이 섞여 들어오는 등 스키마
    위반이면 조용히 흡수하지 않고 빈 문자열로 비우고 위반 목록에 남긴다."""
    out = dict(pred)
    violations: list[str] = []
    for field, allowed in _ENUM_FIELDS.items():
        v = (out.get(field) or "").strip()
        if v and v not in allowed:
            violations.append(f"{field}={v!r} (허용값 {allowed} 아님)")
            out[field] = ""
    return out, violations
