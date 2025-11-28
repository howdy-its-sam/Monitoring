# TypeScript vs Python Feature Comparison

**Date:** 2025-11-26
**Purpose:** Identify features unique to each implementation before porting Python enhancements to TypeScript

---

## Executive Summary

### TypeScript Advantages (Production Features)
- ✅ S3/R2 cloud storage integration
- ✅ HTTP server with health checks and flush endpoints
- ✅ Token bucket rate limiter (simple, predictable)
- ✅ Backfill mode with comprehensive state management
- ✅ DAG deletion tracking (marks missing nodes as deleted)
- ✅ Legacy Python data aggregator/converter
- ✅ Production-ready Railway deployment

### Python Advantages (Research Features - NEW)
- ✅ **Adaptive rate limiter** (auto-discovers Reddit's actual limits from headers)
- ✅ **Intensity profiles system** (AGGRESSIVE/BALANCED/CONSERVATIVE)
- ✅ **Signal-based depth selection** (engagement, recency, sibling density, author reputation)
- ✅ **Author profile caching** (7-day TTL, budget-aware fetching)
- ✅ **Thread-scoped author scoring** (interestingness calculation)
- ✅ **Dynamic intensity switching** (based on available budget)
- ✅ Adaptive scheduler with PID controller
- ✅ Coverage allocator (budget distribution)
- ✅ Temperature scheduler (temporal weighting)
- ✅ More sophisticated analytics tools

---

## 1. Core Architecture

### TypeScript (`/reddit/src/`)

**Entry Points:**
- `server.ts` - Production entry (HTTP server + scraper loop)
- `backfill.ts` - One-time backfill script
- `scraper.ts` - Original simple scraper
- `scraper_v3.ts` - Adaptive scheduler version (references missing scheduler files)

**Key Classes:**
```typescript
RedditAPI        - API integration with token bucket rate limiter
DAG              - Temporal graph structure with deletion tracking
StorageDriver    - S3/local filesystem abstraction
Discovery        - Subreddit scanning for new posts
Telemetry        - Event logging
Scraper          - Simple scraper with adaptive backoff
```

**Data Flow:**
1. HTTP server starts scraper loop
2. Discovery polls subreddits every 5 minutes
3. Scraper processes threads with adaptive intervals
4. DAG merges snapshots, tracks deletions
5. Saves to S3 or local disk

### Python (`/reddit/reddit-adaptive-sampler/`)

**Entry Points:**
- `unified_scraper.py` - Main production scraper
- `scrape_single_post.py` - Single-post testing

**Key Modules:**
```python
RedditScraperAPI        - API integration (recursive "more" expansion)
RateLimiter             - Sliding window with header-based adaptation
IntensityProfile        - Signal-based depth selection
AdaptiveScheduler       - PID controller for rate optimization
CoverageAllocator       - Budget distribution across subreddits
TemperatureScheduler    - Temporal weighting (BREAKING/EMERGING/SUSTAINED)
DepthAdvisor            - Signal-based exploration decisions
AuthorCache             - 7-day TTL profile cache
AuthorScoring           - Thread-scoped interestingness calculation
```

**Data Flow:**
1. Unified scraper loads intensity profile
2. Adaptive scheduler allocates budget
3. Scraper fetches threads recursively with "more" expansion
4. Depth advisor decides whether to continue exploring
5. Author scoring identifies top contributors
6. Budget-aware author profile fetching
7. Dynamic intensity switching based on available budget
8. Saves to local disk (JSON snapshots)

---

## 2. Rate Limiting

### TypeScript: Token Bucket Algorithm

**File:** `rate_limiter.ts`

**Implementation:**
```typescript
class RateLimiter {
  private tokens: number;
  private maxTokens: number = 600;
  private refillRate: number = 10; // tokens/second

  public async wait(cost: number = 1) {
    this.refill();
    if (this.tokens >= cost) {
      this.tokens -= cost;
      return;
    }
    const deficit = cost - this.tokens;
    const waitTime = (deficit / this.refillRate) * 1000;
    await sleep(waitTime);
    return this.wait(cost); // Recurse
  }
}
```

**Characteristics:**
- ✅ Simple, predictable behavior
- ✅ Bucket refills continuously at fixed rate
- ✅ Reads `x-ratelimit-remaining` header to sync state
- ⚠️ Does NOT auto-adjust `maxTokens` or `refillRate`
- ⚠️ Hardcoded 600 tokens / 10 RPS

### Python: Sliding Window + Adaptive Adjustment

**File:** `rate_limiter.py`

**Implementation:**
```python
class RateLimiter:
    def __init__(self, max_requests=90, window_seconds=600):
        self.max_requests = max_requests  # Dynamic!
        self.window_seconds = window_seconds
        self.request_times = deque()
        self.observed_limits = []  # For adaptive adjustment

    def update_from_headers(self, headers):
        """Auto-discover Reddit's actual limit from response headers."""
        remaining = int(headers.get('X-RateLimit-Remaining'))
        used = int(headers.get('X-RateLimit-Used'))
        observed_limit = remaining + used

        self.observed_limits.append(observed_limit)
        if len(self.observed_limits) > 10:
            self.observed_limits.pop(0)

        # Use median for robust estimation
        new_limit = sorted(self.observed_limits)[len(self.observed_limits) // 2]

        if new_limit != self.max_requests:
            print(f"📊 Rate limit adjusted: {old_rpm:.0f} → {new_rpm:.0f} req/min")
            self.max_requests = new_limit
```

**Characteristics:**
- ✅ Auto-discovers Reddit's actual rate limit
- ✅ Adjusts from conservative 90 req/10min → actual 100 req/10min
- ✅ Detects OAuth failures (drops from 100→10 req/min)
- ✅ Uses median of last 10 observations (robust to outliers)
- ✅ Future-proof for Reddit API changes

**Verdict:** Python's adaptive approach is SUPERIOR for production use.

---

## 3. Depth Selection Strategy

### TypeScript: No Depth Selection

**Status:** ❌ NOT IMPLEMENTED

**Current Behavior:**
- Fetches entire thread with `limit=500`
- Parses all returned comments
- No filtering based on depth, score, or engagement
- Skips "more" objects (TODO comment in code)

**Code Reference:** `api.ts:86-117`

### Python: Signal-Based Depth Selection (NEW)

**Files:**
- `intensity_profiles.py` - Profile definitions
- `depth_advisor.py` - Decision logic

**Implementation:**
```python
def should_continue_exploring(comment, parent, profile, author_cache):
    """Multi-signal decision engine."""

    # 1. Always fetch minimum visible depth
    if depth < profile.min_guaranteed_depth:
        return (True, True)

    # 2. Recent comments may not have votes yet
    if comment_age_hours < profile.recency_window_hours:
        return (True, True)

    # 3. Active discussion clusters (sibling density)
    if num_siblings >= profile.sibling_density_threshold:
        return (True, True)

    # 4. High-reputation authors
    author_profile = author_cache.get(author)
    if author_profile and author_profile.comment_karma > profile.karma_threshold:
        return (True, False)

    # 5. Engagement scores (both parent and comment)
    if parent_score <= threshold and comment_score <= threshold:
        return (False, False)  # Dead branch, stop

    return (True, False)  # Default: continue selectively
```

**Profiles:**
```python
AGGRESSIVE:
  min_guaranteed_depth: 4
  score_threshold: 0.0         # Don't stop on score alone
  recency_window_hours: None   # No time restriction
  karma_threshold: 100
  max_requests_per_post: 100

BALANCED:
  min_guaranteed_depth: 3
  score_threshold: 2.0
  recency_window_hours: 24.0
  karma_threshold: 1000
  max_requests_per_post: 25

CONSERVATIVE:
  min_guaranteed_depth: 3
  score_threshold: 5.0
  recency_window_hours: 12.0
  karma_threshold: 10000
  max_requests_per_post: 10
```

**Verdict:** Python has MAJOR feature advantage here. TypeScript needs this.

---

## 4. Author Reputation Tracking

### TypeScript: Not Implemented

**Status:** ❌ NOT IMPLEMENTED

### Python: Comprehensive Author Infrastructure (NEW)

**Files:**
- `author_cache.py` - Persistent 7-day TTL cache
- `author_fetcher.py` - Reddit user API integration
- `author_scoring.py` - Thread-scoped interestingness scoring

**Features:**

**1. Thread-Scoped Scoring (No API calls):**
```python
interestingness = (
    total_score * 1.0 +              # Raw engagement
    comment_count * 0.5 +            # Participation
    (total_length / 100) * 0.3 +     # Effort
    spawned_replies * 2.0 +          # Discussion catalyst
    max_depth_reached * 0.2          # Deep engagement
)
```

**2. Profile Fetching (Budget-aware):**
```python
# Fetch top N authors based on available budget
fetch_limit = 10 if budget > 100 else 5 if budget > 50 else 2
uncached_authors = [a for a, _ in top_authors[:fetch_limit]
                    if author_cache.get(a) is None]
new_profiles = batch_fetch_authors(uncached_authors, max_fetches=fetch_limit)
```

**3. Data Collected:**
- `comment_karma`, `link_karma`
- `account_age_days`
- `verified`, `is_gold`, `is_mod`
- `hide_from_robots`, `profile_is_private`

**API Cost:** ~1-4 req/min average (budget-aware)

**Verdict:** Python has exclusive feature. TypeScript needs this for signal-based depth.

---

## 5. Storage Layer

### TypeScript: S3 + Local Dual Support

**File:** `storage.ts`

**Features:**
- ✅ S3/R2 cloud storage via AWS SDK
- ✅ Local filesystem fallback
- ✅ Environment variable configuration
- ✅ Automatic directory creation
- ✅ Production-ready for Railway deployment

**Code:**
```typescript
class StorageDriver {
  private s3: S3Client | null;
  private useS3: boolean;

  constructor() {
    if (process.env.USE_S3 === "true") {
      this.s3 = new S3Client({
        region: process.env.AWS_REGION || "auto",
        endpoint: process.env.AWS_ENDPOINT,
        forcePathStyle: true,
        credentials: { ... }
      });
    }
  }

  async save(key: string, data: string) {
    if (this.useS3) {
      await this.s3.send(new PutObjectCommand({ ... }));
    } else {
      writeFileSync(join(this.localDir, key), data);
    }
  }
}
```

### Python: Local Filesystem Only

**Status:** ⚠️ NO CLOUD STORAGE

**Current Implementation:**
- Saves to `reddit-adaptive-sampler/temporal_test/` or `merged_posts/`
- No S3 integration
- Not suitable for Railway deployment without modification

**Verdict:** TypeScript has production advantage. Python needs S3 support.

---

## 6. Backfill Mode

### TypeScript: Full-Featured Backfill Script

**File:** `backfill.ts`

**Features:**
- ✅ Comprehensive state management (`backfill_state.json`)
- ✅ Resume from previous run (tracks processed IDs)
- ✅ Subreddit blacklisting (403/404 errors)
- ✅ Per-subreddit statistics
- ✅ Failed post tracking with retry counts
- ✅ Progress bar and detailed logging
- ✅ Rate utilization warnings
- ✅ Final summary report (top subreddits, avg comments/post)
- ✅ Safety limits (1000 posts per subreddit)
- ✅ Lookback window (72 hours)

**Code Highlights:**
```typescript
interface BackfillState {
  processedIds: string[];
  failedSubreddits: string[];
  lastRun?: string;
  stats: {
    totalSubreddits: number;
    completedSubreddits: number;
    totalPostsScraped: number;
    totalCommentsScraped: number;
    subredditStats: Record<string, SubredditStats>;
    failedPosts: FailedPost[];
  };
}
```

**Output Example:**
```
═══════════════════════════════════════════════════════
📊 BACKFILL COMPLETE
═══════════════════════════════════════════════════════
⏱️  Duration: 45.2 minutes
📡 Total API Requests: 2847
⚡ Average RPS: 1.05 (target: 10.0)
📈 Rate Utilization: 10.5%

📂 Subreddits:
   ├─ Total: 38
   ├─ Completed: 35
   └─ Blacklisted: 3

📝 Posts:
   ├─ Scraped: 1423
   ├─ Skipped: 892
   └─ Failed: 12

💬 Comments:
   ├─ Total: 45,892
   └─ Avg per post: 32.3

🏆 Top 10 Subreddits by Total Comments:
   1. r/LocalLLaMA: 12,847 comments (89 posts, avg 144.3/post)
   ...
```

### Python: No Backfill Script

**Status:** ❌ NOT IMPLEMENTED

**Current Approach:**
- Run `unified_scraper.py` continuously
- Manually track posts
- No state persistence for backfill

**Verdict:** TypeScript has major production advantage.

---

## 7. DAG Structure & Deletion Tracking

### TypeScript: Deletion Detection

**File:** `dag.ts`

**Feature:**
```typescript
class DAG {
  public merge(incomingNodes: RedditNode[], timestamp: string) {
    const incomingIds = new Set<string>();

    // ... merge logic ...

    // CHECK FOR DELETIONS (Absence)
    for (const [id, node] of this.nodes) {
      if (!incomingIds.has(id) && !node.isDeleted) {
        node.isDeleted = true;
        node.deletedAt = timestamp;
        this.dirty = true;
        stats.updatedNodes++;
      }
    }
  }
}
```

**Characteristics:**
- ✅ Tracks when comments disappear from API
- ✅ Marks deletion timestamp
- ✅ Can detect "undelete" (comment reappears)

### Python: No Deletion Tracking

**Status:** ⚠️ MISSING FEATURE

**Current Behavior:**
- Only detects `[deleted]` or `[removed]` text
- Does not track absence from subsequent fetches

**Verdict:** TypeScript has data integrity advantage.

---

## 8. Scheduling & Adaptive Systems

### TypeScript: Simple Adaptive Backoff

**File:** `scraper.ts`

**Logic:**
```typescript
if (stats.newNodes > 0) {
  // HOT: Speed up
  newInterval = Math.max(60, interval / 2);
} else if (stats.scoreDelta > 0 || stats.updatedNodes > 0) {
  // WARM: Maintain pace
  newInterval = Math.max(300, interval);
} else {
  // COLD: Backoff exponentially
  newInterval = Math.min(21600, interval * 2); // Cap at 6h
}
```

**Characteristics:**
- ✅ Simple exponential backoff
- ✅ Activity-based adjustments
- ⚠️ No global budget management
- ⚠️ No cross-post priority system

### Python: Sophisticated Multi-Layer System

**Files:**
- `adaptive_scheduler.py` - PID controller for rate optimization
- `coverage_allocator.py` - Budget distribution across subreddits
- `temperature_scheduler.py` - Temporal weighting
- `rate_controller.py` - PID-based rate control

**Components:**

**1. PID Rate Controller:**
```python
class RateController:
    def update(self, measured_rps, dt):
        error = self.target_rps - measured_rps

        self.integral += error * dt
        derivative = (error - self.prev_error) / dt if dt > 0 else 0

        output = (self.kp * error +
                  self.ki * self.integral +
                  self.kd * derivative)

        self.gain = np.clip(1.0 + output, 0.1, 2.0)
```

**2. Coverage Allocator:**
- Distributes budget across subreddits
- Priority-based allocation
- Tracks per-subreddit usage

**3. Temperature Scheduler:**
- BREAKING (t < 30min): High priority
- EMERGING (30min - 6h): Medium priority
- SUSTAINED (6h - 72h): Low priority
- RESURGENT (activity spike): Boost priority

**Verdict:** Python has much more sophisticated scheduling.

---

## 9. Telemetry & Analytics

### TypeScript: Basic Telemetry

**File:** `telemetry.ts`

**Features:**
- Logs timestamp, thread ID, delta stats
- No aggregation or analysis

### Python: Comprehensive Analytics

**Files:**
- `telemetry.py` - Event logging
- `info_gain_analytics.py` - Information gain analysis
- `scrape_cost_estimator.py` - Cost prediction
- `subreddit_priors.py` - Subreddit priority management

**Verdict:** Python has richer analytics.

---

## 10. "More" Object Expansion

### TypeScript: Not Implemented

**Code Comment:** `api.ts:159-161`
```typescript
// TODO: Handle "kind: more" (Pagination)
// For v1, we skip 'more' objects. The Python script had complex logic for this.
// We will add that in Phase 3.
```

**Status:** ❌ SKIPS "MORE" OBJECTS

### Python: Full Recursive Expansion

**File:** `reddit_scraper_api.py`

**Implementation:**
```python
def get_reddit_data_recursive(post_id, max_requests=200, ...):
    def fetch_more_comments(more_obj, depth):
        """Recursively expand 'more' objects."""
        if requests_made >= max_requests:
            return

        children = more_obj.get('children', [])
        if not children:
            return

        # Reddit API: /api/morechildren
        response = session.get(f"https://oauth.reddit.com/api/morechildren",
                               params={'children': ','.join(children[:100])})

        # Parse and recurse
        for comment in response.json():
            process_comment(comment, depth)
            if 'replies' in comment:
                fetch_more_comments(comment['replies'], depth+1)
```

**Characteristics:**
- ✅ Expands "more" objects recursively
- ✅ Respects `max_requests` budget
- ✅ Batches children (100 at a time)

**Verdict:** Python has critical feature advantage.

---

## 11. HTTP Server & Deployment

### TypeScript: Production-Ready Server

**File:** `server.ts`

**Features:**
- ✅ HTTP server on PORT (Railway compatible)
- ✅ Health check endpoint (`/` and `/health`)
- ✅ Flush endpoint (`/flush`) for manual saves
- ✅ SIGINT/SIGTERM handling
- ✅ Always-on scraper loop

**Code:**
```typescript
serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);

    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response("OK", { status: 200 });
    }

    if (url.pathname === "/flush" && req.method === "POST") {
      await scraper.shutdown();
      return new Response("Flushed", { status: 200 });
    }

    return new Response("Not Found", { status: 404 });
  }
});
```

### Python: No HTTP Server

**Status:** ❌ NOT IMPLEMENTED

**Current Deployment:**
- Launched via `launcher.py` subprocess
- No health checks
- No graceful shutdown API

**Verdict:** TypeScript production-ready, Python is not.

---

## 12. Legacy Data Migration

### TypeScript: Python Data Aggregator

**File:** `aggregator.ts`

**Purpose:** Convert Python's temporal snapshots to TypeScript DAG format

**Features:**
- ✅ Parses Python snapshot format
- ✅ Converts to `RedditNode[]`
- ✅ Merges into DAG
- ✅ Outputs TypeScript-compatible JSON

**Verdict:** TypeScript can ingest Python data.

---

## Summary Table

| Feature | TypeScript | Python | Winner |
|---------|-----------|--------|--------|
| **Rate Limiting** | Token bucket (static) | Sliding window + adaptive | 🐍 Python |
| **Depth Selection** | ❌ None | ✅ Signal-based profiles | 🐍 Python |
| **Author Tracking** | ❌ None | ✅ Full infrastructure | 🐍 Python |
| **Storage** | ✅ S3 + Local | ⚠️ Local only | 🟦 TypeScript |
| **Backfill Mode** | ✅ Full-featured | ❌ None | 🟦 TypeScript |
| **DAG Deletion Tracking** | ✅ Yes | ❌ No | 🟦 TypeScript |
| **Scheduling** | ⚠️ Simple backoff | ✅ PID + allocator + temperature | 🐍 Python |
| **"More" Expansion** | ❌ Skipped | ✅ Recursive | 🐍 Python |
| **HTTP Server** | ✅ Production-ready | ❌ None | 🟦 TypeScript |
| **Telemetry** | ⚠️ Basic | ✅ Comprehensive | 🐍 Python |
| **Legacy Import** | ✅ Python converter | N/A | 🟦 TypeScript |

---

## Recommended Port Priority

### Phase 1: Critical Production Features (Python → TypeScript)
1. **Adaptive rate limiter** - Auto-discovers limits from headers
2. **Signal-based depth selection** - Intensity profiles system
3. **Author infrastructure** - Caching + scoring + fetching
4. **"More" object expansion** - Recursive comment loading

### Phase 2: Advanced Scheduling (Python → TypeScript)
5. **PID rate controller** - Optimal rate utilization
6. **Coverage allocator** - Budget distribution
7. **Temperature scheduler** - Temporal weighting

### Phase 3: Production Infrastructure (TypeScript → Python)
8. **S3 storage support** - Cloud persistence
9. **Backfill script** - Historical data collection
10. **DAG deletion tracking** - Data integrity

### Phase 4: Deployment (TypeScript Only)
11. **HTTP server already exists** - Use TypeScript exclusively

---

## Files Requiring Port

### Python → TypeScript (Essential)

| Python File | Purpose | TypeScript Equivalent Needed |
|------------|---------|------------------------------|
| `intensity_profiles.py` | Profile definitions | `src/intensity_profiles.ts` |
| `depth_advisor.py` | Signal-based decisions | `src/depth_advisor.ts` |
| `author_cache.py` | 7-day TTL cache | `src/author_cache.ts` |
| `author_fetcher.py` | Reddit user API | `src/author_fetcher.ts` |
| `author_scoring.py` | Thread-scoped scoring | `src/author_scoring.ts` |
| `rate_limiter.py` (UPDATE) | Adaptive headers | Update `src/rate_limiter.ts` |
| `reddit_scraper_api.py` (PARTIAL) | "More" expansion logic | Update `src/api.ts` |

### Optional (Advanced)

| Python File | Purpose | Priority |
|------------|---------|----------|
| `adaptive_scheduler.py` | PID controller | Medium |
| `coverage_allocator.py` | Budget allocation | Medium |
| `temperature_scheduler.py` | Temporal weighting | Low |
| `rate_controller.py` | PID rate control | Medium |

---

## Validation Plan

### After Porting to TypeScript:

1. **Run both versions on same posts** - Compare outputs
2. **Verify DAG structure matches** - Node counts, depths, scores
3. **Compare API request counts** - Ensure similar efficiency
4. **Validate author cache behavior** - Check fetching logic
5. **Test intensity profiles** - AGGRESSIVE/BALANCED/CONSERVATIVE
6. **Monitor rate limit discovery** - Should adjust from 90→100
7. **Check deletion tracking** - Ensure TypeScript still detects deletions

---

## Next Steps

1. ✅ **This document** - Feature comparison complete
2. ⏭️ **Port intensity profiles** - Start with `intensity_profiles.ts`
3. ⏭️ **Port depth advisor** - Signal-based logic
4. ⏭️ **Port author infrastructure** - Cache, fetcher, scoring
5. ⏭️ **Update rate limiter** - Add adaptive header reading
6. ⏭️ **Update API class** - Add "more" expansion
7. ⏭️ **Integration testing** - Compare outputs
8. ⏭️ **Railway deployment** - TypeScript-only production
