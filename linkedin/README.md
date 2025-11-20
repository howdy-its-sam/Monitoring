# LinkedIn Module

Scaffolding for ingesting activity from LinkedIn company pages as part of the monitoring program.

- `linkedin_credentials.env` – Client credentials, access token placeholders (never commit real values).
- `data/` – Raw payload snapshots and lightweight state (e.g., rate-limit checkpoints).
- `src/` – Bun + TypeScript sources (entry point and API helpers).

## Prerequisites

1. Install [Bun](https://bun.sh) locally and ensure `bun` is on your `PATH`.
2. Provision a dedicated LinkedIn developer application (Marketing Developer Platform) with the required Page scopes.
3. Populate `linkedin_credentials.env` with placeholder values, then replace them once you complete the OAuth flow.

## Usage

```bash
cd linkedin
bun install
bun start
```

The current entry point only validates that credentials exist. Extend the module with token refresh, rate-limit handling, and snapshot persistence following the pattern documented in `docs/ingestion_outline.md`.

## TODO

- Implement OAuth token loader/refresh logic.
- Surface LinkedIn rate-limit metadata and persist the next allowed fetch window.
- Add company-page fetch utilities and snapshot storage under `data/`.
- Update this README with real setup steps once the first API call succeeds.

