from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
import re

DECK_ID_RE = re.compile(r"^/decks/(?P<deck_id>[A-Za-z0-9_-]+)(?:/|$)", re.IGNORECASE)


def extract_deck_id(deck_url: str) -> str:
    match = DECK_ID_RE.match(urlparse(deck_url).path)
    if not match:
        raise ValueError(f"Could not extract deck id: {deck_url}")
    return match.group("deck_id")


def shared_slots(deck_a: dict[str, int], deck_b: dict[str, int]) -> int:
    return sum(
        min(deck_a[card], deck_b[card])
        for card in deck_a.keys() & deck_b.keys()
    )


def build_similarity_matrix(decks):
    ids = sorted(decks)
    sims = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            sims[(a, b)] = shared_slots(decks[a]["nonlands"], decks[b]["nonlands"])
    return sims


def sim(a, b, sims):
    if a == b:
        raise ValueError("Self similarity is not stored")
    return sims[(a, b) if a < b else (b, a)]


def transitive_clusters(deck_ids, sims, threshold=20):
    """
    Connected components of the >= threshold similarity graph.

    Similarity is transitive for grouping:
        A ~ B and B ~ C => A, B, C are one archetype,
    even when A and C do not directly meet the threshold.
    """
    ids = sorted(deck_ids)
    adjacency = {deck_id: set() for deck_id in ids}

    for (a, b), shared in sims.items():
        if shared >= threshold:
            adjacency[a].add(b)
            adjacency[b].add(a)

    seen = set()
    clusters = []

    for start_id in ids:
        if start_id in seen:
            continue

        stack = [start_id]
        component = set()

        while stack:
            current = stack.pop()
            if current in seen:
                continue

            seen.add(current)
            component.add(current)

            for neighbor in sorted(adjacency[current], reverse=True):
                if neighbor not in seen:
                    stack.append(neighbor)

        clusters.append(frozenset(component))

    return sorted(
        clusters,
        key=lambda c: (-len(c), tuple(sorted(c))),
    )


def representative_deck(cluster, sims):
    if len(cluster) == 1:
        return next(iter(cluster))
    scored = []
    for candidate in cluster:
        total = sum(sim(candidate, other, sims) for other in cluster if other != candidate)
        scored.append((total, candidate))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][1]


def read_results(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["deck_id"] = extract_deck_id(row["deck_url"])
    return rows


def choose_submitted_name(rows, cluster, representative):
    relevant = [r for r in rows if r["deck_id"] in cluster and r.get("submitted_archetype")]
    if not relevant:
        return ""
    counts = Counter(r["submitted_archetype"].casefold() for r in relevant)
    best = max(counts.values())
    tied = {k for k, v in counts.items() if v == best}
    for r in relevant:
        if r["deck_id"] == representative and r["submitted_archetype"].casefold() in tied:
            return r["submitted_archetype"]
    for r in relevant:
        if r["submitted_archetype"].casefold() in tied:
            return r["submitted_archetype"]
    return ""


def cluster_all(
    decks_json: Path,
    results_csv: Path,
    *,
    output_dir: Path,
    threshold: int = 20,
):
    decks = json.loads(decks_json.read_text(encoding="utf-8"))
    rows = read_results(results_csv)
    sims = build_similarity_matrix(decks)
    clusters = transitive_clusters(decks.keys(), sims, threshold=threshold)

    cluster_ids = {}
    representatives = {}
    for i, cluster in enumerate(clusters, start=1):
        cid = f"C{i:03d}"
        rep = representative_deck(cluster, sims)
        representatives[cid] = rep
        for deck_id in cluster:
            cluster_ids[deck_id] = cid

    output_dir.mkdir(parents=True, exist_ok=True)

    deck_cluster_rows = []
    for row in rows:
        deck_id = row["deck_id"]
        cid = cluster_ids.get(deck_id)
        if not cid:
            continue
        deck_cluster_rows.append(
            {
                **row,
                "cluster_id": cid,
                "representative_deck_id": representatives[cid],
                "representative_deck_name": decks[representatives[cid]].get("moxfield_name", ""),
            }
        )

    fields = list(deck_cluster_rows[0].keys()) if deck_cluster_rows else []
    with (output_dir / "deck_clusters.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(deck_cluster_rows)

    cluster_rows = []
    total_results = len(deck_cluster_rows)
    for cluster in clusters:
        rep = representative_deck(cluster, sims)
        cid = cluster_ids[rep]
        result_count = sum(1 for r in deck_cluster_rows if r["cluster_id"] == cid)

        pair_values = []
        members = sorted(cluster)
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                pair_values.append(sim(a, b, sims))

        cluster_rows.append(
            {
                "cluster_id": cid,
                "temporary_archetype_name": choose_submitted_name(rows, cluster, rep),
                "unique_deck_count": len(cluster),
                "result_count": result_count,
                "meta_percent": (100 * result_count / total_results) if total_results else 0,
                "representative_deck_id": rep,
                "representative_deck_name": decks[rep].get("moxfield_name", ""),
                "min_shared_slots": min(pair_values) if pair_values else "",
                "avg_shared_slots": (sum(pair_values) / len(pair_values)) if pair_values else "",
                "max_shared_slots": max(pair_values) if pair_values else "",
            }
        )

    cluster_rows.sort(key=lambda r: (-r["result_count"], r["cluster_id"]))
    with (output_dir / "clusters.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = list(cluster_rows[0].keys()) if cluster_rows else []
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(cluster_rows)

    return cluster_rows, deck_cluster_rows
