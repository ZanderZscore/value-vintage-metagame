from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

COLOR_NAMES = {
    frozenset(): "Colorless",
    frozenset({"W"}): "Mono White",
    frozenset({"U"}): "Mono Blue",
    frozenset({"B"}): "Mono Black",
    frozenset({"R"}): "Mono Red",
    frozenset({"G"}): "Mono Green",
    frozenset({"W", "U"}): "Azorius",
    frozenset({"U", "B"}): "Dimir",
    frozenset({"B", "R"}): "Rakdos",
    frozenset({"R", "G"}): "Gruul",
    frozenset({"G", "W"}): "Selesnya",
    frozenset({"W", "B"}): "Orzhov",
    frozenset({"U", "R"}): "Izzet",
    frozenset({"B", "G"}): "Golgari",
    frozenset({"R", "W"}): "Boros",
    frozenset({"G", "U"}): "Simic",
    frozenset({"W", "U", "G"}): "Bant",
    frozenset({"W", "U", "B"}): "Esper",
    frozenset({"U", "B", "R"}): "Grixis",
    frozenset({"B", "R", "G"}): "Jund",
    frozenset({"R", "G", "W"}): "Naya",
    frozenset({"W", "B", "G"}): "Abzan",
    frozenset({"W", "U", "R"}): "Jeskai",
    frozenset({"U", "B", "G"}): "Sultai",
    frozenset({"W", "B", "R"}): "Mardu",
    frozenset({"U", "R", "G"}): "Temur",
}

NAME_TO_COLORS = {
    "azorius": {"W", "U"}, "uw": {"W", "U"}, "wu": {"W", "U"},
    "dimir": {"U", "B"}, "ub": {"U", "B"}, "bu": {"U", "B"},
    "rakdos": {"B", "R"}, "rb": {"B", "R"}, "br": {"B", "R"},
    "gruul": {"R", "G"}, "rg": {"R", "G"}, "gr": {"R", "G"},
    "selesnya": {"G", "W"}, "gw": {"G", "W"}, "wg": {"G", "W"},
    "orzhov": {"W", "B"}, "wb": {"W", "B"}, "bw": {"W", "B"},
    "izzet": {"U", "R"}, "ur": {"U", "R"}, "ru": {"U", "R"},
    "golgari": {"B", "G"}, "bg": {"B", "G"}, "gb": {"B", "G"},
    "boros": {"R", "W"}, "rw": {"R", "W"}, "wr": {"R", "W"},
    "simic": {"G", "U"}, "gu": {"G", "U"}, "ug": {"G", "U"},
    "bant": {"W", "U", "G"}, "esper": {"W", "U", "B"},
    "grixis": {"U", "B", "R"}, "jund": {"B", "R", "G"},
    "naya": {"R", "G", "W"}, "abzan": {"W", "B", "G"},
    "jeskai": {"W", "U", "R"}, "sultai": {"U", "B", "G"},
    "mardu": {"W", "B", "R"}, "temur": {"U", "R", "G"},
    "mono white": {"W"}, "mono w": {"W"},
    "mono blue": {"U"}, "mono u": {"U"},
    "mono black": {"B"}, "mono b": {"B"},
    "mono red": {"R"}, "mono r": {"R"},
    "mono green": {"G"}, "mono g": {"G"},
}
COLOR_PREFIXES = sorted(NAME_TO_COLORS, key=len, reverse=True)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def parse_color_prefix(name: str):
    original = clean_text(name)
    folded = original.casefold()
    for prefix in COLOR_PREFIXES:
        pf = prefix.casefold()
        if folded == pf:
            return set(NAME_TO_COLORS[prefix]), ""
        if folded.startswith(pf + " "):
            return set(NAME_TO_COLORS[prefix]), clean_text(original[len(prefix):].strip(" -–—:/"))
    return None, original


def canonical_color_name(colors):
    return COLOR_NAMES.get(frozenset(colors), "")


def normalized_stem(stem: str):
    stem = re.sub(r"^[\W_]+|[\W_]+$", "", clean_text(stem)).casefold()
    stem = re.sub(r"[^a-z0-9]+", " ", stem)
    return " ".join(stem.split())


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _entry_quantity(entry: dict[str, Any]) -> int:
    try:
        return int(entry.get("quantity", 1))
    except (TypeError, ValueError):
        return 1


def _card_object(entry: dict[str, Any]) -> dict[str, Any]:
    card = entry.get("card")
    return card if isinstance(card, dict) else entry


def _type_line(card: dict[str, Any]) -> str:
    return clean_text(card.get("type_line") or card.get("typeLine"))


def _is_land(card: dict[str, Any]) -> bool:
    type_line = _type_line(card)
    if not type_line:
        return False

    for face in type_line.split("//"):
        card_types = re.split(r"\s+[—-]\s+", face.strip(), maxsplit=1)[0]
        tokens = re.findall(r"[A-Za-z]+", card_types)
        if any(token.casefold() == "land" for token in tokens):
            return True

    return False


def _produced_colors(card: dict[str, Any]) -> set[str]:
    """
    Return colors the card can produce, preferring Scryfall-style
    `produced_mana` metadata.

    Fall back to land color identity only when produced-mana metadata is absent.
    This intentionally does NOT use the spell's own colors.
    """
    for key in ("produced_mana", "producedMana"):
        value = card.get(key)
        if isinstance(value, list):
            return {
                str(color).upper()
                for color in value
                if str(color).upper() in {"W", "U", "B", "R", "G"}
            }

    for key in ("color_identity", "colorIdentity"):
        value = card.get(key)
        if isinstance(value, list):
            return {
                str(color).upper()
                for color in value
                if str(color).upper() in {"W", "U", "B", "R", "G"}
            }

    return set()


def infer_raw_colors(raw_path: Path):
    """
    Infer practical deck colors from the MAINBOARD MANA BASE.

    Why mana-base first?
    --------------------
    Spell color/color-identity is too aggressive for deck naming. For example,
    a mono-blue deck can play Expansion // Explosion only for the hybrid-blue
    Expansion half. Counting the split card's colors would incorrectly make
    the deck Izzet.

    Instead:
      * inspect mainboard lands;
      * weight colors by the number of land slots that can produce them;
      * require meaningful support before calling a color part of the deck;
      * ignore spell colors entirely when the mana base is informative.

    A color is included when at least:
      max(2 land slots, 10% of all mainboard land slots)
    can produce that color.

    If there is colored mana production but nothing clears that threshold,
    use the single best-supported color as a conservative fallback.

    Returns:
        set[str] | None
        None means the raw deck did not contain enough mana-base metadata.
    """
    if not raw_path.exists():
        return None

    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    board = payload.get("mainboard")
    if not isinstance(board, dict):
        boards = payload.get("boards", {})
        main = boards.get("mainboard", {}) if isinstance(boards, dict) else {}
        board = main.get("cards", main) if isinstance(main, dict) else None

    if not isinstance(board, dict):
        return None

    support = Counter()
    total_land_slots = 0
    saw_land_metadata = False

    for entry in board.values():
        if not isinstance(entry, dict):
            continue

        card = _card_object(entry)
        if not _is_land(card):
            continue

        quantity = max(0, _entry_quantity(entry))
        if quantity == 0:
            continue

        total_land_slots += quantity

        # The presence of a recognizable land is itself useful metadata, even
        # if that specific land (e.g. a fetch land) does not directly produce
        # colored mana.
        saw_land_metadata = True

        for color in _produced_colors(card):
            support[color] += quantity

    if not saw_land_metadata:
        return None

    if not support:
        # Land metadata exists, but no usable produced-mana/color-identity
        # metadata was found. Let the naming fall back to submitted names.
        return None

    minimum_support = max(2, int(math.ceil(total_land_slots * 0.10)))

    inferred = {
        color
        for color, count in support.items()
        if count >= minimum_support
    }

    if inferred:
        return inferred

    # Conservative fallback: choose only the best-supported color(s).
    max_support = max(support.values())
    leaders = {color for color, count in support.items() if count == max_support}

    # If several colors tie from a single rainbow source, that is not strong
    # enough evidence to declare a multicolor deck.
    if len(leaders) == 1:
        return leaders

    return None

def choose_name(cluster_rows, decks, representative_id, raw_deck_dir: Path | None):
    stem_votes = Counter()
    stem_display = defaultdict(Counter)
    color_votes = Counter()
    rep_stem_keys = []
    rep_colors = []

    for row in cluster_rows:
        submitted = clean_text(row.get("submitted_archetype"))
        if submitted:
            colors, stem = parse_color_prefix(submitted)
            key = normalized_stem(stem or submitted)
            if key:
                stem_votes[key] += 3
                stem_display[key][stem or submitted] += 1
                if row["deck_id"] == representative_id:
                    rep_stem_keys.append(key)
            if colors is not None:
                f = frozenset(colors)
                color_votes[f] += 4
                if row["deck_id"] == representative_id:
                    rep_colors.append(f)

    member_ids = sorted({r["deck_id"] for r in cluster_rows})
    for deck_id in member_ids:
        mox_name = clean_text(decks.get(deck_id, {}).get("moxfield_name"))
        title = re.split(r"\s+by\s+", mox_name, maxsplit=1, flags=re.IGNORECASE)[0] if mox_name else ""
        if title:
            colors, stem = parse_color_prefix(title)
            key = normalized_stem(stem or title)
            if key:
                stem_votes[key] += 1
                stem_display[key][stem or title] += 1
                if deck_id == representative_id:
                    rep_stem_keys.append(key)
            if colors is not None:
                f = frozenset(colors)
                color_votes[f] += 1
                if deck_id == representative_id:
                    rep_colors.append(f)

        if raw_deck_dir:
            raw_colors = infer_raw_colors(raw_deck_dir / f"{deck_id}.json")
            if raw_colors is not None:
                f = frozenset(raw_colors)
                # Mana-base inference is strong evidence, but explicit
                # submitted color labels remain the highest-priority signal
                # when several results consistently agree.
                color_votes[f] += 2
                if deck_id == representative_id:
                    rep_colors.append(f)

    if stem_votes:
        best = max(stem_votes.values())
        tied = {k for k, v in stem_votes.items() if v == best}
        chosen_key = next((k for k in rep_stem_keys if k in tied), None)
        if chosen_key is None:
            chosen_key = sorted(tied, key=lambda k: (len(k.split()), len(k), k))[0]
        forms = stem_display[chosen_key]
        max_count = max(forms.values())
        stem = sorted([f for f, c in forms.items() if c == max_count], key=lambda x: (len(x), x.casefold()))[0]
    else:
        stem = "Unknown"

    color_name = ""
    if color_votes:
        best = max(color_votes.values())
        tied = {k for k, v in color_votes.items() if v == best}
        chosen = next((c for c in rep_colors if c in tied), None)
        if chosen is None:
            chosen = sorted(tied, key=lambda c: (len(c), "".join(sorted(c))))[0]
        color_name = canonical_color_name(chosen)

    if color_name and not stem.casefold().startswith(color_name.casefold() + " "):
        name = f"{color_name} {stem}".strip()
    else:
        name = stem

    return name, color_name, stem


def signature_cards(member_ids, decks, top_n=3):
    total_decks = len(decks)
    global_freq = Counter()
    for deck in decks.values():
        for card in deck.get("nonlands", {}):
            global_freq[card] += 1

    present = Counter()
    copies = Counter()
    for deck_id in member_ids:
        for card, qty in decks[deck_id].get("nonlands", {}).items():
            present[card] += 1
            copies[card] += int(qty)

    scored = []
    for card, p in present.items():
        inclusion = p / len(member_ids)
        avg_copies = copies[card] / p
        inv = math.log((total_decks + 1) / (global_freq[card] + 1) + 1)
        score = inclusion * avg_copies * inv
        scored.append((score, inclusion, avg_copies, card))

    scored.sort(key=lambda x: (-x[0], -x[1], -x[2], x[3].casefold()))
    return [x[3] for x in scored[:top_n]]


def build_profiles(
    clusters_csv: Path,
    deck_clusters_csv: Path,
    decks_json: Path,
    deck_cards_csv: Path,
    *,
    raw_deck_dir: Path | None,
    output_dir: Path,
):
    clusters = read_csv(clusters_csv)
    deck_rows = read_csv(deck_clusters_csv)
    decks = json.loads(decks_json.read_text(encoding="utf-8"))
    card_rows = read_csv(deck_cards_csv)

    image_by_card = {}
    for row in card_rows:
        if row.get("image_url"):
            image_by_card.setdefault(row["card_name"], row["image_url"])

    rows_by_cluster = defaultdict(list)
    for row in deck_rows:
        rows_by_cluster[row["cluster_id"]].append(row)

    profiles = []
    for cluster in clusters:
        cid = cluster["cluster_id"]
        rows = rows_by_cluster[cid]
        rep = cluster["representative_deck_id"]
        member_ids = {r["deck_id"] for r in rows}
        name, color, stem = choose_name(rows, decks, rep, raw_deck_dir)
        cards = signature_cards(member_ids, decks, top_n=3)

        profiles.append(
            {
                **cluster,
                "archetype_name": name,
                "color_name": color,
                "archetype_stem": stem,
                "signature_card_1": cards[0] if len(cards) > 0 else "",
                "signature_card_2": cards[1] if len(cards) > 1 else "",
                "signature_card_3": cards[2] if len(cards) > 2 else "",
                "signature_image_url": image_by_card.get(cards[0], "") if cards else "",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "archetype_profiles.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(profiles[0].keys()) if profiles else [])
        writer.writeheader()
        writer.writerows(profiles)

    (output_dir / "archetype_profiles.json").write_text(
        json.dumps(profiles, indent=2),
        encoding="utf-8",
    )
    return profiles
