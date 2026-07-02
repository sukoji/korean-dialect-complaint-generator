# -*- coding: utf-8 -*-
"""아파트·장소 지명 — 구어 별칭(축약)·STT/방언 발화용 변형 (정규 지명과 분리)."""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

_PLACE_TOKEN_RE = re.compile(r"[가-힣]{2,}")
_CITY_PREFIX_RE = re.compile(r"^([가-힣]{2,10}(?:시|군|구))\s+")
_PHASE_RE = re.compile(r"(\d+)\s*단지")
_CENTRAL_PARK_RE = re.compile(r"센트럴\s*파크|센트럴파크", re.I)
_EPYEONHAN_RE = re.compile(r"(?:e|이)?편한\s*세상", re.I)


def primary_place_token(location: str) -> str:
    """위치 문자열에서 핵심 고유명사 토큰(가장 긴 한글 연속)."""
    chunks = _PLACE_TOKEN_RE.findall((location or "").strip())
    if not chunks:
        return ""
    return max(chunks, key=len)


def _split_location_suffix(
    loc: str, suffixes: List[str]
) -> Tuple[str, str]:
    text = (loc or "").strip()
    for suf in sorted(suffixes, key=len, reverse=True):
        s = suf.strip()
        if not s:
            continue
        if text.endswith(s):
            return text[: -len(s)].strip(), suf if suf.startswith(" ") else f" {s}"
    return text, ""


def colloquial_short_place_phrase(
    location: str,
    rng: random.Random,
    cfg: Optional[Dict[str, Any]] = None,
) -> str:
    """
    정규·풀네임 지명 → 주민이 실제로 부르는 짧은 별칭.
    슬롯 GT(location)는 풀네임 유지, 민원인 발화(location_asr)용.
    """
    cfg = cfg or {}
    prob = float(cfg.get("apply_prob", 0.88))
    max_chars = int(cfg.get("max_spoken_chars", 22))
    suffixes = list(cfg.get("suffixes") or [" 근처", " 앞", " 쪽", " 인근"])
    suffix_prob = float(cfg.get("suffix_prob", 0.72))

    loc = (location or "").strip()
    if not loc or rng.random() > prob:
        return loc

    core, suffix = _split_location_suffix(loc, suffixes)
    city = ""
    m_city = _CITY_PREFIX_RE.match(core)
    if m_city:
        city = m_city.group(1)
        core = core[m_city.end() :].strip()

    core = re.sub(r"\s*아파트\s*$", "", core, flags=re.I)
    core = re.sub(r"\s*APT\s*$", "", core, flags=re.I)
    core = re.sub(r"\s+", "", core)

    options: List[str] = []
    phase_m = _PHASE_RE.search(core)
    phase_s = f"{phase_m.group(1)}단지" if phase_m else ""

    if _EPYEONHAN_RE.search(core):
        tail = _EPYEONHAN_RE.sub("", core).strip()
        if _CENTRAL_PARK_RE.search(tail) or "연동" in tail:
            opts = [
                f"{city} 센트럴 {phase_s}".strip(),
                f"{city} 연동 센트럴".strip(),
                "연동 센트럴",
                f"센트럴 {phase_s}".strip(),
                f"{city} 편한 {phase_s}".strip() if phase_s else f"{city} 편한세상".strip(),
                "편한세상",
            ]
            options.extend(o for o in opts if o and len(o) >= 2)
        elif tail:
            short = primary_place_token(tail)[:8] or tail[:8]
            options.append(f"{city} {short}".strip() if city else short)
        else:
            options.append(f"{city} 편한세상".strip() if city else "편한세상")

    dong_m = re.search(r"([가-힣]{2,6})동", core)
    if dong_m and len(options) < 4:
        dong = dong_m.group(1) + "동"
        options.append(f"{city} {dong}".strip() if city else dong)

    token = primary_place_token(core)
    if token and len(token) > 9:
        for n in (5, 7, 9):
            nick = token[:n]
            if phase_s and phase_s not in nick:
                options.append(f"{city} {nick} {phase_s}".strip() if city else f"{nick} {phase_s}")
            options.append(f"{city} {nick}".strip() if city else nick)

    # 단지번호 단독(예: '1단지')은 지명성이 없어 GIS 복원 불가 → 옵션에서 제외.
    # 과축약(3자 이하 '울산동' 류)도 복원 불가하므로 최소 4자 유지(없으면 core 폴백).
    options = [o for o in dict.fromkeys(options) if o and 4 <= len(o) <= max_chars + 6]
    if not options:
        if len(core) > max_chars:
            short = core[: max(6, max_chars - len(city) - 1)]
            picked = f"{city} {short}".strip() if city else short
        else:
            picked = f"{city} {core}".strip() if city else core
    else:
        options.sort(key=len)
        top = options[: min(4, len(options))]
        picked = rng.choice(top)

    if len(picked) > max_chars:
        picked = picked[:max_chars]

    if not suffix and suffixes and rng.random() < suffix_prob:
        suffix = rng.choice(suffixes)
    return (picked + suffix).strip()


# ── 자모 단위 STT 오인식 노이즈 (지명 음소 왜곡) ──────────────────────────
_HANGUL_BASE = 0xAC00
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = "_ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"  # '_' = 종성 없음
# STT가 흔히 혼동하는 자모 쌍(경음화·격음·유사 모음). 양방향 적용.
_CHO_CONFUSE = {
    "ㄱ": "ㄲㅋ", "ㄲ": "ㄱ", "ㅋ": "ㄲㄱ", "ㄷ": "ㄸㅌ", "ㄸ": "ㄷ", "ㅌ": "ㄷㄸ",
    "ㅂ": "ㅃㅍ", "ㅃ": "ㅂ", "ㅍ": "ㅂ", "ㅅ": "ㅆ", "ㅆ": "ㅅ",
    "ㅈ": "ㅉㅊ", "ㅉ": "ㅈ", "ㅊ": "ㅈ",
}
_JUNG_CONFUSE = {
    "ㅐ": "ㅔ", "ㅔ": "ㅐ", "ㅗ": "ㅜ", "ㅜ": "ㅗ", "ㅓ": "ㅗ", "ㅡ": "ㅜ",
    "ㅒ": "ㅖ", "ㅖ": "ㅒ", "ㅚ": "ㅙ", "ㅢ": "ㅣ",
}
_JONG_CONFUSE = {"ㄱ": "_", "ㄴ": "ㅇ", "ㅇ": "ㄴ", "ㅁ": "ㄴ", "ㅂ": "_"}


def _decompose(ch: str) -> Optional[Tuple[int, int, int]]:
    code = ord(ch) - _HANGUL_BASE
    if 0 <= code < 11172:
        return code // 588, (code % 588) // 28, code % 28
    return None


def _compose(cho: int, jung: int, jong: int) -> str:
    return chr(_HANGUL_BASE + (cho * 21 + jung) * 28 + jong)


def jamo_stt_noise(token: str, rng: random.Random) -> Optional[str]:
    """지명 토큰에 STT 흔한 자모 오인식 1곳 적용(경음/격음/유사모음/종성).

    1편집만 가해 GIS 자모 퍼지 매칭으로 복원 가능한 거리를 유지한다.
    """
    if len(token) < 2:
        return None
    idxs = list(range(len(token)))
    rng.shuffle(idxs)
    for i in idxs:
        d = _decompose(token[i])
        if not d:
            continue
        cho, jung, jong = d
        choices = []
        c = _CHO[cho]
        if c in _CHO_CONFUSE:
            choices.append(("cho", rng.choice(_CHO_CONFUSE[c])))
        v = _JUNG[jung]
        if v in _JUNG_CONFUSE:
            choices.append(("jung", _JUNG_CONFUSE[v]))
        t = _JONG[jong]
        if t in _JONG_CONFUSE:
            choices.append(("jong", _JONG_CONFUSE[t]))
        if not choices:
            continue
        kind, repl = rng.choice(choices)
        if kind == "cho":
            cho = _CHO.index(repl)
        elif kind == "jung":
            jung = _JUNG.index(repl)
        else:
            jong = _JONG.index(repl)
        new_ch = _compose(cho, jung, jong)
        if new_ch == token[i]:
            continue
        return token[:i] + new_ch + token[i + 1 :]
    return None


def slur_first_two_syllables(token: str) -> Optional[str]:
    """
    복합 브랜드 접두 2음절 누락·ㅎ 혼동.
    예: 서희스타힐스 → 스히스타힐스 (첫 음절 탈락 + 희→히, ㅅ 잔류).
    """
    if len(token) < 4:
        return None
    s1, s2, tail = token[0], token[1], token[2:]
    if not tail:
        return None
    if s2 == "희":
        return "스히" + tail
    if s2 in ("희", "히") and s1 in "서수선신사새":
        return s1 + "히" + tail
    return None


def drop_leading_syllable(token: str) -> Optional[str]:
    if len(token) < 3:
        return None
    return token[1:]


def _apply_replacement_map(text: str, pairs: List[Dict[str, str]]) -> str:
    out = text
    for pair in sorted(pairs, key=lambda p: len(p.get("from") or ""), reverse=True):
        fr = (pair.get("from") or "").strip()
        to = (pair.get("to") or "").strip()
        if fr and fr in out:
            out = out.replace(fr, to, 1)
            return out
    return out


def maybe_asr_place_variant(
    location: str,
    rng: random.Random,
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    (canonical, spoken) — spoken은 민원인 발화·STT용, canonical은 슬롯 GT용.
    구어 별칭 축약 후 선택적 음소 누락·혼동을 적용한다.
    """
    canon = (location or "").strip()
    if not canon:
        return "", ""

    cfg = cfg or {}
    coll_cfg = cfg.get("colloquial") if isinstance(cfg.get("colloquial"), dict) else {}
    spoken_base = colloquial_short_place_phrase(canon, rng, coll_cfg)
    if spoken_base == canon:
        spoken_base = canon

    prob = float(cfg.get("apply_prob", 0.45))
    if rng.random() > prob:
        if spoken_base != canon:
            return canon, spoken_base
        return canon, canon

    spoken = _apply_replacement_map(spoken_base, list(cfg.get("replacements") or []))
    if spoken != spoken_base:
        return canon, spoken.strip()

    rules = list(cfg.get("rules") or ["jamo_stt_noise", "slur_hieung_second", "drop_leading_syllable"])
    token = primary_place_token(spoken_base)
    if not token:
        return canon, spoken_base if spoken_base != canon else canon

    variant_token: Optional[str] = None
    if "jamo_stt_noise" in rules:  # 지명 음소 오인식(영일대→영일때) — 우선
        variant_token = jamo_stt_noise(token, rng)
    if not variant_token and "slur_hieung_second" in rules:
        variant_token = slur_first_two_syllables(token)
    if not variant_token and "drop_leading_syllable" in rules:
        variant_token = drop_leading_syllable(token)

    if variant_token and variant_token != token:
        spoken = spoken_base.replace(token, variant_token, 1)
        return canon, spoken.strip()

    if spoken_base != canon:
        return canon, spoken_base
    return canon, canon


def attach_location_asr_to_meta(
    meta: Dict[str, Any], rng: random.Random, cfg: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """meta에 location(정규) + location_asr(구어·발화) 설정."""
    out = dict(meta or {})
    loc = (out.get("location") or "").strip()
    if not loc:
        out.pop("location_asr", None)
        out.pop("location_colloquial", None)
        return out
    canon, spoken = maybe_asr_place_variant(loc, rng, cfg)
    out["location"] = canon
    coll_only = colloquial_short_place_phrase(
        canon, rng, (cfg or {}).get("colloquial") if isinstance((cfg or {}).get("colloquial"), dict) else {}
    )
    if coll_only and coll_only != canon:
        out["location_colloquial"] = coll_only
    else:
        out.pop("location_colloquial", None)
    if spoken and spoken != canon:
        out["location_asr"] = spoken
    else:
        out.pop("location_asr", None)
    return out


def citizen_location_phrase(meta: Dict[str, Any]) -> str:
    """민원인 발화에 쓸 위치 표현 (구어 별칭·ASR 변형 우선)."""
    asr = (meta.get("location_asr") or "").strip()
    if asr:
        return asr
    coll = (meta.get("location_colloquial") or "").strip()
    if coll:
        return coll
    return (meta.get("location") or "").strip()


def reinject_place_asr_in_dialogue(text: str, meta: Dict[str, Any]) -> str:
    """GIS가 정규 지명으로 되돌린 뒤, 의도한 구어·ASR 표기를 민원인 구간에 복원."""
    canon = (meta.get("location") or "").strip()
    asr = (meta.get("location_asr") or meta.get("location_colloquial") or "").strip()
    if not text or not asr or asr == canon:
        return text or ""
    out = text
    if canon and canon in out:
        return out.replace(canon, asr, 1)
    ct = primary_place_token(canon)
    at = primary_place_token(asr)
    if ct and at and ct in out and ct != at:
        return out.replace(ct, at, 1)
    if asr in out:
        return out
    return out
