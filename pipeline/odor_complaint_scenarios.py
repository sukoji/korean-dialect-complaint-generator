# -*- coding: utf-8 -*-
"""
포항시 악취 민원 상담 시나리오 (성격별·단계별) — 대량 생성 시드.

data/odor_complaint_scenarios.json: 상담 단계, 성격 유형, 포항 20건, 템플릿 20건.
"""

from __future__ import annotations

import csv
import json
import os
import random
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

Turn = Tuple[str, str]  # (role, text)  role: 상담원 | 민원인

# 패키지 배포판: 모든 데이터는 <repo>/data/ 에 평면 배치(원본 대형 CSV/JSON 대신
# 미리 계산한 경량 풀 사용). __file__ = <repo>/pipeline/odor_complaint_scenarios.py
_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_DATA_PATH = _DATA_DIR / "odor_complaint_scenarios.json"
_KEYWORD_CONFIG_PATH = _DATA_DIR / "odor_keyword_config.json"
_KEYWORD_CONFIG_CACHE: Optional[Dict[str, Any]] = None
_CONS_DIR = _DATA_DIR
_KEYWORD_FILE_CANDIDATES = {
    "odor_types": [_CONS_DIR / "odor_smell.json"],
    "intensity_changes": [_CONS_DIR / "odor_intensity_200.json"],
    "durations": [_CONS_DIR / "odor_duration_300.json"],
}
# 미리 계산한 권역 지명 풀(원본 118MB 지명 CSV를 대체)
_REGION_POOLS_JSON = _DATA_DIR / "region_pools.json"

META_FIELDS = ("location", "odor_type", "intensity_change", "duration", "cause_guess")
META_FIELD_LABELS = {
    "location": "위치",
    "odor_type": "냄새종류",
    "intensity_change": "냄새강도변화",
    "duration": "지속시간",
    "cause_guess": "원인추정지역",
}
# 공식 상담 스크립트 3.2~3.6 순서 — 상담원은 항상 모두 질문
MANDATORY_QUESTION_ORDER = (
    "odor_type",
    "location",
    "intensity_change",
    "duration",
    "cause_guess",
)

# 상담원 3.2~3.6 — 한 문장·예시 나열 없음 (프롬프트·복원·시드 공통)
COMPACT_COUNSELOR_QUESTIONS: Dict[str, str] = {
    "odor_type": "어떤 냄새로 느껴지시나요?",
    "location": "냄새가 나는 위치가 어디신가요?",
    "intensity_change": "냄새 강도가 시간에 따라 변하나요?",
    "duration": "냄새가 얼마나 오래 지속되고 있나요?",
    "cause_guess": "어디서 나는 냄새로 보이시나요?",
}
COMPACT_CLOSING_COUNSELOR = (
    "알겠습니다. 말씀해 주신 내용 확인 후 조치하겠습니다. 감사합니다."
)
_OFFICIAL_QUESTION_BLOAT_SEP = (" 또는 ", " 혹시 ", " 예를 들어", " 예를 들면")

_CITIZEN_CONFIRMED_REPLIES: Dict[str, Tuple[str, ...]] = {
    "odor_type": (
        "역한 냄새가 올라와요.",
        "냄새가 좀 고약해요.",
        "쓰렁한 내가 나요.",
        "타는 냄새 같기도 해요.",
    ),
    "intensity_change": (
        "처음보다는 좀 약해졌어요.",
        "점점 더 심해져요. 갈수록 못 참겠어요.",
        "그냥 비슷해요. 큰 차이는 없고요.",
        "밤만 되면 확 심해져요.",
    ),
    "duration": (
        "오늘부터인지 예전부터인지 잘 모르겠어요.",
        "며칠째 계속 이래요.",
        "한참 됐어요.",
        "오늘 아침부터 그래요.",
    ),
    "cause_guess": (
        "어디서 나는지 잘 모르겠어요.",
        "공장 때문인지는 잘 모르겠어요.",
        "특정 시설은 잘 모르겠어요.",
    ),
}

_EVASIVE_CITIZEN_REPLIES: Dict[str, Tuple[str, ...]] = {
    "location": (
        "잘 모르겠어요.",
        "대략 이 근처예요.",
        "정확한 주소는 잘 모르겠어요.",
    ),
    "odor_type": (
        "잘 모르겠어요, 그냥 역한 냄새 같아요.",
        "딱 집어말하긴 어려운데 고약해요.",
        "쓰레기인지 화학 냄새인지 모르겠어요.",
    ),
    "intensity_change": (
        "잘 모르겠어요.",
        "그냥 비슷해요.",
        "밤에 좀 더 심하긴 해요.",
    ),
    "duration": (
        "얼마나 됐는지 잘 모르겠어요.",
        "며칠은 된 것 같은데 정확히는 몰라요.",
        "오늘부터인지 예전부터인지 모르겠어요.",
    ),
    "cause_guess": (
        "모르겠어요.",
        "어디서 나는지 잘 모르겠어요.",
        "공장 때문인지는 잘 모르겠어요.",
    ),
}

_COLLECT_PROB_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%?")

REGIONS_FOR_ODOR = ("경상", "전라", "제주", "충청", "강원")

# 권역별 시·군 (매 시도마다 rng.choice — 고정 순서 아님)
REGION_CITIES: Dict[str, List[str]] = {
    "경상": ["포항시", "구미시", "울산", "경주시", "창원시", "김해시", "거제시"],
    "전라": ["여수시", "목포시", "순천시", "광주", "군산시", "광양시"],
    "제주": ["제주시", "서귀포시"],
    "충청": ["천안시", "아산시", "청주시", "대전", "보령시"],
    "강원": ["원주시", "강릉시", "춘천시", "속초시", "삼척시"],
}

# 지역별 대표 거주/민원 지역 (방언 생성 시 맥락)
REGION_CITY_HINT = {
    "경상": "포항시·구미시·울산 등 경상권",
    "전라": "여수시·목포시·광주 등 전라권",
    "제주": "제주시·서귀포시",
    "충청": "대전·천안·청주 등 충청권",
    "강원": "강릉·원주·춘천 등 강원권",
}

# pools.locations 항목을 권역별로 필터할 때 쓰는 키워드
_LOCATION_REGION_HINTS: Dict[str, Tuple[str, ...]] = {
    "경상": ("포항", "구미", "울산", "경주", "창원", "김해", "오천", "우방", "송도", "영일", "부영"),
    "전라": ("여수", "목포", "순천", "광주", "군산", "광양", "여천"),
    "제주": ("제주", "서귀", "애월", "노형"),
    "충청": ("천안", "아산", "청주", "대전", "보령", "둔산", "불당"),
    "강원": ("원주", "강릉", "춘천", "속초", "삼척", "태장"),
}

_CAUSE_SOURCE_KEYWORD_RE = re.compile(
    r"(공단|산업단지|공장|처리장|하수|축사|양돈|매립장|소각|정화조|폐수|제철|항만)"
)
_CAUSE_NON_SOURCE_RE = re.compile(
    r"(아파트|오피스텔|메가박스|학교|주민센터|시장|상가|마트|병원|역|터미널)"
)
_REGIONAL_CAUSE_CANDIDATES: Dict[str, Tuple[str, ...]] = {
    "경상": ("철강공단", "국가산업단지", "폐수처리장"),
    "전라": ("국가산업단지", "제철소 인근 공단", "항만 수산물처리장"),
    "제주": ("양돈농가 밀집지역", "하수처리장", "수산물 처리시설"),
    "충청": ("산업단지 화학공장", "폐기물 처리시설", "하수처리장"),
    "강원": ("축사 밀집지역", "분뇨 처리시설", "시멘트 공장 인근"),
}


def _coerce_rng(rng: Optional[Any] = None) -> random.Random:
    """random.Random 인스턴스만 사용 (모듈 전달 시 새 RNG)."""
    if isinstance(rng, random.Random):
        return rng
    return random.Random()


def _normalize_odor_region(region: str) -> str:
    r = (region or "").strip()
    if r in REGIONS_FOR_ODOR:
        return r
    for key in REGIONS_FOR_ODOR:
        if key in r:
            return key
    return "경상"


def sample_regional_city(
    region: str, rng: Optional[random.Random] = None
) -> str:
    """증강 권역마다 시·군을 무작위 선택 (매번 동일 도시 고정 아님)."""
    rng = _coerce_rng(rng)
    key = _normalize_odor_region(region)
    cities = REGION_CITIES.get(key, REGION_CITIES["경상"])
    return rng.choice(cities)


# ── 전국 지명 마스터에서 권역별 실제 민원 위치 추출 (포항 고정 풀 대체) ──
_TOPONYM_CSV = _CONS_DIR / "지역별_지명_지역_도로명주소_통합_work.csv"
_TOPONYM_PER_REGION_CAP = max(200, int(os.environ.get("ODOR_LOC_PER_REGION_CAP", "2000")))
_REGION_LOC_PAT: Dict[str, "re.Pattern[str]"] = {
    # "안동"에 부정 후읽기(?<!천) — "천안동남구"(충남 천안) 오염 방지.
    # "구미"에 부정 전방탐색(?!동) — "동해시 구미동"(강원) 오염 방지(구미시 표기엔 "구미동" 없음, 확인함).
    "경상": re.compile(r"경상|대구|울산|부산|포항|구미(?!동)|경주|창원|김해|거제|(?<!천)안동|김천"),
    "전라": re.compile(r"전라|광주|전주|여수|순천|목포|광양|나주|익산"),
    "제주": re.compile(r"제주|서귀"),
    "충청": re.compile(r"충청|대전|세종|천안|아산|공주|청주|충주"),
    "강원": re.compile(r"강원|춘천|원주|강릉|속초|삼척|동해|태백"),
}
# 경기·서울은 5개 권역 밖 — "위치한 지역" 컬럼이 시·군명만 담아 부분일치라
# 예: "경기도 광주시"의 "광주"가 전라 패턴("광주")에 오염되는 걸 막는다.
_OUT_OF_SCOPE_LOC_RE = re.compile(r"경기|서울")
# 민원 위치로 자연스러운 카테고리(아파트·주거·시설). 너무 잡다한 기업명은 제외.
_LOC_NAME_OK = re.compile(r"(아파트|마을|단지|타운|빌라|힐스테이트|푸르지오|자이|래미안|아이파크)")
# 주거지 부분매칭 오탐 차단(버스노선·금고·도서관·학교 등 — '마을/아파트' 글자만 겹침)
_LOC_NAME_BAD = re.compile(
    r"(버스|정류장|노선|환승|[:→]|금고|도서관|학교|병원|의원|약국|센터|상가|관리사무소|"
    r"교회|성당|마트|편의점|주유소|휴게소|연구소|협회|공단|공장|시청|구청|주민센터|"
    r"우체국|은행|농협|수협|지점|분소|사무소|체육관|복지관|회관|경로당|"
    # 음식점·요식업(예: '굴마을굴국밥' — '마을' 글자만 겹치는 식당)은 민원 위치 부적합
    r"식당|국밥|국수|냉면|곱창|족발|보쌈|갈비|구이|굽는|횟집|초밥|치킨|피자|버거|"
    r"분식|뷔페|주점|포차|호프|카페|커피|베이커리|제과|정육|반찬|감자탕|백반|백숙)"
)
# 악취 원인시설 키워드(처리장·축산·화학·소각·매립·산업단지 등) / 비-시설 제외
_CAUSE_SRC = re.compile(
    r"(폐수처리|하수처리|수처리|처리장|소각장|소각|매립장|매립|축산|양돈|양계|도축|분뇨|퇴비|"
    r"비료|사료|제철|제강|화학|석유화학|정유|발전소|화력|열병합|시멘트|제지|염색|도금|주물|"
    r"산업단지|국가산단|일반산단|농공단지|환경자원|자원순환|재활용)"
)
_CAUSE_BAD = re.compile(
    r"(협회|복지|장애인|연합회|진흥회|교회|학교|어린이집|유치원|병원|의원|약국|마트|편의점|"
    r"학원|정비|중개|부동산|식당|카페|미용|성당|교육|문화|체육|관리사무소|아파트|사택)"
)


# ── 지명 키워드 정제 ─────────────────────────────────────────────────
# 비주거 상호(매장·모텔·회사)는 위치 키워드로 부적합 → 풀에서 배제.
_PLACE_BIZ_RE = re.compile(r"(모텔|여관|다방|클럽|CLUB|제작소|공작소|백화점|주유소)")
# 상호형 괄호주석 (주)/(유)/(영)/(사) 은 회사 → 배제.
_PLACE_CORP_PAREN_RE = re.compile(r"\((주|유|영|사)\)")
# 꼬리 노이즈: 괄호주석·입구/정문/후문 등(진짜 아파트명이라 접미만 제거).
_PLACE_TAIL_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")
# 게이트/주차장/시설 단어부터 문자열 끝까지 제거("…아파트 지하주차장 1층",
# "…입구1", "…아파트 전기차충전소", "…아파트상가" 등 꼬리 서술 통째로).
_PLACE_TAIL_GATE_RE = re.compile(
    r"\s*(지하주차장|입출구|출입구|입구|정문|후문|대피소|전기차충전소|충전소|상가).*$"
)
# 교차로·네거리 등은 도로 교차점(주거 아님) → place 배제.
_PLACE_ROAD_RE = re.compile(r"(교차로|네거리|사거리|삼거리|오거리|로터리)")
# DB 이름 앞에 공백으로 박힌 시/군/구 접두어("양양군 …", "광양 중마동…"의 시·군·구)
# → 제거. 붙어있는 동(중마동) 이름은 시/군/구가 아니라 보존됨.
_PLACE_LEAD_CITY_RE = re.compile(r"^[가-힣]{1,3}(시|군|구)\s+")


def _clean_place_name(name: str) -> str:
    """DB 원본 지명 → 위치 키워드용 정제. 비주거 상호면 빈 문자열(배제),
    아니면 꼬리 노이즈(괄호주석·입구/정문/후문)를 벗긴 이름."""
    n = (name or "").strip()
    if not n:
        return ""
    if _PLACE_BIZ_RE.search(n) or _PLACE_CORP_PAREN_RE.search(n) or _PLACE_ROAD_RE.search(n):
        return ""
    if n.startswith("("):          # (업타운클럽)…, (주)광성자이 등 상호 표기
        return ""
    if n.endswith("점"):           # CU…타운점·빽다방…점 등 매장 지점
        return ""
    n = _PLACE_LEAD_CITY_RE.sub("", n).strip()   # 앞 시/군/구 접두어 제거
    prev = None
    while prev != n:               # 꼬리 괄호·입구/정문 반복 제거
        prev = n
        n = _PLACE_TAIL_PAREN_RE.sub("", n).strip()
        n = _PLACE_TAIL_GATE_RE.sub("", n).strip()
    # 꼬리 제거로 뼈대만 남은 무의미 지명("단지" 등)은 배제.
    if len(n) < 3:
        return ""
    return n


_METRO_SUFFIX_RE = re.compile(r"(광역시|특별시)$")
# 광역시·특별자치시는 그 자체가 단일 도시 → "대전광역시"·"세종특별자치시"에서
# "대전"·"세종"을 도시로 인정(도/특별자치도는 시가 모호하므로 제외).
_METRO_CITY_RE = re.compile(r"^([가-힣]{2})(?:광역시|특별시|특별자치시)$")


def _extract_city_from_loc(loc: str) -> str:
    """'위치한 지역' 컬럼에서 실제 소속 도시 추출. 우선 시·군·구, 없으면
    광역시·특별자치시 자체(대전·세종 등). 도(道)만 있으면 시가 모호하므로 빈값."""
    toks = (loc or "").split()
    for tok in toks:
        if _METRO_SUFFIX_RE.search(tok) or tok.endswith("특별자치시"):
            continue
        # {1,10}: "남구"·"북구"처럼 1글자+구 짧은 구명도 잡아야 함(대구·부산·울산 등 흔함)
        if re.match(r"^[가-힣]{1,10}(?:시|군|구)$", tok):
            return tok
    # 시·군·구가 없으면 광역시/특별자치시 자체를 도시로("대전광역시"→"대전")
    for tok in toks:
        m = _METRO_CITY_RE.match(tok)
        if m:
            return m.group(1)
    return ""


@lru_cache(maxsize=1)
def _scan_region_pools() -> Dict[str, Any]:
    """권역별 {place: 주거/장소, cause: 악취원시설, place_city: 이름→실제도시} 풀 로드.

    배포판은 원본 118MB 지명 CSV 대신 data/region_pools.json(미리 계산본)을 읽는다.
    미리 계산 로직(정제·권역판별·도시추출)은 이 파일의 _clean_place_name /
    _extract_city_from_loc / tools/build_pools.py 참고. 결과는 동일.
    """
    with open(_REGION_POOLS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "place": {k: tuple(v) for k, v in (data.get("place") or {}).items()},
        "cause": {k: tuple(v) for k, v in (data.get("cause") or {}).items()},
        "place_city": {k: dict(v) for k, v in (data.get("place_city") or {}).items()},
        "cause_city": {k: dict(v) for k, v in (data.get("cause_city") or {}).items()},
    }


def _region_place_pools() -> Dict[str, Tuple[str, ...]]:
    return _scan_region_pools()["place"]


def _region_cause_pools() -> Dict[str, Tuple[str, ...]]:
    return _scan_region_pools()["cause"]


def _region_place_city_map(region: str) -> Dict[str, str]:
    """해당 권역의 place 이름 → 실제 소속 시·군(스캔 시점 기록)."""
    return _scan_region_pools()["place_city"].get(region) or {}


def _region_cause_city_map(region: str) -> Dict[str, str]:
    """해당 권역의 원인추정 시설 이름 → 실제 소속 시·군(스캔 시점 기록)."""
    return _scan_region_pools()["cause_city"].get(region) or {}


_CAUSE_PHRASES = (
    "{} 쪽이 의심돼요",
    "{}에서 나는 것 같아요",
    "{} 때문인 것 같아요",
    "근처 {}이 의심됩니다",
)


def _pool_locations_for_region(
    region: str, pools: Dict[str, List[str]]
) -> List[str]:
    # 1M 지명 마스터에서 해당 권역 실제 주거/장소명 우선 사용(포항 고정값 탈피)
    key0 = _normalize_odor_region(region) if region else ""
    if key0:
        real = _region_place_pools().get(key0) or ()
        if real:
            return list(real)
    locs = list(pools.get("locations") or [])
    if not locs:
        return locs
    key = _normalize_odor_region(region)
    hints = _LOCATION_REGION_HINTS.get(key, ())
    if not hints:
        return locs
    matched = [loc for loc in locs if any(h in loc for h in hints)]
    if matched:
        return matched
    cities = REGION_CITIES.get(key, ())
    city_matched = [
        loc
        for loc in locs
        if any(c.replace("시", "") in loc or c in loc for c in cities)
    ]
    return city_matched if city_matched else locs


def scenario_keyword_plan(scenario: Dict[str, Any]) -> Dict[str, str]:
    """선샘플 키워드(대화·슬롯 GT와 분리된 사실 계획)."""
    kp = scenario.get("keyword_plan")
    if isinstance(kp, dict) and kp:
        return {k: str(v or "").strip() for k, v in kp.items() if k in META_FIELDS}
    meta = scenario.get("meta") or {}
    return {f: str(meta.get(f) or "").strip() for f in META_FIELDS}


def _is_plausible_duration_keyword(text: str) -> bool:
    """악취 지속이 아닌 설비·진동 문장은 duration 풀에서 제외."""
    t = (text or "").strip()
    if not t:
        return False
    if re.search(r"진동", t) and not re.search(
        r"(냄새|악취|지속|매일|며칠|주|달|개월|아침|밤|새벽|시간|부터|이후)",
        t,
    ):
        return False
    return True


def _paraphrase_keyword_reply(
    field: str, keyword: str, rng: random.Random
) -> str:
    """선샘플 키워드를 구어로 바꾸되 GT 원문을 그대로 붙여넣지 않음."""
    kw = (keyword or "").strip()
    if not kw:
        return rng.choice(_CITIZEN_CONFIRMED_REPLIES.get(field, ("네, 그런 것 같아요.",)))

    if field == "odor_type":
        if re.search(r"쇳|철|금속", kw):
            opts = (
                "쇳물 탄 듯한 냄새가 나요.",
                "금속 탄내 비슷한 냄새예요.",
                "쇳가루 탄 것 같은 냄새가 올라와요.",
            )
        elif re.search(r"간장|된장|젓", kw):
            opts = (
                "간장 졸인 듯한 냄새가 나요.",
                "장 담근 냄새 같아요.",
                "짠내 섞인 냄새예요.",
            )
        elif re.search(r"쓰레|분뇨|오물", kw):
            opts = ("쓰레기 썩은 냄새 같아요.", "분뇨 냄새 비슷해요.")
        elif re.search(r"매캐|타는|화학", kw):
            opts = ("매캐한 냄새가 나요.", "타는 냄새 같기도 해요.")
        else:
            opts = (
                "역한 냄새가 나요.",
                "고약한 냄새가 올라와요.",
                "타는 냄새 같기도 해요.",
            )
    elif field == "intensity_change":
        if re.search(r"옅|약|줄", kw) and re.search(r"진|심|강", kw):
            opts = (
                "가끔 옅어졌다가 또 진해져요.",
                "약해졌다가 다시 심해지기도 해요.",
            )
        elif re.search(r"심|진|강", kw):
            opts = ("점점 더 심해져요.", "밤만 되면 확 심해져요. 못 살겠어요.")
        elif re.search(r"옅|약|줄", kw):
            opts = ("처음보다는 좀 약해졌어요.", "예전보다는 덜해요.")
        else:
            opts = ("그냥 비슷해요.", "밤에 좀 더 심하긴 해요.")
    elif field == "duration":
        if re.search(r"개월|수개월", kw):
            opts = ("몇 달째 계속 이래요.", "한참 됐어요.")
        elif re.search(r"새벽|밤|야간", kw):
            opts = ("새벽에 특히 심해요.", "밤에만 그래요.")
        elif re.search(r"오늘|아침", kw):
            opts = ("오늘 아침부터 그래요.", "오늘부터 이러네요.")
        else:
            opts = ("며칠째 계속 이래요.", "한참 됐어요.")
    elif field == "cause_guess":
        if re.search(r"하수|정화|오수", kw):
            opts = ("하수구 쪽인 것 같아요.", "하수 쪽에서 나는 것 같아요.")
        elif re.search(r"공장|공단|처리", kw):
            opts = ("공장 쪽인 것 같아요.", "근처 시설 때문인 것 같아요.")
        else:
            opts = ("그쪽에서 나는 것 같아요.", "근처 시설 때문인 것 같아요.")
    else:
        opts = (f"{kw} 쪽이에요.", f"{kw} 근처예요.")

    phrase = rng.choice(opts)
    return phrase if phrase[-1] in ".!?…" else phrase + "."


def _normalize_cause_guess_for_region(
    cause_guess: str,
    region_key: str,
    *,
    odor_type: str = "",
    seed: int = 0,
) -> str:
    """
    원인추정지역을 '악취 발생원으로 자연스러운 시설/권역' 중심으로 정규화.
    - 이미 공단/처리장/축사 등 발생원 키워드면 유지
    - 생활 시설(아파트/극장/학교 등) 중심 표현이면 권역 후보로 보정
    """
    val = (cause_guess or "").strip()
    if not val:
        return ""
    if _CAUSE_SOURCE_KEYWORD_RE.search(val) and not _CAUSE_NON_SOURCE_RE.search(val):
        return val

    cands = list(_REGIONAL_CAUSE_CANDIDATES.get(region_key, _REGIONAL_CAUSE_CANDIDATES["경상"]))
    low_odor = (odor_type or "").strip()
    if re.search(r"(분뇨|암모니아|축사)", low_odor):
        cands = [c for c in cands if ("축사" in c or "양돈" in c or "처리" in c)] + cands
    elif re.search(r"(하수|오니|정화조)", low_odor):
        cands = [c for c in cands if ("하수" in c or "처리" in c)] + cands
    elif re.search(r"(매캐|탄내|화학|용제|기름|쇳물)", low_odor):
        cands = [c for c in cands if ("공단" in c or "공장" in c or "제철" in c)] + cands

    uniq: List[str] = []
    seen = set()
    for c in cands:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    rng = random.Random((seed or 0) + sum(ord(ch) for ch in (val + region_key + low_odor)))
    return rng.choice(uniq or [val])


def _load_data() -> Dict[str, Any]:
    if not _DATA_PATH.is_file():
        return {"consultation_steps": [], "personalities": [], "pohang": [], "templates": [], "pools": {}}
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_keyword_config(*, reload: bool = False) -> Dict[str, Any]:
    """data/odor_keyword_config.json — 슬롯 확률·풀 가중치·위치 alias."""
    global _KEYWORD_CONFIG_CACHE
    if _KEYWORD_CONFIG_CACHE is not None and not reload:
        return _KEYWORD_CONFIG_CACHE
    if not _KEYWORD_CONFIG_PATH.is_file():
        _KEYWORD_CONFIG_CACHE = {}
        return _KEYWORD_CONFIG_CACHE
    try:
        with open(_KEYWORD_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _KEYWORD_CONFIG_CACHE = data if isinstance(data, dict) else {}
    except Exception:
        _KEYWORD_CONFIG_CACHE = {}
    return _KEYWORD_CONFIG_CACHE


def _pool_sampling_cfg(pool_key: str) -> Dict[str, Any]:
    cfg = load_keyword_config()
    pools_cfg = cfg.get("pool_sampling") or {}
    entry = pools_cfg.get(pool_key) or {}
    return entry if isinstance(entry, dict) else {}


def _pick_from_pool(
    pool: List[str], pool_key: str, rng: random.Random
) -> str:
    sampling = _pool_sampling_cfg(pool_key)
    fallback = list(sampling.get("fallback") or [])
    items = [str(x).strip() for x in (pool or []) if str(x).strip()]
    if not items:
        items = [str(x).strip() for x in fallback if str(x).strip()]
    if not items:
        return ""
    strategy = (sampling.get("strategy") or "uniform").strip().lower()
    weights_map = sampling.get("weights") or {}
    if strategy == "weighted" and isinstance(weights_map, dict) and weights_map:
        default_w = float(weights_map.get("*", 1.0))
        weights = [float(weights_map.get(item, default_w)) for item in items]
        return rng.choices(items, weights=weights, k=1)[0]
    return rng.choice(items)


def _load_keyword_values_from_json(
    file_path: Path, field_candidates: Tuple[str, ...]
) -> List[str]:
    if not file_path.is_file():
        return []
    try:
        with open(file_path, encoding="utf-8") as f:
            arr = json.load(f)
    except Exception:
        return []
    if not isinstance(arr, list):
        return []
    out: List[str] = []
    for row in arr:
        if not isinstance(row, dict):
            continue
        val = ""
        for key in field_candidates:
            v = (row.get(key) or "").strip() if isinstance(row.get(key), str) else ""
            if v:
                val = v
                break
        if not val:
            continue
        if val not in out:
            out.append(val)
    return out


def _merge_external_keyword_pools(pools: Dict[str, List[str]]) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {k: list(v or []) for k, v in (pools or {}).items()}
    fields = {
        "odor_types": ("odor_keywords", "normalized_odor", "odor_type"),
        "intensity_changes": ("intensity_keywords", "relative_intensity", "intensity_change"),
        "durations": ("duration_keywords", "estimated_hours", "duration"),
    }
    for pool_key, candidate_keys in fields.items():
        # 냄새/강도/지속은 data_consolidated 파일 단독 사용(시드 JSON base 병합 안 함)
        # → "파일에 없는 내용" 혼입 방지. 파일 없으면 _pick_from_pool 폴백.
        current: List[str] = []
        seen: set = set()
        # 환경변수로 사용자 로컬 파일 경로를 덮어쓸 수 있도록 지원
        env_override = (os.environ.get(f"ODOR_{pool_key.upper()}_JSON") or "").strip()
        candidates = [Path(env_override)] if env_override else _KEYWORD_FILE_CANDIDATES.get(pool_key, [])
        for p in candidates:
            for item in _load_keyword_values_from_json(p, candidate_keys):
                if pool_key == "durations" and not _is_plausible_duration_keyword(item):
                    continue
                if item not in seen:
                    seen.add(item)
                    current.append(item)
        merged[pool_key] = current
    return merged


def _alias_location(location: str, rng: random.Random) -> str:
    loc = (location or "").strip()
    if not loc:
        return loc
    alias_cfg = load_keyword_config().get("location_alias") or {}
    city_drop_prob = float(alias_cfg.get("city_drop_prob", 0.28))
    suffix_prob = float(alias_cfg.get("suffix_prob", 0.35))
    suffixes = alias_cfg.get("suffixes") or [" 근처", " 앞", " 인근", " 맞은편"]
    if rng.random() < city_drop_prob:
        loc = re.sub(r"([가-힣]{2,10})시", r"\1", loc)
    if rng.random() < suffix_prob and not re.search(
        r"(근처|인근|앞|옆|맞은편)$", loc
    ):
        loc += rng.choice(tuple(suffixes))
    return re.sub(r"\s+", " ", loc).strip()


def _sample_keyword_meta(
    pools: Dict[str, List[str]], region_key: str, rng: random.Random
) -> Dict[str, str]:
    regional_locs = _pool_locations_for_region(region_key, pools)
    loc_pool = regional_locs or pools.get("locations") or ["아파트 근처"]
    city = ""
    if region_key:
        # 예외 0 보장: 실제 소속 도시를 아는 건물만 후보로 남긴다. 도시를 모르는
        # 건물(원본 loc이 시·군 없이 도(道)만 있는 경우)은 무작위 도시를 붙일 수밖에
        # 없어 "천안 둔산주공"(둔산은 대전)처럼 인사말-지명 불일치를 만든다.
        cmap = _region_place_city_map(region_key)
        known = [x for x in loc_pool if x in cmap]
        loc_raw = _pick_from_pool(known, "locations", rng) if known else ""
        if not loc_raw:
            loc_raw = _pick_from_pool(loc_pool, "locations", rng) or "아파트 근처"
        # 지명 키워드에는 도시/지역구 접두어를 붙이지 않는다 — DB 원본 건물명
        # 그대로 사용("중마동진아리채1차아파트"이지 "광양 중마동진아리채1차아파트"
        # 아님). 도시는 인사말용 location_city로만 따로 넘긴다.
        city = cmap.get(loc_raw) or sample_regional_city(region_key, rng)
    else:
        loc_raw = _pick_from_pool(loc_pool, "locations", rng) or "아파트 근처"
    sampled = {
        "location": _alias_location(loc_raw, rng),
        # 상담원 인사말("OO시 기후대기과")이 위치와 같은 실제 도시를 쓰도록
        # run.py가 이 값을 그대로 location_address로 채택한다(각자 독립적으로
        # 다시 추측하면 "춘천시 기후대기과"인데 실제 위치는 철원군인 불일치 발생).
        "location_city": city,
        "odor_type": _pick_from_pool(
            pools.get("odor_types") or [], "odor_types", rng
        ),
        "intensity_change": _pick_from_pool(
            pools.get("intensity_changes") or [], "intensity_changes", rng
        ),
        "duration": _pick_from_pool(
            pools.get("durations") or [], "durations", rng
        ),
        "cause_guess": _pick_from_pool(
            pools.get("cause_guesses") or [], "cause_guesses", rng
        ),
    }
    # 원인: 1M 권역 악취원시설에서 우선 추출(포항 고정 'cause_guesses' 탈피)
    # 민원인 위치(city)와 같은 시·군 시설을 우선 사용 — 첫 문장 관할 지역과
    # 원인추정 지역이 다른 시/군으로 튀는 것을 방지(place_city와 동일 패턴).
    if region_key:
        cause_pool = _region_cause_pools().get(region_key) or ()
        if cause_pool:
            cause_cmap = _region_cause_city_map(region_key)
            same_city = [c for c in cause_pool if cause_cmap.get(c) == city] if city else []
            fac = _pick_from_pool(same_city or list(cause_pool), "cause_facilities", rng)
            if fac:
                sampled["cause_guess"] = rng.choice(_CAUSE_PHRASES).format(fac)
    for key, fallback_key in (
        ("odor_type", "odor_types"),
        ("intensity_change", "intensity_changes"),
        ("duration", "durations"),
        ("cause_guess", "cause_guesses"),
    ):
        if not (sampled.get(key) or "").strip():
            fb = _pool_sampling_cfg(fallback_key).get("fallback") or []
            if fb:
                sampled[key] = str(rng.choice(fb)).strip()
    try:
        from place_asr_variants import maybe_asr_place_variant
    except ImportError:
        from agent.place_asr_variants import maybe_asr_place_variant
    asr_cfg = load_keyword_config().get("place_asr") or {}
    canon, spoken = maybe_asr_place_variant(
        sampled.get("location") or "", rng, asr_cfg
    )
    sampled["location"] = canon
    if spoken and spoken != canon:
        sampled["location_asr"] = spoken
    return sampled


def get_consultation_steps() -> List[Dict[str, Any]]:
    return _load_data().get("consultation_steps") or []


def get_personalities() -> List[Dict[str, Any]]:
    return _load_data().get("personalities") or []


def list_pohang_scenarios() -> List[Dict[str, Any]]:
    return _load_data().get("pohang") or []


def list_template_scenarios() -> List[Dict[str, Any]]:
    return _load_data().get("templates") or []


def turns_to_dialogue(turns: List[Turn]) -> str:
    """상담원·민원인 턴을 한 줄 대화문으로 (역할 라벨 없음, 턴 경계 `. `)."""
    try:
        from dialogue_boundaries import join_turn_texts
    except ImportError:
        from agent.dialogue_boundaries import join_turn_texts
    parts: List[str] = []
    for _role, text in turns:
        t = (text or "").strip()
        if t:
            parts.append(t)
    return join_turn_texts(parts)


def parse_collect_prob(prob: str) -> float:
    """'90%' / '50' → 0.0~1.0"""
    if not prob:
        return 1.0
    m = _COLLECT_PROB_RE.search(str(prob).strip())
    if not m:
        return 1.0
    v = float(m.group(1))
    return min(1.0, max(0.0, v / 100.0 if v > 1.0 else v))


def roll_collected_fields(rng: random.Random) -> set:
    """슬롯 GT에 넣을 주제 (collect_prob: 위치·냄새 90%, 강도·지속 50%, 원인 10%)."""
    return roll_slot_fields(rng)


def roll_slot_fields(rng: random.Random) -> set:
    """민원인이 실제로 말해 슬롯에 남길 주제."""
    return roll_sparse_meta_fields(rng)


def roll_counselor_question_topics(
    rng: random.Random, slot_fields: Optional[set] = None
) -> set:
    """(레거시/테스트) 상황별 부분 주제 롤 — `prepare_scenario_for_generation`는 공식 매뉴얼대로 전체 질문을 사용."""
    rng = _coerce_rng(rng)
    slots = set(slot_fields or ())
    topics = set(slots)
    for field in META_FIELDS:
        if field in topics:
            continue
        if rng.random() < 0.4:
            topics.add(field)
    if not topics:
        topics.add(rng.choice(list(META_FIELDS)))
    if len(topics) < 2 and rng.random() < 0.55:
        extra = rng.choice([f for f in META_FIELDS if f not in topics])
        topics.add(extra)
    return topics


def roll_sparse_meta_fields(rng: random.Random) -> set:
    """collect_prob에 따라 슬롯 GT 후보 주제 (odor_keyword_config 우선)."""
    probs = load_keyword_config().get("slot_collect_prob") or {}
    if isinstance(probs, dict) and probs:
        collected: set = set()
        for field in META_FIELDS:
            p = probs.get(field)
            if p is None:
                continue
            if rng.random() < float(p):
                collected.add(field)
        return collected
    collected = set()
    for step in get_consultation_steps():
        field = step.get("meta_field")
        if not field:
            continue
        if rng.random() < parse_collect_prob(step.get("collect_prob", "100%")):
            collected.add(field)
    return collected


def apply_collection_to_meta(meta: Dict[str, Any], collected: set) -> Dict[str, Any]:
    """미수집 필드는 빈 문자열로 — 데이터셋 칸도 비워 둠."""
    out = dict(meta or {})
    for field in META_FIELDS:
        if field not in collected:
            out[field] = ""
    return out


def _is_counselor_field_question_text(text: str) -> bool:
    """민원인 진술(공장·시설 언급)과 상담원 질문 구분."""
    t = (text or "").strip()
    if not t:
        return False
    if "?" in t:
        return True
    # 평서문형 정보 요청도 상담원 질문으로 인정(예: "어떤 냄새가 나는지 말씀해 주시면…")
    if re.search(r"말씀해\s*주(?:시면|세요|시겠|십시오)|(?:는지|ㄴ지)\s*(?:말씀|알려)", t):
        return True
    return bool(
        re.search(
            r"(?:습니까|할까요|인가요|있나요|드릴까요|나요|세요|주시겠)\s*\.?\s*$",
            t,
        )
    )


def primary_counselor_question_for_field(field: str) -> str:
    """COMPACT에 질문이 2개 이상이어도 대화에는 1문장만."""
    q = (COMPACT_COUNSELOR_QUESTIONS.get(field) or "").strip()
    if not q:
        return q
    if q.count("?") <= 1:
        return q if q.endswith(("?", ".", "!", "…")) else q + "?"
    first = q.split("?", 1)[0].strip()
    return first + "?" if first else q


def _counselor_question_field(text: str) -> Optional[str]:
    """상담원 확인 질문 → 메타 필드 (3.1·3.7은 None)."""
    t = (text or "").strip()
    if not t:
        return None
    if not _is_counselor_field_question_text(t):
        return None
    if re.search(r"감사합니다|조치하겠|신속히\s*확인", t) and re.search(r"알겠", t):
        return None
    if re.search(r"어떤\s*도움|악취\s*대응팀", t) and re.search(r"안녕", t):
        return None
    if re.search(
        r"어떤\s*냄새|냄새.*(종류|구체|어떤)|쓰레기.*화학|화학.*하수|역한\s*냄새",
        t,
    ):
        return "odor_type"
    if re.search(r"강도|변동|변화|같은가요|심해졌|시간에\s*따라", t):
        return "intensity_change"
    if re.search(r"얼마나\s*오래|지속|아침부터\s*났|전부터\s*계속", t):
        return "duration"
    if re.search(
        r"공장|시설|의심|어디서\s*나는|특정\s*방향|원인|나는\s*것\s*같", t
    ):
        return "cause_guess"
    if re.search(r"위치|어디신|주소|어느\s*지역|랜드마크|나는\s*위치", t):
        return "location"
    return None


def compact_counselor_question_text(text: str) -> str:
    """상담원 질문·마무리를 짧은 표준어로 (또는/예시 나열 제거)."""
    t = (text or "").strip()
    if not t:
        return t
    field = _counselor_question_field(t)
    if field and field in COMPACT_COUNSELOR_QUESTIONS:
        return primary_counselor_question_for_field(field)
    if re.search(r"알겠습니다|조치하겠|신속히\s*확인", t) and re.search(
        r"감사|연락\s*주", t
    ):
        return COMPACT_CLOSING_COUNSELOR
    for sep in _OFFICIAL_QUESTION_BLOAT_SEP:
        if sep in t:
            t = t.split(sep, 1)[0].strip()
    return t


def _counselor_question_text_for_field(field: str) -> str:
    if field in COMPACT_COUNSELOR_QUESTIONS:
        return primary_counselor_question_for_field(field)
    for step in get_consultation_steps():
        if step.get("meta_field") == field:
            return compact_counselor_question_text(step.get("question") or "")
    return ""


def build_standard_anchor_dialogue(
    scenario: Dict[str, Any], region: str
) -> str:
    """상담원·민원인 턴을 표준어 한 줄로 — 시드 구조 앵커(복원·검증용)."""
    try:
        from regional_localization import localize_official_clause
    except ImportError:
        from agent.regional_localization import localize_official_clause
    region_key = _normalize_odor_region(region)
    parts: List[str] = []
    turns = dedupe_counselor_turns_by_field(list(scenario.get("turns") or []))
    for role, text in turns:
        t = (text or "").strip()
        if not t:
            continue
        if role == "상담원":
            t = compact_counselor_question_text(t)
            t = localize_official_clause(t, region_key)
        parts.append(t)
    try:
        from dialogue_boundaries import join_turn_texts, normalize_consultation_dialogue
    except ImportError:
        from agent.dialogue_boundaries import join_turn_texts, normalize_consultation_dialogue
    return normalize_consultation_dialogue(join_turn_texts(parts))


def build_standard_reference_dialogue(
    scenario: Dict[str, Any], region: str
) -> str:
    """시드·증강 후 상담원 구간 복원용 표준어 참조 한 줄."""
    try:
        from regional_localization import localize_for_region, localize_official_clause
    except ImportError:
        from agent.regional_localization import localize_for_region, localize_official_clause
    region_key = _normalize_odor_region(region)
    parts: List[str] = []
    for role, text in scenario.get("turns") or []:
        t = (text or "").strip()
        if not t:
            continue
        if role == "상담원":
            t = compact_counselor_question_text(t)
            t = localize_official_clause(t, region_key)
        else:
            seed_i = int((scenario.get("meta") or {}).get("rule_sample_seed") or 0) or None
            t = localize_for_region(t, region_key, official=False, seed=seed_i)
        parts.append(t)
    try:
        from dialogue_boundaries import join_turn_texts
    except ImportError:
        from agent.dialogue_boundaries import join_turn_texts
    return join_turn_texts(parts)


def _default_closing_counselor_turn() -> Turn:
    for step in get_consultation_steps():
        if step.get("id") == "3.7":
            q = (step.get("question") or "").strip()
            if q:
                return ("상담원", q)
    return ("상담원", COMPACT_CLOSING_COUNSELOR)


def _fields_covered_in_turns(turns: List[Turn]) -> set:
    covered: set = set()
    for role, text in turns:
        if role == "상담원":
            field = _counselor_question_field(text)
            if field:
                covered.add(field)
    return covered


def _find_closing_turn_index(turns: List[Turn]) -> int:
    for i, (role, text) in enumerate(turns):
        if role != "상담원":
            continue
        if re.search(r"알겠습니다|조치하겠|신속히\s*확인", text) and re.search(
            r"감사|연락\s*주", text
        ):
            return i
        if re.search(r"알겠습니다", text) and re.search(r"조치|확인", text):
            return i
    return len(turns)


def _citizen_reply_for_field(
    field: str,
    meta: Dict[str, Any],
    rng: random.Random,
    *,
    slot_fields: Optional[set] = None,
    keyword_plan: Optional[Dict[str, Any]] = None,
) -> str:
    """슬롯 GT에 없는 주제는 회피. 수집 슬롯은 keyword_plan(선샘플) 사실을 구어로 반영."""
    if slot_fields is not None and field not in slot_fields:
        return rng.choice(_EVASIVE_CITIZEN_REPLIES.get(field, ("잘 모르겠어요.",)))
    kp = keyword_plan or {}
    fact = (kp.get(field) or meta.get(field) or "").strip()
    if field == "location":
        try:
            from place_asr_variants import citizen_location_phrase
        except ImportError:
            from agent.place_asr_variants import citizen_location_phrase
        loc_meta = dict(meta)
        if fact and not (loc_meta.get("location") or "").strip():
            loc_meta["location"] = fact
            if kp.get("location_asr"):
                loc_meta["location_asr"] = kp.get("location_asr")
        val = (citizen_location_phrase(loc_meta) or "").strip()
        if not val and fact:
            val = fact
        if val:
            return val if val[-1] in ".!?…" else val + "."
    if fact:
        return _paraphrase_keyword_reply(field, fact, rng)
    phrase = rng.choice(
        _CITIZEN_CONFIRMED_REPLIES.get(field, ("네, 그런 것 같아요.",))
    )
    return phrase if phrase[-1] in ".!?…" else phrase + "."


def rewrite_citizen_turns_for_slot_fields(
    turns: List[Turn],
    meta: Dict[str, Any],
    slot_fields: set,
    rng: random.Random,
    *,
    keyword_plan: Optional[Dict[str, Any]] = None,
) -> List[Turn]:
    """기존 시나리오 턴에 남아 있는 '메타 전체 답'을 슬롯 확률에 맞게 회피/확정 답으로 교체."""
    out: List[Turn] = []
    i = 0
    n = len(turns)
    while i < n:
        role, text = turns[i]
        if (
            role == "상담원"
            and i + 1 < n
            and turns[i + 1][0] == "민원인"
        ):
            field = _counselor_question_field(text)
            if field:
                out.append((role, text))
                out.append(
                    (
                        "민원인",
                        _citizen_reply_for_field(
                            field,
                            meta,
                            rng,
                            slot_fields=slot_fields,
                            keyword_plan=keyword_plan,
                        ),
                    )
                )
                i += 2
                continue
        out.append((role, text))
        i += 1
    return out


def dedupe_counselor_turns_by_field(turns: List[Turn]) -> List[Turn]:
    """동일 주제 상담원 질문 중복 제거(표현만 다른 경우 포함)."""
    seen: set = set()
    out: List[Turn] = []
    i = 0
    n = len(turns)
    while i < n:
        role, text = turns[i]
        if role == "상담원":
            field = _counselor_question_field(text)
            if field and field in seen:
                if i + 1 < n and turns[i + 1][0] == "민원인":
                    i += 2
                else:
                    i += 1
                continue
            if field:
                seen.add(field)
        out.append((role, text))
        i += 1
    return out


def build_slot_gt_preview(scenario: Dict[str, Any]) -> Dict[str, str]:
    """UI·SSE용 슬롯 GT 미리보기(대화 본문과 분리)."""
    meta = scenario.get("meta") or {}
    slots = set(
        scenario.get("slot_fields") or scenario.get("collected_fields") or []
    )
    labels = {
        "location": "위치",
        "odor_type": "냄새종류",
        "intensity_change": "냄새강도변화",
        "duration": "지속시간",
        "cause_guess": "원인추정지역",
    }
    out: Dict[str, str] = {}
    for field in MANDATORY_QUESTION_ORDER:
        col = labels.get(field, field)
        if field not in slots:
            out[col] = ""
            continue
        val = (meta.get(field) or "").strip()
        out[col] = val if val else "NULL"
    return out


def repair_turn_sequence_with_citizen_replies(
    turns: List[Turn],
    meta: Dict[str, Any],
    rng: random.Random,
    *,
    slot_fields: Optional[set] = None,
    keyword_plan: Optional[Dict[str, Any]] = None,
) -> List[Turn]:
    """상담원 질문 연속/빈 민원인 턴 보정 — 상담원Q 뒤에는 반드시 민원인A 1턴."""
    slots = set(slot_fields or META_FIELDS)
    repaired: List[Turn] = []
    n = len(turns)
    for i, (role, text) in enumerate(turns):
        t = (text or "").strip()
        if not t:
            continue
        repaired.append((role, t))
        if role != "상담원":
            continue
        field = _counselor_question_field(t) or "location"
        next_role = turns[i + 1][0] if i + 1 < n else ""
        next_text = (turns[i + 1][1] or "").strip() if i + 1 < n else ""
        # 상담원 다음이 민원인이 아니거나 빈 발화면 즉시 보정 응답을 삽입.
        if next_role != "민원인" or not next_text:
            repaired.append(
                (
                    "민원인",
                    _citizen_reply_for_field(
                        field,
                        meta,
                        rng,
                        slot_fields=slots,
                        keyword_plan=keyword_plan,
                    ),
                )
            )
    return repaired


def ensure_mandatory_counselor_questions(
    turns: List[Turn],
    meta: Optional[Dict[str, Any]] = None,
    rng: Optional[random.Random] = None,
    *,
    collected: Optional[set] = None,
    slot_fields: Optional[set] = None,
    keyword_plan: Optional[Dict[str, Any]] = None,
) -> List[Turn]:
    """상담원 질문 시도(collected) + 슬롯 GT(slot_fields) 분리."""
    rng = _coerce_rng(rng)
    meta = meta or {}
    topics = set(collected if collected is not None else META_FIELDS)
    slots = set(slot_fields if slot_fields is not None else topics)
    if not turns:
        return turns
    closing_idx = _find_closing_turn_index(turns)
    prefix = list(turns[:closing_idx])
    suffix = list(turns[closing_idx:])
    covered = _fields_covered_in_turns(prefix)
    inserts: List[Turn] = []
    for field in MANDATORY_QUESTION_ORDER:
        if field not in topics:
            continue
        if field in covered:
            continue
        q = _counselor_question_text_for_field(field)
        if not q:
            continue
        inserts.append(("상담원", q))
        inserts.append(
            (
                "민원인",
                _citizen_reply_for_field(
                    field, meta, rng, slot_fields=slots, keyword_plan=keyword_plan
                ),
            )
        )
    if not inserts:
        return turns
    out = prefix + inserts
    if suffix:
        return out + suffix
    out.append(_default_closing_counselor_turn())
    return out


def filter_turns_for_collection(turns: List[Turn], collected: set) -> List[Turn]:
    """미수집 단계(3.2~3.6)의 상담원 질문+민원인 답 턴 제거."""
    out: List[Turn] = []
    i = 0
    n = len(turns)
    while i < n:
        role, text = turns[i]
        if role == "상담원":
            field = _counselor_question_field(text)
            if field and field not in collected:
                if i + 1 < n and turns[i + 1][0] == "민원인":
                    i += 2
                    continue
                i += 1
                continue
        out.append(turns[i])
        i += 1
    return out


def prepare_scenario_for_generation(
    scenario: Dict[str, Any], rng: Optional[random.Random] = None
) -> Dict[str, Any]:
    """슬롯 GT(확률) + 상담원 질문 시도(별도) + multi-turn 대화."""
    rng = _coerce_rng(rng)
    sc = dict(scenario)
    if not sc.get("keyword_plan") and sc.get("meta"):
        sc["keyword_plan"] = {
            f: str((sc.get("meta") or {}).get(f) or "").strip() for f in META_FIELDS
        }
    keyword_plan = scenario_keyword_plan(sc)
    asr_cfg = load_keyword_config().get("place_asr") or {}
    try:
        from place_asr_variants import attach_location_asr_to_meta
    except ImportError:
        from agent.place_asr_variants import attach_location_asr_to_meta
    if sc.get("meta"):
        sc["meta"] = attach_location_asr_to_meta(dict(sc["meta"]), rng, asr_cfg)
    slot_fields = roll_slot_fields(rng)
    # 공식 상담 3.2~3.6: 상담원 질문 시도는 매 통화 5주제(표현·순서는 모델이 변주).
    # 슬롯 GT 확률(collect_prob)은 slot_fields·meta 비움으로만 반영.
    question_fields = set(META_FIELDS)
    meta = apply_collection_to_meta(dict(sc.get("meta") or {}), slot_fields)
    turns = [
        (role, compact_counselor_question_text(text) if role == "상담원" else text)
        for role, text in (sc.get("turns") or [])
    ]
    turns = filter_turns_for_collection(turns, question_fields)
    turns = ensure_mandatory_counselor_questions(
        turns,
        meta,
        rng,
        collected=question_fields,
        slot_fields=slot_fields,
        keyword_plan=keyword_plan,
    )
    turns = rewrite_citizen_turns_for_slot_fields(
        turns, meta, slot_fields, rng, keyword_plan=keyword_plan
    )
    turns = repair_turn_sequence_with_citizen_replies(
        turns, meta, rng, slot_fields=slot_fields, keyword_plan=keyword_plan
    )
    turns = dedupe_counselor_turns_by_field(turns)
    sc["meta"] = meta
    sc["keyword_plan"] = dict(keyword_plan)
    sc["turns"] = turns
    sc["collected_fields"] = sorted(slot_fields)
    sc["slot_fields"] = sorted(slot_fields)
    sc["question_fields"] = sorted(question_fields)
    return sc


def _fill_template(template: Dict[str, Any], pools: Dict[str, List[str]], rng: random.Random) -> Dict[str, Any]:
    """플레이스홀더 시나리오에 풀에서 값 채우기."""
    meta = dict(template.get("meta") or {})
    picks = {
        "location": rng.choice(pools.get("locations") or ["아파트 근처"]),
        "odor_type": rng.choice(pools.get("odor_types") or ["매캐한 냄새"]),
        "intensity_change": rng.choice(pools.get("intensity_changes") or ["저녁에 더 심해져요"]),
        "duration": rng.choice(pools.get("durations") or ["오늘 아침부터"]),
        "cause_guess": rng.choice(pools.get("cause_guesses") or ["근처 공장이 의심돼요"]),
    }
    for k, v in picks.items():
        if not meta.get(k):
            meta[k] = v

    turns: List[Turn] = []
    for role, tmpl in template.get("turn_templates") or []:
        line = tmpl
        for key, val in picks.items():
            line = line.replace(f"({key})", val).replace(f"({key} )", val)
        for ph, val in (
            ("(악취 종류)", picks["odor_type"]),
            ("(아파트 이름이나 근처 주소)", picks["location"]),
            ("(냄새 강도 변화)", picks["intensity_change"]),
            ("(지속시간)", picks["duration"]),
            ("(원인 추정지)", picks["cause_guess"]),
            ("(원인 추정지역)", picks["cause_guess"]),
        ):
            line = line.replace(ph, val)
        turns.append((role, line))

    sc = {
        "id": template.get("id"),
        "personality": template.get("personality", ""),
        "source": "template",
        "city": meta.get("city", "포항시"),
        "meta": meta,
        "turns": turns,
    }
    return prepare_scenario_for_generation(sc, rng)


def sample_odor_scenario(
    rng: Optional[random.Random] = None,
    *,
    pohang_weight: float = 0.75,
    target_region: str = "",
) -> Dict[str, Any]:
    """포항 실데이터 시나리오 또는 성격 템플릿 샘플."""
    rng = _coerce_rng(rng)
    data = _load_data()
    pohang = data.get("pohang") or []
    templates = data.get("templates") or []
    pools = _merge_external_keyword_pools(dict(data.get("pools") or {}))
    region_key = _normalize_odor_region(target_region) if target_region else ""
    if region_key:
        sampled_meta = _sample_keyword_meta(pools, region_key, rng)
    else:
        sampled_meta = _sample_keyword_meta(pools, "경상", rng)

    if pohang and rng.random() < pohang_weight:
        sc = dict(rng.choice(pohang))
        sc["source"] = "pohang"
        sc["turns"] = [(t[0], t[1]) for t in sc.get("turns") or []]
        meta = dict(sc.get("meta") or {})
        meta.update(sampled_meta)
        sc["meta"] = meta
        if region_key:
            sc["city"] = sample_regional_city(region_key, rng)
        sc["keyword_plan"] = dict(sampled_meta)
        return prepare_scenario_for_generation(sc, rng)

    if templates:
        tpl = rng.choice(templates)
        if region_key:
            regional_locs = _pool_locations_for_region(region_key, pools)
            if regional_locs:
                pools["locations"] = regional_locs
        sc = _fill_template(tpl, pools, rng)
        meta = dict(sc.get("meta") or {})
        meta.update(sampled_meta)
        sc["meta"] = meta
        if region_key:
            sc["city"] = sample_regional_city(region_key, rng)
        sc["keyword_plan"] = dict(sampled_meta)
        return prepare_scenario_for_generation(sc, rng)

    if pohang:
        sc = dict(rng.choice(pohang))
        sc["source"] = "pohang"
        sc["turns"] = [(t[0], t[1]) for t in sc.get("turns") or []]
        meta = dict(sc.get("meta") or {})
        meta.update(sampled_meta)
        sc["meta"] = meta
        if region_key:
            sc["city"] = sample_regional_city(region_key, rng)
        sc["keyword_plan"] = dict(sampled_meta)
        return prepare_scenario_for_generation(sc, rng)

    return prepare_scenario_for_generation(
        {
        "id": 0,
        "personality": "기본",
        "source": "fallback",
        "city": "포항시",
        "meta": {},
        "turns": [
            ("상담원", "안녕하세요, 포항시 기후대기과 악취 대응팀입니다. 어떤 도움을 드릴까요?"),
            ("민원인", "여기 냄새 때문에 전화했어요."),
        ],
        },
        rng,
    )


def sample_target_region(rng: Optional[random.Random] = None) -> str:
    """포항 데이터 비중이 높으나 5권역 증강을 위해 전 권역 샘플."""
    rng = _coerce_rng(rng)
    # 경상 가중 (포항 맥락)
    weights = {"경상": 0.45, "전라": 0.15, "제주": 0.1, "충청": 0.15, "강원": 0.15}
    return rng.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]


def format_consultation_script_for_prompt(
    collected_fields: Optional[set] = None,
    question_fields: Optional[set] = None,
) -> str:
    ask = set(
        question_fields
        if question_fields is not None
        else (collected_fields if collected_fields is not None else META_FIELDS)
    )
    slot_hint = set(collected_fields or ())
    labels = " · ".join(
        META_FIELD_LABELS[f] for f in MANDATORY_QUESTION_ORDER if f in ask
    )
    lines = [
        "[공식 상담 — 상담원 표준어, 민원인 방언, multi-turn]",
        f"**상담원 질문 시도**: {labels or '냄새·위치·강도·지속·원인'} — "
        "다섯 주제 각각 최소 1회 질문(한 질문 한 문장, 통화마다 순서·표현 변주). "
        "민원인은 모름·회피·짧은 답·topic drift 가능.",
        "**슬롯 GT(민원인이 실제 말한 것만)**: "
        + (
            " · ".join(
                META_FIELD_LABELS[f]
                for f in MANDATORY_QUESTION_ORDER
                if f in slot_hint
            )
            if slot_hint
            else "이번 통화는 위치·냄새 등 일부만 명시"
        ),
        "**상담원 질문**: 한 문장(25~40자). 「또는」「예를 들어」·항목 나열 금지.",
    ]
    for step in get_consultation_steps():
        mf = step.get("meta_field") or ""
        if mf and mf not in ask:
            continue
        q = COMPACT_COUNSELOR_QUESTIONS.get(mf) or compact_counselor_question_text(
            step.get("question") or ""
        )
        lines.append(f"- {step.get('id', '')} {step.get('title', '')}: {q}")
    return "\n".join(lines)


def build_odor_bulk_prompt(
    scenario: Dict[str, Any],
    target_region: str,
    feedback_block: str = "",
    *,
    vary: bool = True,
    rng: Optional[random.Random] = None,
) -> str:
    """대량 생성용 시드 프롬프트 (dialect_seed_prompts 위임)."""
    try:
        from dialect_seed_prompts import build_odor_bulk_prompt as _impl
    except ImportError:
        from agent.dialect_seed_prompts import build_odor_bulk_prompt as _impl
    return _impl(
        scenario,
        target_region,
        feedback_block,
        vary=vary,
        rng=rng,
    )


def apply_scenario_metadata_to_record(
    record: Dict[str, Any],
    scenario: Dict[str, Any],
    *,
    target_region: str = "",
) -> Dict[str, Any]:
    """포항 골드 메타가 있으면 추출값보다 우선(환각 방지). 문장형 → 키워드 라벨로 정규화."""
    meta = scenario.get("meta") or {}
    if not meta:
        return record
    try:
        from complaint_metadata import normalize_meta_fields
    except ImportError:
        from agent.complaint_metadata import normalize_meta_fields
    try:
        from regional_localization import (
            localize_for_region,
            localize_metadata_fields,
            _normalize_region,
        )
    except ImportError:
        from agent.regional_localization import (
            localize_for_region,
            localize_metadata_fields,
            _normalize_region,
        )

    mapping = {
        "location": "위치",
        "odor_type": "냄새종류",
        "cause_guess": "원인추정지역",
        "intensity_change": "냄새강도의변화",
        "duration": "지속시간",
    }
    collected = set(
        scenario.get("slot_fields") or scenario.get("collected_fields") or []
    )
    out = dict(record)
    region_key = _normalize_region(target_region) if target_region else "경상"
    try:
        from locale_profile import build_locale_profile_from_scenario
    except ImportError:
        from agent.locale_profile import build_locale_profile_from_scenario
    lp = build_locale_profile_from_scenario(scenario, region_key)
    out["지역세부프로필"] = lp.get("sub_region") or ""
    out["규칙샘플시드"] = str(lp.get("rule_sample_seed", ""))
    out["locale_profile"] = lp
    locked_empty = {
        mapping[f]
        for f in META_FIELDS
        if f not in collected
    }
    try:
        from complaint_metadata import slot_fill_mode
    except ImportError:
        from agent.complaint_metadata import slot_fill_mode

    if slot_fill_mode() == "strict":
        for col in mapping.values():
            out[col] = ""
    else:
        for src, col in mapping.items():
            if src not in collected:
                out[col] = ""
                continue
            val = (meta.get(src) or "").strip()
            if not val:
                out[col] = ""
                continue
            if col == "원인추정지역":
                val = _normalize_cause_guess_for_region(
                    val,
                    region_key,
                    odor_type=(meta.get("odor_type") or ""),
                    seed=int(lp.get("rule_sample_seed") or 0),
                )
            if col in ("위치", "원인추정지역") and target_region:
                seed_i = int(lp.get("rule_sample_seed") or 0) or None
                out[col] = localize_for_region(
                    val, region_key, official=False, seed=seed_i
                )
            else:
                out[col] = val
        ctx = (out.get("민원내용") or out.get("표준어민원") or "").strip()
        out.update(
            normalize_meta_fields(out, context_text=ctx, locked_empty=locked_empty)
        )
    if target_region:
        out = localize_metadata_fields(out, region_key)
    out["scenario_id"] = scenario.get("id")
    personality = (scenario.get("personality") or "").strip()
    out["scenario_personality"] = personality
    out["시나리오유형"] = personality
    out["scenario_source"] = scenario.get("source", "")
    out["collected_fields"] = list(collected)
    out["slot_fields"] = list(collected)
    out["question_fields"] = list(scenario.get("question_fields") or [])
    out["_meta_locked_empty"] = list(locked_empty)
    kp = scenario.get("keyword_plan")
    if isinstance(kp, dict) and kp:
        out["keyword_plan"] = dict(kp)
        try:
            from complaint_metadata import apply_keyword_plan_columns
        except ImportError:
            from agent.complaint_metadata import apply_keyword_plan_columns
        out = apply_keyword_plan_columns(out, kp)
    try:
        from complaint_metadata import enrich_record_metadata
    except ImportError:
        from agent.complaint_metadata import enrich_record_metadata
    return enrich_record_metadata(out)


def scenario_summary_line(scenario: Dict[str, Any]) -> str:
    p = scenario.get("personality", "")
    src = scenario.get("source", "")
    sid = scenario.get("id", "")
    return f"시나리오 #{sid} ({src}) {p}"
