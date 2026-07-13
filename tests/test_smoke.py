# -*- coding: utf-8 -*-
"""API 키 없이 실행 가능한 스모크 테스트 (CI용)."""
from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import config  # noqa: E402
import odor_complaint_scenarios as O  # noqa: E402
sys.path.insert(0, str(ROOT))
import run  # noqa: E402


class SmokeTest(unittest.TestCase):
    def test_data_json_files_are_valid(self) -> None:
        data_dir = ROOT / "data"
        json_files = list(data_dir.glob("*.json"))
        self.assertGreater(len(json_files), 0, "data/*.json 파일이 없습니다")
        for path in json_files:
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_prompt_templates_exist(self) -> None:
        for name in ("prompt_template.txt", "extract_prompt.txt"):
            path = ROOT / "prompts" / name
            with self.subTest(name=name):
                self.assertTrue(path.is_file(), f"누락: {path}")
                self.assertGreater(len(path.read_text(encoding="utf-8").strip()), 0)

    def test_scenario_sampling_for_all_regions(self) -> None:
        data = O._load_data()
        pools = O._merge_external_keyword_pools(dict(data.get("pools") or {}))
        rng = random.Random(42)
        for region in config.REGION_KEYS:
            with self.subTest(region=region):
                meta = O._sample_keyword_meta(pools, region, rng)
                self.assertTrue((meta.get("location") or "").strip())

    def test_region_pools_have_all_regions(self) -> None:
        pools = json.loads((ROOT / "data" / "region_pools.json").read_text(encoding="utf-8"))
        place_pools = pools.get("place") or {}
        for region in config.REGION_KEYS:
            with self.subTest(region=region):
                self.assertIn(region, place_pools)
                self.assertGreater(len(place_pools[region]), 0)

    def test_sampled_suspected_location_matches_location_city(self) -> None:
        rng = random.Random(20260713)
        for region in config.REGION_KEYS:
            for _ in range(20):
                with self.subTest(region=region):
                    scenario = run.sample_scenario(rng, region)
                    if scenario["suspected_location_text"] == config.UNMENTIONED:
                        continue
                    city_map = run._ensure_location_city_map()[scenario["region_name"]]
                    self.assertEqual(
                        scenario["location_address"],
                        city_map[scenario["suspected_location_text"]],
                    )

    def test_location_city_is_not_a_bare_district(self) -> None:
        data = json.loads((ROOT / "data" / "location_pools.json").read_text(encoding="utf-8"))
        for region, city_map in (data.get("city") or {}).items():
            for place, city in city_map.items():
                with self.subTest(region=region, place=place):
                    self.assertFalse(
                        city.endswith("구") and " " not in city,
                        f"상위 도시 없이 구만 저장됨: {city}",
                    )


if __name__ == "__main__":
    unittest.main()
