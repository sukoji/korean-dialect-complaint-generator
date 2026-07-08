# -*- coding: utf-8 -*-
"""data/region_pools.json · data/location_pools.json 재생성 스크립트.

배포판에는 원본 대형 파일(지명 마스터 CSV ~118MB, location.json ~294MB)을
포함하지 않고, 여기서 미리 계산한 경량 풀만 data/ 에 넣는다.

원본 두 파일을 별도로 전달받은 경우, 아래 고정 경로에 그대로 넣고 인자 없이 실행하면
풀이 다시 생성된다(파일명 변경 불필요):

    data/raw/지역별_지명_지역_도로명주소_통합_work.csv
    data/raw/location.json

    python tools/build_pools.py            # 위 고정 경로 자동 사용

경로가 다르면 직접 지정:

    python tools/build_pools.py --toponym <경로.csv> --location <경로.json>
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipeline"))
import odor_complaint_scenarios as O  # noqa: E402

LOC_CAP = 4000  # 원인추정 위치 풀 권역당 상한

# 원본 대형 파일을 별도로 받았을 때 넣어두는 고정 경로(파일명 그대로)
_RAW_DIR = HERE / "data" / "raw"
_DEFAULT_TOPONYM = _RAW_DIR / "지역별_지명_지역_도로명주소_통합_work.csv"
_DEFAULT_LOCATION = _RAW_DIR / "location.json"


def build_region_pools(toponym_csv: str) -> dict:
    """지명 마스터 CSV → 권역별 place/cause 풀 + place_city 맵.

    _scan_region_pools 와 동일 로직을 원본 CSV에 직접 적용(배포판 _scan_region_pools
    는 이 결과 JSON을 읽기만 함). 정제 규칙은 pipeline/odor_complaint_scenarios.py
    의 _clean_place_name / _extract_city_from_loc 참조.
    """
    import csv

    place = {k: [] for k in O._REGION_LOC_PAT}
    cause = {k: [] for k in O._REGION_LOC_PAT}
    place_city = {k: {} for k in O._REGION_LOC_PAT}
    cause_city = {k: {} for k in O._REGION_LOC_PAT}
    with open(toponym_csv, encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) < 2:
                continue
            name, loc = (row[0] or "").strip(), (row[1] or "").strip()
            if not name or O._OUT_OF_SCOPE_LOC_RE.search(loc):
                continue
            is_place = bool(O._LOC_NAME_OK.search(name)) and not O._LOC_NAME_BAD.search(name)
            is_cause = bool(O._CAUSE_SRC.search(name)) and not O._CAUSE_BAD.search(name)
            place_name = O._clean_place_name(name) if is_place else ""
            if not place_name:
                is_place = False
            if not (is_place or is_cause):
                continue
            for reg, pat in O._REGION_LOC_PAT.items():
                if not pat.search(loc):
                    continue
                if is_place and len(place[reg]) < O._TOPONYM_PER_REGION_CAP:
                    place[reg].append(place_name)
                    if place_name not in place_city[reg]:
                        city = O._extract_city_from_loc(loc)
                        if city:
                            place_city[reg][place_name] = city
                if is_cause and len(cause[reg]) < O._TOPONYM_PER_REGION_CAP:
                    cause[reg].append(name)
                    if name not in cause_city[reg]:
                        city = O._extract_city_from_loc(loc)
                        if city:
                            cause_city[reg][name] = city
                break
    dedup = lambda v: list(dict.fromkeys(v))
    return {
        "place": {k: dedup(v) for k, v in place.items()},
        "cause": {k: dedup(v) for k, v in cause.items()},
        "place_city": place_city,
        "cause_city": cause_city,
    }


def build_location_pools(location_json: str) -> dict:
    """원인추정 위치 풀(broad_region -> [place_name]) + 이름->실제 시/군 맵.

    location.json의 location/road_address 컬럼에서 시/군을 뽑아 place_city와
    동일한 방식으로 기록(odor_complaint_scenarios._extract_city_from_loc 재사용).
    """
    entries = json.loads(Path(location_json).read_text(encoding="utf-8"))
    by = collections.defaultdict(list)
    city = collections.defaultdict(dict)
    for e in entries:
        region = e.get("broad_region", "")
        name = (e.get("place_name") or "").strip()
        if region and name and len(by[region]) < LOC_CAP:
            by[region].append(name)
            if name not in city[region]:
                c = O._extract_city_from_loc(e.get("location", "") or e.get("road_address", ""))
                if c:
                    city[region][name] = c
    return {"pools": dict(by), "city": dict(city)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--toponym", default=str(_DEFAULT_TOPONYM),
        help=f"지명 마스터 CSV 경로 (기본: {_DEFAULT_TOPONYM})",
    )
    ap.add_argument(
        "--location", default=str(_DEFAULT_LOCATION),
        help=f"location.json 경로 (기본: {_DEFAULT_LOCATION})",
    )
    args = ap.parse_args()

    for label, p in (("지명 마스터 CSV", args.toponym), ("location.json", args.location)):
        if not Path(p).is_file():
            sys.exit(
                f"[중단] {label} 을(를) 찾을 수 없습니다: {p}\n"
                f"  원본 파일을 data/raw/ 에 넣거나 --toponym/--location 으로 경로를 지정하세요."
            )

    data_dir = HERE / "data"
    rp = build_region_pools(args.toponym)
    (data_dir / "region_pools.json").write_text(
        json.dumps(rp, ensure_ascii=False), encoding="utf-8"
    )
    print("region_pools.json:", {k: len(v) for k, v in rp["place"].items()})

    lp = build_location_pools(args.location)
    (data_dir / "location_pools.json").write_text(
        json.dumps(lp, ensure_ascii=False), encoding="utf-8"
    )
    print("location_pools.json:", {k: len(v) for k, v in lp["pools"].items()})


if __name__ == "__main__":
    main()
