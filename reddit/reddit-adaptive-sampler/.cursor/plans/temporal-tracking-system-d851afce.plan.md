<!-- d851afce-d9a0-4170-94c6-d2ba13199bfb 9a5593b6-9a74-4a38-8db0-f641aa1cc3d1 -->
# Repository Cleanup and Consolidation Plan

## Scope and Goals

- Remove truly irrelevant/obsolete files
- Consolidate scattered reports/results into a clear structure
- Preserve important datasets, logs, and validated analyses
- No behavior changes to scraper code in this pass

## Questions (blocking decisions)

1) Keep `24h_final_report/` as canonical test package? If yes, we’ll preserve it fully and reference from the mega report.
2) Data retention: keep all of `scraped_posts/` raw JSONs locally, or archive only exemplars and rely on `24h_final_report/` merged_v2 as canonical?

## Target Structure

- `data/`
- `raw/` (archived raw scrapes worth keeping)
- `merged/` (current canonical merged_v2 snapshots)
- `examples/` (a few full temporal exemplars referenced by guide)
- `reports/`
- `24h_endurance/` (move existing `24h_final_report/` here 1:1)
- `MEGA_TEST_REPORT.md` (single index of all tests + links)
- `analysis/` (all reusable analysis scripts)
- `docs/` (prompts, schema, guides)
- `scripts/` (operational helpers like `run_long_test.sh`)
- `archive/` (deprecated scripts kept for reference; no longer run)

## Actions

1. Preserve intact

- Move `24h_final_report/` → `reports/24h_endurance/` (no edits inside)
- Keep `run_long_test.sh` under `scripts/`

2. Consolidate data

- Move `24h_final_report/scraped_data/merged_v2/` → `data/merged/`
- Move chosen temporal exemplars → `data/examples/`
- Decide on `scraped_posts/` retention (all vs subset)

3. Consolidate analysis scripts

- Keep: `analyze_24h_results.py`, `analyze_consecutive_score_pruning.py`, `analyze_comments_per_request.py`, `batch_remerge_all_posts.py`, `validate_edit_capture.py`
- Move to `analysis/`

4. Consolidate docs

- Move `deep_prompt.txt` (reformatted), `DATA_INTERPRETATION_GUIDE.md`, `REDDIT_JSON_TREE_STRUCTURE.md`, `temporal-tracking-system.plan.md` → `docs/`

5. Archive or delete

- Delete truly obsolete files already removed (no action)
- Move legacy/one-off or superseded helpers → `archive/` (e.g., `fix_text_history_merge.py`, `create_true_merged_dataset.py` if superseded by `batch_remerge_all_posts.py`)

6. Create index and README

- `reports/MEGA_TEST_REPORT.md` summarizing: goals, runs, key metrics, links to full artifacts
- `README.md` at repo root: new structure map + quickstart to data and reports

## Safeguards

- Perform a dry-run list of moves/deletions for approval
- No destructive deletions without explicit confirmation
- Preserve git history; add a tag `pre-cleanup` before changes

## Deliverables

- Cleaned tree per structure
- `reports/MEGA_TEST_REPORT.md`
- Updated root `README.md`
- `docs/` and `analysis/` organized and linked

### To-dos

- [ ] Create merge_with_existing_data() function to handle temporal updates
- [ ] Update comment/post data structure to include history arrays and timestamps
- [ ] Modify scrape_reddit_post_api() to load existing data and merge
- [ ] Test temporal tracking by running same URL multiple times