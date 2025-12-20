# Architecture Decision Log

This document records major design decisions with their rationale and impact. Organized chronologically (most recent first).

---

## 2025-11-29: Added Token Waste Tracking

**Decision:** Track and log tokens that expire unused when Reddit's rate limit window resets.

**Rationale:**
- Reddit uses fixed 10-minute windows that reset completely
- Our sliding window model is more conservative but could leave tokens unused
- Need visibility into whether we're fully utilizing API capacity
- User principle: "make sure we are logging any time the token bucket refreshes before we can use them all"

**Implementation:**
- Detect window reset by watching `x-ratelimit-used` header drop significantly
- When reset detected, `last_remaining` = tokens that expired unused
- Log warning: `⚠️ TOKEN WASTE: X tokens expired unused (Y% of window capacity)`
- Track cumulative stats: `total_wasted_tokens`, `window_reset_count`, `waste_rate_pct`

**Detection Logic:**
```python
if self.last_used is not None and used < self.last_used - 5:
    # Window reset detected - last_remaining tokens were wasted
    wasted = self.last_remaining
```

**Files Modified:**
- `src/rate_limiter.py:49-53` (added tracking variables)
- `src/rate_limiter.py:223-244` (window reset detection and logging)
- `src/rate_limiter.py:301-304` (added waste stats to get_status)

**Note:** This will only apply to runs started after this change. Current run continues without this tracking.

---

## 2025-11-29: Fixed Author Scoring Data Schema Mismatch

**Decision:** Fix two bugs preventing author interestingness scoring from working.

**Symptoms:** ~2,270 errors per run: `'list' object has no attribute 'get'`

**Root Causes:**

1. **Wrong input format:** `calculate_author_interestingness(result)` received full scrape result (`{'post': {...}, 'comments': [...], 'metadata': {...}}`) but expected `{node_id: node_data}` dict

2. **Wrong field names:** Function used camelCase (`scoreHistory`, `textHistory`, `parentId`) but scrape data uses snake_case (`score_history`, `text_history`, `parent_id`)

3. **Wrong value access:** Function expected `[{'value': X}]` but actual format is `[[value, timestamp], ...]`

**Fixes Applied:**

1. In `unified_scraper.py:676-678`:
```python
# Convert comments list to dict keyed by ID for author analysis
comments_dict = {c['id']: c for c in result.get('comments', [])}
author_scores = calculate_author_interestingness(comments_dict)
```

2. In `author_scoring.py:48-70`:
   - `scoreHistory` → `score_history`
   - `textHistory` → `text_history`
   - `parentId` → `parent_id`
   - `score_history[-1]['value']` → `score_history[-1][0]`
   - `text_history[-1]['value']` → `text_history[-1][0]`

**Verified:** Test with real scrape data produces correct scores:
```
ilintar: 6.8, noiserr: 2.9, No-Statement-0001: 2.6, Mythril_Zombie: 1.6
```

**Files Modified:**
- `src/unified_scraper.py:676-678` (transform input to dict)
- `src/author_scoring.py:48-70` (fix field names and access patterns)

---

## 2025-11-28: Project Reorganization for Human Navigation

**Decision:** Reorganized project directory structure to separate source code, scripts, documentation, data, and archived files into dedicated directories.

**Rationale:**
- Root directory had become cluttered with 81+ items (Python files, scripts, docs, data, logs)
- Difficult for humans to quickly understand project structure
- Mix of active workflow files and deprecated/reference utilities
- Needed clear separation between "what's running" and "what's for reference"

**Structure Implemented:**
```
reddit-adaptive-sampler/
├── src/                 # Python source files (17 modules)
├── scripts/             # Shell scripts for workflow (4 scripts)
├── docs/                # Documentation (DESIGN.md, DECISIONS.md, etc.)
├── logs/                # Historical log files and reports
├── data/                # Archived data snapshots
├── .archive/            # Two-tier archive system
│   ├── deprecated/      # Files likely safe to delete (4 files)
│   └── reference/       # Keep indefinitely for future use (8 files)
└── .claude/             # Agent workflow commands

Active data (temporal_test/, telemetry.jsonl) remain in root
PID files (scraper.pid, caffeinate.pid) remain in root
```

**Archive Strategy:**
- Deprecated files: Delete after 1-3 months if not needed
- Reference files: Keep indefinitely for manual debugging/analysis
- Review schedule documented in `.archive/ARCHIVE_LOG.md`
- Archive review integrated into `/scraper` command

**Impact:**
- Scripts now reference files via relative paths (../docs/, ../src/, ../logs/)
- Running scraper (PID 40986) unaffected - continues using root directory
- Git safety commit (57ba2a20) created as rollback point
- Future launches will use `scripts/run_scraper_48h.sh`

**Files Changed:**
- Created: 4 new directories, `.archive/ARCHIVE_LOG.md`
- Moved: 17 Python files → `src/`, 4 scripts → `scripts/`, 4 docs → `docs/`
- Archived: 12 utility files → `.archive/`
- Updated: All scripts to use new paths, `/scraper` command to check archive status

---

## 2025-11-29: Fixed Rate Limit Header Parsing Bug

**Decision:** Fix float string parsing in rate limiter header updates.

**Discovery:** Reddit returns rate limit headers as float strings (e.g., "997.0") but we parsed with `int()` which throws ValueError. The exception was silently caught, so the rate limiter never learned the actual limit.

**Impact:**
- Reddit allows 1000 req/10min with OAuth
- We were stuck at 90 req/10min (9% of capacity)
- 91% of API capacity was being wasted

**Fix:** Changed `int(remaining)` to `int(float(remaining))` in rate_limiter.py:211-212

**Expected Result:** Rate limiter will learn 1000 req/10min limit from headers, unlocking 10x capacity.

---

## 2025-11-28: Identified Pontryagin Scheduler as Waste Bottleneck

**Context:** Despite adaptive intervals and removed orchestration sleeps, waste remained at 28%.

**Discovery:** The `temperature_scheduler.py` uses Pontryagin's maximum principle to calculate optimal "next scrape times" for each post. The `get_ready_posts()` function filters out posts not yet "due", creating temporal gaps where NO posts are available to scrape even with 37 tokens in buffer.

**Root Cause:**
- Scheduler calculates when each post should be scraped based on information gain curves
- Posts are scheduled for future times (e.g., "scrape in 2 minutes")
- During gaps, tokens accumulate unused → waste
- Two layers of temporal control (scheduler + rate limiter) conflict

**Impact:**
- 28% waste persists despite other optimizations
- Average buffer stays at 37 tokens (should be 5-15)
- Contradicts "use tokens as available" principle

**Proposed Solution:**
- Keep temperature calculation (good at ranking WHICH posts are valuable)
- Remove time-based filtering (scheduler shouldn't control WHEN)
- Return ALL posts sorted by temperature/priority
- Let rate limiter be sole temporal gatekeeper

**Status:** Implemented 2025-11-28

**Fix Applied:**
- Removed `entry.next_time <= now` filter from `get_ready_posts()`
- Now returns ALL posts in temperature-priority order
- Rate limiter remains sole temporal gatekeeper

**Files Modified:**
- `src/temperature_scheduler.py:332` (removed time filter from get_ready_posts)

---

## 2025-11-27: Removed All Orchestration-Level Sleeps

**Decision:** Eliminate all fixed sleep statements from orchestration layer (`unified_scraper.py`).

**Rationale:**
- Fixed sleeps (30s, 60s, 180s) created temporal gaps during refill periods
- When budget exhausted, orchestration would sleep while tokens accumulated
- Contradicts philosophy of "dynamic sleep times based on actual refill schedules"
- Request-level `wait_for_budget()` already handles dynamic pacing

**Previous Behavior:**
- Budget depleted → sleep 60s (or 180s for hard starvation)
- Budget low (<30) → sleep 30s
- After deferrals → sleep 15-120s cooldown

**New Behavior:**
- No orchestration sleeps at all
- Continuous scrape attempts
- `wait_for_budget()` at request level handles all pacing
- Natural backpressure when budget unavailable

**Expected Impact:** Waste 25% → <10%

**Actual Impact:** Waste remained ~28% (scheduler filtering was true bottleneck)

**Files Modified:**
- `unified_scraper.py:530-546` (removed budget depletion sleeps)
- `unified_scraper.py:580-584` (removed soft guard sleep)
- `unified_scraper.py:625-630` (removed post-scrape retry loops)
- `unified_scraper.py:775-777` (removed deferral cooldown)

---

## 2025-11-27: Implemented Adaptive Interval Pacing

**Decision:** Add buffer-based request intervals to rate limiter.

**Rationale:**
- User philosophy: "don't like minimal interval pacing, goes against using tokens as available"
- Compromise between burst consumption and smooth pacing
- Proportional control: consumption rate inversely proportional to buffer size
- Creates self-dampening feedback loop (high buffer → fast consumption → buffer shrinks)

**Algorithm:**
```python
if available >= 50:
    return 0.5s  # Very fast: 2 req/sec
elif available >= 25:
    return 2.0s  # Fast: 0.5 req/sec
elif available >= 10:
    return 4.0s  # Medium: 0.25 req/sec
else:
    return 6.0s  # Slow: match refill rate (~0.16 req/sec)
```

**Expected Behavior:**
- Prevents bursts (vs immediate consumption)
- Prevents fixed pacing (vs rigid scheduling)
- Naturally stabilizes at equilibrium
- More aggressive than fixed 6s interval

**Expected Impact:** Better utilization without burst risk

**Actual Impact:** Worked as designed but didn't reduce waste (orchestration & scheduler were bottlenecks)

**Files Modified:**
- `rate_limiter.py:160-186` (get_adaptive_interval method)
- `rate_limiter.py:276-314` (updated wait_for_budget to use adaptive intervals)
- `rate_limiter.py` (added last_request_time tracking)

---

## 2025-11-27: Philosophy - Dynamic vs Fixed Sleep Times

**Stated Principle:** "I am generally against setting fixed sleep times and would prefer to sleep for dynamic amounts of time. Like if we know we will get a refill in 4 seconds, we can sleep for 5 seconds."

**Implication:**
- All sleeps should be calculated based on actual system state
- Prefer `time_until_refill + small_margin` over hardcoded durations
- Rate limiter already does this via token bucket math
- Orchestration should trust rate limiter's calculations

**Applied To:**
- Removed all `time.sleep(60)` style statements
- Use `wait_for_budget()` which calculates exact refill times
- No magic numbers for sleep durations

---

## 2025-11-27: Philosophy - Use Tokens As Available

**Core Principle Established:**

User: "I don't like minimal interval pacing, because that goes against the philosophy of request consumption that dynamically scales up or down to use up what is available."

**Contrast With:**
- **Fixed scheduling:** "Scrape this at 2:15pm regardless of capacity"
- **Burst prevention only:** "Never use more than 1 req/6s even if we have 50 tokens"
- **Pre-planned pacing:** "Space these 10 requests over 60 seconds"

**Prefer:**
- **Dynamic consumption:** "Use whatever's available right now"
- **Rate-responsive:** "Adjust speed based on current buffer"
- **Backpressure natural:** Let capacity limits slow us down organically

**Implementation:**
- Rate limiter controls temporal pacing based on current state
- No pre-scheduling of scrape times
- Continuous attempt to scrape, gated only by actual budget

---

## 2025-11-27: Acknowledged Two Types of "Bursts"

**Clarification from user:**

**Type 1 - Single Large Job:**
- One post scrape consuming ~20 tokens
- Example: Deep thread with many comments
- User's primary meaning when saying "burst"

**Type 2 - Accumulated Buffer:**
- 50 small jobs each using 1 token
- All executing rapidly after budget accumulation
- Creates burst even though individual jobs are small

**Design Implication:**
Both types should be handled by adaptive intervals:
- Type 1: Still consumes 20 tokens but spread over ~10 seconds (at 0.5s intervals)
- Type 2: 50 tokens spread over ~25 seconds instead of instant burst

Adaptive pacing handles both automatically without distinguishing between them.

---

## Template for Future Entries

```markdown
## YYYY-MM-DD: Decision Title

**Decision:** What was decided

**Rationale:** Why this decision was made

**Previous Behavior:** How it worked before

**New Behavior:** How it works now

**Expected Impact:** What we expect to change

**Actual Impact:** What actually happened (fill in after observation)

**Files Modified:**
- file.py:line (description)
```

---

## Notes on This Log

- Most recent decisions appear first
- Include both successful and failed approaches
- Record actual vs expected impact when known
- Link to DESIGN.md for philosophy
- Include user quotes when they express key principles
- Cross-reference file locations for future debugging
