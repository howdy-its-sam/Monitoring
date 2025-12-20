# Development Backlog

Running list of pending tasks, bugs, and improvements. Updated as discoveries are made.

---

## Bugs / Fixes Needed

### HIGH PRIORITY

1. **Telemetry `posts_queue` bug** (2025-12-01)
   - `telemetry.py:515` checks `scheduler.posts_queue` which doesn't exist
   - Always returns `Infinity` for `soonest_next_scrape_delta_s`
   - **Fix:** Update to use `scheduler.control_tick()` or remove metric
   - **Impact:** Misleading diagnostic output

2. **Depth advisor schema mismatch** (2025-12-01)
   - `depth_advisor.py:77-82` expects camelCase (`scoreHistory`, `parentId`)
   - Actual data uses snake_case (`score_history`, `parent_id`)
   - Also expects `[{'value': X}]` but actual format is `[[value, timestamp], ...]`
   - **Impact:** Author-based depth decisions may not work correctly

3. **Information waste rate high (45%)** (2025-12-01)
   - Root cause: Removed time-based filtering from scheduler
   - Now ALL posts always "ready" - no respect for calculated intervals
   - Posts re-scraped too frequently before they change
   - **Fix:** Need intelligent interval-spacing that doesn't create dead periods

### COMPLETED (for reference)

- [x] **Rate limit header parsing** - Fixed `int(remaining)` → `int(float(remaining))` (2025-11-29)
- [x] **Author scoring input format** - Transform comments list to dict (2025-12-01)
- [x] **Author scoring schema** - Fixed camelCase→snake_case field names (2025-12-01)
- [x] **Subreddit typos** - Fixed dead/misspelled subreddits in priority list (2025-11-29)
- [x] **Token waste tracking** - Added logging for expired unused tokens (2025-11-29)

---

## Features / Enhancements

### FOR GITHUB RELEASE

1. **Commit and push to gist-geo-experiments** (2025-12-01 - IN PROGRESS)
   - Project copied to `experiments/reddit-sampler/`
   - README.md, .env.example, .gitignore created
   - **Next:** Run `git add experiments/reddit-sampler/ && git commit && git push`

2. **Code already supports unauthenticated mode**
   - Falls back gracefully if no credentials found
   - Uses public API (~10 req/min vs 100 req/min)
   - No code changes needed - just don't provide credentials

### FUTURE ENHANCEMENTS

1. **Pre-warm author cache**
   - One-time batch job to fetch all authors in existing threads
   - Eliminate "cold start" overhead

2. **Subreddit-specific profiles**
   - r/MachineLearning → AGGRESSIVE (high signal)
   - r/funny → CONSERVATIVE (low signal)

3. **Real-time sibling density**
   - Refactor scraping to check siblings before expanding

4. **Author-based discovery**
   - Track high-karma authors across subreddits
   - Discover new communities via author traversal

5. **Metrics dashboard**
   - Visualize intensity profile effectiveness
   - Track author cache hit rate
   - Monitor rate limit adjustments

---

## Run Stats (Historical Reference)

### Run: Nov 29 - Nov 30, 2025 (32h healthy)
- Posts scraped: 82,799
- Throughput: 43 posts/min
- Information waste: 45% (scheduling issue)
- Token waste: Not tracked (code added after start)
- Ended: OAuth token expired

---

## Notes

- Most recent DECISIONS.md entry: 2025-11-29 (Author Scoring Fix)
- OAuth tokens expire after ~24h - need refresh mechanism
- Reddit rate limit: 1000 req/10min with OAuth, ~100 req/10min without
