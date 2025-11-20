# Preprint Servers Module

Container for ingesting AI-relevant research preprints (arXiv, bioRxiv, medRxiv, OpenReview, etc.). Each server lives in its own subfolder while sharing the same ingestion conventions.

## Structure

- `arxiv/` – arXiv-specific tooling (RSS/API polling, rate-limit tracking, snapshot storage).
- Additional subdirectories (e.g., `biorxiv/`, `openreview/`) will follow the same pattern when added.

## Shared Principles

- **Common scaffold** – Each provider gets its own Bun + TypeScript project with `src/`, `data/`, and a README describing setup.
- **Rate-limit aware** – Respect provider-specific quotas (arXiv has request-rate guidelines tied to user agents; others may expose headers).
- **Snapshot-first** – Store raw feed responses and metadata in `data/<provider>/` before any downstream processing.
- **Config via env** – Credentials or identification strings (user-agent, API keys) live in provider-specific `.env` files that remain untracked.

Refer to `docs/ingestion_outline.md` for the full ingestion design philosophy before extending this module.

