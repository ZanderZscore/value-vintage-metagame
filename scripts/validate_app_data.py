#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DATA = ROOT / "app_data"
DATA = ROOT / "data"

REQUIRED = [
    APP_DATA / "archetype_profiles.csv",
    APP_DATA / "archetype_profiles.json",
    APP_DATA / "deck_results.csv",
    APP_DATA / "vv_online_results.csv",
    DATA / "vv_online_results.csv",
    DATA / "decks_normalized.json",
    DATA / "deck_cards.csv",
    DATA / "clustering" / "clusters.csv",
    DATA / "clustering" / "deck_clusters.csv",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    missing = [
        str(path.relative_to(ROOT))
        for path in REQUIRED
        if not path.exists()
    ]
    if missing:
        raise SystemExit(
            "Missing generated files:\n  - " + "\n  - ".join(missing)
        )

    profiles = read_csv(APP_DATA / "archetype_profiles.csv")
    results = read_csv(APP_DATA / "deck_results.csv")
    raw_results = read_csv(APP_DATA / "vv_online_results.csv")

    if not profiles:
        raise SystemExit("archetype_profiles.csv is empty")
    if not results:
        raise SystemExit("deck_results.csv is empty")
    if not raw_results:
        raise SystemExit("vv_online_results.csv is empty")

    profile_ids = {row["cluster_id"] for row in profiles}
    result_ids = {row["cluster_id"] for row in results}

    missing_profiles = sorted(result_ids - profile_ids)
    if missing_profiles:
        raise SystemExit(
            "deck_results.csv references missing cluster IDs: "
            + ", ".join(missing_profiles)
        )

    required_result_fields = {
        "event_date",
        "event_name",
        "placement",
        "player",
        "record_raw",
        "submitted_archetype",
        "deck_url",
        "event_url",
        "cluster_id",
        "deck_id",
    }
    actual_fields = set(results[0])
    missing_fields = sorted(required_result_fields - actual_fields)

    if missing_fields:
        raise SystemExit(
            "deck_results.csv is missing fields: "
            + ", ".join(missing_fields)
        )

    decks = json.loads(
        (DATA / "decks_normalized.json").read_text(encoding="utf-8")
    )
    if not isinstance(decks, dict) or not decks:
        raise SystemExit("decks_normalized.json is empty or malformed")

    for deck_id, deck in decks.items():
        nonlands = deck.get("nonlands", {})
        nonland_total = int(deck.get("nonland_total", -1))
        land_total = int(deck.get("land_total", -1))
        mainboard_total = int(deck.get("mainboard_total", -1))

        if sum(int(qty) for qty in nonlands.values()) != nonland_total:
            raise SystemExit(
                f"{deck_id}: nonland_total does not match card quantities"
            )

        if land_total + nonland_total != mainboard_total:
            raise SystemExit(
                f"{deck_id}: land + nonland totals do not match mainboard"
            )

    print(
        f"Validation passed: {len(raw_results)} tournament results, "
        f"{len(decks)} normalized decks, {len(profiles)} archetypes."
    )


if __name__ == "__main__":
    main()
