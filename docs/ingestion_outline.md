# Monitoring Platform Ingestion – Cross-Platform Outline

This document captures the reusable shape of our ingestion utilities so we can reproduce the same experience when onboarding new data sources (Twitter/X, Reddit, Substack, company blogs, etc.).

## Purpose

- Keep each platform in its own module while sharing a consistent project skeleton.
- Fetch data in lean, schedulable scripts that can run headless or on a schedule.
- Persist raw responses in a predictable structure so downstream tooling can replay or transform them later.

## Core Workflow

1. **Bootstrap the runtime** – use Bun + TypeScript (or another agreed runtime) with a thin entry point per platform.
2. **Load credentials/config** – read environment variables or a local `.env` file that is never committed to source control.
3. **Order fetch targets** – decide which accounts/feeds/queries should run next (oldest snapshot first, skip items within the cooldown window).
4. **Call the remote API** – keep dependencies minimal, prefer native `fetch`, and surface rate-limit metadata or other service quotas.
5. **Respect backoff** – if the provider signals a limit (429s, Retry-After headers, etc.), compute the earliest safe retry and persist that timestamp so subsequent runs don’t waste requests.
6. **Persist snapshots** – write raw responses to `data/<platform>/` with timestamped filenames plus the context used (handle, subreddit, feed URL, etc.).
7. **Log and exit cleanly** – record what succeeded, what was skipped, and why, so we can decide on follow-up actions without re-reading code.

## Design Principles That Carry Across Platforms

- **Modular layout**: each platform folder mirrors the same contents (`README.md`, `data/`, `src/`, `.gitignore`, optional `docs/`). This keeps the onboarding checklist identical no matter the service.
- **Configuration first**: everything that varies per environment (API keys, limits, output directories) is surfaced via environment variables with safe defaults.
- **Minimal beginnings**: start with credential verification + a single fetch path; add error handling, pagination, and enrichment only when needed.
- **Rate-limit awareness**: always parse whatever metadata the provider returns (headers, response body fields) and store the next legal request time. Treat “don’t make a doomed call” as a first-class invariant.
- **Snapshot storage**: store raw JSON (or other canonical format) before any transformation. Include metadata such as `fetchedAt`, request parameters, and optionally response headers.
- **Pluggable scheduling**: the script decides which target to fetch next, but the strategy is encapsulated (e.g., `isHandleEligibleForFetch`), so we can swap in more advanced policies without rewriting the loop.
- **Observable behaviour**: logs should tell the story—when we wait, what we skip, how many items we fetched, and where the snapshot lives.
- **Testing mindset**: carve out pure helpers (parsers, eligibility checks, rate-limit calculators) so they can be unit-tested regardless of the external API.
- **Security hygiene**: avoid ever writing secrets to disk; keep `.env` files git-ignored; prefer environment variables in CI/CD.
- **Extensibility**: new platform modules should be able to copy the scaffold and swap in platform-specific API calls without touching shared infrastructure.

## Expected Outputs (Generalised)

- Timestamped raw dumps inside `data/<platform>/<context>-<ISO8601>.json` (or `.ndjson`, `.csv`, etc. where appropriate).
- Optional state files for scheduling (e.g., `data/<platform>/rate-limit.json`, `last-run.json`, etc.).
- Console output or structured logs summarising:
  - which targets were fetched,
  - how many records were retrieved,
  - which targets were skipped (cooldown, missing config, rate-limits),
  - any external errors that require intervention.

## Applying the Outline to New Sources

1. Copy the module skeleton (README, `.gitignore`, `data/`, `src/`).
2. Implement a credential loader for the new service.
3. Add the first “fetch target” function that returns raw payload + rate-limit info.
4. Reuse the scheduling helpers (`isHandleEligibleForFetch`, `loadHandleRecency`, etc.) or create a platform-specific variant.
5. Persist snapshots using the same timestamped convention.
6. Update the platform README with setup steps and environment switches.
7. Add TODOs or docs for future enhancements (pagination, richer storage, sync to a lake, etc.).

Keeping these guardrails in place lets us scale horizontally—each new integration feels predictable, and improvements (rate-limit handling, logging, retry logic) can be rolled out everywhere with minimal churn.

