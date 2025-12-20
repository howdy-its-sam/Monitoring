#!/usr/bin/env python3
"""
Continuous Temperature Scheduler
Replaces discrete 3-phase system with continuous temperature T ∈ [0,1].
Based on reference_books/adaptive_scheduler_reference.ipynb
"""

import math
import heapq
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

# Policy knobs (env overrides for quick experimentation)
ZERO_STREAK_SLOWDOWN_THRESHOLD = int(os.getenv("SCRAPER_ZERO_SLOWDOWN_THRESHOLD", "1"))
ZERO_STREAK_SLOWDOWN_MULT = float(os.getenv("SCRAPER_ZERO_SLOWDOWN_MULT", "1.5"))
MAX_INTERVAL_DEFAULT_HOURS = float(os.getenv("SCRAPER_MAX_INTERVAL_HOURS", "1.5"))
DORMANT_INTERVAL_CAP_HOURS = float(os.getenv("SCRAPER_DORMANT_INTERVAL_CAP_HOURS", "6.0"))
MAX_INTERVAL_DEFAULT_HOURS = max(0.5, min(MAX_INTERVAL_DEFAULT_HOURS, DORMANT_INTERVAL_CAP_HOURS))
DORMANT_INTERVAL_CAP_HOURS = max(MAX_INTERVAL_DEFAULT_HOURS, DORMANT_INTERVAL_CAP_HOURS)


@dataclass
class ScrapeDelta:
    """
    Records information gain from a single scrape.
    """
    ts: datetime
    new_comments: int = 0
    edited_comments: int = 0
    score_changed: int = 0
    deleted_comments: int = 0
    
    def weighted(self, w_new: float = 1.0, w_edit: float = 0.5, 
                 w_score: float = 0.2, w_delete: float = 0.1) -> float:
        """
        Compute weighted ΔInfo.
        """
        return (w_new * self.new_comments +
                w_edit * self.edited_comments +
                w_score * self.score_changed +
                w_delete * self.deleted_comments)


@dataclass
class PostState:
    """
    Runtime state for a tracked post.
    """
    post_id: str
    subreddit: str = "news"  # Default
    url: str = ""
    
    # Scrape history
    deltas: List[ScrapeDelta] = field(default_factory=list)
    last_scrape_ts: Optional[datetime] = None
    last_nonzero_ts: Optional[datetime] = None
    scrape_count: int = 0  # Number of times scraped
    
    # Computed metrics (cached)
    recent_rate: float = 0.0        # ΔInfo/hour over last k scrapes
    volatility: float = 0.0         # std(ΔInfo) over last k scrapes
    temperature: float = 0.0        # T ∈ [0,1]
    lambda_hat: float = 0.15        # Decay rate (prior from subreddit)
    
    # Metadata (for cost estimation)
    num_comments_discovered: int = 0  # Comment count at discovery
    
    # Scheduling state
    next_due: Optional[datetime] = None
    interval_hours: float = 1.0
    zero_delta_streak: int = 0
    last_delta_info: float = 0.0
    ready_for_retirement: bool = False
    
    def __post_init__(self):
        """Initialize next_due if not set."""
        if self.next_due is None and self.last_scrape_ts:
            self.next_due = self.last_scrape_ts + timedelta(hours=self.interval_hours)


@dataclass(order=True)
class QueueEntry:
    """
    Priority queue entry for scheduling.
    Uses due time as primary ordering.
    """
    priority: float  # Lower = higher priority (for heapq min-heap)
    post_id: str = field(compare=False)
    next_time: datetime = field(compare=False)


def hours_between(a: datetime, b: datetime) -> float:
    """
    Compute hours between two datetimes.
    """
    return max(0.0, (a - b).total_seconds() / 3600.0)


def compute_recent_stats(post: PostState, k: int = 5, 
                        weights: tuple = (1.0, 0.5, 0.2, 0.1)):
    """
    Update recent_rate and volatility from last k deltas.
    Also updates last_nonzero_ts.
    
    Args:
        post: PostState to update
        k: Window size (default 5 scrapes)
        weights: (w_new, w_edit, w_score, w_delete)
    """
    if not post.deltas:
        post.recent_rate = 0.0
        post.volatility = 0.0
        return
    
    # Sort by timestamp and take last k
    ds = sorted(post.deltas, key=lambda d: d.ts)[-k:]
    vals = [d.weighted(*weights) for d in ds]
    
    # Compute rate (ΔInfo per hour)
    if len(ds) >= 2:
        hours = hours_between(ds[-1].ts, ds[0].ts) or 1e-6
        rate = sum(vals) / hours
    else:
        rate = vals[-1] if vals else 0.0
    
    post.recent_rate = rate
    
    # Compute volatility (std)
    if len(vals) > 1:
        import statistics
        post.volatility = statistics.stdev(vals)
    else:
        post.volatility = 0.0
    
    # Update last_nonzero_ts
    for d in reversed(ds):
        if d.weighted(*weights) > 0:
            post.last_nonzero_ts = d.ts
            break


def compute_temperature(posts: List[PostState], now: datetime,
                       alpha: float = 0.6, beta: float = 0.3, gamma: float = 0.1):
    """
    Compute continuous temperature T ∈ [0,1] for all posts.
    
    T_i = α * (rate_i / max_rate)           # Recent activity
        + β * exp(-λ_i * h_i)               # Decay since last change
        + γ * (volatility_i / max_vol)      # Uncertainty
    
    Args:
        posts: List of PostState objects
        now: Current time
        alpha, beta, gamma: Weight parameters (should sum to 1.0)
    """
    if not posts:
        return
    
    # Normalize recent_rate and volatility across cohort
    max_rate = max((p.recent_rate for p in posts), default=1.0) or 1.0
    max_vol = max((p.volatility for p in posts), default=1.0) or 1.0
    
    for p in posts:
        # Hours since last non-zero ΔInfo
        h = hours_between(now, p.last_nonzero_ts or p.last_scrape_ts or now)
        
        # Three-term temperature
        t = (alpha * (p.recent_rate / max_rate) +
             beta * math.exp(-p.lambda_hat * h) +
             gamma * (p.volatility / max_vol))
        
        # Clamp to [0, 1]
        p.temperature = max(0.0, min(1.0, t))


def compute_interval_hours(T: float, k: float = 1.5, g: float = 1.0,
                           min_h: float = 0.008, max_h: float = MAX_INTERVAL_DEFAULT_HOURS) -> float:
    """
    Compute scrape interval from temperature using bounded log curve.
    
    NEW: Much tighter bounds (30s to 30min) prevent multi-hour waits.
    Uses log curve for smooth scaling across temperature range.
    
    Args:
        T: Temperature ∈ [0,1]
        k: Tunable constant (unused in new formula, kept for compatibility)
        g: Global gain from rate controller (default 1.0)
        min_h: Minimum interval in hours (default 0.008h = 30s)
        max_h: Maximum interval in hours (default 0.5h = 30min)
    
    Returns:
        Interval in hours
    """
    MIN_INTERVAL_HOURS = min_h  # 0.008h = 30 seconds
    MAX_INTERVAL_HOURS = max_h  # default configurable via env
    ALPHA = 3.0  # Curve strength
    
    # Bounded log curve: smooth transition from hot to cold
    T_clamped = max(0.0, min(1.0, T))
    base_interval = MIN_INTERVAL_HOURS
    
    # Log-based scaling
    dt = base_interval * (1 + ALPHA * math.log1p(max(0.0, 1.0 - T_clamped)))
    
    # Hard clamps
    dt = max(MIN_INTERVAL_HOURS, min(MAX_INTERVAL_HOURS, dt))
    
    return dt * g


def compute_priority(T: float, lam: float, lateness_frac: float, 
                    dt: float) -> float:
    """
    Compute lateness-aware priority score.
    
    S_i = T_i / (1 + λ_i * φ_i * Δt_i)
    
    Lower score = higher priority (delays low-λ posts first).
    
    Args:
        T: Temperature
        lam: Lambda (decay rate)
        lateness_frac: φ = (now - due) / Δt
        dt: Interval hours
    
    Returns:
        Priority score (lower = more urgent)
    """
    return T / (1.0 + lam * lateness_frac * dt)


def schedule_next(posts: List[PostState], now: datetime, g: float,
                 lateness_setpoint: float = 0.15,
                 clamp_early_lateness: float = 0.25) -> List[QueueEntry]:
    """
    Build priority queue for next scrapes.
    
    Args:
        posts: List of PostState objects
        now: Current time
        g: Global gain from rate controller
        lateness_setpoint: Target average lateness (default 15%)
        clamp_early_lateness: Max lateness for recently active posts (default 25%)
    
    Returns:
        Priority queue (heapq min-heap) of QueueEntry objects
    """
    q = []
    
    for p in posts:
        # AGGRESSIVE INITIAL INTERVALS for new posts
        if p.scrape_count < 2:
            if p.scrape_count == 0:
                dt = 1.0 / 60.0  # 1 minute (0.0167 hours)
            else:  # scrape_count == 1
                dt = 3.0 / 60.0  # 3 minutes (0.05 hours)
            
            p.interval_hours = dt
        else:
            # Normal temperature-based interval
            dt = compute_interval_hours(p.temperature, g=g)

            if ZERO_STREAK_SLOWDOWN_THRESHOLD >= 0:
                streak = getattr(p, "zero_delta_streak", 0)
                if streak > 0 and streak >= ZERO_STREAK_SLOWDOWN_THRESHOLD:
                    # Exponential slowdown capped for politeness
                    slowdown_pow = streak - ZERO_STREAK_SLOWDOWN_THRESHOLD + 1
                    slowdown = ZERO_STREAK_SLOWDOWN_MULT ** max(0, slowdown_pow)
                    dt = min(dt * slowdown, DORMANT_INTERVAL_CAP_HOURS)

            p.interval_hours = dt
        
        # Compute due time with staggered reschedules (FIX #12)
        if p.last_scrape_ts:
            # Stagger within interval window to prevent synchronized readiness
            # Use symmetric randomization to avoid upward bias in average interval
            stagger_factor = random.uniform(-0.15, 0.15)  # Randomize ±15% of interval
            staggered_dt = dt * (1.0 + stagger_factor)
            due = p.last_scrape_ts + timedelta(hours=staggered_dt)
        else:
            due = now  # Never scraped, do it now
        
        p.next_due = due
        
        # Compute lateness fraction
        late_hours = hours_between(now, due)
        phi = late_hours / dt if dt > 0 else 0.0
        phi = max(0.0, phi)
        
        # Early-window clamp: limit lateness for recently active posts
        if p.last_nonzero_ts:
            time_since_activity = hours_between(now, p.last_nonzero_ts)
            if time_since_activity < dt:
                phi = min(phi, clamp_early_lateness)
        
        # Compute priority score
        S = compute_priority(p.temperature, p.lambda_hat, phi, dt)
        
        # Use due time + small priority-based epsilon for ordering
        # This creates time-ordered queue with priority tie-breaking
        eps_seconds = (1.0 - S) * 1e-6  # Higher S → smaller epsilon → earlier in queue
        priority_time = due.timestamp() + eps_seconds
        
        heapq.heappush(q, QueueEntry(
            priority=priority_time,
            post_id=p.post_id,
            next_time=due
        ))
    
    return q


def get_ready_posts(queue: List[QueueEntry], now: datetime, limit: Optional[int] = None) -> List[str]:
    """
    Extract post_ids from queue in priority order.

    Returns ALL posts sorted by temperature/priority. Time-based filtering
    was removed to let the rate limiter be the sole temporal gatekeeper.
    See DECISIONS.md entry 2025-11-28.

    Args:
        queue: Priority queue from schedule_next()
        now: Unused (kept for API compatibility)
        limit: Optional limit on number of posts to return

    Returns:
        List of post_ids in priority order
    """
    ready = [entry.post_id for entry in queue]

    if limit is not None:
        ready = ready[:limit]

    return ready


def compute_avg_lateness(posts: List[PostState], now: datetime) -> float:
    """
    Compute average lateness fraction across all posts.
    
    Used for rate controller feedback.
    
    Args:
        posts: List of PostState objects
        now: Current time
    
    Returns:
        Average lateness fraction
    """
    if not posts:
        return 0.0
    
    latenesses = []
    for p in posts:
        if p.next_due and p.interval_hours > 0:
            late_hours = hours_between(now, p.next_due)
            phi = late_hours / p.interval_hours
            latenesses.append(max(0.0, phi))
    
    return sum(latenesses) / len(latenesses) if latenesses else 0.0


if __name__ == '__main__':
    # Simple demonstration
    print("="*80)
    print("🌡️  TEMPERATURE SCHEDULER - Demo")
    print("="*80)
    print()
    
    # Create sample posts
    now = datetime.now(timezone.utc)
    
    posts = [
        PostState(
            post_id="hot_post",
            last_scrape_ts=now - timedelta(hours=0.5),
            last_nonzero_ts=now - timedelta(hours=0.5),
            lambda_hat=0.8,  # Fast decay
            deltas=[
                ScrapeDelta(ts=now - timedelta(hours=1), new_comments=50, score_changed=100),
                ScrapeDelta(ts=now - timedelta(hours=0.5), new_comments=30, score_changed=80),
            ]
        ),
        PostState(
            post_id="warm_post",
            last_scrape_ts=now - timedelta(hours=2),
            last_nonzero_ts=now - timedelta(hours=2),
            lambda_hat=0.3,  # Medium decay
            deltas=[
                ScrapeDelta(ts=now - timedelta(hours=4), new_comments=10, score_changed=20),
                ScrapeDelta(ts=now - timedelta(hours=2), new_comments=5, score_changed=10),
            ]
        ),
        PostState(
            post_id="cool_post",
            last_scrape_ts=now - timedelta(hours=12),
            last_nonzero_ts=now - timedelta(hours=12),
            lambda_hat=0.1,  # Slow decay
            deltas=[
                ScrapeDelta(ts=now - timedelta(hours=24), new_comments=2, score_changed=5),
                ScrapeDelta(ts=now - timedelta(hours=12), new_comments=1, score_changed=2),
            ]
        ),
    ]
    
    # Compute stats and temperature
    for p in posts:
        compute_recent_stats(p)
    compute_temperature(posts, now)
    
    # Build queue
    queue = schedule_next(posts, now, g=1.0)
    
    # Display results
    print("Post States:")
    print(f"{'Post ID':<15} {'T':<6} {'λ':<6} {'Rate':<8} {'Vol':<6} {'Δt(h)':<8} {'Due':<20}")
    print("-"*80)
    for p in posts:
        due_str = p.next_due.strftime("%H:%M:%S") if p.next_due else "N/A"
        print(f"{p.post_id:<15} {p.temperature:<6.3f} {p.lambda_hat:<6.2f} "
              f"{p.recent_rate:<8.2f} {p.volatility:<6.2f} {p.interval_hours:<8.2f} {due_str:<20}")
    
    print()
    print("Queue (priority order):")
    for i, entry in enumerate(sorted(queue)[:10], 1):
        print(f"  {i}. {entry.post_id} (due: {entry.next_time.strftime('%H:%M:%S')})")
    
    print()
    print("Ready to scrape now:")
    ready = get_ready_posts(queue, now)
    if ready:
        for post_id in ready:
            print(f"  ✓ {post_id}")
    else:
        print("  (none)")
    
    print()
    print("="*80)

