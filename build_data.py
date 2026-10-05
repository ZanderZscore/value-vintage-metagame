#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

from src.vv_crawler import VVCrawler, write_results_csv
from src.decks import normalize_all_decks
from src.clustering import cluster_all
from src.profiles import build_profiles


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build all data required by the Value Vintage Streamlit app."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="How many days of VV online results to crawl (default: 90).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Working/cache directory (default: data).",
    )
    parser.add_argument(
        "--app-data-dir",
        type=Path,
        default=Path("app_data"),
        help="Final Streamlit data directory (default: app_data).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=20,
        help="Shared nonland card-slot threshold (default: 20).",
    )
    parser.add_argument(
        "--refresh-decks",
        action="store_true",
        help="Redownload Moxfield deck JSON instead of using cache.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional VV archive page limit for debugging.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    args.data_dir.mkdir(parents=True, exist_ok=True)
    args.app_data_dir.mkdir(parents=True, exist_ok=True)

    cutoff = date.today() - timedelta(days=args.days)

    print("\n[1/4] Crawling VV online tournament results")
    crawler = VVCrawler()
    results = crawler.crawl(
        cutoff_date=cutoff,
        max_pages=args.max_pages,
    )
    results_csv = args.data_dir / "vv_online_results.csv"
    write_results_csv(results, results_csv)
    print(f"  {len(results)} tournament deck results -> {results_csv}")

    print("\n[2/4] Fetching/caching and normalizing Moxfield decks")
    decks, card_rows, failures = normalize_all_decks(
        results_csv,
        output_dir=args.data_dir,
        refresh=args.refresh_decks,
    )
    print(f"  {len(decks)} normalized decks")
    if failures:
        print(f"  WARNING: {len(failures)} deck fetch failures")

    print("\n[3/4] Clustering decks")
    clustering_dir = args.data_dir / "clustering"
    cluster_rows, deck_cluster_rows = cluster_all(
        args.data_dir / "decks_normalized.json",
        results_csv,
        output_dir=clustering_dir,
        threshold=args.threshold,
    )
    print(f"  {len(cluster_rows)} clusters")

    print("\n[4/4] Building Streamlit archetype profiles")
    profiles = build_profiles(
        clustering_dir / "clusters.csv",
        clustering_dir / "deck_clusters.csv",
        args.data_dir / "decks_normalized.json",
        args.data_dir / "deck_cards.csv",
        raw_deck_dir=args.data_dir / "decklists_raw",
        output_dir=args.app_data_dir,
    )

    # The Streamlit app needs original tournament rows + cluster assignment.
    # Copy the complete joined result table into app_data.
    (args.app_data_dir / "deck_results.csv").write_bytes(
        (clustering_dir / "deck_clusters.csv").read_bytes()
    )
    (args.app_data_dir / "vv_online_results.csv").write_bytes(
        results_csv.read_bytes()
    )

    print(f"  {len(profiles)} profiles -> {args.app_data_dir}")
    print("\nDone.")
    print("Run the app with:")
    print("  streamlit run app.py")


if __name__ == "__main__":
    main()
