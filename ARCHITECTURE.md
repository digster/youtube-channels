# Architecture

## Overview

This repository is a single-purpose data enrichment pipeline for YouTube channel exports.
It reads an existing subscriptions CSV, fetches live metadata from YouTube Data API v3, derives additional fields, and writes a new enriched CSV.

Primary entrypoint:

- `scripts/enrich_channels.py`

## Data Flow

1. Read source CSV rows.
2. Extract unique `channel_id` values.
3. Fetch channel metadata in batched `channels.list` calls.
4. Fetch recent upload titles per channel using `playlistItems.list`.
5. Derive output columns:
   - direct API values (`link`, `subscribers`)
   - formatted value (`subscribers_readable`)
   - inferred text outputs (`about`, `category`)
6. Write enriched CSV with original columns preserved and new columns appended.

## Key Components

- `YouTubeClient`: HTTP layer with retries, backoff, timeout, and quota error handling.
- Enrichment helpers:
  - text cleanup and sentence extraction
  - subscriber formatting
  - topic/category mapping
  - summary generation using description + recent uploads
- `enrich_rows`: central orchestration function used by CLI and tests.

## Operational Notes

- API key is read from `YOUTUBE_API_KEY` by default (configurable via `--api-key-env`).
- Before key lookup, the script loads dotenv entries from local `.env` (non-overriding), so shell exports still take precedence.
- The script sleeps between API calls (`--sleep-ms`) to reduce rate-limit risk.
- Missing uploads playlists from `playlistItems.list` (HTTP 404) are treated as a per-channel data gap, logged at warning level, and do not fail the full run.
- Output defaults to `<input>.enriched.csv` to avoid mutating original data.

## Testing Workflow

- Unit tests are in `tests/test_enrich_channels.py`.
- Run tests via:
  - `uv run python -m unittest discover -s tests -p "test_*.py"`
