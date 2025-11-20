# Reddit Module

Placeholder for future Reddit ingestion tooling.

## Structure

- `reddit_credentials.env` – OAuth client ID/secret and tokens (never commit real values).
- `data/` – Output files or intermediate state.
- `src/` – Bun + TypeScript scripts (pending implementation).

Replicate the authentication pattern used in the Twitter module when adding Reddit credentials. The rate-limit budgeting logic from the existing monitoring system will be revisited and ported here when we integrate that project.

