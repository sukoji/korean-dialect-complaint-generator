# Korean Dialect Odor-Complaint Generator

권역별 방언 **악취 민원 상담 대화**를 생성하는 파이프라인입니다.
키워드(위치·냄새·강도·지속·원인)를 미리 계산한 사전 풀에서 뽑아 프롬프트를 채우고,
LLM으로 상담원(표준어)·민원인(방언) 대화를 만듭니다.

- 5개 권역: 경상 · 전라 · 제주 · 충청 · 강원
- 지명은 각 권역의 **실제 시·군·구에 존재하는 지명**만 사용 (인사말 도시 ↔ 지명 정합 보장)
- 냄새는 **객관 발생원**만 (주관 표현 배제), 강도·지속시간은 카테고리 고정

## 빠른 시작

```bash
# 1) 파이썬 3.9+ (외부 의존성 없음, 표준 라이브러리만 사용)
# 2) API 키 설정
cp .env.example .env
#   .env 에 ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 입력

# 3) 생성 (권역 순환으로 100건, Opus 사용 예)
python run.py --n 100 --models claude-opus-4-8
```

결과는 `results/` 에 저장됩니다:
- `comparison_<타임스탬프>.csv` — 키워드(정답) + 생성 대화
- `raw_<타임스탬프>.jsonl` — 입력·출력·토큰 사용량 원본

## 주요 옵션

| 옵션 | 설명 | 기본 |
|---|---|---|
| `--n` | 시나리오 개수 (권역 순환) | 6 |
| `--models` | 쉼표구분 모델 필터(부분일치) | 전체 |
| `--workers` | 병렬 워커 수 | 5 |
| `--max-tokens` | 생성 최대 토큰 | 2500 |
| `--out` | 출력 폴더 | `results/` |

지원 모델 목록은 `config.py`의 `MODELS` 참고 (Anthropic / OpenAI). 키가 없는 provider는 자동 스킵됩니다.

## 폴더 구조

```
run.py                     생성 실행 진입점
config.py                  모델 목록 · 슬롯 채택 확률 · 권역 표기
prompts/
  prompt_template.txt      민원 대화 생성 프롬프트
  extract_prompt.txt       (평가용) 대화 → 5키워드 추출 프롬프트
pipeline/
  odor_complaint_scenarios.py   키워드 샘플러 (미리 계산한 풀 로드)
  place_asr_variants.py         지명 ASR 변형
  complaint_metadata.py         메타 정규화 유틸
  keyword_normalize.py          (평가용) 추출 결과 채점 정규화
data/
  odor_smell.json               냄새 종류 사전 (객관 발생원)
  odor_intensity_200.json       강도 변화 사전
  odor_duration_300.json        지속시간 사전
  odor_keyword_config.json      슬롯 확률·위치 alias 설정
  odor_complaint_scenarios.json 상담 단계·성격 유형
  region_pools.json             권역별 지명 풀 + 실제 도시맵 (미리 계산)
  location_pools.json           원인추정 위치 풀 (미리 계산)
tools/
  build_pools.py                원본 대형 지명 DB → 경량 풀 재생성 스크립트
```

## 사전 데이터에 대해

지명 풀은 원본 지명 마스터(약 118MB CSV)와 `location.json`(약 294MB)에서
미리 계산해 `data/region_pools.json` · `data/location_pools.json`(각 수백 KB)로
포함했습니다. 원본 대형 파일은 저장소에 넣지 않습니다.

원본을 갱신해 풀을 다시 만들려면:

```bash
python tools/build_pools.py --toponym <지명마스터.csv> --location <location.json>
```

## 파이프라인 흐름

```
[사전 풀]        [생성 프롬프트]      [LLM]              [저장]
권역별 지명·냄새 → 키워드 채움      → 방언 민원 대화    → CSV / JSONL
(코드가 샘플)     +방언 금지규칙        (상담원+민원인)     (키워드=정답 라벨)
```

생성된 대화의 "정답"은 샘플링한 키워드 그 자체입니다.
`prompts/extract_prompt.txt` 는 대화만 보고 키워드를 재추출하는 **평가용** 프롬프트로,
정답과 비교해 추출 성능(WER/CER/단어 F1)을 재는 용도입니다(생성 흐름과 분리).
