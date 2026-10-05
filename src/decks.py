from __future__ import annotations

import csv
import json
import logging
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

MOXFIELD_ENDPOINTS = (
    "https://api2.moxfield.com/v3/decks/all/{deck_id}",
    "https://api2.moxfield.com/v2/decks/all/{deck_id}",
    "https://api.moxfield.com/v2/decks/all/{deck_id}",
)
SCRYFALL_BY_ID = "https://api.scryfall.com/cards/{scryfall_id}"
SCRYFALL_NAMED = "https://api.scryfall.com/cards/named"
DEFAULT_USER_AGENT = "ValueVintageMetagame/1.0"
DECK_ID_RE = re.compile(r"^/decks/(?P<deck_id>[A-Za-z0-9_-]+)(?:/|$)", re.IGNORECASE)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def extract_deck_id(deck_url: str) -> str:
    parsed = urlparse(deck_url)
    match = DECK_ID_RE.match(parsed.path)
    if not match:
        raise ValueError(f"Could not extract Moxfield deck id: {deck_url}")
    return match.group("deck_id")


def is_land_type_line(type_line: str) -> bool:
    for face in clean_text(type_line).split("//"):
        card_types = re.split(r"\s+[—-]\s+", face.strip(), maxsplit=1)[0]
        tokens = re.findall(r"[A-Za-z]+", card_types)
        if any(token.casefold() == "land" for token in tokens):
            return True
    return False


class MoxfieldClient:
    def __init__(
        self,
        *,
        cache_dir: Path,
        delay_seconds: float = 0.75,
        timeout_seconds: float = 25.0,
        bearer_token: str | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": os.environ.get("MOXFIELD_USER_AGENT", DEFAULT_USER_AGENT),
                "Accept": "application/json",
            }
        )
        if bearer_token:
            self.session.headers["Authorization"] = f"Bearer {bearer_token}"

    def fetch(self, deck_id: str, *, refresh: bool = False) -> dict[str, Any]:
        cache = self.cache_dir / f"{deck_id}.json"
        if cache.exists() and not refresh:
            return json.loads(cache.read_text(encoding="utf-8"))

        errors = []
        for endpoint in MOXFIELD_ENDPOINTS:
            url = endpoint.format(deck_id=deck_id)
            try:
                response = self.session.get(url, timeout=self.timeout_seconds)
                if response.status_code in {401, 403, 404}:
                    errors.append(f"{url}: HTTP {response.status_code}")
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Expected JSON object")
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                time.sleep(self.delay_seconds)
                return payload
            except Exception as exc:
                errors.append(f"{url}: {exc}")

        hint = ""
        if any("401" in e or "403" in e for e in errors):
            hint = " Set MOXFIELD_BEARER_TOKEN if Moxfield is blocking anonymous API access."
        raise RuntimeError(f"Could not fetch Moxfield deck {deck_id}.{hint}\n" + "\n".join(errors))


class ScryfallClient:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        self.cache = {}
        if cache_path.exists():
            try:
                self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                self.cache = {}
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"})

    def _flush(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=2), encoding="utf-8")

    def lookup(self, card_name: str, scryfall_id: str | None) -> dict[str, Any]:
        key = f"id:{scryfall_id}" if scryfall_id else f"name:{card_name.casefold()}"
        if key in self.cache:
            return self.cache[key]

        if scryfall_id:
            response = self.session.get(SCRYFALL_BY_ID.format(scryfall_id=scryfall_id), timeout=20)
        else:
            response = self.session.get(SCRYFALL_NAMED, params={"exact": card_name}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        self.cache[key] = payload
        self._flush()
        time.sleep(0.12)
        return payload


def get_mainboard(payload: dict[str, Any]) -> dict[str, Any]:
    direct = payload.get("mainboard")
    if isinstance(direct, dict):
        return direct

    boards = payload.get("boards")
    if isinstance(boards, dict):
        main = boards.get("mainboard")
        if isinstance(main, dict):
            cards = main.get("cards")
            if isinstance(cards, dict):
                return cards
            if all(isinstance(v, dict) for v in main.values()):
                return main

    raise ValueError("Moxfield response has no recognizable mainboard")


def get_card_data(entry_key: str, entry: dict[str, Any]):
    quantity = int(entry.get("quantity", 1))
    card = entry.get("card") if isinstance(entry.get("card"), dict) else entry
    name = clean_text(card.get("name")) or clean_text(entry_key)
    type_line = clean_text(card.get("type_line") or card.get("typeLine"))
    scryfall_id = clean_text(
        card.get("scryfall_id") or card.get("scryfallId") or card.get("scryfallIdString")
    ) or None
    return name, quantity, type_line, scryfall_id


def read_unique_decks(results_csv: Path):
    seen = set()
    decks = []
    with results_csv.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            deck_url = clean_text(row.get("deck_url"))
            if not deck_url:
                continue
            deck_id = extract_deck_id(deck_url)
            if deck_id not in seen:
                seen.add(deck_id)
                decks.append((deck_id, deck_url))
    return decks


def normalize_all_decks(
    results_csv: Path,
    *,
    output_dir: Path,
    refresh: bool = False,
    delay_seconds: float = 0.75,
):
    raw_dir = output_dir / "decklists_raw"
    moxfield = MoxfieldClient(
        cache_dir=raw_dir,
        delay_seconds=delay_seconds,
        bearer_token=os.environ.get("MOXFIELD_BEARER_TOKEN"),
    )
    scryfall = ScryfallClient(output_dir / "card_cache.json")

    normalized = {}
    card_rows = []
    failures = []

    unique = read_unique_decks(results_csv)
    logging.info("Found %d unique Moxfield decks", len(unique))

    for i, (deck_id, deck_url) in enumerate(unique, start=1):
        logging.info("[%d/%d] %s", i, len(unique), deck_url)
        try:
            payload = moxfield.fetch(deck_id, refresh=refresh)
            mainboard = get_mainboard(payload)

            nonlands = Counter()
            mainboard_total = 0
            land_total = 0

            for entry_key, entry in mainboard.items():
                if not isinstance(entry, dict):
                    continue

                name, quantity, type_line, scryfall_id = get_card_data(str(entry_key), entry)
                if quantity <= 0:
                    continue

                if not type_line:
                    sf = scryfall.lookup(name, scryfall_id)
                    type_line = clean_text(sf.get("type_line"))
                    scryfall_id = scryfall_id or clean_text(sf.get("id")) or None

                mainboard_total += quantity
                if is_land_type_line(type_line):
                    land_total += quantity
                    continue

                nonlands[name] += quantity
                card_rows.append(
                    {
                        "deck_id": deck_id,
                        "deck_url": deck_url,
                        "card_name": name,
                        "quantity": quantity,
                        "type_line": type_line,
                        "scryfall_id": scryfall_id or "",
                        "image_url": (
                            f"https://api.scryfall.com/cards/{scryfall_id}"
                            "?format=image&version=normal"
                            if scryfall_id else ""
                        ),
                    }
                )

            normalized[deck_id] = {
                "deck_id": deck_id,
                "deck_url": deck_url,
                "moxfield_name": clean_text(payload.get("name")),
                "mainboard_total": mainboard_total,
                "land_total": land_total,
                "nonland_total": sum(nonlands.values()),
                "nonlands": dict(sorted(nonlands.items())),
            }
        except Exception as exc:
            logging.exception("Failed deck %s", deck_id)
            failures.append(
                {
                    "deck_id": deck_id,
                    "deck_url": deck_url,
                    "error": clean_text(exc),
                }
            )

    (output_dir / "decks_normalized.json").write_text(
        json.dumps(normalized, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with (output_dir / "deck_cards.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "deck_id",
            "deck_url",
            "card_name",
            "quantity",
            "type_line",
            "scryfall_id",
            "image_url",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(card_rows)

    with (output_dir / "deck_fetch_failures.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["deck_id", "deck_url", "error"])
        writer.writeheader()
        writer.writerows(failures)

    return normalized, card_rows, failures
