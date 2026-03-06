#!/usr/bin/env python3
"""Enrich a YouTube subscriptions CSV with metadata fetched from YouTube Data API."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
DEFAULT_INPUT = "subscriptions_2026-03-05.csv"
REQUEST_TIMEOUT_SECONDS = 25
MAX_CHANNEL_BATCH = 50

TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "you",
    "your",
}

# These buckets intentionally stay broad because many channels are multi-topic.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Technology": (
        "ai",
        "artificial intelligence",
        "software",
        "programming",
        "coding",
        "developer",
        "tech",
        "startup",
        "open source",
        "machine learning",
    ),
    "Business": (
        "business",
        "entrepreneur",
        "startup",
        "marketing",
        "sales",
        "finance",
        "investing",
        "economy",
        "career",
    ),
    "Education": (
        "learn",
        "tutorial",
        "course",
        "explained",
        "lesson",
        "education",
        "study",
        "guide",
    ),
    "Science": (
        "science",
        "physics",
        "biology",
        "chemistry",
        "space",
        "research",
        "experiment",
        "neuroscience",
    ),
    "Sports": (
        "sports",
        "football",
        "soccer",
        "basketball",
        "nfl",
        "nba",
        "premier league",
        "highlights",
        "scouting",
        "match",
    ),
    "Gaming": (
        "gaming",
        "gameplay",
        "stream",
        "esports",
        "xbox",
        "playstation",
        "nintendo",
        "minecraft",
        "fortnite",
    ),
    "Health & Fitness": (
        "fitness",
        "workout",
        "nutrition",
        "diet",
        "health",
        "wellness",
        "mental health",
    ),
    "News & Politics": (
        "news",
        "politics",
        "policy",
        "election",
        "government",
        "geopolitics",
        "commentary",
    ),
    "Music": (
        "music",
        "song",
        "album",
        "artist",
        "beats",
        "remix",
        "concert",
        "record",
    ),
    "Entertainment": (
        "comedy",
        "interview",
        "podcast",
        "entertainment",
        "reaction",
        "vlog",
        "show",
    ),
    "Film & Animation": (
        "film",
        "movie",
        "cinema",
        "animation",
        "short film",
        "documentary",
    ),
    "Lifestyle": (
        "lifestyle",
        "self improvement",
        "habits",
        "productivity",
        "daily",
        "minimalism",
        "motivation",
    ),
    "Travel": ("travel", "trip", "tour", "destination", "backpacking"),
    "Food": ("food", "cooking", "recipe", "chef", "kitchen"),
}

TOPIC_HINTS: dict[str, str] = {
    "music": "Music",
    "film": "Film & Animation",
    "entertainment": "Entertainment",
    "science": "Science",
    "technology": "Technology",
    "knowledge": "Education",
    "sports": "Sports",
    "soccer": "Sports",
    "gaming": "Gaming",
    "lifestyle": "Lifestyle",
    "fitness": "Health & Fitness",
    "politics": "News & Politics",
    "news": "News & Politics",
    "business": "Business",
    "food": "Food",
    "travel": "Travel",
}


@dataclass(slots=True)
class YouTubeClient:
    """Minimal YouTube Data API client with retry and backoff support."""

    api_key: str
    retries: int
    timeout_seconds: int
    sleep_seconds: float

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query_params = dict(params)
        query_params["key"] = self.api_key
        url = f"{YOUTUBE_API_BASE}/{path}?{urlencode(query_params, doseq=True)}"

        for attempt in range(1, self.retries + 2):
            try:
                request = Request(url, headers={"User-Agent": "channel-enricher/1.0"})
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = response.read().decode("utf-8")
                return json.loads(payload)
            except HTTPError as error:
                body = ""
                try:
                    body = error.read().decode("utf-8", errors="ignore")
                except Exception:
                    body = ""
                lowered_body = body.lower()

                if (
                    path == "playlistItems"
                    and error.code == 404
                    and query_params.get("playlistId")
                ):
                    # Some channels expose an uploads playlist id that later becomes
                    # unavailable (deleted/private/inconsistent). This should not halt
                    # the full CSV enrichment run, so treat it as "no recent uploads".
                    logging.warning(
                        "Uploads playlist %s was not found (404); continuing without recent titles.",
                        query_params["playlistId"],
                    )
                    return {"items": []}

                if error.code in TRANSIENT_HTTP_CODES and attempt <= self.retries:
                    backoff = self.sleep_seconds * attempt
                    logging.warning(
                        "Transient API error %s on %s, retrying in %.2fs (attempt %s/%s)",
                        error.code,
                        path,
                        backoff,
                        attempt,
                        self.retries + 1,
                    )
                    time.sleep(backoff)
                    continue

                if error.code == 403 and "quota" in lowered_body:
                    raise RuntimeError(
                        "YouTube API quota exceeded. Try again after quota reset."
                    ) from error

                raise RuntimeError(
                    f"YouTube API request failed ({error.code}) for {path}: {body[:200]}"
                ) from error
            except URLError as error:
                if attempt <= self.retries:
                    backoff = self.sleep_seconds * attempt
                    logging.warning(
                        "Network error on %s, retrying in %.2fs (attempt %s/%s): %s",
                        path,
                        backoff,
                        attempt,
                        self.retries + 1,
                        error,
                    )
                    time.sleep(backoff)
                    continue
                raise RuntimeError(f"Network error for {path}: {error}") from error

        raise RuntimeError(f"Failed request for {path} after retries")

    def fetch_channels(self, channel_ids: list[str]) -> dict[str, dict[str, Any]]:
        channels_by_id: dict[str, dict[str, Any]] = {}
        total = len(channel_ids)

        for index, batch in enumerate(chunked(channel_ids, MAX_CHANNEL_BATCH), start=1):
            data = self._get_json(
                "channels",
                {
                    "part": "snippet,statistics,topicDetails,contentDetails",
                    "id": ",".join(batch),
                    "maxResults": MAX_CHANNEL_BATCH,
                },
            )
            for item in data.get("items", []):
                channel_id = item.get("id")
                if channel_id:
                    channels_by_id[channel_id] = item

            logging.info(
                "Fetched channel batch %s (%s channels processed of %s)",
                index,
                min(index * MAX_CHANNEL_BATCH, total),
                total,
            )
            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)

        return channels_by_id

    def fetch_recent_titles(self, uploads_playlist_id: str, max_videos: int) -> list[str]:
        if max_videos <= 0:
            return []

        data = self._get_json(
            "playlistItems",
            {
                "part": "snippet",
                "playlistId": uploads_playlist_id,
                "maxResults": max_videos,
            },
        )
        titles: list[str] = []
        for item in data.get("items", []):
            title = (
                item.get("snippet", {})
                .get("title", "")
                .strip()
            )
            if title and title.lower() != "private video":
                titles.append(title)
        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)
        return titles


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def clean_text(value: str) -> str:
    cleaned = re.sub(r"https?://\S+", " ", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def first_sentence(value: str, max_length: int = 220) -> str:
    if not value:
        return ""
    sentence_break = re.split(r"(?<=[.!?])\s+", value, maxsplit=1)[0].strip()
    if len(sentence_break) <= max_length:
        return sentence_break
    trimmed = sentence_break[: max_length - 1].rstrip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0]
    return f"{trimmed}."


def extract_title_keywords(titles: list[str], max_terms: int = 4) -> list[str]:
    # For summary text we keep this intentionally simple and deterministic:
    # derive recurrent keywords from recent uploads so channels with sparse
    # descriptions still get meaningful "about" context.
    frequency: dict[str, int] = {}
    for title in titles:
        for token in re.findall(r"[A-Za-z0-9+#]{3,}", title.lower()):
            if token in STOP_WORDS or token.isdigit():
                continue
            frequency[token] = frequency.get(token, 0) + 1

    ordered = sorted(frequency.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ordered[:max_terms]]


def format_subscribers(count: int | None) -> str:
    if count is None:
        return ""
    if count < 1_000:
        return str(count)

    units = (
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    )
    for divisor, suffix in units:
        if count >= divisor:
            scaled = count / divisor
            if scaled >= 100:
                text = f"{scaled:.0f}"
            elif scaled >= 10:
                text = f"{scaled:.1f}"
            else:
                text = f"{scaled:.2f}"
            text = text.rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return str(count)


def topic_url_to_label(topic_url: str) -> str:
    slug = unquote(urlparse(topic_url).path.split("/")[-1])
    return slug.replace("_", " ").strip()


def topic_labels_to_categories(topic_labels: list[str]) -> list[str]:
    categories: list[str] = []
    for label in topic_labels:
        lowered = label.lower()
        for hint, category in TOPIC_HINTS.items():
            if hint in lowered:
                if category not in categories:
                    categories.append(category)
                break
    return categories


def infer_categories(
    title: str,
    description: str,
    recent_titles: list[str],
    topic_categories: list[str],
    top_n: int = 5,
) -> list[str]:
    title_text = clean_text(title).lower()
    description_text = clean_text(description).lower()
    recent_text = clean_text(" ".join(recent_titles)).lower()

    score: dict[str, int] = {}
    for category in topic_categories:
        score[category] = score.get(category, 0) + 12

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in title_text:
                score[category] = score.get(category, 0) + 4
            if keyword in description_text:
                score[category] = score.get(category, 0) + 2
            if keyword in recent_text:
                score[category] = score.get(category, 0) + 3

    if not score:
        return ["General"]

    ordered = sorted(score.items(), key=lambda item: (-item[1], item[0]))
    return [category for category, _value in ordered[:top_n]]


def build_about_summary(
    channel_title: str,
    description: str,
    recent_titles: list[str],
    categories: list[str],
) -> str:
    cleaned_description = clean_text(description)
    desc_sentence = first_sentence(cleaned_description)

    if desc_sentence:
        first = desc_sentence
    else:
        if categories and categories[0] != "General":
            focus = ", ".join(categories[:3]).lower()
            first = f"{channel_title} is a YouTube channel focused on {focus}."
        else:
            first = f"{channel_title} is a YouTube channel with a mix of videos."

    keywords = extract_title_keywords(recent_titles, max_terms=3)
    if keywords:
        second = f"Recent uploads focus on {', '.join(keywords)}."
        return f"{first} {second}".strip()
    return first


def parse_subscriber_count(channel_payload: dict[str, Any]) -> int | None:
    statistics = channel_payload.get("statistics", {})
    if statistics.get("hiddenSubscriberCount"):
        return None
    raw = statistics.get("subscriberCount")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def derive_output_path(input_path: str) -> str:
    if input_path.lower().endswith(".csv"):
        return f"{input_path[:-4]}.enriched.csv"
    return f"{input_path}.enriched.csv"


def parse_dotenv_line(line: str) -> tuple[str, str] | None:
    """Parse a single dotenv line into key/value or return None for non-assignments."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()

    if "=" not in stripped:
        return None

    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        return None

    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    else:
        # Keep support intentionally simple: trim inline comments for unquoted values.
        value = value.split(" #", 1)[0].strip()

    return key, value


def load_dotenv_file(dotenv_path: str = ".env", overwrite: bool = False) -> None:
    """Load dotenv-style key/value pairs into process environment variables."""
    if not os.path.exists(dotenv_path):
        return

    try:
        with open(dotenv_path, encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                parsed = parse_dotenv_line(line)
                if parsed is None:
                    continue
                key, value = parsed

                if overwrite or key not in os.environ:
                    os.environ[key] = value
                else:
                    logging.debug(
                        "Skipping %s from %s:%s because it is already set in environment",
                        key,
                        dotenv_path,
                        line_number,
                    )
    except OSError as error:
        logging.warning("Unable to read %s: %s", dotenv_path, error)


def read_rows(csv_path: str) -> tuple[list[str], list[dict[str, str]]]:
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"CSV file has no headers: {csv_path}")
        rows = list(reader)
    return list(reader.fieldnames), rows


def write_rows(csv_path: str, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def enrich_rows(
    rows: list[dict[str, str]],
    client: YouTubeClient,
    max_recent_videos: int,
    top_categories: int,
) -> tuple[list[str], list[dict[str, str]]]:
    channel_ids = sorted({row.get("channel_id", "").strip() for row in rows if row.get("channel_id")})
    channels_by_id = client.fetch_channels(channel_ids)

    recent_titles_by_channel: dict[str, list[str]] = {}
    total_channels = len(channel_ids)
    for index, channel_id in enumerate(channel_ids, start=1):
        payload = channels_by_id.get(channel_id, {})
        uploads_playlist_id = (
            payload.get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if uploads_playlist_id:
            recent_titles_by_channel[channel_id] = client.fetch_recent_titles(
                uploads_playlist_id, max_recent_videos
            )
        if index % 100 == 0 or index == total_channels:
            logging.info(
                "Fetched recent uploads for %s/%s channels",
                index,
                total_channels,
            )

    enriched_rows: list[dict[str, str]] = []
    for row in rows:
        channel_id = row.get("channel_id", "").strip()
        payload = channels_by_id.get(channel_id, {})
        snippet = payload.get("snippet", {})

        title = snippet.get("title") or row.get("title", "").strip()
        description = snippet.get("description") or row.get("description", "").strip()
        recent_titles = recent_titles_by_channel.get(channel_id, [])

        topic_urls = payload.get("topicDetails", {}).get("topicCategories", [])
        topic_labels = [topic_url_to_label(url) for url in topic_urls]
        topic_categories = topic_labels_to_categories(topic_labels)
        categories = infer_categories(
            title=title,
            description=description,
            recent_titles=recent_titles,
            topic_categories=topic_categories,
            top_n=top_categories,
        )

        subscriber_count = parse_subscriber_count(payload)
        enriched = dict(row)
        enriched["link"] = f"https://www.youtube.com/channel/{channel_id}" if channel_id else ""
        enriched["subscribers"] = str(subscriber_count) if subscriber_count is not None else ""
        enriched["subscribers_readable"] = format_subscribers(subscriber_count)
        enriched["about"] = build_about_summary(title, description, recent_titles, categories)
        enriched["category"] = ", ".join(categories)
        enriched_rows.append(enriched)

    original_fields = list(rows[0].keys()) if rows else []
    new_fields = ["link", "subscribers", "subscribers_readable", "about", "category"]
    fieldnames = original_fields + [field for field in new_fields if field not in original_fields]
    return fieldnames, enriched_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Enrich a YouTube subscriptions CSV with channel link, subscribers, "
            "about summary, and inferred categories."
        )
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input CSV path")
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path (defaults to <input>.enriched.csv)",
    )
    parser.add_argument(
        "--api-key-env",
        default="YOUTUBE_API_KEY",
        help="Environment variable name that stores YouTube API key",
    )
    parser.add_argument(
        "--max-recent-videos",
        type=int,
        default=3,
        help="Number of recent upload titles to fetch per channel for summaries",
    )
    parser.add_argument(
        "--top-categories",
        type=int,
        default=5,
        help="Maximum number of categories to include in category column",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=50,
        help="Delay in milliseconds between API requests",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retries for transient API/network errors",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log verbosity",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    load_dotenv_file(".env", overwrite=False)
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(
            f"Missing API key: set environment variable {args.api_key_env} before running."
        )

    output_path = args.output or derive_output_path(args.input)
    original_fields, rows = read_rows(args.input)
    if not rows:
        raise SystemExit(f"No rows found in input CSV: {args.input}")

    logging.info("Loaded %s rows with columns: %s", len(rows), ", ".join(original_fields))

    client = YouTubeClient(
        api_key=api_key,
        retries=max(args.retries, 0),
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        sleep_seconds=max(args.sleep_ms, 0) / 1000.0,
    )
    fieldnames, enriched_rows = enrich_rows(
        rows,
        client,
        max_recent_videos=max(args.max_recent_videos, 0),
        top_categories=max(args.top_categories, 1),
    )
    write_rows(output_path, fieldnames, enriched_rows)
    logging.info("Wrote enriched CSV to %s", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
