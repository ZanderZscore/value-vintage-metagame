from __future__ import annotations

import csv
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://vvmtg.com"
ARCHIVES = (
    ("premier", f"{BASE_URL}/category/premier-events/"),
    ("paper", f"{BASE_URL}/category/paper-events/"),
    ("online", f"{BASE_URL}/category/online-tournaments/"),
)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; ValueVintageMetagameCrawler/1.0; "
    "+https://vvmtg.com/)"
)

RESULT_PREFIX_RE = re.compile(
    r"""
    ^\s*
    (?P<placement>\d+)
    (?:st|nd|rd|th)?
    [\s.:\-–—]+
    (?P<player>.+?)
    \s*
    \(
        (?P<record>[^)]+)
    \)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

FULL_RESULT_RE = re.compile(
    r"""
    ^\s*
    (?P<placement>\d+)
    (?:st|nd|rd|th)?
    [\s.:\-–—]+
    (?P<player>.+?)
    \s*
    \(
        (?P<record>[^)]+)
    \)
    \s+
    (?P<archetype>.+?)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

RECORD_RE = re.compile(
    r"^\s*(?P<wins>\d+)\s*[-/]\s*(?P<losses>\d+)"
    r"(?:\s*[-/]\s*(?P<draws>\d+))?\s*$"
)


@dataclass(frozen=True)
class TournamentResult:
    event_date: str
    event_name: str
    event_url: str
    placement: int
    player: str
    wins: int | None
    losses: int | None
    draws: int | None
    record_raw: str
    submitted_archetype: str
    deck_url: str
    event_category: str
    source: str = "vvmtg"


CSV_FIELDS = [
    "event_date",
    "event_name",
    "event_url",
    "placement",
    "player",
    "wins",
    "losses",
    "draws",
    "record_raw",
    "submitted_archetype",
    "deck_url",
    "event_category",
    "source",
]


def clean_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split()).strip()


def parse_date_text(text: str) -> date | None:
    text = clean_text(text)
    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},\s+\d{4}",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%B %d, %Y").date()
    except ValueError:
        return None


def is_moxfield_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == "moxfield.com" or host.endswith(".moxfield.com")


class VVCrawler:
    def __init__(
        self,
        *,
        delay_seconds: float = 0.75,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

    def get_soup(self, url: str) -> BeautifulSoup:
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout_seconds)
                response.raise_for_status()
                return BeautifulSoup(response.text, "html.parser")
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.delay_seconds * attempt)
        raise RuntimeError(f"Failed to fetch {url}") from last_error

    @staticmethod
    def archive_page_url(archive_url: str, page_number: int) -> str:
        return archive_url if page_number == 1 else f"{archive_url}page/{page_number}/"

    def iter_archive_event_urls(
        self,
        archive_name: str,
        archive_url: str,
        *,
        cutoff_date: date | None = None,
        max_pages: int | None = None,
    ) -> Iterable[tuple[str, str]]:
        """
        Yield (event_url, event_category) from one VV archive.

        ARCHIVES is ordered premier -> paper -> online. The top-level crawl
        deduplicates event URLs across archives, so a premier event that also
        appears under Paper Events is classified as premier and counted once.
        """
        page_number = 1

        while True:
            if max_pages is not None and page_number > max_pages:
                return

            url = self.archive_page_url(archive_url, page_number)
            logging.info("%s archive page %d: %s", archive_name, page_number, url)
            soup = self.get_soup(url)
            entries = find_archive_entries(soup)
            if not entries:
                return

            dated = 0
            in_range = 0

            for event_url, posted_date in entries:
                if posted_date is not None:
                    dated += 1
                    if cutoff_date and posted_date < cutoff_date:
                        continue

                in_range += 1
                yield event_url, archive_name

            if cutoff_date and dated and in_range == 0:
                return

            if not find_next_archive_page(soup):
                return

            page_number += 1
            time.sleep(self.delay_seconds)

    def iter_event_urls(
        self,
        *,
        cutoff_date: date | None = None,
        max_pages: int | None = None,
    ) -> Iterable[tuple[str, str]]:
        seen: set[str] = set()

        for archive_name, archive_url in ARCHIVES:
            for event_url, event_category in self.iter_archive_event_urls(
                archive_name,
                archive_url,
                cutoff_date=cutoff_date,
                max_pages=max_pages,
            ):
                if event_url in seen:
                    continue

                seen.add(event_url)
                yield event_url, event_category

    def parse_event(
        self,
        event_url: str,
        event_category: str,
    ) -> list[TournamentResult]:
        soup = self.get_soup(event_url)
        event_name = parse_event_name(soup)
        event_date = parse_event_date(soup)
        event_date_str = event_date.isoformat() if event_date else ""

        rows = parse_result_rows(
            soup,
            event_date=event_date_str,
            event_name=event_name,
            event_url=event_url,
            event_category=event_category,
        )

        logging.info(
            "Parsed %d decks from %s [%s]",
            len(rows),
            event_name,
            event_category,
        )
        return rows

    def crawl(
        self,
        *,
        cutoff_date: date | None = None,
        max_pages: int | None = None,
    ) -> list[TournamentResult]:
        rows: list[TournamentResult] = []

        for event_url, event_category in self.iter_event_urls(
            cutoff_date=cutoff_date,
            max_pages=max_pages,
        ):
            try:
                event_rows = self.parse_event(event_url, event_category)
            except Exception:
                logging.exception("Failed to parse event: %s", event_url)
                continue

            if cutoff_date and event_rows and event_rows[0].event_date:
                if date.fromisoformat(event_rows[0].event_date) < cutoff_date:
                    continue

            rows.extend(event_rows)
            time.sleep(self.delay_seconds)

        rows = deduplicate_results(rows)
        rows.sort(
            key=lambda row: (
                -date.fromisoformat(row.event_date).toordinal()
                if row.event_date
                else 0,
                row.event_name.casefold(),
                row.placement,
            )
        )
        return rows


def find_archive_entries(soup: BeautifulSoup) -> list[tuple[str, date | None]]:
    entries: list[tuple[str, date | None]] = []
    containers = list(soup.find_all("article"))

    if not containers:
        containers = [
            tag for tag in soup.find_all(["div", "section"])
            if tag.find(["h2", "h3"]) is not None
        ]

    for container in containers:
        heading = container.find(["h1", "h2", "h3"])
        if not heading:
            continue
        link = heading.find("a", href=True)
        if not link:
            continue

        href = urljoin(BASE_URL, link["href"])
        if urlparse(href).netloc.lower() not in {"vvmtg.com", "www.vvmtg.com"}:
            continue

        posted_date = parse_date_text(container.get_text(" ", strip=True))
        entries.append((href, posted_date))

    seen = set()
    out = []
    for item in entries:
        if item[0] not in seen:
            seen.add(item[0])
            out.append(item)
    return out


def find_next_archive_page(soup: BeautifulSoup) -> str | None:
    link = soup.find("a", attrs={"rel": lambda v: v and "next" in v})
    if link and link.get("href"):
        return urljoin(BASE_URL, link["href"])

    for link in soup.find_all("a", href=True):
        text = clean_text(link.get_text(" ", strip=True)).lower()
        if text in {"next", "next page", "older posts", "older"}:
            return urljoin(BASE_URL, link["href"])
    return None


def parse_event_name(soup: BeautifulSoup) -> str:
    heading = soup.find("h1")
    if heading:
        value = clean_text(heading.get_text(" ", strip=True))
        if value and value.lower() != "value vintage":
            return value

    title = soup.find("title")
    if title:
        return re.sub(
            r"\s*[–—|-]\s*Value Vintage\s*$",
            "",
            clean_text(title.get_text(" ", strip=True)),
        )
    return ""


def parse_event_date(soup: BeautifulSoup) -> date | None:
    for time_tag in soup.find_all("time"):
        dt = time_tag.get("datetime")
        if dt:
            try:
                return datetime.fromisoformat(dt.replace("Z", "+00:00")).date()
            except ValueError:
                pass
        parsed = parse_date_text(time_tag.get_text(" ", strip=True))
        if parsed:
            return parsed

    for selector in (".entry-date", ".posted-on", ".entry-meta", ".post-meta"):
        node = soup.select_one(selector)
        if node:
            parsed = parse_date_text(node.get_text(" ", strip=True))
            if parsed:
                return parsed

    return parse_date_text(soup.get_text(" ", strip=True))


def parse_record(record_raw: str):
    match = RECORD_RE.match(clean_text(record_raw))
    if not match:
        return None, None, None
    return (
        int(match.group("wins")),
        int(match.group("losses")),
        int(match.group("draws")) if match.group("draws") else 0,
    )


def preceding_result_prefix(anchor: Tag) -> str:
    fragments = []
    for sibling in anchor.previous_siblings:
        if isinstance(sibling, Tag):
            if sibling.name in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
                break
            text = sibling.get_text(" ", strip=True)
        else:
            text = str(sibling)

        text = clean_text(text)
        if text:
            fragments.append(text)

        combined = clean_text(" ".join(reversed(fragments)))
        if ")" in combined:
            break

    prefix = clean_text(" ".join(reversed(fragments)))
    if prefix:
        return prefix

    parent = anchor.parent
    if isinstance(parent, Tag):
        full = clean_text(parent.get_text(" ", strip=True))
        archetype = clean_text(anchor.get_text(" ", strip=True))
        if full.endswith(archetype):
            return clean_text(full[: -len(archetype)])
    return ""


def parse_result_rows(
    soup: BeautifulSoup,
    *,
    event_date: str,
    event_name: str,
    event_url: str,
    event_category: str,
) -> list[TournamentResult]:
    results = []

    for anchor in soup.find_all("a", href=True):
        deck_url = urljoin(event_url, anchor["href"])
        if not is_moxfield_url(deck_url):
            continue

        submitted_archetype = clean_text(anchor.get_text(" ", strip=True))
        if not submitted_archetype:
            continue

        prefix = preceding_result_prefix(anchor)
        match = RESULT_PREFIX_RE.match(prefix)

        if match is None:
            parent = anchor.parent
            full_text = (
                clean_text(parent.get_text(" ", strip=True))
                if isinstance(parent, Tag)
                else ""
            )
            full_match = FULL_RESULT_RE.match(full_text)
            if full_match is None:
                logging.warning("Could not parse row: %r (%s)", full_text or prefix, deck_url)
                continue
            placement = int(full_match.group("placement"))
            player = clean_text(full_match.group("player"))
            record_raw = clean_text(full_match.group("record"))
        else:
            placement = int(match.group("placement"))
            player = clean_text(match.group("player"))
            record_raw = clean_text(match.group("record"))

        wins, losses, draws = parse_record(record_raw)

        results.append(
            TournamentResult(
                event_date=event_date,
                event_name=event_name,
                event_url=event_url,
                placement=placement,
                player=player,
                wins=wins,
                losses=losses,
                draws=draws,
                record_raw=record_raw,
                submitted_archetype=submitted_archetype,
                deck_url=deck_url,
                event_category=event_category,
            )
        )
    return results


def deduplicate_results(rows):
    seen = set()
    output = []
    for row in rows:
        key = (row.event_url, row.placement, row.player.casefold(), row.deck_url)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def write_results_csv(rows: Iterable[TournamentResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
