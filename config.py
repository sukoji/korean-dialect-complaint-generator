# -*- coding: utf-8 -*-
"""모델 목록 · 슬롯 수집 확률 · 키워드 소스 경로.

키워드(냄새·강도·지속·위치·원인)는 하드코딩하지 않고, 기존 프로젝트가 참조하는
실제 데이터 파일에서 슬롯별로 랜덤 1개씩 뽑는다(원본 odor_complaint_scenarios 재사용).
  - data_consolidated/odor_smell.json        -> smell_type
  - data_consolidated/odor_intensity_200.json -> smell_intensity
  - data_consolidated/odor_duration_300.json  -> smell_duration
  - 지역별_지명_지역_도로명주소_통합_work.csv  -> location / 원인 시설(권역별)
"""

# ── 비교할 모델 (provider, model_id) ─────────────────────────────────
# 유효하지 않은 ID는 호출 시 셀에 [ERROR ...] 기록 후 계속 진행(스킵).
# 키는 기존 프로젝트 .env(ANTHROPIC_API_KEY / OPENAI_API_KEY) 재사용.
MODELS = [
    ("anthropic", "claude-opus-4-8"),
    ("anthropic", "claude-opus-4-7"),
    ("anthropic", "claude-opus-4-6"),
    ("anthropic", "claude-fable-5"),
    ("anthropic", "claude-sonnet-4-6"),
    ("anthropic", "claude-sonnet-4-5"),
    ("openai", "gpt-5.5"),
    ("openai", "gpt-5.4"),
    ("openai", "gpt-5.4-mini"),
    ("openai", "gpt-5-mini"),
    ("openai", "gpt-5-nano"),
]

# ── 슬롯 수집 확률(채택률) — 미채택 슬롯은 '미언급' ───────────────────
#   위치 100% / 악취종류 90% / 강도 50% / 지속 50% / 원인 10%
SLOT_PROB = {
    "location": 1.0,
    "smell_type": 0.9,
    "smell_intensity": 0.5,
    "smell_duration": 0.5,
    "suspected": 0.1,
}
UNMENTIONED = "미언급"

from pathlib import Path

_HERE = Path(__file__).resolve().parent

# 샘플링용 권역키 ↔ 프롬프트 표기
REGION_KEYS = ["경상", "전라", "제주", "충청", "강원"]
REGION_DISPLAY = {
    "경상": "경상도", "전라": "전라도", "제주": "제주도",
    "충청": "충청도", "강원": "강원도",
}
