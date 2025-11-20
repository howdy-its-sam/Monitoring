# Blogs Module

Ingestion engine for official AI company and research lab blogs.

## Supported Sources

| Source | Type | Status |
|--------|------|--------|
| Google DeepMind | RSS | ✅ |
| NVIDIA | RSS | ✅ |
| OpenAI | Scraper | 🚧 |
| Anthropic | Scraper | 🚧 |

## Configuration

To add a new RSS-based blog, edit `sources.json`:

```json
[
  {
    "id": "google_blog",
    "name": "The Keyword",
    "url": "https://blog.google/rss"
  }
]
```

For sites that require scraping (no RSS feed), you must add a custom fetcher in `src/fetchers/custom/` and register it in `src/sources/index.ts`.

## Structure

- `sources.json` - Configuration for RSS feeds
- `src/` - TypeScript source code
  - `fetchers/` - Logic for retrieving content (RSS vs Custom Scrapers)
  - `sources/` - Configuration registry for blog targets
- `data/` - Output directory for raw snapshots

## Usage

```bash
# Install dependencies
bun install

# Run ingestion
bun run start
```
