# YouTube Channel CSV Enricher

This project enriches a YouTube subscriptions CSV with extra channel metadata.

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

## Tests

```bash
uv run python -m unittest discover -s tests -p "test_*.py"
```
