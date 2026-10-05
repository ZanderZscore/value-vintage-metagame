#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DATA = ROOT / "app_data"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    profiles = read_csv(APP_DATA / "archetype_profiles.csv")
    results = read_csv(APP_DATA / "deck_results.csv")

    counts = Counter(row["cluster_id"] for row in results)
    profile_by_id = {row["cluster_id"]: row for row in profiles}

    print(f"Tournament results: {len(results)}")
    print(f"Archetypes: {len(profiles)}")
    print("Top archetypes:")

    for cluster_id, count in counts.most_common(10):
        profile = profile_by_id.get(cluster_id, {})
        name = profile.get("archetype_name", cluster_id)
        print(f"  {count:>3}  {name}")


if __name__ == "__main__":
    main()
