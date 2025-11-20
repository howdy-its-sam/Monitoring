# arXiv Module

Scaffolding for ingesting AI-relevant preprints from arXiv (e.g., cs.AI, cs.LG, cs.CV, cs.CL, stat.ML) while respecting arXiv’s usage guidelines.

- `arxiv_credentials.env` – Identification strings (e.g., contact email, user agent) kept out of version control.
- `data/` – Raw feed snapshots and lightweight state for scheduling and rate-limit tracking.
- `src/` – Bun + TypeScript sources for polling RSS/API endpoints.

## Prerequisites

1. Install [Bun](https://bun.sh) locally and ensure `bun` is on your `PATH`.
2. Review [arXiv API Terms of Use](https://info.arxiv.org/help/api/index.html), especially the request-rate limits and identification requirements.
3. Populate `arxiv_credentials.env` with a descriptive user agent, contact email, default category list, and the minimum request interval (defaults to 5000 ms if omitted).

## Usage

### Configuration File

Edit `arxiv_categories.conf` to define which categories to track and their start dates:

```
category: cs.AI
start_date: 2024-11-01

category: cs.RO
start_date: 2024-06-01
```

The system automatically:
- Backfills historical data when you add new categories
- Extends the date range when you change a start date to earlier
- Uses these categories for daily ingestion

To add a new category, copy the template in the config file and update the values.

### Daily Ingestion (Normal Mode)

```bash
cd preprints/arxiv
bun install
bun start
```

Fetches new papers and tarballs since last run for all configured categories. On first run or when config changes, automatically backfills historical data.

### Historical Backfill

Fetch historical data for a specific category (new or existing):

```bash
# Add a new category with 6 months of history
ARXIV_HISTORICAL_CATEGORY=cs.RO ARXIV_HISTORICAL_MONTHS=6 bun start

# Extend existing category from 2 months to 6 months
ARXIV_HISTORICAL_CATEGORY=cs.AI ARXIV_HISTORICAL_MONTHS=6 bun start
```

**Features:**
- Automatically skips papers already downloaded for that category
- **Cross-category deduplication**: Papers appearing in multiple categories only download tarball once
- Respects rate limits (5 second intervals)
- Can fetch up to 100,000 papers per run by default (1000 batches × 100 per batch)
- Warns if batch limit is hit, indicating incomplete data

Environment switches:

- `ARXIV_CREDENTIALS_PATH` – Alternate path to the credentials file.
- `ARXIV_CATEGORIES_CONFIG` – Path to the categories configuration file (default `arxiv_categories.conf`).
- `ARXIV_DATA_DIR` – Directory where snapshots/state are written (default `data/`).
- `ARXIV_MAX_RESULTS` – Number of entries to request per category (default `100`, clamped to `300` by API rules).
- `ARXIV_MIN_REQUEST_INTERVAL_MS` – Minimum milliseconds between requests (default `5000` for politeness).
- `ARXIV_DOWNLOAD_TARBALLS` – `true` (default) downloads unique source tarballs for new/updated entries; set to `false` to skip.
- `ARXIV_DOWNLOAD_SAMPLE_TARBALLS` – Set to `true` to download a one-off batch of recent tarballs (default `false`).
- `ARXIV_SAMPLE_TARBALL_CATEGORY` – Category to use when sample tarball download is enabled (default `cs.AI`).
- `ARXIV_SAMPLE_TARBALL_COUNT` – How many recent tarballs to pull in sample mode (default `10`, capped at `50`).
- `ARXIV_LOOKBACK_DAYS` – How many days of history to request on each run (default `7`).
- `ARXIV_LOOKBACK_PADDING_DAYS` – Extra days to prepend to the stored `lastPublished` timestamp when rebuilding the query window (default `2`).
- `ARXIV_LOOKAHEAD_MINUTES` – How far into the future to extend the upper bound when querying (default `120`).
- `ARXIV_DEBUG` – Set to `true` to emit verbose pagination/freshness logs for troubleshooting (default `false`).
- `ARXIV_MAX_PAGES` – Maximum number of paginated API requests per category when looking for new papers (default `5`, each page up to `ARXIV_MAX_RESULTS` entries).
- `ARXIV_HISTORICAL_MAX_BATCHES` – Maximum number of batches to fetch during historical backfill (default `1000`, each batch is 100 papers, max `10000`). Increase if backfilling very large categories.

## TODO

- Implement category polling (cs.AI, cs.LG, cs.CV, cs.CL, stat.ML) with batching.
- Surface arXiv rate-limit guidance (requests per minute/hour) and persist the next allowable window.
- Persist raw XML/JSON feed responses into `data/` alongside metadata (category, fetchedAt).
- Add deduplication strategy (track last seen arXiv IDs per category).

