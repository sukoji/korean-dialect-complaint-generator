# -*- coding: utf-8 -*-
"""악취 방언 민원 대화 생성 파이프라인 (독립 실행).

- 권역별 키워드(위치·냄새·강도·지속·원인)를 미리 계산한 풀에서 샘플
  → prompts/prompt_template.txt 채움
- 지정 모델로 방언 민원 대화 생성(병렬) → 비교 CSV + 상세 JSONL

사용:
  python run.py --n 100 --models claude-opus-4-8       # 권역 순환 100건
  python run.py --n 25  --models gpt-5.5
  python run.py --max-tokens 3000 --workers 6
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import config

HERE = Path(__file__).resolve().parent
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
SYSTEM_MSG = "너는 악취 민원 상담 시나리오 생성기다. 출력은 오직 대화체만 포함한다."


# ── .env 로딩 (기존 프로젝트 키 재사용) ──────────────────────────────
def load_env() -> None:
    candidates = [HERE / ".env"]
    for p in candidates:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k and not os.environ.get(k):
                os.environ[k] = v


# ── 모델 파라미터 규칙 (실측 기반) ───────────────────────────────────
def openai_is_reasoning(model: str) -> bool:
    m = model.lower()
    return m.startswith("gpt-5") or re.match(r"^o\d", m) is not None or m.startswith("chatgpt-5")


# ── API 호출 ─────────────────────────────────────────────────────────
def call_openai(model: str, prompt: str, max_tokens: int, timeout: float) -> dict:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "OPENAI_API_KEY 없음", "text": ""}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user", "content": prompt},
        ],
    }
    # 조건 동일성: temperature는 전 모델 생략(각 모델 기본값) → '모델만' 변수.
    # gpt-5/o 계열은 max_completion_tokens, 그 외는 max_tokens (동일 의미, 파라미터명만 상이).
    if openai_is_reasoning(model):
        body["max_completion_tokens"] = max_tokens
    else:
        body["max_tokens"] = max_tokens
    return _post(OPENAI_URL, body, {"Authorization": f"Bearer {key}"}, "openai", timeout)


def call_anthropic(model: str, prompt: str, max_tokens: int, timeout: float) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "ANTHROPIC_API_KEY 없음", "text": ""}
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": SYSTEM_MSG,
        "messages": [{"role": "user", "content": prompt}],
    }
    # 조건 동일성: temperature 생략(각 모델 기본값) → '모델만' 변수.
    return _post(
        ANTHROPIC_URL,
        body,
        {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION},
        "anthropic",
        timeout,
    )


def _post(url: str, body: dict, headers: dict, provider: str, timeout: float, _try: int = 0) -> dict:
    headers = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:300] if e.fp else ""
        # 400 temperature 거부 시 1회 재시도(파라미터 제거)
        if e.code == 400 and "temperature" in msg and "temperature" in body:
            body.pop("temperature", None)
            return _post(url, body, headers, provider, timeout, _try)
        # 일시 오류(429 rate / 529 overload / 5xx)는 백오프 후 재시도(최대 3회)
        if (e.code in (429, 529) or 500 <= e.code < 600) and _try < 3:
            time.sleep(2 + _try * 4)
            return _post(url, body, headers, provider, timeout, _try + 1)
        return {"ok": False, "error": f"HTTP {e.code}: {msg}", "text": "", "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        # 타임아웃·연결 오류도 재시도
        if _try < 3:
            time.sleep(2 + _try * 4)
            return _post(url, body, headers, provider, timeout, _try + 1)
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "text": "", "ms": int((time.time() - t0) * 1000)}
    ms = int((time.time() - t0) * 1000)
    if provider == "openai":
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content", "") or ""
        usage = data.get("usage") or {}
    else:
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = data.get("usage") or {}
    return {"ok": True, "error": "", "text": text.strip(), "ms": ms, "usage": usage}


# ── 키워드 소스: 번들된 pipeline 모듈 + 미리 계산한 풀 ────────────────
_ODOR = None
_POOLS = None
_LOCATION_POOLS: dict[str, list[str]] = {}  # broad_region -> [place_name, ...]
_LOCATION_POOLS_JSON = HERE / "data" / "location_pools.json"


def _ensure_location_pools() -> dict[str, list[str]]:
    """원인추정 위치 풀 — 미리 계산한 data/location_pools.json 로드."""
    global _LOCATION_POOLS
    if _LOCATION_POOLS:
        return _LOCATION_POOLS
    _LOCATION_POOLS = json.loads(_LOCATION_POOLS_JSON.read_text(encoding="utf-8"))
    return _LOCATION_POOLS


def _ensure_orig_sampler():
    """번들된 pipeline/odor_complaint_scenarios 로드(미리 계산한 데이터 풀)."""
    global _ODOR, _POOLS
    if _ODOR is not None:
        return _ODOR, _POOLS
    pipe = str(HERE / "pipeline")
    if pipe not in sys.path:
        sys.path.insert(0, pipe)
    try:
        import odor_complaint_scenarios as O
    except Exception as e:
        print(f"[중단] 샘플러 로드 실패: {e}")
        sys.exit(1)
    data = O._load_data()
    _POOLS = O._merge_external_keyword_pools(dict(data.get("pools") or {}))
    _ODOR = O
    return _ODOR, _POOLS


def sample_scenario(rng: random.Random, region_key: str) -> dict:
    """참조 파일들에서 슬롯별 랜덤 1개 → 사용자 채택률대로 '미언급' 처리."""
    O, pools = _ensure_orig_sampler()
    m = O._sample_keyword_meta(pools, region_key, rng)  # 실제 파일에서 1개씩
    loc = (m.get("location") or "").strip()
    # location_city = _sample_keyword_meta가 loc 채택 시 이미 확인한 "실제" 소속
    # 시·군. 인사말 도시를 여기서 별도로 다시 추측하면(REGION_CITIES 5개 대표
    # 도시만 보고 못 찾으면 무작위 재선택) "춘천시 기후대기과"인데 실제 위치는
    # 철원군인 것처럼 인사말과 위치가 서로 다른 도시가 되는 불일치가 생긴다.
    location_address = (m.get("location_city") or "").strip() or O.sample_regional_city(
        region_key, rng
    )

    def keep(slot: str) -> bool:
        return rng.random() < config.SLOT_PROB[slot]

    return {
        "region_name": config.REGION_DISPLAY.get(region_key, region_key),
        "location_address": location_address,
        "complainant_location_text": loc,  # 위치 100%
        "smell_type": (m.get("odor_type") or "").strip() if keep("smell_type") else config.UNMENTIONED,
        "smell_intensity": (m.get("intensity_change") or "").strip() if keep("smell_intensity") else config.UNMENTIONED,
        "smell_duration": (m.get("duration") or "").strip() if keep("smell_duration") else config.UNMENTIONED,
        "suspected_location_text": rng.choice(_ensure_location_pools().get(config.REGION_DISPLAY.get(region_key, ""), [""]) or [""]) if keep("suspected") else config.UNMENTIONED,
    }


def fill_prompt(template: str, sc: dict) -> str:
    out = template
    for k, v in sc.items():
        out = out.replace("{" + k + "}", str(v))
    return out + runtime_forbidden_block(sc.get("region_name", ""))


def runtime_forbidden_block(region_name: str) -> str:
    """prompt_template.txt 는 그대로 두고, 실행 시에만 금지 규칙 주입."""
    lines = [
        "",
        "[실행 시 추가 금지 — 반드시 준수]",
        "* 모든 권역: 민원인 발화에 '-드래-' 계열(~드래요, ~더래요, ~했드래요, ~드래, ~드래유, ~거드래요 등)을 절대 쓰지 않는다.",
    ]
    if region_name == "강원도":
        lines += [
            "* 강원도: '-드래-'는 매체 가짜 방언이므로 전면 금지. 대신 ~래요(아니래요, 맞래요), ~우야, ~잖소, ~겠소, ~주소 등 실제 강원 어미를 쓴다.",
            "* 강원도: '-래-'는 '이다/아니다' 활용(판단·부정)에만 쓰고, '-드래-'로 대체하지 않는다.",
        ]
    if region_name == "경상도":
        lines += [
            "* 경상도: '~카이' 계열 종결(맞다카이, 온다카이, 그렇다카이, ~다카이 등)을 절대 쓰지 않는다. 대신 ~심더, ~라예, ~기라예, ~다 아입니꺼, ~다 아이가 등 다른 경상 어미로 끝낸다.",
        ]
    return "\n".join(lines)


# ── 메인 ─────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6, help="시나리오 개수(권역 순환)")
    ap.add_argument("--models", type=str, default="", help="쉼표구분 모델 포함 필터(부분일치)")
    ap.add_argument("--exclude", type=str, default="", help="쉼표구분 모델 제외 필터(부분일치)")
    ap.add_argument("--max-tokens", type=int, default=2500)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument(
        "--seed", type=int, default=None,
        help="난수 seed. 미지정 시 매 실행 랜덤(매번 다른 데이터). "
             "특정 실행을 재현하려면 그때 출력된 seed 값을 지정.",
    )
    ap.add_argument("--out", type=str, default=str(HERE / "results"))
    args = ap.parse_args()

    load_env()
    have = {
        "openai": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
    }
    print(f"[키] OpenAI={'OK' if have['openai'] else '없음'} · Anthropic={'OK' if have['anthropic'] else '없음'}")

    models = list(config.MODELS)
    if args.models:
        wanted = [w.strip() for w in args.models.split(",") if w.strip()]
        models = [m for m in models if any(w in m[1] for w in wanted)]
    if args.exclude:
        drop = [w.strip() for w in args.exclude.split(",") if w.strip()]
        models = [m for m in models if not any(w in m[1] for w in drop)]
    models = [m for m in models if have.get(m[0])]
    if not models:
        print("[중단] 실행 가능한 모델이 없습니다(키 또는 필터 확인).")
        sys.exit(1)
    print(f"[모델] {len(models)}종: " + ", ".join(m[1] for m in models))

    template = (HERE / "prompts" / "prompt_template.txt").read_text(encoding="utf-8")
    # seed 미지정 시 매 실행 랜덤(다양성). 어떤 seed로 돌았는지 출력해 재현 가능하게 남긴다.
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    print(f"[seed] {seed}" + (" (지정됨)" if args.seed is not None else " (랜덤 — 재현하려면 --seed {} )".format(seed)))
    rng = random.Random(seed)
    regions = config.REGION_KEYS
    _ensure_orig_sampler()  # 데이터 파일 풀 사전 로드(첫 1회 수 초)
    scenarios = []
    for i in range(args.n):
        region = regions[i % len(regions)]
        sc = sample_scenario(rng, region)
        sc["scenario_id"] = i + 1
        scenarios.append(sc)

    # 모든 (시나리오 × 모델) 작업 병렬 실행
    tasks = []
    for sc in scenarios:
        prompt = fill_prompt(template, sc)
        for provider, model in models:
            tasks.append((sc, prompt, provider, model))

    print(f"[실행] {len(scenarios)}시나리오 × {len(models)}모델 = {len(tasks)}콜 (workers={args.workers})")
    results: dict = {}  # (sid, model) -> result
    done = 0

    def work(task):
        sc, prompt, provider, model = task
        fn = call_openai if provider == "openai" else call_anthropic
        res = fn(model, prompt, args.max_tokens, args.timeout)
        return sc["scenario_id"], model, provider, res

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, t) for t in tasks]
        for fut in as_completed(futs):
            sid, model, provider, res = fut.result()
            results[(sid, model)] = res
            done += 1
            status = "OK" if res["ok"] else f"ERR({res['error'][:40]})"
            print(f"  [{done}/{len(tasks)}] s{sid} · {model} · {res.get('ms','?')}ms · {status}")

    # 출력 디렉터리·파일명
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = outdir / f"comparison_{stamp}.csv"
    jsonl_path = outdir / f"raw_{stamp}.jsonl"

    model_ids = [m[1] for m in models]
    input_cols = [
        "scenario_id", "region_name", "location_address", "complainant_location_text",
        "smell_type", "smell_intensity", "smell_duration", "suspected_location_text",
    ]
    # 비교 CSV (모델별 출력 컬럼, 한 시나리오 = 한 행)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(input_cols + [f"out__{mid}" for mid in model_ids])
        for sc in scenarios:
            row = [sc[c] for c in input_cols]
            for mid in model_ids:
                r = results.get((sc["scenario_id"], mid), {})
                row.append(r.get("text") if r.get("ok") else f"[ERROR] {r.get('error','')}")
            w.writerow(row)

    # 상세 JSONL (지연·토큰·에러 포함)
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for sc in scenarios:
            for provider, mid in models:
                r = results.get((sc["scenario_id"], mid), {})
                f.write(json.dumps({
                    "scenario_id": sc["scenario_id"],
                    "provider": provider,
                    "model": mid,
                    "input": {c: sc[c] for c in input_cols},
                    "ok": r.get("ok", False),
                    "error": r.get("error", ""),
                    "latency_ms": r.get("ms"),
                    "usage": r.get("usage"),
                    "output": r.get("text", ""),
                }, ensure_ascii=False) + "\n")

    # 모델별 성공/평균지연 요약
    print("\n[요약] 모델별 성공률·평균지연")
    for provider, mid in models:
        rs = [results.get((sc["scenario_id"], mid), {}) for sc in scenarios]
        ok = [r for r in rs if r.get("ok")]
        avg = int(sum(r.get("ms", 0) for r in ok) / len(ok)) if ok else 0
        err = next((r["error"] for r in rs if not r.get("ok")), "")
        print(f"  {mid:22s} {len(ok)}/{len(rs)} OK · 평균 {avg}ms" + (f" · 예: {err[:50]}" if err else ""))

    print(f"\n[저장] 비교 CSV : {csv_path}")
    print(f"[저장] 상세 JSONL: {jsonl_path}")


if __name__ == "__main__":
    main()
