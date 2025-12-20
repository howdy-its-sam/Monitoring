#!/usr/bin/env python3
"""
Adaptive Information-Weighted Scheduler
Main control loop integrating temperature, rate control, and subreddit priors.
Based on reference_books/adaptive_scheduler_reference.ipynb
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
import heapq

from temperature_scheduler import (
    PostState, ScrapeDelta, QueueEntry,
    compute_recent_stats, compute_temperature, 
    schedule_next, get_ready_posts, compute_avg_lateness,
    hours_between
)
from rate_controller import RateController
from subreddit_priors import SubredditPriors
from info_gain_analytics import compute_delta_info

# Dormancy policy knobs (override via SCRAPER_* env vars to tune without code changes)
DORMANCY_MIN_SCRAPES = int(os.getenv("SCRAPER_DORMANCY_MIN_SCRAPES", "3"))
DORMANCY_ZERO_STREAK = int(os.getenv("SCRAPER_DORMANCY_ZERO_STREAK", "2"))
DORMANCY_INACTIVITY_HOURS = float(os.getenv("SCRAPER_DORMANCY_INACTIVITY_H", "12"))
DORMANCY_LOOKBACK = int(os.getenv("SCRAPER_DORMANCY_LOOKBACK", "4"))

# Budget conservation knobs
BUDGET_CONSERVE_SCRAPE_CAP = int(os.getenv("SCRAPER_BUDGET_SCRAPE_CAP", "3"))
BUDGET_CONSERVE_LAUNCH_CAP = int(os.getenv("SCRAPER_BUDGET_LAUNCH_CAP", "5"))


class AdaptiveScheduler:
    """
    Main adaptive scheduler coordinating all components.
    
    Replaces the old 3-phase discrete priority system with continuous
    temperature-based scheduling with rate-limit feedback.
    """
    
    def __init__(self,
                 target_rps: float = 10.0,
                 lateness_setpoint: float = 0.15,
                 state_dir: str = "temporal_test"):
        """
        Initialize adaptive scheduler.
        
        Args:
            target_rps: Target requests per second (default 10.0 = 600/min)
            lateness_setpoint: Target average lateness fraction (default 0.15 = 15%)
            state_dir: Directory for storing scheduler state
        """
        self.target_rps = target_rps
        self.lateness_setpoint = lateness_setpoint
        self.state_dir = state_dir
        
        # Components
        self.controller = RateController(target_rps=target_rps)
        self.priors = SubredditPriors()
        
        # Post tracking
        self.posts: Dict[str, PostState] = {}  # post_id → PostState
        
        # Metrics
        self.total_scrapes = 0
        self.total_delta_info = 0.0
        self.last_tick_time = None

        # Budget-aware prioritisation
        self._conserve_budget = False
        
        # Load existing state if available
        self._load_state()
    
    def add_post(self, post_id: str, url: str, subreddit: str = "news") -> PostState:
        """
        Add a new post to tracking.
        
        Initializes with subreddit priors.
        
        Args:
            post_id: Reddit post ID
            url: Post URL
            subreddit: Subreddit name
        
        Returns:
            Created PostState
        """
        if post_id in self.posts:
            return self.posts[post_id]
        
        # Initialize with subreddit priors
        lambda_prior = self.priors.get_lambda(subreddit)
        
        post = PostState(
            post_id=post_id,
            url=url,
            subreddit=subreddit,
            lambda_hat=lambda_prior,
            last_scrape_ts=None,
            last_nonzero_ts=None,
        )
        
        self.posts[post_id] = post
        return post
    
    def update_post_metadata(self, post_id: str, num_comments: int):
        """
        Update post metadata (e.g., comment count at discovery).
        
        Used for pre-scrape cost estimation.
        
        Args:
            post_id: Reddit post ID
            num_comments: Comment count from discovery
        """
        if post_id in self.posts:
            self.posts[post_id].num_comments_discovered = num_comments
    
    def get_post_metadata(self, post_id: str) -> Dict[str, any]:
        """
        Get post metadata for cost estimation.
        
        Returns metadata including comment count, subreddit, temperature, etc.
        
        Args:
            post_id: Reddit post ID
        
        Returns:
            Dictionary with post metadata
        """
        if post_id not in self.posts:
            return {"num_comments": 0, "subreddit": "unknown", "temperature": 0.0}
        
        post = self.posts[post_id]
        
        # Get latest comment count estimate
        # Use discovered count if available, otherwise estimate from deltas
        num_comments = post.num_comments_discovered
        if num_comments == 0 and post.deltas:
            # Estimate based on most recent scrape
            last_delta = post.deltas[-1]
            num_comments = getattr(last_delta, 'total_comments', 0)
        
        return {
            "num_comments": num_comments,
            "subreddit": post.subreddit,
            "temperature": post.temperature,
            "scrape_count": post.scrape_count,
            "url": post.url
        }
    
    def record_scrape(self, post_id: str, delta: ScrapeDelta):
        """
        Record the result of a scrape.
        
        Updates post state with new delta information.
        
        Args:
            post_id: Reddit post ID
            delta: ScrapeDelta from this scrape
        """
        if post_id not in self.posts:
            return
        
        post = self.posts[post_id]

        delta_value = delta.weighted()
        post.deltas.append(delta)
        post.last_scrape_ts = delta.ts
        post.scrape_count += 1  # FIX #2: Increment scrape counter
        post.last_delta_info = delta_value
        
        if delta_value > 0:
            post.last_nonzero_ts = delta.ts
            post.zero_delta_streak = 0
            post.ready_for_retirement = False
        else:
            post.zero_delta_streak = min(post.zero_delta_streak + 1, 1000)
            if (
                post.scrape_count >= max(DORMANCY_MIN_SCRAPES, 1)
                and post.zero_delta_streak >= max(DORMANCY_ZERO_STREAK, 1)
            ):
                post.ready_for_retirement = True
        
        # Update metrics
        self.total_scrapes += 1
        self.total_delta_info += delta_value
    
    def control_tick(self, now: Optional[datetime] = None, 
                    instantaneous_rps: Optional[float] = None) -> List[QueueEntry]:
        """
        Main control loop tick.
        
        1. Update stats & temperature for all posts
        2. Build priority queue
        3. Update global gain (if rps provided)
        4. Return queue
        
        Args:
            now: Current time (default: now in UTC)
            instantaneous_rps: Optional actual measured RPS from API request counter
        
        Returns:
            Priority queue of posts ready to scrape
        """
        if now is None:
            now = datetime.now(timezone.utc)
        
        self.last_tick_time = now
        
        if not self.posts:
            return []
        
        posts_list = list(self.posts.values())
        
        # 1. Update stats & temperature
        for p in posts_list:
            compute_recent_stats(p, k=5)
        compute_temperature(posts_list, now)
        
        # 2. Build priority queue
        queue = schedule_next(
            posts_list, 
            now, 
            g=self.controller.g,
            lateness_setpoint=self.lateness_setpoint
        )
        
        # 3. Update global gain (if rps measurement provided)
        if instantaneous_rps is not None:
            avg_lateness = compute_avg_lateness(posts_list, now)
            self.controller.update(
                instantaneous_rps,
                avg_lateness,
                self.lateness_setpoint
            )
        
        return queue
    
    def get_next_posts(self, limit: int = 1) -> List[str]:
        """
        Get next post(s) to scrape.
        
        Gain now scales HOW MANY posts launch, not WHETHER they can.
        
        Args:
            limit: Maximum number of posts to return
        
        Returns:
            List of post_ids in priority order
        """
        now = datetime.now(timezone.utc)
        queue = self.control_tick(now)
        
        # All posts past due time are candidates
        ready = get_ready_posts(queue, now, limit=None)
        ready = [
            post_id for post_id in ready
            if post_id in self.posts and not self.posts[post_id].ready_for_retirement
        ]
        
        if not ready:
            return []
        
        # FIX #9: Gain scales launch capacity based on target throughput
        # Instead of base_concurrency, use controller's target RPS
        target_rps = getattr(self.controller, 'target', 10.0)  # Default to 10 if not available
        launch_cap = int(max(5, target_rps * max(0.5, self.controller.g) * 0.5))

        if self._conserve_budget:
            # Prefer new or lightly-scraped posts when conserving budget.
            ready.sort(
                key=lambda pid: (
                    self.posts[pid].scrape_count,
                    -self.posts[pid].temperature
                )
            )
            # Bubble low-scrape posts to the front while still allowing fallback.
            primary = [pid for pid in ready if self.posts[pid].scrape_count < BUDGET_CONSERVE_SCRAPE_CAP]
            if primary:
                remainder = [pid for pid in ready if pid not in primary]
                ready = primary + remainder
            launch_cap = max(1, min(launch_cap, BUDGET_CONSERVE_LAUNCH_CAP))
        
        # Respect the user's limit if provided
        if limit is not None:
            launch_cap = min(launch_cap, limit)
        
        # Return up to launch_cap posts
        return ready[:launch_cap]
    
    def set_budget_conservation(self, conserve: bool) -> None:
        """
        Toggle budget conservation mode.

        When enabled, new/low-scrape posts are prioritised ahead of repeat
        scrapes and launch capacity is trimmed to preserve tokens for intake.
        """
        self._conserve_budget = conserve
    
    def retire_dormant_posts(self):
        """
        Check for dormant posts and record them in subreddit priors.
        
        A post is considered dormant if:
        - It has 3+ consecutive zero-Δ scrapes
        - OR it hasn't had activity in 48+ hours
        """
        from info_gain_analytics import (
            time_to_dormancy_hours,
            waste_rate,
            estimate_lambda_from_curve
        )
        
        now = datetime.now(timezone.utc)
        to_retire = []
        
        retire_reasons: Dict[str, str] = {}
        
        for post_id, post in self.posts.items():
            if post.scrape_count < max(DORMANCY_MIN_SCRAPES, 1):
                continue
            
            recent_deltas = post.deltas[-max(DORMANCY_LOOKBACK, 1):]
            zero_streak = getattr(post, "zero_delta_streak", 0)
            inactivity_hours = (
                hours_between(now, post.last_nonzero_ts)
                if post.last_nonzero_ts else None
            )
            since_last_scrape = (
                hours_between(now, post.last_scrape_ts)
                if post.last_scrape_ts else None
            )
            
            reason: Optional[str] = None
            if zero_streak >= max(DORMANCY_ZERO_STREAK, 1):
                reason = f"{zero_streak} zero-Δ scrapes"
            elif recent_deltas and all(d.weighted() == 0 for d in recent_deltas):
                reason = f"{len(recent_deltas)} recent zero-Δ scrapes"
            elif inactivity_hours is not None and inactivity_hours >= DORMANCY_INACTIVITY_HOURS:
                reason = f"no activity for {inactivity_hours:.1f}h"
            elif since_last_scrape is not None and since_last_scrape >= DORMANCY_INACTIVITY_HOURS * 1.5:
                reason = f"no scrape gain for {since_last_scrape:.1f}h"
            elif post.ready_for_retirement:
                reason = "flagged for retirement"
            
            if reason:
                to_retire.append(post_id)
                retire_reasons[post_id] = reason
        
        # Record in priors and remove
        for post_id in set(to_retire):
            post = self.posts[post_id]
            
            # Compute final metrics
            timeline = [d.ts for d in post.deltas]
            deltas_weighted = [d.weighted() for d in post.deltas]
            
            lambda_est = estimate_lambda_from_curve(timeline, deltas_weighted) or post.lambda_hat
            dormancy_h = time_to_dormancy_hours(timeline, deltas_weighted)
            waste = waste_rate(deltas_weighted)
            
            # Record in priors
            self.priors.record_post(
                post.subreddit,
                lambda_est,
                half_life_h=dormancy_h,
                waste_rate=waste
            )
            
            # Remove from tracking
            del self.posts[post_id]
            
            reason = retire_reasons.get(post_id)
            reason_suffix = f" – {reason}" if reason else ""
            print(f"🛌 Retired dormant post: {post_id} (λ={lambda_est:.3f}{reason_suffix})")
    
    def get_status(self) -> Dict:
        """
        Get current scheduler status for monitoring.
        
        Returns:
            Dict with metrics and state
        """
        now = datetime.now(timezone.utc)
        
        return {
            "total_posts": len(self.posts),
            "total_scrapes": self.total_scrapes,
            "total_delta_info": self.total_delta_info,
            "avg_delta_info_per_scrape": self.total_delta_info / self.total_scrapes if self.total_scrapes > 0 else 0,
            "controller": self.controller.get_status(),
            "last_tick": self.last_tick_time.isoformat() if self.last_tick_time else None,
        }
    
    def _save_state(self):
        """
        Persist scheduler state to disk.
        
        Saves post states to temporal_test/{post_id}/scheduler_state.json
        """
        for post_id, post in self.posts.items():
            post_dir = os.path.join(self.state_dir, post_id)
            os.makedirs(post_dir, exist_ok=True)
            
            state_file = os.path.join(post_dir, "scheduler_state.json")
            
            # Serialize post state
            state_data = {
                "post_id": post.post_id,
                "url": post.url,
                "subreddit": post.subreddit,
                "lambda_hat": post.lambda_hat,
                "temperature": post.temperature,
                "recent_rate": post.recent_rate,
                "volatility": post.volatility,
                "interval_hours": post.interval_hours,
                "last_scrape_ts": post.last_scrape_ts.isoformat() if post.last_scrape_ts else None,
                "last_nonzero_ts": post.last_nonzero_ts.isoformat() if post.last_nonzero_ts else None,
                "next_due": post.next_due.isoformat() if post.next_due else None,
                "delta_count": len(post.deltas),
                "total_delta_info": sum(d.weighted() for d in post.deltas),
                "zero_delta_streak": post.zero_delta_streak,
                "ready_for_retirement": post.ready_for_retirement,
                "last_delta_info": post.last_delta_info,
            }
            
            with open(state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
    
    def _load_state(self):
        """
        Load scheduler state from disk if available.
        """
        if not os.path.exists(self.state_dir):
            return
        
        for post_id in os.listdir(self.state_dir):
            post_dir = os.path.join(self.state_dir, post_id)
            if not os.path.isdir(post_dir):
                continue
            
            state_file = os.path.join(post_dir, "scheduler_state.json")
            if not os.path.exists(state_file):
                continue
            
            try:
                with open(state_file, 'r') as f:
                    state_data = json.load(f)
                
                # Reconstruct PostState (without full delta history)
                post = PostState(
                    post_id=state_data["post_id"],
                    url=state_data["url"],
                    subreddit=state_data.get("subreddit", "news"),
                    lambda_hat=state_data.get("lambda_hat", 0.15),
                )
                
                # Restore state
                post.temperature = state_data.get("temperature", 0.0)
                post.recent_rate = state_data.get("recent_rate", 0.0)
                post.volatility = state_data.get("volatility", 0.0)
                post.interval_hours = state_data.get("interval_hours", 1.0)
                
                if state_data.get("last_scrape_ts"):
                    post.last_scrape_ts = datetime.fromisoformat(state_data["last_scrape_ts"])
                if state_data.get("last_nonzero_ts"):
                    post.last_nonzero_ts = datetime.fromisoformat(state_data["last_nonzero_ts"])
                if state_data.get("next_due"):
                    post.next_due = datetime.fromisoformat(state_data["next_due"])
                post.zero_delta_streak = state_data.get("zero_delta_streak", 0)
                post.ready_for_retirement = state_data.get("ready_for_retirement", False)
                post.last_delta_info = state_data.get("last_delta_info", 0.0)
                post.scrape_count = state_data.get("delta_count", post.scrape_count)

                self.posts[post_id] = post
                
            except Exception as e:
                print(f"⚠️  Failed to load state for {post_id}: {e}")


if __name__ == '__main__':
    print("="*80)
    print("🚀 ADAPTIVE SCHEDULER - Demo")
    print("="*80)
    print()
    
    # Create scheduler
    scheduler = AdaptiveScheduler(target_rps=10.0)
    
    # Add some sample posts
    print("Adding posts...")
    scheduler.add_post("post1", "https://reddit.com/r/news/1", "news")
    scheduler.add_post("post2", "https://reddit.com/r/news/2", "news")
    scheduler.add_post("post3", "https://reddit.com/r/worldnews/3", "worldnews")
    print(f"  ✓ Added {len(scheduler.posts)} posts")
    print()
    
    # Simulate some scrapes
    now = datetime.now(timezone.utc)
    
    print("Simulating scrapes...")
    scheduler.record_scrape("post1", ScrapeDelta(ts=now - timedelta(hours=1), new_comments=50, score_changed=100))
    scheduler.record_scrape("post1", ScrapeDelta(ts=now - timedelta(hours=0.5), new_comments=30, score_changed=80))
    scheduler.record_scrape("post2", ScrapeDelta(ts=now - timedelta(hours=2), new_comments=10, score_changed=20))
    scheduler.record_scrape("post3", ScrapeDelta(ts=now - timedelta(hours=4), new_comments=5, score_changed=10))
    print(f"  ✓ Recorded {scheduler.total_scrapes} scrapes")
    print()
    
    # Run control tick
    print("Running control tick...")
    queue = scheduler.control_tick(now)
    print(f"  ✓ Built queue with {len(queue)} posts")
    print()
    
    # Display status
    print("="*80)
    print("SCHEDULER STATUS")
    print("="*80)
    print()
    
    status = scheduler.get_status()
    for key, val in status.items():
        if key == "controller":
            print(f"{key}:")
            for k, v in val.items():
                print(f"  ├─ {k}: {v}")
        else:
            print(f"{key}: {val}")
    
    print()
    
    # Show queue
    print("="*80)
    print("PRIORITY QUEUE")
    print("="*80)
    print()
    
    for i, entry in enumerate(sorted(queue)[:5], 1):
        post = scheduler.posts[entry.post_id]
        print(f"{i}. {entry.post_id}")
        print(f"   ├─ T={post.temperature:.3f}, λ={post.lambda_hat:.3f}")
        print(f"   ├─ Δt={post.interval_hours:.2f}h")
        print(f"   └─ Due: {entry.next_time.strftime('%H:%M:%S')}")
        print()
    
    print("="*80)

