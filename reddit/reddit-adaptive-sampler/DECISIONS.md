# Architecture Decision Log

This document records major design decisions with their rationale and impact. Organized chronologically (most recent first).

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

**Status:** Decision pending - analyzing implementation approach

**Files Affected:**
- `adaptive_scheduler.py:259` (get_ready_posts call)
- `temperature_scheduler.py` (schedule_next, compute_interval_hours)

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
