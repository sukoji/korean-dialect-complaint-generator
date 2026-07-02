# -*- coding: utf-8 -*-
"""민원(악취) 텍스트에서 데이터셋용 구조화 메타데이터 추출."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

REGIONS_5 = ("경상", "전라", "제주", "충청", "강원")

AUGMENT_COLUMN_KEYS = [f"증강_{r}" for r in REGIONS_5]

META_FIELD_KEYS = (
    "위치",
    "냄새종류",
    "원인추정지역",
    "냄새강도의변화",
    "지속시간",
)

# 선샘플 키워드 구성(슬롯 GT와 별도 — odor_keyword_config 기반)
KEYWORD_PLAN_COLUMN_KEYS = (
    "키워드_위치",
    "키워드_냄새",
    "키워드_강도",
    "키워드_지속",
    "키워드_원인",
)

_KEYWORD_PLAN_INTERNAL = {
    "location": "키워드_위치",
    "location_asr": "키워드_위치_ASR",
    "odor_type": "키워드_냄새",
    "intensity_change": "키워드_강도",
    "duration": "키워드_지속",
    "cause_guess": "키워드_원인",
}


def apply_keyword_plan_columns(
    record: Dict[str, Any], keyword_plan: Dict[str, Any]
) -> Dict[str, Any]:
    """keyword_plan → 테이블·CSV용 한글 컬럼."""
    out = dict(record)
    kp = keyword_plan or {}
    for src, col in _KEYWORD_PLAN_INTERNAL.items():
        val = (kp.get(src) or "").strip() if isinstance(kp.get(src), str) else ""
        if val:
            out[col] = val
    if kp:
        out["keyword_plan"] = dict(kp)
    return out


# 평가 결과 열 — REJECT(쳐내기)도 버리지 않고 점수·사유·통과여부와 함께 저장.
EVAL_RESULT_COLUMN_KEYS = ("통과여부", "평가점수", "평가사유")

DATASET_COLUMN_KEYS = [
    "pass_id",
    "증강권역",
    "방언종류",
    "시나리오유형",
    "시드방언권역",
    "지역세부프로필",
    "규칙샘플시드",
    *META_FIELD_KEYS,
    *KEYWORD_PLAN_COLUMN_KEYS,
    *EVAL_RESULT_COLUMN_KEYS,
    "표준어민원",
    "민원내용",
    "증강민원",
]

# 배포·STT·slot extraction GT CSV (GPT 프롬프트 정렬)
STT_DATASET_CSV_HEADERS = (
    "ID",
    "방언종류",
    "시나리오유형",
    "악취민원위치",
    "냄새종류",
    "원인추정지역",
    "냄새강도변화",
    "지속시간",
    "민원내용",
)
STT_SIMPLE_CSV_HEADERS = STT_DATASET_CSV_HEADERS  # alias

SLOT_INTERNAL_TO_EXPORT = {
    "위치": "악취민원위치",
    "냄새종류": "냄새종류",
    "원인추정지역": "원인추정지역",
    "냄새강도의변화": "냄새강도변화",
    "지속시간": "지속시간",
}

_EVASIVE_SLOT_RE = re.compile(
    r"(?:모르겠|잘\s*모르|글쎄|모름|어렵|말씀\s*드리기\s*어렵|딱\s*집어)",
    re.I,
)


def slot_fill_mode() -> str:
    """strict: 수집 주제·대화 명시만 슬롯 채움. enriched: 규칙·LLM 보강 허용."""
    m = (os.environ.get("SLOT_FILL_MODE") or "strict").strip().lower()
    return m if m in ("strict", "enriched") else "strict"


def _record_locked_empty(record: Dict[str, Any]) -> set:
    locked = record.get("_meta_locked_empty")
    if isinstance(locked, (list, tuple, set)):
        return {str(x) for x in locked if x}
    mapping = {
        "location": "위치",
        "odor_type": "냄새종류",
        "cause_guess": "원인추정지역",
        "intensity_change": "냄새강도의변화",
        "duration": "지속시간",
    }
    collected = record.get("collected_fields")
    if isinstance(collected, (list, tuple)):
        picked = set(collected)
        return {mapping[k] for k in mapping if k not in picked}
    return set()

REGION_ALIASES = {
    "경상": "경상",
    "경상도": "경상",
    "전라": "전라",
    "전라도": "전라",
    "제주": "제주",
    "제주도": "제주",
    "충청": "충청",
    "충청도": "충청",
    "강원": "강원",
    "강원도": "강원",
}

# STT 9열 CSV — 학습 데이터 관례(경상도·충청도 등)
REGION_STT_EXPORT_LABEL: Dict[str, str] = {
    "경상": "경상도",
    "전라": "전라도",
    "제주": "제주도",
    "충청": "충청도",
    "강원": "강원도",
    "미상": "미상",
}

_ODOR_TYPES = (
    "쓰레기", "하수", "하수구", "배설물", "축사", "공장", "매연", "탄", "화학",
    "썩은", "악취", "정화조", "음식물", "담배", "비료", "분뇨",
)
_INTENSITY_PATTERNS = [
    (re.compile(r"(심해|더\s*심|점점\s*심|악화|심각|많이\s*심)"), "심해짐"),
    (re.compile(r"(약해|줄었|나아|감소|조금\s*나)"), "약해짐"),
    (re.compile(r"(비슷|그대로|여전|계속\s*같)"), "변화없음"),
    (re.compile(r"(새로|처음|갑자기\s*생|시작)"), "새로발생"),
]
# 지속시간·강도·원인 등 컬럼용 짧은 키워드 라벨 (문장형 금지)
DURATION_KEYWORDS = (
    "당일",
    "1~3일",
    "1주이상",
    "1개월이상",
    "매일반복",
)
INTENSITY_KEYWORDS = (
    "심해짐",
    "약해짐",
    "변화없음",
    "새로발생",
)
CAUSE_KEYWORDS = (
    "공단·공장",
    "하수·우수",
    "축사·농장",
    "쓰레기·폐기물",
    "주거지",
)

_SENTENCE_TAIL_RE = re.compile(
    r"(?:했어요|했습니다|해요|합니다|인데요|거든요|같아요|모르겠|말씀|드렸|있긴|한데요|쯤부터|부터요|인 것 같)"
)
_SPEAKER_PREFIX_RE = re.compile(
    r"(?:상담원|민원인|공무원|시민)\s*[:：]\s*",
    re.I,
)
# (위치: …) / 위치: … 형태 시드·LLM 부가 설명
_PAREN_META_RE = re.compile(
    r"\(\s*위치\s*[:：]\s*([^,)]+?)(?:,\s*냄새(?:종류)?\s*[:：]\s*([^,)]+))?"
    r"(?:,\s*(?:강도(?:변화)?|냄새강도(?:의)?변화)\s*[:：]\s*([^,)]+))?"
    r"(?:,\s*(?:원인추정(?:지)?|원인)\s*[:：]\s*([^)]+))?\s*\)",
    re.I,
)


def _dialogue_plain(text: str) -> str:
    if not text:
        return ""
    t = _SPEAKER_PREFIX_RE.sub(" ", text)
    return re.sub(r"\s+", " ", t).strip()


def _combined_context(*parts: str) -> str:
    seen: set = set()
    chunks: List[str] = []
    for p in parts:
        plain = _dialogue_plain((p or "").strip())
        if plain and plain not in seen:
            seen.add(plain)
            chunks.append(plain)
    return " ".join(chunks)


def _extract_paren_meta_hints(text: str) -> Dict[str, str]:
    """시드 문자열 괄호 메타 (위치: …, 냄새종류: …) 파싱."""
    out: Dict[str, str] = {}
    for m in _PAREN_META_RE.finditer(text or ""):
        loc, odor, intensity, cause = m.groups()
        if loc and loc.strip():
            out["위치"] = loc.strip()
        if odor and odor.strip():
            out["냄새종류"] = odor.strip()
        if intensity and intensity.strip():
            out["냄새강도의변화"] = intensity.strip()
        if cause and cause.strip():
            out["원인추정지역"] = cause.strip()
    return out


def normalize_region(region: Optional[str]) -> str:
    if not region:
        return "미상"
    r = str(region).strip()
    for key, val in REGION_ALIASES.items():
        if key in r:
            return val
    if r in REGION_ALIASES.values():
        return r
    return "미상"


def stt_dialect_export_label(region: Optional[str]) -> str:
    """STT CSV 방언종류 열 — 권역 약칭을 ○○도 형식으로."""
    macro = normalize_region(region)
    return REGION_STT_EXPORT_LABEL.get(macro, macro or "미상")


# '~로'로 끝나는 폐쇄류 부사 — 도로명(…로)과 표면이 같아 위치로 오인되는 단어들.
# (지명·브랜드 나열이 아니라 한국어 기능어 목록 — 일반화 원칙 위배 아님)
_NON_PLACE_RO_ADVERBS = frozenset({
    "제대로", "그대로", "별로", "바로", "새로", "스스로", "함부로", "억지로",
    "대체로", "실제로", "주로", "서로", "절로", "날로", "멋대로", "맘대로",
    "마음대로", "곧바로", "똑바로", "정말로", "진짜로", "참말로", "의외로",
    "고대로", "제멋대로", "너대로", "나대로", "이대로", "저대로", "그런대로",
})


def _extract_location(text: str) -> str:
    patterns = [
        r"([가-힣0-9]{2,12}\s*(?:아파트|APT|아이파크|힐스|뷰|타운|단지|공단|산업단지|주민센터|마을|하천|주공(?:\d+차)?|맨션|연립|부영|푸르지오|자이|래미안|더샵|캐슬))",
        r"([가-힣]{2,10}(?:동|읍|면|리)\s*(?:아파트|단지)?)",
        r"([가-힣][가-힣0-9]{1,11}(?:\s*(?:앞|근처|인근|맞은편|뒤편)))",
        # '살겠구' 같은 종결어미 오인 방지: 단독 '...구'는 위치로 잡지 않음
        r"([가-힣]{2,10}(?:동|읍|면|리)(?:\s*[0-9]+차)?)",
        r"([가-힣]{2,10}구\s*[가-힣]{1,10}(?:동|로|길))",
        # 도로명(…로/…길): '제대로·참말로' 같은 부사 오인 방지 — 번지수 동반 또는
        # 장소 문맥(근처·인근·쪽 등)이 뒤따를 때만 도로명으로 인정
        r"([가-힣]{2,12}(?:로|길)\s*\d+|[가-힣]{2,12}(?:로|길)(?=\s*(?:근처|인근|쪽|앞|사거리|삼거리|에서)))",
        r"(포항[시읍동면]*|오천[읍면]*|두호[동]*|송도[동공단]*|대송[동면]*|우방[0-9차]*|부영[0-9차]*)",
        r"((?:우방|부영|송도|영일|오천|여천|해도)[가-힣0-9]{0,8})",
        r"([가-힣0-9]{2,16}(?:더샵|레이크|아이파크|힐스|뷰|타운)[가-힣0-9\s]{0,24}(?:\d+동)?\s*(?:근처|앞|인근)?)",
        r"([가-힣]{2,10}\s+[가-힣0-9]{2,20}(?:\d+동)?\s*근처)",
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            loc = m.group(1).strip()
            # '바로 근처'·'제대로'처럼 폐쇄류 부사가 장소로 잡히는 것 방지
            core = re.sub(r"\s*(?:근처|인근|앞|쪽|맞은편|뒤편)$", "", loc).strip()
            if core in _NON_PLACE_RO_ADVERBS:
                continue
            # 이미 잡힌 더 긴 지명의 부분 문자열('제주삼화6차부영' 뒤의 '부영')은 중복 제외
            if any(loc != f and loc in f for f in found):
                continue
            if len(loc) >= 2 and loc not in found:
                found.append(loc)
    return ", ".join(found[:2]) if found else ""


def _extract_odor_type(text: str) -> str:
    t = text.lower()
    if re.search(r"분뇨\s*냄새", t):
        return "분뇨 냄새"
    hits = []
    keyword_map = {
        "지린내": "지린내·찔내",
        "찔내": "지린내·찔내",
        "탄내": "탄·연소 냄새",
        "비린내": "생선·비린내",
        "황화수소": "황화수소·계란썩은냄새",
        "계란": "계란썩은냄새",
        "암모니아": "축사·암모니아",
        "유기용제": "화학·유기용제",
        "톨루엔": "화학·유기용제",
        "쓰레기": "쓰레기 악취",
        "하수": "하수·하수구 악취",
        "하수구": "하수·하수구 악취",
        "썩은": "썩은 냄새",
        "정화조": "정화조 악취",
        "축사": "축사 악취",
        "분뇨": "분뇨 냄새",
        "공장": "공장 배출 악취",
        "매연": "매연·연소 냄새",
        "음식물": "음식물 쓰레기 악취",
        "담배": "담배 냄새",
        "화학": "화학 악취",
        "배설물": "배설물 악취",
        "매립": "매립·쓰레기 악취",
        "침출수": "매립·침출수",
    }
    for kw, label in keyword_map.items():
        if kw in t and label not in hits:
            hits.append(label)
    if hits:
        return hits[0]
    if "냄새" in t or "악취" in t or "앞냄" in t:
        return "일반 악취"
    return ""


def _extract_intensity_change(text: str) -> str:
    return _normalize_intensity_keyword(text, text)


def _split_citizen_clauses(text: str) -> List[str]:
    parts = re.split(r"(?<=[.?!…])\s+|[.?!…]\s*", (text or "").strip())
    return [p.strip() for p in parts if p and p.strip()]


def _extract_duration(text: str) -> str:
    for clause in reversed(_split_citizen_clauses(text)):
        if re.search(r"지속|얼마나|며칠|오늘\s*아침|부터|당일|일주|개월", clause, re.I):
            hit = _normalize_duration_keyword(clause, clause)
            if hit:
                return hit
    return _normalize_duration_keyword(text, text)


def _normalize_duration_keyword(value: str, context: str = "") -> str:
    """문장형 지속 표현 → 당일 / 1~3일 / 1주이상 / 1개월이상 / 매일반복."""
    val = (value or "").strip()
    src = f"{val} {context}".strip()
    if not src:
        return ""
    # 다른 슬롯의 「모르겠어요」가 섞인 민원인 발화 전체에서 지속만 지우지 않도록 value 우선
    if val and re.search(r"모르|기억\s*안|잘\s*모", val):
        return ""

    m = re.search(r"(\d+)\s*개월", src)
    if m:
        return "1개월이상"
    m = re.search(r"(\d+)\s*주", src)
    if m:
        return "1주이상"
    m = re.search(r"(\d+)\s*일", src)
    if m:
        n = int(m.group(1))
        return "1주이상" if n >= 7 else "1~3일"

    if re.search(r"한\s*달|몇\s*달|오래|오랫", src):
        return "1개월이상"
    if re.search(r"며칠|몇\s*일", src):
        return "1~3일"
    if re.search(r"오늘\s*아침\s*부터", src, re.I):
        return "오늘 아침부터"
    if re.search(r"오늘|금일|방금|아침\s*\d|오전\s*\d", src):
        return "당일"
    if re.search(r"어제", src):
        return "1~3일"
    if re.search(
        r"매일|새벽마다|밤마다|밤새|계속|항상|날마다|지난주|일주일|한참|며칠째",
        src,
    ):
        return "매일반복"
    if re.search(r"지속|계속\s*나|안\s*없어", src):
        return "1~3일"
    return ""


def _normalize_intensity_keyword(value: str, context: str = "") -> str:
    """문장형 강도 변화 → 심해짐 / 약해짐 / 변화없음 / 새로발생."""
    src = f"{value} {context}".strip()
    if not src:
        return ""
    # 저녁·밤에 더 심해지는 패턴 우선
    if re.search(
        r"(비\s*오|비가\s*오|습한\s*날).{0,16}(심|강|독|심해)|"
        r"(저녁|밤|야간).{0,12}(심|강|독)|"
        r"(심해|더\s*심|점점\s*심|악화|심각|많이\s*심|심해졌|억수로)",
        src,
    ):
        return "심해짐"
    if re.search(r"(약해|줄었|나아|감소|조금\s*나)", src):
        return "약해짐"
    if re.search(r"(비슷|그대로|여전|계속\s*같|변동\s*없)", src):
        # 「분뇨 냄새 비슷해유」 등 냄새 묘사 오인 방지
        if re.search(
            r"(?:분뇨|냄새|악취|탄내|비린|쓰레기|하수).{0,12}(?:비슷|비슷해)",
            src,
        ):
            return ""
        return "변화없음"
    if re.search(r"(새로|처음|갑자기\s*생|시작|생겼)", src):
        return "새로발생"
    for pat, label in _INTENSITY_PATTERNS:
        if pat.search(src):
            return label
    return ""


def _normalize_cause_keyword(value: str, context: str = "", location: str = "") -> str:
    """문장형 원인 추정 → 시설·구역 키워드."""
    src = f"{value} {context}".strip()
    if not src:
        return ""
    unknown_only = bool(re.search(r"모르|잘\s*모|확실\s*않", src)) and not re.search(
        r"공장|공단|하수|축사|쓰레기|매립|아파트|시설", src
    )
    if unknown_only:
        return ""

    # 구체 시설·구역명 우선 (짧은 구절)
    facility = re.search(
        r"(?:인근|근처|옆)(?:\s*에)?\s*([가-힣0-9]{0,16}"
        r"(?:공단|공장|매립(?:장)?|처리장|축사|하수(?:처리)?장|정화조|야적장|퇴비))",
        src,
    )
    if facility:
        phrase = _SENTENCE_TAIL_RE.sub("", facility.group(1)).strip()
        if len(phrase) >= 2:
            return phrase[:32]
    facility2 = re.search(
        r"([가-힣0-9]{2,24}(?:공단|공장|매립(?:장)?|처리장|축사|농장|하수(?:처리)?장|정화조|야적장|시설))",
        src,
    )
    if facility2:
        phrase = _SENTENCE_TAIL_RE.sub("", facility2.group(1)).strip()
        if len(phrase) >= 2:
            return phrase[:32]

    cause_hints = [
        (r"송도\s*공단|산업\s*단지|국가산업|석유화학|포스코|철강|제철|화학공장|폐수|공장", "공단·공장"),
        (r"하수구|하수|정화조|우수|종말처리", "하수·우수"),
        (r"축사|가축|분뇨|돈사|양돈|농가", "축사·농장"),
        (r"항만|수산|어항|어시장", "항만·수산"),
        (r"쓰레기|음식물|매립|태우|퇴비|소각", "쓰레기·폐기물"),
        (r"아파트|주택|골목|단지", "주거지"),
    ]
    for pat, label in cause_hints:
        if re.search(pat, src):
            return label
    return ""


def _normalize_odor_keyword(value: str, context: str = "") -> str:
    src = f"{value} {context}".strip()
    if not src:
        return ""
    hit = _extract_odor_type(src)
    if hit:
        return hit
    if re.search(r"냄새|악취|앞냄", src):
        return "일반 악취"
    return ""


def _dedupe_location_parts(parts: List[str]) -> List[str]:
    """'부영2차, 부영2차 근처'처럼 포함 관계로 겹치는 슬롯 조각 제거."""
    cleaned = [p.strip() for p in parts if (p or "").strip()]
    if len(cleaned) < 2:
        return cleaned
    out: List[str] = []
    for p in cleaned:
        if any(p != q and p in q for q in out):
            continue
        out = [q for q in out if not (q != p and q in p)]
        if p not in out:
            out.append(p)
    return out


def _normalize_location_keyword(value: str, context: str = "") -> str:
    """지명·시설명만 남기고 문장 꼬리·'근처' 등 제거."""
    src = (value or "").strip()
    if not src:
        src = _extract_location(context)
    else:
        loc = _extract_location(src)
        if loc:
            src = loc
        else:
            src = _SENTENCE_TAIL_RE.sub("", src)
            src = re.sub(r"(근처|인근|앞|뒤|쪽|에서|으로|로)\s*$", "", src).strip()
            src = re.sub(r"\s+", " ", src)
    parts = [p.strip() for p in re.split(r"[,，]", src) if p.strip()]
    if len(parts) > 1:
        src = ", ".join(_dedupe_location_parts(parts)[:2])
    if len(src) > 48:
        parts = [p.strip() for p in re.split(r"[,，]", src) if p.strip()]
        src = ", ".join(_dedupe_location_parts(parts)[:2])
    return src[:48].strip()


def normalize_meta_fields(
    meta: Dict[str, str],
    *,
    context_text: str = "",
    locked_empty: Optional[set] = None,
) -> Dict[str, str]:
    """데이터셋 메타 5열을 키워드·짧은 구절로 통일.

    locked_empty: 시나리오 생성용(대화에 넣지 않음). **저장 시** enrich_record_metadata가
    최종 민원문에서 빈 칸을 다시 채움.
    """
    ctx = _dialogue_plain(context_text or meta.get("민원내용") or "")
    loc_hint = meta.get("위치") or ""
    locked = locked_empty or set()

    out = dict(meta)

    def _norm_field(field: str, normalizer) -> str:
        raw = (meta.get(field) or "").strip()
        if field in locked and not raw:
            return ""
        if field in locked and raw:
            return normalizer(raw, ctx) if normalizer else raw
        return normalizer(raw, ctx)

    out["위치"] = _norm_field("위치", _normalize_location_keyword)
    out["냄새종류"] = _norm_field("냄새종류", _normalize_odor_keyword)
    out["원인추정지역"] = _norm_field(
        "원인추정지역",
        lambda v, c: _normalize_cause_keyword(v, c, out.get("위치") or loc_hint),
    )
    out["냄새강도의변화"] = _norm_field("냄새강도의변화", _normalize_intensity_keyword)
    out["지속시간"] = _norm_field("지속시간", _normalize_duration_keyword)
    return out


def merge_meta_prefer_primary(
    primary: Dict[str, str],
    secondary: Dict[str, str],
) -> Dict[str, str]:
    """primary(시나리오·PASS) 값 우선, 비어 있으면 secondary(추출)로 채움."""
    out = dict(primary)
    for field in META_FIELD_KEYS:
        cur = (out.get(field) or "").strip()
        ext = (secondary.get(field) or "").strip()
        if not cur and ext:
            out[field] = ext
    return out


def enrich_record_metadata(
    record: Dict[str, Any],
    query_llm: Optional[Callable[[list, float], str]] = None,
) -> Dict[str, Any]:
    """메타 5열: strict=수집 주제·명시 추출만, enriched=규칙·LLM 보강."""
    out = dict(record)
    locked = _record_locked_empty(out)
    strict = slot_fill_mode() == "strict"
    if strict:
        region = normalize_region(
            out.get("시드방언권역") or out.get("방언종류") or "경상"
        )
        dlg = (out.get("민원내용") or "").strip()
        aug = out.get("augmented")
        if isinstance(aug, dict):
            seed_reg = normalize_region(out.get("시드방언권역") or "")
            if seed_reg and (aug.get(seed_reg) or "").strip():
                dlg = (aug.get(seed_reg) or dlg).strip()
        slots = extract_strict_slots_from_dialogue(
            dlg, region, locked_empty=locked
        )
        for field in META_FIELD_KEYS:
            out[field] = "" if field in locked else (slots.get(field) or "")
        return out
    llm_fn = query_llm
    aug_text = ""
    aug = out.get("augmented")
    if isinstance(aug, dict):
        aug_text = " ".join(str(v) for v in aug.values() if v)
    ctx = _combined_context(
        out.get("표준어민원") or "",
        out.get("민원내용") or "",
        aug_text,
    )
    hints = _extract_paren_meta_hints(ctx) if not strict else {}
    extracted = extract_complaint_metadata(
        out.get("민원내용") or "",
        corrected_text=ctx,
        translated_text=out.get("표준어민원") or "",
        dominant_region=out.get("시드방언권역") or out.get("방언종류") or "미상",
        query_llm=llm_fn,
    )
    if not strict:
        for field in META_FIELD_KEYS:
            if hints.get(field) and not (extracted.get(field) or "").strip():
                extracted[field] = hints[field]
    base = {f: (out.get(f) or "").strip() for f in META_FIELD_KEYS}
    merged = merge_meta_prefer_primary(base, extracted)
    merged = normalize_meta_fields(
        merged,
        context_text=ctx,
        locked_empty=locked,
    )
    for field in META_FIELD_KEYS:
        if field in locked:
            out[field] = ""
        elif merged.get(field):
            out[field] = merged[field]
    return out


def _extract_cause_region(text: str, location: str) -> str:
    return _normalize_cause_keyword(text, text, location)


def _rule_based_metadata(
    raw_text: str,
    corrected_text: str,
    dominant_region: str,
    translated_text: str = "",
) -> Dict[str, str]:
    src = _combined_context(translated_text, corrected_text, raw_text)
    hints = _extract_paren_meta_hints(src)
    location = hints.get("위치") or _extract_location(src)
    return {
        "방언종류": normalize_region(dominant_region),
        "위치": location,
        "냄새종류": hints.get("냄새종류") or _extract_odor_type(src),
        "원인추정지역": hints.get("원인추정지역")
        or _extract_cause_region(src, location),
        "냄새강도의변화": hints.get("냄새강도의변화")
        or _extract_intensity_change(src),
        "지속시간": hints.get("지속시간") or _extract_duration(src),
        "민원내용": raw_text.strip(),
    }


def _llm_extract_metadata(
    query_llm: Callable[[list, float], str],
    context: str,
) -> Dict[str, str]:
    """규칙으로 못 채운 칸만 LLM JSON 추출 (저비용 1회)."""
    if not context.strip():
        return {}
    prompt = (
        "다음 악취 민원 통화/전사에서 메타데이터만 JSON으로 추출하세요. "
        "없으면 빈 문자열.\n"
        "키: 위치, 냄새종류, 원인추정지역, 냄새강도의변화, 지속시간\n"
        "냄새강도의변화는 심해짐|약해짐|변화없음|새로발생 중 하나 또는 짧은 설명.\n"
        "지속시간은 당일|1~3일|1주이상|1개월이상|매일반복 중 하나 또는 짧은 설명.\n\n"
        f"[민원문]\n{_trunc_meta_context(context)}\n"
    )
    raw = query_llm(
        [
            {
                "role": "system",
                "content": "JSON만 출력. 마크다운 금지.",
            },
            {"role": "user", "content": prompt},
        ],
        0.0,
    )
    return _parse_json_metadata(raw)


def _trunc_meta_context(text: str, limit: int = 2400) -> str:
    t = (text or "").strip()
    return t if len(t) <= limit else t[:limit] + "…"


def _parse_json_metadata(text: str) -> Dict[str, str]:
    text = (text or "").strip()
    if not text:
        return {}
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: Dict[str, str] = {}
    key_map = {
        "위치": "위치",
        "location": "위치",
        "냄새종류": "냄새종류",
        "odor_type": "냄새종류",
        "원인추정지역": "원인추정지역",
        "cause_region": "원인추정지역",
        "냄새강도의변화": "냄새강도의변화",
        "intensity_change": "냄새강도의변화",
        "지속시간": "지속시간",
        "duration": "지속시간",
    }
    for k, v in data.items():
        target = key_map.get(k) or key_map.get(str(k).strip())
        if target and v is not None:
            out[target] = str(v).strip()
    return out


def extract_complaint_metadata(
    raw_dialect: str,
    corrected_text: str = "",
    translated_text: str = "",
    dominant_region: str = "미상",
    query_llm: Optional[Callable[[list, float], str]] = None,
) -> Dict[str, str]:
    """민원 텍스트에서 데이터셋 컬럼용 메타데이터 추출 (규칙 → 빈 칸만 LLM)."""
    base = _rule_based_metadata(
        raw_dialect, corrected_text, dominant_region, translated_text
    )
    base["민원내용"] = raw_dialect.strip()
    base["방언종류"] = normalize_region(dominant_region)
    ctx = _combined_context(translated_text, corrected_text, raw_dialect)
    out = normalize_meta_fields(base, context_text=ctx, locked_empty=set())

    if query_llm and any(not (out.get(f) or "").strip() for f in META_FIELD_KEYS):
        llm_meta = _llm_extract_metadata(query_llm, ctx)
        llm_meta = normalize_meta_fields(llm_meta, context_text=ctx, locked_empty=set())
        out = merge_meta_prefer_primary(out, llm_meta)
    return out


def _flatten_augmented_columns(augmented: Optional[Dict[str, str]]) -> Dict[str, str]:
    """PASS 내부 보관용 — 5권역 증강 맵 (롱 포맷 펼치기 전)."""
    out: Dict[str, str] = {}
    aug = augmented or {}
    for r in REGIONS_5:
        out[f"증강_{r}"] = (aug.get(r) or "").strip()
    return out


def _augmented_text_by_region(pass_record: Dict[str, Any]) -> Dict[str, str]:
    aug: Dict[str, str] = {}
    src = pass_record.get("augmented")
    if isinstance(src, dict):
        aug.update({k: (v or "").strip() for k, v in src.items() if v})
    for r in REGIONS_5:
        key = f"증강_{r}"
        val = (pass_record.get(key) or aug.get(r) or "").strip()
        if val:
            aug[r] = val
    return aug


def _pass_location_fields_for_region(
    pass_record: Dict[str, Any], region: str, seed_i: Optional[int] = None
) -> Dict[str, str]:
    """PASS 메타·영문 키 → 권역별 위치·원인 (증강문 재추출보다 우선)."""
    try:
        from regional_localization import localize_metadata_fields
    except ImportError:
        from agent.regional_localization import localize_metadata_fields

    loc = (
        (pass_record.get("위치") or pass_record.get("location") or "").strip()
    )
    cause = (
        (pass_record.get("원인추정지역") or pass_record.get("cause_guess") or "").strip()
    )
    src_region = (
        pass_record.get("시드방언권역")
        or pass_record.get("시드권역")
        or pass_record.get("seed_region")
        or ""
    ).strip()
    return localize_metadata_fields(
        {"위치": loc, "원인추정지역": cause},
        region,
        seed=seed_i,
        source_region=src_region,
    )


def _citizen_only_text(dialogue: str) -> str:
    """증강/시드 통화문에서 민원인 구간만 (슬롯 GT용)."""
    text = (dialogue or "").strip()
    if not text:
        return ""
    try:
        from consultation_augment import is_official_segment, segment_dialogue
    except ImportError:
        from agent.consultation_augment import is_official_segment, segment_dialogue

    segs = segment_dialogue(text)
    if not segs:
        return text
    parts = [
        (t or "").strip()
        for role, t, _q in segs
        if (t or "").strip() and not is_official_segment(role, t)
    ]
    if parts:
        return " ".join(parts)
    # STT 한 줄·표준어 종결 민원인: 상담원 인사·질문 구간 제거 후 추출
    t = text
    t = re.sub(
        r"(?:"
        r"안녕하세요[^.]*[.\s]*|"
        r"(?:기후대기|악취\s*대응)[^.]*[.\s]*|"
        r"어떤\s*도움[^.]*[.\s]*|"
        r"어떤\s*냄새[^?]*\?\s*|"
        r"위치가\s*어디[^?]*\?\s*|"
        r"어디서\s*나는\s*것\s*같[^?]*\?\s*|"
        r"확인\s*후\s*조치[^.]*[.\s]*|"
        r"감사합니다[.\s]*"
        r")",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s+", " ", t).strip()
    return t or text


def _slot_value_evasive(value: str) -> bool:
    v = (value or "").strip()
    if not v or len(v) < 2:
        return True
    return bool(_EVASIVE_SLOT_RE.search(v))


def extract_strict_slots_from_dialogue(
    dialogue_text: str,
    region: str,
    *,
    locked_empty: Optional[set] = None,
) -> Dict[str, str]:
    """민원인 발화에 명시된 정보만 canonical 슬롯 — 추론·상담원 발화 제외."""
    locked = locked_empty or set()
    citizen = _citizen_only_text(dialogue_text)
    out = {f: "" for f in META_FIELD_KEYS}
    if not citizen.strip():
        return out
    extracted = extract_complaint_metadata(
        citizen,
        corrected_text=citizen,
        translated_text="",
        dominant_region=region,
        query_llm=None,
    )
    extracted = normalize_meta_fields(
        extracted, context_text=citizen, locked_empty=locked
    )
    for field in META_FIELD_KEYS:
        if field in locked:
            continue
        v = (extracted.get(field) or "").strip()
        if v and not _slot_value_evasive(v):
            out[field] = v
    cause = out.get("원인추정지역") or ""
    if cause in ("주거지", "일반") and not re.search(
        r"공장|공단|축사|하수|매립|처리장|정화조|쓰레기|야적|퇴비|의심|원인",
        citizen,
        re.I,
    ):
        out["원인추정지역"] = ""
    return out


def _regional_meta_for_row(
    pass_record: Dict[str, Any],
    region: str,
    augment_text: str,
) -> Dict[str, str]:
    """슬롯 GT: strict는 민원인 발화만, enriched는 기존 병합."""
    locked = _record_locked_empty(pass_record)
    seed_raw = (pass_record.get("규칙샘플시드") or "").strip()
    seed_i: Optional[int] = None
    if seed_raw:
        try:
            seed_i = int(seed_raw)
        except ValueError:
            seed_i = None
    if slot_fill_mode() == "strict":
        # 본문(augment_text)은 이미 권역 현지화된 텍스트 — 거기서 추출한 위치를
        # 다시 localize_for_region에 넣으면 풀의 다른 POI로 드리프트해
        # 슬롯 GT가 본문에 없는 지명이 된다(예: 제주삼화6차부영→뜨란채아파트212동).
        # 추출값을 그대로 GT로 사용한다.
        return extract_strict_slots_from_dialogue(
            augment_text, region, locked_empty=locked
        )

    loc_fields = _pass_location_fields_for_region(pass_record, region, seed_i)

    ctx = _combined_context(
        pass_record.get("표준어민원") or "",
        pass_record.get("민원내용") or "",
        augment_text,
    )
    extracted = extract_complaint_metadata(
        pass_record.get("민원내용") or augment_text,
        corrected_text=ctx,
        translated_text=(pass_record.get("표준어민원") or ""),
        dominant_region=region,
    )
    base = {f: (pass_record.get(f) or "").strip() for f in META_FIELD_KEYS}
    meta = merge_meta_prefer_primary(base, extracted)
    meta = normalize_meta_fields(meta, context_text=ctx, locked_empty=locked)
    if loc_fields.get("위치") and "위치" not in locked:
        meta["위치"] = loc_fields["위치"]
    if loc_fields.get("원인추정지역") and "원인추정지역" not in locked:
        meta["원인추정지역"] = loc_fields["원인추정지역"]
    for field in locked:
        meta[field] = ""
    return meta


def expand_pass_to_regional_rows(
    pass_record: Dict[str, Any],
    *,
    start_global_id: int = 0,
) -> List[Dict[str, Any]]:
    """PASS 1건(5권역 증강) → 권역당 1행 롱 포맷."""
    aug = _augmented_text_by_region(pass_record)
    pass_id = pass_record.get("pass_id") or pass_record.get("id") or 0

    rows: List[Dict[str, Any]] = []
    gid = int(start_global_id)
    for region in REGIONS_5:
        augment_text = (aug.get(region) or "").strip()
        if not augment_text:
            continue
        gid += 1
        meta = _regional_meta_for_row(pass_record, region, augment_text)
        seed_raw = (pass_record.get("규칙샘플시드") or "").strip()
        seed_i: Optional[int] = None
        if seed_raw:
            try:
                seed_i = int(seed_raw)
            except ValueError:
                seed_i = None
        try:
            from regional_localization import localize_for_region
        except ImportError:
            from agent.regional_localization import localize_for_region

        std_src = (pass_record.get("표준어민원") or "").strip()
        raw_src = (pass_record.get("민원내용") or "").strip()
        try:
            std_local = localize_for_region(std_src, region, seed=seed_i)
        except Exception:
            std_local = std_src
        try:
            raw_local = localize_for_region(raw_src, region, seed=seed_i)
        except Exception:
            raw_local = raw_src
        try:
            aug_local = localize_for_region(augment_text, region, seed=seed_i)
        except Exception:
            aug_local = augment_text
        scenario_type = (
            (pass_record.get("시나리오유형") or pass_record.get("scenario_personality") or "")
            .strip()
        )
        row: Dict[str, Any] = {
            "pass_id": pass_id,
            "global_id": gid,
            "id": gid,
            "증강권역": region,
            "방언종류": region,
            "시나리오유형": scenario_type,
            "악취민원위치": meta.get("위치", ""),
            "냄새강도변화": meta.get("냄새강도의변화", ""),
            "시드방언권역": (pass_record.get("시드방언권역") or "").strip(),
            "지역세부프로필": (pass_record.get("지역세부프로필") or "").strip(),
            "규칙샘플시드": (pass_record.get("규칙샘플시드") or "").strip(),
            "표준어민원": std_local,
            "민원내용": raw_local,
            "증강민원": aug_local,
            # 평가 결과(REJECT 포함 저장) — PASS 기본값, web_app에서 덮어씀
            "통과여부": (pass_record.get("통과여부") or "PASS"),
            "평가점수": pass_record.get("평가점수", ""),
            "평가사유": (pass_record.get("평가사유") or "").strip(),
            **meta,
        }
        if pass_record.get("locale_profile"):
            row["locale_profile"] = pass_record["locale_profile"]
        if pass_record.get("scenario_id") is not None:
            row["scenario_id"] = pass_record["scenario_id"]
        if pass_record.get("collected_fields") is not None:
            row["collected_fields"] = pass_record["collected_fields"]
        if pass_record.get("slot_fields") is not None:
            row["slot_fields"] = pass_record["slot_fields"]
        if pass_record.get("_meta_locked_empty") is not None:
            row["_meta_locked_empty"] = pass_record["_meta_locked_empty"]
        kp = pass_record.get("keyword_plan")
        if isinstance(kp, dict) and kp:
            # 저장용 권역 행에서는 증강 결과의 최종 위치와 키워드 위치를 맞춘다.
            kp_row = dict(kp)
            final_loc = (meta.get("위치") or row.get("악취민원위치") or "").strip()
            seed_region = (pass_record.get("시드방언권역") or "").strip()
            if final_loc:
                kp_row["location"] = final_loc
            elif seed_region and region != seed_region:
                # 비-시드 권역에서 본문 위치 추출 실패 시, 시드 권역 지명(예: 춘천…)이
                # 그대로 KW위치로 새지 않게 비움(null) — 권역 불일치 키워드 방지
                kp_row["location"] = ""
                kp_row.pop("location_asr", None)
            row = apply_keyword_plan_columns(row, kp_row)
        rows.append(row)
    return rows


def collapse_regional_rows_to_stt_rows(
    regional_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Long CSV(권역 5행) → STT CSV(통화 1행). 시드 권역 증강문 + strict 슬롯 GT."""
    by_pass: Dict[Any, List[Dict[str, Any]]] = {}
    for r in regional_rows:
        pid = r.get("pass_id")
        if pid is None:
            pid = r.get("id")
        by_pass.setdefault(pid, []).append(r)

    stt_rows: List[Dict[str, Any]] = []
    for pid in sorted(by_pass.keys(), key=lambda x: (int(x) if str(x).isdigit() else str(x))):
        group = by_pass[pid]
        seed = (group[0].get("시드방언권역") or "").strip()
        picked = None
        for r in group:
            reg = (r.get("증강권역") or r.get("방언종류") or "").strip()
            if seed and reg == seed:
                picked = dict(r)
                break
        if not picked:
            picked = dict(group[0])
        gids = [int(x.get("global_id") or 0) for x in group if x.get("global_id")]
        if gids:
            picked["global_id"] = min(gids)
            picked["id"] = picked["global_id"]
        locked = _record_locked_empty(picked)
        region = (picked.get("증강권역") or picked.get("방언종류") or "경상").strip()
        if slot_fill_mode() == "strict":
            slots = extract_strict_slots_from_dialogue(
                picked.get("증강민원") or picked.get("민원내용") or "",
                region,
                locked_empty=locked,
            )
            for field in META_FIELD_KEYS:
                picked[field] = slots.get(field, "")
        stt_rows.append(picked)
    return stt_rows


def build_dataset_record(
    record_id: int,
    global_id: int,
    raw_dialect: str,
    corrected_text: str,
    translated_text: str,
    dominant_region: str,
    query_llm: Optional[Callable[[list, float], str]] = None,
    augmented: Optional[Dict[str, str]] = None,
    seed_dialect_region: str = "",
) -> Dict[str, Any]:
    """PASS 번들 — G-Eval·병합용 (저장·보내기는 expand_pass_to_regional_rows)."""
    meta = extract_complaint_metadata(
        raw_dialect,
        corrected_text=corrected_text,
        translated_text=translated_text,
        dominant_region=dominant_region,
        query_llm=query_llm,
    )
    record: Dict[str, Any] = {
        "id": record_id,
        "pass_id": record_id,
        "global_id": global_id,
        **meta,
        "표준어민원": (translated_text or "").strip(),
        "시드방언권역": (seed_dialect_region or "").strip(),
        "지역세부프로필": "",
        "규칙샘플시드": "",
        **_flatten_augmented_columns(augmented),
    }
    if augmented:
        record["augmented"] = dict(augmented)
    return record


def merge_pass_text_into_record(
    record: Dict[str, Any],
    *,
    raw_dialect: str,
    translated_text: str,
    augmented: Optional[Dict[str, str]] = None,
    seed_dialect_region: str = "",
    query_llm: Optional[Callable[[list, float], str]] = None,
) -> Dict[str, Any]:
    """시나리오 메타 병합 후에도 표준어·원문·5권역 증강 필드가 비지 않도록 보강."""
    out = dict(record)
    aug_src = augmented if augmented is not None else out.get("augmented")
    aug: Dict[str, str] = dict(aug_src) if isinstance(aug_src, dict) else {}

    raw = (raw_dialect or out.get("민원내용") or "").strip()
    translated = (translated_text or out.get("표준어민원") or "").strip()
    if raw:
        out["민원내용"] = raw
    if translated:
        out["표준어민원"] = translated
    if seed_dialect_region:
        out["시드방언권역"] = (seed_dialect_region or out.get("시드방언권역") or "").strip()

    for r in REGIONS_5:
        key = f"증강_{r}"
        val = (aug.get(r) or out.get(key) or "").strip()
        if val:
            out[key] = val
            aug[r] = val
    if aug:
        out["augmented"] = aug
    return enrich_record_metadata(out, query_llm=query_llm)


def dataset_csv_headers() -> List[str]:
    return ["global_id", "row_id"] + DATASET_COLUMN_KEYS


def dataset_csv_row_id(record: Dict[str, Any]) -> Any:
    return record.get("global_id", record.get("id", ""))


def record_to_csv_row(record: Dict[str, Any]) -> List[Any]:
    return [record.get("global_id", ""), dataset_csv_row_id(record)] + [
        record.get(k, "") for k in DATASET_COLUMN_KEYS
    ]


def to_stt_export_text(text: str) -> str:
    """STT CSV용 — 화자 태그 제거·구두점 최소·공백 연결."""
    try:
        from dialogue_boundaries import strip_speaker_labels_for_stt
    except ImportError:
        from agent.dialogue_boundaries import strip_speaker_labels_for_stt
    t = strip_speaker_labels_for_stt(text or "")
    t = re.sub(r"\s*\.\s*", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def slot_csv_cell(record: Dict[str, Any], internal_key: str) -> str:
    """빈 슬롯은 NULL 문자열."""
    v = (record.get(internal_key) or "").strip()
    return "null" if not v else v


def stt_row_location(record: Dict[str, Any]) -> str:
    return (record.get("악취민원위치") or record.get("위치") or "").strip()


def stt_row_intensity_change(record: Dict[str, Any]) -> str:
    return (record.get("냄새강도변화") or record.get("냄새강도의변화") or "").strip()


def record_to_stt_simple_csv_row(record: Dict[str, Any]) -> List[Any]:
    """STT 학습용 9열 — 시드 권역 증강·민원인 발화만 + strict 슬롯 GT."""
    body = (record.get("증강민원") or record.get("민원내용") or "").strip()
    body = _citizen_only_text(body)
    region = (
        record.get("시드방언권역")
        or record.get("방언종류")
        or record.get("증강권역")
        or ""
    )
    return [
        record.get("global_id") or record.get("id") or "",
        stt_dialect_export_label(region),
        record.get("시나리오유형")
        or record.get("시나리오")
        or record.get("scenario_personality")
        or "",
        slot_csv_cell({"위치": stt_row_location(record)}, "위치"),
        slot_csv_cell(record, "냄새종류"),
        slot_csv_cell(record, "원인추정지역"),
        slot_csv_cell({"냄새강도의변화": stt_row_intensity_change(record)}, "냄새강도의변화"),
        slot_csv_cell(record, "지속시간"),
        to_stt_export_text(body),
    ]


def stt_simple_csv_headers() -> List[str]:
    return list(STT_DATASET_CSV_HEADERS)
