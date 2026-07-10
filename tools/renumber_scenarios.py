#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run.py로 생성한 comparison CSV를 지역별로 scenario_id 1..N 재번호.

run.py는 권역을 순환하며 배분하므로(경상/전라/제주/충청/강원 순서 반복) 지역별
scenario_id가 5,10,15... 처럼 띄엄띄엄 나온다. 이 스크립트는 시나리오 생성 다음
단계로 실행해서 지역 내에서 1부터 연속되게 다시 매긴 CSV를 만든다.

CSV(텍스트)만 다루고 오디오는 건드리지 않는다. TTS 오디오 결과물과 이 CSV를 합쳐
최종 데이터셋 폴더 구조를 만드는 건 별개 파이프라인(오디오 쪽)의 몫이며, 거기에는
이미 동일한 역할을 하는 코드가 있다 — 이 스크립트가 그 병합을 대신하지 않는다.

주의: 여기서 정해지는 scenario_id/uid는 이후 TTS 단계에서 그대로 폴더명
(<지역>_id<번호>_min-..._sang-...) 접두어로 쓰인다. 즉 이 CSV가 이미 지역별
1..N으로 정리돼 있어야 TTS 폴더명도 깔끔하게 나온다.

실행:  python tools/renumber_scenarios.py [CSV 경로 또는 결과 폴더] [--start-id N]
       (인자 없으면 results/ 안 최신 comparison_*.csv 사용, --start-id 없으면 1부터)
"""
import argparse
import csv
import glob
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULTS_DIR = os.path.join(HERE, "..", "results")


def latest_csv(results_dir):
    cands = sorted(glob.glob(os.path.join(results_dir, "comparison_*.csv")))
    if not cands:
        sys.exit(f"[에러] comparison CSV 없음: {results_dir}")
    return cands[-1]


def resolve_input(arg):
    if arg is None:
        return latest_csv(DEFAULT_RESULTS_DIR)
    if os.path.isdir(arg):
        return latest_csv(arg)
    return arg


def renumber_by_region(rows, start_id=1):
    """지역(region_name)별로 원래 scenario_id 순서를 유지한 채 start_id..N 재부여."""
    by_region = {}
    for r in rows:
        by_region.setdefault(r["region_name"], []).append(r)
    for region, rs in by_region.items():
        rs.sort(key=lambda r: int(r["scenario_id"]))
        for i, r in enumerate(rs, start=start_id):
            r["scenario_id"] = str(i)
            if "uid" in r:
                r["uid"] = f"{region}_{i}"
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=None, help="CSV 경로 또는 결과 폴더")
    ap.add_argument("--start-id", type=int, default=1, help="지역별 재번호 시작값 (기본 1)")
    args = ap.parse_args()

    src = resolve_input(args.path)
    with open(src, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    renumber_by_region(rows, start_id=args.start_id)

    base, ext = os.path.splitext(src)
    dst = f"{base}_renumbered{ext}"
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by = Counter(r["region_name"] for r in rows)
    print(f"[+] {src}\n -> {dst}")
    for region, n in sorted(by.items()):
        end = args.start_id + n - 1
        print(f"    {region}: {n}개, scenario_id {args.start_id}~{end}")


def _check():
    """API/파일 없이 재번호 로직만 점검."""
    rows = [
        {"region_name": "강원도", "scenario_id": "5"},
        {"region_name": "강원도", "scenario_id": "10"},
        {"region_name": "강원도", "scenario_id": "15"},
        {"region_name": "전라도", "scenario_id": "3"},
        {"region_name": "전라도", "scenario_id": "8"},
    ]
    renumber_by_region(rows)
    gw = [r["scenario_id"] for r in rows if r["region_name"] == "강원도"]
    jl = [r["scenario_id"] for r in rows if r["region_name"] == "전라도"]
    assert gw == ["1", "2", "3"], gw
    assert jl == ["1", "2"], jl
    print("check OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        _check()
    else:
        main()
