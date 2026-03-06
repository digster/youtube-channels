# YouTube Channel CSV Enricher

This project enriches a YouTube subscriptions CSV with extra channel metadata.
It also includes a standalone browser dashboard for exploring enriched CSV output.

## Input

Expected CSV columns:

- `channel_id`
- `title`
- `description`
- `thumbnail_url`
- `subscribed_at`

Default input file:

- `subscriptions_2026-03-05.csv`

## Added Columns

The script appends:

- `link`: Full channel URL.
- `subscribers`: Raw integer subscriber count.
- `subscribers_readable`: Human-readable subscriber count (for example `1.23M`).
- `about`: Concise summary generated from channel description and recent uploads.
- `category`: Comma-separated ranked category guesses (most likely first).

## Setup

Set your YouTube Data API key:

```bash
export YOUTUBE_API_KEY="your_key_here"
```

You can also place it in a local `.env` file as:

```bash
YOUTUBE_API_KEY="your_key_here"
```

The script automatically loads `.env` from the current working directory and uses it when the variable is not already exported in the shell.

## Run

```bash
uv run python scripts/enrich_channels.py \
  --input subscriptions_2026-03-05.csv \
  --output subscriptions_2026-03-05.enriched.csv
```

Useful options:

- `--max-recent-videos` (default: `3`)
- `--top-categories` (default: `5`)
- `--sleep-ms` (default: `50`)
- `--retries` (default: `2`)
- `--log-level` (`DEBUG|INFO|WARNING|ERROR`)

If a channel's uploads playlist cannot be fetched (`playlistItems` returns `404`), the script logs a warning and continues without recent titles for that channel.

## Tests

```bash
uv run python -m unittest discover -s tests -p "test_*.py"
```

## Dashboard

`dashboard.html` is a single-file local dashboard for exploring enriched subscription exports.

### Features

- File-picker based CSV loading (no backend required).
- Search, category filtering, subscriber range controls, and sorting.
- KPI cards for filtered channel count, median subscribers, max subscribers, and category count.
- Category distribution chart and subscriber distribution chart with compact large-number labels.
- Insight panels for top channels, missing data audit, and category-vs-subscriber-tier heatmap.
- Paginated channel table with safe external links.

### Run

Open the file directly in a modern browser:

```bash
open dashboard.html
```

Then choose an enriched CSV file such as `subscriptions_2026-03-05.enriched.csv`.

### Required Columns

The dashboard expects these headers in the loaded CSV:

- `channel_id`
- `title`
- `description`
- `thumbnail_url`
- `subscribed_at`
- `link`
- `subscribers`
- `subscribers_readable`
- `about`
- `category`

### Manual Verification Checklist

- Load a valid `.enriched.csv` file and confirm row count plus loaded-file metadata update.
- Apply search + category + subscriber-range filters and confirm table/charts/KPIs stay in sync.
- Change sort and verify ordering in the table.
- Open a channel link from table rows and confirm it opens in a new tab.
- Resize to mobile width and confirm controls/table remain usable.
