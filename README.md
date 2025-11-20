# Monitoring

This workspace holds data-ingestion utilities for multiple platforms.

## Layout

- `twitter/` – Twitter/X specific scripts, configuration, and credentials.
- `reddit/` – Placeholder for future Reddit ingestion tooling.

## Getting Started

1. Populate `twitter/twitter_credentials.env` with your API key, secret, and bearer token.
2. Twitter tooling (to be added) will read credentials from that file and write results into platform-specific storage (for example `twitter/data/`).
3. Add additional platform folders (e.g. `youtube/`, `tiktok/`) following the same pattern as needs expand.

