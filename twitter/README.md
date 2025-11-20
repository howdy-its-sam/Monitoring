# Twitter Module

Minimal Bun + TypeScript scaffolding for working with the Twitter/X API.

- `twitter_credentials.env` – API key, secret, and bearer token (do not commit to source control).
- `data/` – Storage for fetched tweets and lightweight state (e.g. rate-limit checkpoint, recent snapshots).
- `src/` – TypeScript sources (currently a credential loader stub).

## Prerequisites

1. Install [Bun](https://bun.sh) locally (`curl https://bun.sh/install | bash`) and restart your shell so `bun` is on the `PATH`.
2. Duplicate `twitter_credentials.env` and fill in real values, or point `TWITTER_CREDENTIALS_PATH` at a secure location.

## Usage

```bash
cd twitter
bun install
bun start
```

Running `bun start` fetches up to 100 recent tweets for whichever handle in the list has the oldest eligible snapshot (skipping any account fetched within the last 24 hours), then writes a new JSON snapshot into `data/`. The script reads Twitter’s rate-limit headers, waits until the window resets, and records the next allowable time in `data/rate-limit.json` so reruns won’t fire off doomed requests.

Environment switches:

- `TWITTER_CREDENTIALS_PATH` – alternate location of the env file.
- `TWITTER_DATA_DIR` – override where snapshots are saved (defaults to `data/`).
- `TWITTER_MAX_RESULTS` – number of tweets to request per account (default `100`, max `100`).

## Next Steps

- Generalise the fetcher into reusable CLI commands (e.g. `bun run src/fetchTimeline.ts @handle`).
- Add JSON schema validation and richer error logging.
- Persist incremental state (e.g. last seen tweet IDs) to avoid duplicates.

