# Optimization Plan: Reddit Scraper V3

**Goal:** Maximize "Information Gain per Token" by transitioning from fixed-interval scraping to adaptive, velocity-based scheduling.

## 1. Current Baseline (The 5-Hour Test)
*   **Architecture:** TypeScript Scraper (`scraper.ts`) with RateLimiter and Discovery.
*   **Settings:** Fixed interval (60s) for all threads.
*   **Results (Preliminary):**
    *   Hit Rate (New Comments): ~3.3%
    *   Hit Rate (Score Changes): ~39%
    *   Waste: ~60% of scrapes yield ZERO change.

## 2. Proposed Algorithm: "Velocity-Based Backoff"

Instead of `interval = 60`, we calculate `interval` dynamically after every scrape.

### A. The Heuristic
Let `V` be the "Velocity" of the thread (Activity per minute).
*   `V_comments` = New Comments / Minutes since last scrape
*   `V_score` = Score Delta / Minutes since last scrape

**Formula:**
`Target_Interval = Base_Interval / (V_total + Epsilon)`

**Simplified Rules Table:**
| State | Definition | Action |
| :--- | :--- | :--- |
| **Hot** | > 1 new comment/min OR > 10 score delta/min | Scrape every **1 min** |
| **Active** | Any new comments in last 10 mins | Scrape every **5 mins** |
| **Warm** | No comments, but score changing | Scrape every **15 mins** |
| **Cold** | No changes for > 1 hour | Scrape every **60 mins** |
| **Dead** | No changes for > 6 hours | **Archive** (Stop scraping) |

### B. Implementation Details (TypeScript)

**1. Update `scraper.ts` processThread:**
```typescript
// After merge...
const stats = dag.merge(...);

// Calculate Volatility
const minutesElapsed = (now - config.lastScrape) / 60000;
const commentVelocity = stats.newNodes / minutesElapsed;
const scoreVelocity = stats.scoreDelta / minutesElapsed;

// Determine Next Interval
let nextInterval = 3600; // Default: Cold

if (commentVelocity > 0.5 || scoreVelocity > 5) {
    nextInterval = 60; // Hot
} else if (stats.newNodes > 0) {
    nextInterval = 300; // Active
} else if (stats.scoreDelta > 0) {
    nextInterval = 900; // Warm
}

// Backoff cap (don't wait more than 6 hours)
nextInterval = Math.min(nextInterval, 21600);

config.interval = nextInterval;
```

**2. Add "Archival" State:**
*   If `nextInterval` reaches a threshold (e.g., 6 hours) AND the thread is older than 24 hours:
*   Mark thread as `ARCHIVED`.
*   Remove from `schedule` map.
*   Flush DAG to disk one last time.
*   Free memory.

## 3. Telemetry Upgrades (For Verification)

To prove V3 works, we need to track **"Missed Opportunity Cost"**:
*   Ideally, when we come back after 60 minutes, we should see *a lot* of stuff.
*   If we wait 60 mins and see 0 stuff, we chose correctly.
*   If we wait 60 mins and see 50 comments, we might have waited too long (lost granularity).

**New Metric:** `Events_Per_Minute_Waited`
*   We want this to remain relatively stable.

## 4. The Coverage Curve (Prioritization Strategy)

To manage high-volume "Firehose" situations, we will prioritize **Subreddits** using a flexible coverage gradient rather than hard-coded tiers.

**Concept:**
*   **Rank 0 (Highest):** Collect 100% of posts.
*   **Rank N (Lowest):** Collect `m`% (minimum floor) of posts.
*   **The Curve:** A function `C(rank)` determines the target coverage percentage.

**Proposed Functions:**

**A. Linear Ramp (Simple)**
*   `d`: Rank where drop-off begins (e.g., Top 10 get 100%).
*   `f`: Rank of last tracked subreddit.
*   `m`: Minimum coverage (e.g., 20%).
*   Logic:
    *   If `rank <= d`: Coverage = 100%
    *   If `rank > d`: Coverage decays linearly from 100% to `m`.

**B. Sigmoid Decay (Smooth)**
*   `C(rank) = m + (100 - m) / (1 + e^(k * (rank - pivot)))`
*   Provides a "Soft Cliff" where high-priority subs stay high, mid-tier drops rapidly, and low-tier flattens out.

**Implementation:**
1.  **Discovery Phase:** When scanning `r/Subreddit` (Rank `R`), calculate target `C(R)`.
2.  **Sampling:** If `C(R) = 40%` and we find 10 new posts, we only add the **Top 4** (by initial score or randomness) to the `Scraper` queue.
3.  **Budget Safety:** This protects the global token budget from being consumed by low-value, high-volume communities.

## 5. Deployment Strategy (Phase 4)

1.  **Code Update:** Implement the adaptive logic in `scraper.ts`.
2.  **Verification:** Run a side-by-side test? (Hard to do).
    *   Alternative: Run V3 on the same subreddits.
    *   Expectation: Total scrapes drops by ~50-80%. Total comments captured remains ~100%.
3.  **Production:** Deploy to Railway/VPS with S3 enabled.

---
*Last Updated: Nov 20, 2025*
