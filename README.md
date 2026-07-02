# 🗣️ Korean Dialect Odor-Complaint Generator

권역별 **방언 악취 민원 상담 대화**를 자동 생성하는 파이프라인입니다.
사전(DB)에서 키워드(위치·냄새·강도·지속·원인)를 뽑아 프롬프트를 채우고,
LLM으로 **상담원(표준어) ↔ 민원인(방언)** 대화를 생성합니다.

> STT·키워드 추출 모델 학습/평가용 합성 데이터 생성을 목표로 만들어졌습니다.

---

## ✨ 특징

- **5개 권역** — 경상 · 전라 · 제주 · 충청 · 강원, 각 권역 고유 어미로 자연스러운 방언 생성
- **지명 정합 보장** — 인사말 도시(“○○시 기후대기과”)와 민원 지명이 항상 같은 **실제 시·군·구**에 존재
- **객관 냄새만** — 발생원 기준(하수·축사·매연 등), 민원인 주관 표현(“머리 아픈 냄새”)은 배제
- **정답 라벨 내장** — 대화를 만든 키워드가 곧 정답(GT). 추출 성능 평가에 바로 사용
- **의존성 0** — 파이썬 표준 라이브러리만 사용 (별도 `pip install` 불필요)
- **바로 실행** — 클론 후 API 키만 넣으면 동작 (대형 원본 DB 없이도 OK)

---

## 🚀 빠른 시작

```bash
# 1) 클론
git clone <이 저장소 URL>
cd korean-dialect-complaint-generator

# 2) API 키 설정 (Anthropic 또는 OpenAI 중 쓰는 것만)
cp .env.example .env
#   .env 를 열어 키 입력:
#     ANTHROPIC_API_KEY=sk-ant-...
#     OPENAI_API_KEY=sk-...

# 3) 생성 — 권역 순환으로 100건 (Opus 예시)
python run.py --n 100 --models claude-opus-4-8
```

> 파이썬 **3.9 이상**이면 됩니다. 가상환경 사용을 권장합니다.

### 결과물

`results/` 폴더에 타임스탬프로 저장됩니다.

| 파일 | 내용 |
|------|------|
| `comparison_<시각>.csv` | 키워드(정답) + 생성된 대화 (모델별 컬럼) |
| `raw_<시각>.jsonl` | 입력·출력·토큰 사용량 원본 |

---

## ⚙️ 실행 옵션

```bash
python run.py --n 25 --models claude-opus-4-8 --workers 8
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--n` | 시나리오 개수 (권역을 순환하며 배분) | `6` |
| `--models` | 모델 필터(쉼표구분, 부분일치) | 전체 |
| `--workers` | 병렬 워커 수 | `5` |
| `--max-tokens` | 생성 최대 토큰 | `2500` |
| `--timeout` | 요청 타임아웃(초) | `300` |
| `--out` | 출력 폴더 | `results/` |

- 지원 모델은 `config.py` 의 `MODELS` 참고 (Anthropic / OpenAI).
- API 키가 없는 provider의 모델은 **자동 스킵**됩니다.
- `--n 100` 이면 5권역 × 20건, `--n 500` 이면 권역별 100건이 됩니다.

---

## 📂 프로젝트 구조

```
korean-dialect-complaint-generator/
├── run.py                     ← 생성 실행 진입점
├── config.py                  모델 목록 · 슬롯 채택 확률 · 권역 표기
├── .env.example               API 키 템플릿 (복사해서 .env 로)
├── requirements.txt           (의존성 없음 안내)
│
├── prompts/
│   ├── prompt_template.txt    민원 대화 생성 프롬프트
│   └── extract_prompt.txt     (평가용) 대화 → 5키워드 추출 프롬프트
│
├── pipeline/
│   ├── odor_complaint_scenarios.py  키워드 샘플러 (미리 계산한 풀 로드)
│   ├── place_asr_variants.py        지명 ASR(음성인식) 변형
│   ├── complaint_metadata.py        메타 정규화 유틸
│   └── keyword_normalize.py         (평가용) 추출 결과 채점 정규화
│
├── data/
│   ├── odor_smell.json              냄새 종류 사전 (객관 발생원)
│   ├── odor_intensity_200.json      강도 변화 사전
│   ├── odor_duration_300.json       지속시간 사전
│   ├── odor_keyword_config.json     슬롯 확률 · 위치 alias 설정
│   ├── odor_complaint_scenarios.json 상담 단계 · 성격 유형
│   ├── region_pools.json            권역별 지명 풀 + 실제 도시맵 (미리 계산)
│   ├── location_pools.json          원인추정 위치 풀 (미리 계산)
│   └── raw/                         (선택) 원본 대형 지명 파일 두는 곳 → 아래 참고
│
└── tools/
    └── build_pools.py         원본 대형 지명 DB → 경량 풀 재생성 스크립트
```

---

## 🔄 파이프라인 흐름

```
 [사전 풀]          [생성 프롬프트]       [LLM]               [저장]
 권역별 지명·냄새  →  키워드 채움        →  방언 민원 대화     →  CSV / JSONL
 (코드가 샘플링)     + 방언 금지규칙 주입    (상담원 + 민원인)     (키워드 = 정답 라벨)
                                                 │
                                   ┌─────────────┘  (평가할 때만)
                                   ▼
                         [추출 프롬프트]  대화만 보고 5키워드 재추출
                                   ▼
                         정답 vs 추출 비교 (WER / CER / 단어 F1)
```

생성된 대화의 “정답”은 샘플링한 키워드 그 자체입니다.
`prompts/extract_prompt.txt` 는 대화만 보고 키워드를 재추출하는 **평가용** 프롬프트로,
생성 흐름과 분리되어 있습니다.

---

## 🗺️ 원본 대형 지명 파일 (선택 사항)

지명 풀은 아래 두 원본 파일에서 **미리 계산**해 `data/region_pools.json` ·
`data/location_pools.json`(합쳐서 약 1MB)로 저장소에 포함했습니다.
따라서 **원본 파일 없이도 파이프라인은 그대로 실행**됩니다.

원본은 용량이 커서(합 약 412MB) 저장소에 넣지 않습니다:

| 원본 파일 | 크기 | 용도 |
|-----------|------|------|
| `지역별_지명_지역_도로명주소_통합_work.csv` | 약 118MB | 권역별 지명 풀 |
| `location.json` | 약 294MB | 원인추정 위치 풀 |

### 원본을 별도로 전달받은 경우 — 넣을 위치

두 파일을 **파일명 그대로** 아래 경로에 넣으세요:

```
data/raw/지역별_지명_지역_도로명주소_통합_work.csv
data/raw/location.json
```

그 다음 프로젝트 루트에서 인자 없이 실행하면 풀이 다시 생성됩니다:

```bash
python tools/build_pools.py
```

경로가 다르면 직접 지정할 수도 있습니다:

```bash
python tools/build_pools.py \
    --toponym /경로/지역별_지명_지역_도로명주소_통합_work.csv \
    --location /경로/location.json
```

> `data/raw/` 안의 원본 파일은 `.gitignore` 로 커밋에서 제외됩니다.
> 재생성 결과(`region_pools.json`, `location_pools.json`)만 저장소에 반영하면 됩니다.
