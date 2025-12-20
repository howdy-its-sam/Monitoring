# Reddit Adaptive Scraper - Design Philosophy

## Core Principle

**"Use tokens as available, not as scheduled"**

Rate limit utilization is the primary constraint. All temporal pacing should happen at the rate limiter layer via `wait_for_budget()`. The system should consume tokens as they become available, with the rate limiter providing the only temporal control.

## Architecture Philosophy

### Layer Responsibilities

1. **Rate Limiter** (`rate_limiter.py`)
   - Controls WHEN requests happen (temporal pacing)
   - Implements adaptive intervals based on buffer size
   - Provides `wait_for_budget()` as the sole temporal gatekeeper
   - Dynamically adjusts consumption rate: high buffer = fast, low buffer = slow

2. **Scheduler** (`adaptive_scheduler.py`, `temperature_scheduler.py`)
   - Controls WHICH posts to scrape (priority ranking)
   - Calculates temperature/information gain potential
   - **Does NOT enforce timing** - only ranks by value
   - Returns posts sorted by priority, not filtered by time

3. **Orchestration** (`unified_scraper.py`)
   - Launches scrapes continuously
   - NO timing logic, NO fixed sleeps
   - Relies entirely on rate limiter for pacing

### Separation of Concerns

- **Priority** (which post is most valuable?) → Scheduler
- **Timing** (when can we scrape?) → Rate Limiter
- **Execution** (run the scrape) → Orchestration

Never mix these concerns. A single layer should not do both priority ranking AND temporal control.

## Target Metrics (Provisional Baselines)

These are **initial intuitive estimates** for comparison, not rigid goals. They represent what we currently think the system should produce, but may be revised as we learn more.

### Rate Limit Utilization
- **Waste: <10%** (currently 28%)
  - Waste = unused budget that expires
  - Lower is better, but 0% might indicate we're not leaving safety margin

- **Average Buffer: 5-15 tokens** (currently 37)
  - Enough for burst capacity, not so much we're hoarding

### Scrape Patterns (Observational Targets)

**Purpose:** These numbers define the data collection pattern we think we want. They're for tracking "what are we getting?" vs "what did we think we wanted?" to guide iterative refinement.

**Discovery Phase:**
- All posts seen within 5-15 minutes of posting
- Quick initial assessment (scrape 0 at ~1min, scrape 1 at ~3-4min)

**Quiet Posts (low activity):**
- Target: 3-5 scrapes over lifetime
- Pattern: Initial check, 1-2 hour later, 1-2 on tail before retirement
- Goal: Confirm it's not interesting, retire efficiently

**Active Posts (high activity):**
- Target: 8-10 scrapes over lifetime
- Pattern: Several during active phase, few during fade-out
- Goal: Capture growth curve and decay pattern

**Avoid:**
- Over-scraping posts that show no change
- Repeated scrapes with no new information

**Important Note:** These numbers may turn out to be unachievable, too much data, or not enough data. They're provisional. If we discover a coherent configuration can't achieve these, or that these metrics are wrong, we adjust the targets - not the architecture.

## Anti-Patterns (Never Do)

These are violations of core principles:

- ❌ **Fixed sleep times** - `time.sleep(60)` or similar hard-coded delays
- ❌ **Time-based filtering in scheduler** - "is this post due yet?"
- ❌ **Orchestration-level pacing** - sleeping between batches
- ❌ **Multiple temporal control layers** - only rate limiter should control timing
- ❌ **Schedule-driven execution** - "scrape this post at 2:15pm"

## Design Trade-offs

### Utilization vs. Information Optimality

**Previous approach:** Pontryagin optimal control maximizes information gain but creates 28% waste

**Current approach:** Greedy JIT selection maximizes utilization, may sacrifice theoretical information optimality

**Decision:** Prioritize utilization. Information ranking still matters for WHICH post, but not WHEN.

### Smoothness vs. Availability

**Previous approach:** Spread scrapes evenly over time via scheduling

**Current approach:** Use tokens as they become available, accept burstiness

**Decision:** Prefer availability. Adaptive intervals provide natural smoothing without rigid schedules.

### Complexity vs. Simplicity

**Principle:** Keep it simple. Add complexity only when empirically justified by results.

**Examples:**
- O(n) calculation on each selection is fine - rate limiter is bottleneck, not CPU
- Cache only if profiling shows it matters
- Use straightforward greedy selection over complex optimization

## Key Implementation Details

### Adaptive Interval Calculation

Currently in `rate_limiter.py:get_adaptive_interval()`:
- High buffer (50+ tokens) → 0.5s interval (fast consumption)
- Medium buffer (25-50) → 2.0s interval
- Low buffer (10-25) → 4.0s interval
- Very low (<10) → 6.0s interval (match refill rate)

Creates self-dampening feedback loop.

### Temperature-Based Priority

Currently in `temperature_scheduler.py:compute_temperature()`:
```
temperature = 0.6 * (recent_rate / max_rate)      # Recent activity
            + 0.3 * exp(-λ * hours_since_change)  # Time decay
            + 0.1 * (volatility / max_vol)        # Uncertainty
```

Used for ranking (which post?), not timing (when to scrape?).

### Zero-Streak Slowdown

Posts with consecutive zero-information scrapes get deprioritized to avoid waste.

## Evolution and Iteration

This document captures current thinking. As we learn from empirical results:

1. **Metrics reveal patterns** → Update provisional targets
2. **Targets prove unachievable** → Adjust targets or architecture
3. **New constraints discovered** → Add to anti-patterns
4. **Complexity justified** → Document trade-offs

The goal is continuous improvement based on observation, not adherence to initial guesses.

## Related Documentation

- **DECISIONS.md** - Chronological log of major decisions with rationale
- **ARCHITECTURE.md** - System diagrams and data flow (if created)
- **scraper_report.sh** - Current metrics vs. targets
