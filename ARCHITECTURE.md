# Architecture

## Overview

This repository is a single-purpose data enrichment pipeline for YouTube channel exports.
It reads an existing subscriptions CSV, fetches live metadata from YouTube Data API v3, derives additional fields, and writes a new enriched CSV.
It also includes a browser-only analysis layer for local exploration of enriched CSV files.

Primary entrypoint:

- `scripts/enrich_channels.py`

Dashboard entrypoint:

- `dashboard.html`

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

### Dashboard Data Flow (Browser)

1. User loads an enriched CSV through the file input in `dashboard.html`.
2. PapaParse parses rows client-side with header validation.
3. Rows are normalized into a derived in-memory model (`primaryCategory`, numeric subscribers, search index text).
4. Filter state (search/category/range/sort) produces a filtered view.
5. Filtered view drives:
   - KPI cards
   - category and subscriber distribution charts (Chart.js)
   - top channels, missing-data audit, and category-tier heatmap
   - paginated data table

## Key Components

- `YouTubeClient`: HTTP layer with retries, backoff, timeout, and quota error handling.
- Enrichment helpers:
  - text cleanup and sentence extraction
  - subscriber formatting
  - topic/category mapping
  - summary generation using description + recent uploads
- `enrich_rows`: central orchestration function used by CLI and tests.
- Dashboard modules (inline in `dashboard.html`):
  - CSV validation/normalization
  - filter/sort/pagination state management
  - chart rendering + insight panel rendering
  - table rendering with escaped HTML output

## Operational Notes

- API key is read from `YOUTUBE_API_KEY` by default (configurable via `--api-key-env`).
- Before key lookup, the script loads dotenv entries from local `.env` (non-overriding), so shell exports still take precedence.
- The script sleeps between API calls (`--sleep-ms`) to reduce rate-limit risk.
- Missing uploads playlists from `playlistItems.list` (HTTP 404) are treated as a per-channel data gap, logged at warning level, and do not fail the full run.
- Output defaults to `<input>.enriched.csv` to avoid mutating original data.
- Dashboard requires internet access for CDN dependencies (`papaparse` and `chart.js`) and otherwise runs fully local with no backend.

## Testing Workflow

- Unit tests are in `tests/test_enrich_channels.py`.
- Run tests via:
  - `uv run python -m unittest discover -s tests -p "test_*.py"`
- UI verification for dashboard is manual in a real browser, using the checklist documented in `README.md`.
