#!/usr/bin/env python3
"""
Unified Adaptive Reddit Scraper
Complete production system integrating all components.
Based on reference_books/architecture.md - Full Implementation
"""

import time
import os
import re
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Set
from collections import deque

from reddit_scraper_api import scrape_reddit_post_api, get_request_count
from reddit_auth import get_authenticated_session
from adaptive_scheduler import AdaptiveScheduler, DORMANCY_ZERO_STREAK
from temperature_scheduler import ScrapeDelta
from info_gain_analytics import compute_delta_info, collect_nodes
try:
    from bootstrap_scheduler_from_merged import bootstrap_from_merged_data  # type: ignore
except ModuleNotFoundError:
    bootstrap_from_merged_data = None
from coverage_allocator import PriorityCoverageAllocator
from discovery_poller import DiscoveryPoller, DiscoveredPost
from depth_advisor import DepthAdvisor, SHALLOW, MEDIUM, DEEP
from telemetry import TelemetryCollector
from subreddit_priors import SubredditPriors
from rate_limiter import RateLimiter
from scrape_cost_estimator import CostPredictor


def extract_post_id(url: str) -> Optional[str]:
    """Extract Reddit post ID from URL"""
    match = re.search(r'/comments/([^/]+)/', url)
    return match.group(1) if match else None


def extract_subreddit(url: str) -> str:
    """Extract subreddit from URL"""
    match = re.search(r'/r/([^/]+)/', url)
    return match.group(1) if match else "news"


def compute_scrape_delta(post_id: str, current_data: dict, 
                        previous_data: Optional[dict] = None) -> ScrapeDelta:
    """
    Compute ΔInfo from a scrape by comparing with previous scrape.
    """
    now = datetime.now(timezone.utc)
    
    if previous_data is None:
        # First scrape - count all as new
        nodes = collect_nodes(current_data)
        comment_count = len([n for (kind, n) in nodes if kind == "comment"])
        
        return ScrapeDelta(
            ts=now,
            new_comments=comment_count,
            edited_comments=0,
            score_changed=0,
            deleted_comments=0
        )
    
    # Compute detailed ΔInfo
    prev_nodes = {n.get('id'): n for (_, n) in collect_nodes(previous_data) if n.get('id')}
    curr_nodes = {n.get('id'): n for (_, n) in collect_nodes(current_data) if n.get('id')}
    
    new_comments = len(set(curr_nodes.keys()) - set(prev_nodes.keys()))
    deleted_comments = len(set(prev_nodes.keys()) - set(curr_nodes.keys()))
    
    edited_comments = 0
    score_changed = 0
    
    for node_id in set(curr_nodes.keys()) & set(prev_nodes.keys()):
        curr = curr_nodes[node_id]
        prev = prev_nodes[node_id]
        
        if curr.get('score', 0) != prev.get('score', 0):
            score_changed += 1
        
        if curr.get('body', '') != prev.get('body', ''):
            edited_comments += 1
    
    return ScrapeDelta(
        ts=now,
        new_comments=new_comments,
        edited_comments=edited_comments,
        score_changed=score_changed,
        deleted_comments=deleted_comments
    )


class UnifiedScraper:
    """
    Complete adaptive scraping system.
    
    Integrates:
    - Multi-subreddit discovery with priority-based coverage
    - Continuous temperature scheduling
    - Adaptive depth selection
    - Rate-limit control with EMA feedback
    - Comprehensive telemetry and alerting
    """
    
    def __init__(self,
                 target_rps: float = 10.0,
                 priorities_file: str = 'subreddit_priorities.txt',
                 temporal_dir: str = 'temporal_test',
                 skip_bootstrap: bool = False):
        """
        Initialize unified scraper.
        
        Args:
            target_rps: Target API requests per second (default 10.0 = 600/min)
            priorities_file: Path to subreddit priorities file
            temporal_dir: Directory for storing scrape data
            skip_bootstrap: If True, skip loading historical data (faster startup)
        """
        self.target_rps = target_rps
        self.temporal_dir = temporal_dir
        self.skip_bootstrap = skip_bootstrap
        
        # Initialize components
        print("🚀 Initializing Unified Adaptive Scraper...")
        print()
        
        # 1. Coverage allocator
        print("📊 Loading subreddit priorities...")
        self.allocator = PriorityCoverageAllocator(budget_rps=target_rps)
        self.allocator.load_from_file(priorities_file)
        self.allocator.compute_coverage_fractions(global_gain=1.0)
        print()
        
        # 2. OAuth authentication
        print("🔐 Authenticating...")
        self.session = get_authenticated_session()
        if self.session:
            print("✅ OAuth authenticated")
        else:
            print("⚠️  Running without authentication")
        print()
        
        # 3. Scheduler
        print("🧠 Initializing scheduler...")
        self.scheduler = AdaptiveScheduler(
            target_rps=target_rps,
            lateness_setpoint=0.15,
            state_dir=temporal_dir
        )
        print()
        
        # 4. Discovery poller
        print("🔍 Initializing discovery poller...")
        self.poller = DiscoveryPoller(self.allocator, self.session)
        print()
        
        # 5. Depth advisor
        print("📏 Initializing depth advisor...")
        self.depth_advisor = DepthAdvisor()
        print()
        
        # 6. Telemetry
        print("📊 Initializing telemetry...")
        self.telemetry = TelemetryCollector()
        print()
        
        # 7. Cost predictor (FIX #16: Pre-scrape cost estimation)
        print("🔮 Initializing cost predictor...")
        self.cost_predictor = CostPredictor(history_size=500)
        print()
        
        # 8. Rate limiter (FIX #13: Reddit compliance - 540 req/10min for safety)
        print("⏱️  Initializing rate limiter...")
        self.rate_limiter = RateLimiter(max_requests=540, window_seconds=600)
        print()
        
        # 8. Subreddit priors (for new posts)
        self.priors = SubredditPriors()
        
        # Track previous scrape data
        self.previous_data: Dict[str, Optional[dict]] = {}
        
        # Track posts scraped in last 6h (for coverage metric)
        self.recent_scrapes: deque = deque(maxlen=500)
        
        # Track discovered posts not yet added
        self.pending_additions: Set[str] = set()
        
        # FIX 16C-16F: Budget recovery tracking
        self.zero_budget_streak = 0  # Track consecutive budget=0 hits
        self.last_budget = 540  # Track previous budget for drift calculation
        self.budget_drift = 0.0  # EMA of budget delta
        self.deferred_count = 0  # Count deferrals per batch
        self.attempted_count = 0  # Count attempts per batch
        self.avg_sleep_refill = 0.9  # Learned refill rate (req/sec)
        self.recovery_mode = False  # Flag for deferred-recovery mode
        
        print("✅ All components initialized")
        print()
    
    def run(self, duration_minutes: int = 60):
        """
        Main control loop.
        
        Args:
            duration_minutes: How long to run (default 60 minutes)
        """
        print("="*80)
        print("🌐 UNIFIED ADAPTIVE SCRAPER - STARTING")
        print("="*80)
        print(f"  ├─ Target: {self.target_rps} rps ({self.target_rps*60:.0f}/min)")
        print(f"  ├─ Duration: {duration_minutes} minutes")
        print(f"  ├─ Subreddits: {len(self.allocator.rank_order)}")
        print(f"  └─ Temporal dir: {self.temporal_dir}")
        print()
        
        # Bootstrap from existing data (unless skipped)
        if not self.skip_bootstrap:
            print("🔄 Bootstrapping from historical data...")
            if bootstrap_from_merged_data is not None:
                bootstrap_from_merged_data(self.scheduler, self.temporal_dir)
            else:
                print("⚠️  bootstrap_scheduler_from_merged.py unavailable; skipping bootstrap.")
            print()
        else:
            print("⏩ Skipping bootstrap (fresh start)")
            print()
        
        # Calculate end time
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        print(f"🚀 Starting at {datetime.now().strftime('%H:%M:%S')}")
        print(f"🏁 Will stop at {datetime.fromtimestamp(end_time).strftime('%H:%M:%S')}")
        print("="*80)
        print()
        
        # API request tracking
        prev_request_count = get_request_count()
        last_telemetry_time = time.time()
        telemetry_interval = 60  # Log every minute
        
        # Discovery tracking
        last_discovery_time = 0
        
        # TEST VALIDATION: Additional logging trackers
        last_telemetry_snapshot = time.time()
        last_coverage_log = time.time()
        last_controller_log = time.time()
        coverage_log_interval = 300  # 5 minutes
        controller_log_interval = 600  # 10 minutes
        
        # Main loop
        while time.time() < end_time:
            now = datetime.now(timezone.utc)
            loop_start = time.time()
            
            # === DISCOVERY PHASE ===
            # Check if any subreddits are due for polling
            if time.time() - last_discovery_time > 60:  # Check every minute
                new_posts = self.poller.poll_all_due(global_gain=self.scheduler.controller.g)
                
                # TEST VALIDATION: Log discovery history
                for discovered in new_posts:
                    discovery_entry = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "subreddit": discovered.subreddit,
                        "post_id": discovered.post_id,
                        "score": discovered.score,
                        "num_comments": discovered.num_comments,
                        "source": "scheduled_poll"
                    }
                    try:
                        with open(f'{self.temporal_dir}/discovery_history.jsonl', 'a') as f:
                            f.write(json.dumps(discovery_entry) + '\n')
                    except Exception:
                        pass  # Don't let logging errors stop scraping
                
                for discovered in new_posts:
                    # FIX #8: Pass post data for policy-based filtering
                    post_data = {
                        "num_comments": discovered.num_comments,
                        "score": discovered.score,
                        "created_utc": discovered.created_utc,
                        "author": discovered.author
                    }
                    
                    # Apply selection policy (probabilistic sampling or rules)
                    if self.allocator.should_scrape_post(discovered.subreddit, post_data):
                        # Add to scheduler
                        post = self.scheduler.add_post(
                            discovered.post_id,
                            discovered.url,
                            discovered.subreddit
                        )
                        
                        # Initialize with subreddit prior
                        post.lambda_hat = self.priors.get_lambda(discovered.subreddit)
                        
                        # FIX #16: Update metadata for cost estimation
                        self.scheduler.update_post_metadata(discovered.post_id, discovered.num_comments)
                        
                        self.pending_additions.add(discovered.post_id)
                
                last_discovery_time = time.time()
            
            # === SCHEDULING PHASE ===
            # Measure actual API request rate
            current_request_count = get_request_count()
            tick_duration = time.time() - loop_start
            
            if tick_duration > 0:
                requests_this_tick = current_request_count - prev_request_count
                instantaneous_rps = requests_this_tick / tick_duration
            else:
                instantaneous_rps = 0.0
            
            # FIX #6: Update coverage fractions with EMA and post rates
            # Get recent discovery rates
            posts_per_sub = self.poller.get_recent_discovery_rates(window_minutes=10)
            
            # Update coverage fractions with better inputs
            self.allocator.compute_coverage_fractions(
                global_gain=self.scheduler.controller.g,
                posts_per_subreddit=posts_per_sub,
                current_rps=instantaneous_rps,  # Still pass but not used in FIX #1
                ema_rps=self.scheduler.controller.rate_ema
            )
            
            # Run scheduler control tick
            queue = self.scheduler.control_tick(now, instantaneous_rps=instantaneous_rps)
            
            # FIX #11: Enhanced batch scaling with gain adaptation (10-100 range)
            gain = getattr(self.scheduler.controller, 'g', 1.0)
            batch_size = int(max(10, min(100, self.target_rps * gain * 2.0)))
            ready_count = len([e for e in queue if e.next_time <= now])
            batch_size = min(batch_size, max(1, ready_count))  # Don't request more than available
            ready_posts = self.scheduler.get_next_posts(limit=batch_size)
            
            # FIX #4: Opportunistic discovery when idle
            if not ready_posts and instantaneous_rps < self.target_rps:
                idle_duration = time.time() - last_discovery_time
                
                if idle_duration > 5.0:  # Only if idle for 5+ seconds
                    # Poll top K most-due subreddits
                    new_posts = self.poller.poll_top_k_due(K=5, global_gain=self.scheduler.controller.g)
                    
                    # TEST VALIDATION: Log opportunistic discovery
                    for discovered in new_posts:
                        discovery_entry = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "subreddit": discovered.subreddit,
                            "post_id": discovered.post_id,
                            "score": discovered.score,
                            "num_comments": discovered.num_comments,
                            "source": "opportunistic_idle"
                        }
                        try:
                            with open(f'{self.temporal_dir}/discovery_history.jsonl', 'a') as f:
                                f.write(json.dumps(discovery_entry) + '\n')
                        except Exception:
                            pass
                    
                    for discovered in new_posts:
                        # Pass post data for policy-based filtering
                        post_data = {
                            "num_comments": discovered.num_comments,
                            "score": discovered.score,
                            "created_utc": discovered.created_utc,
                            "author": discovered.author
                        }
                        
                        # Apply coverage filter
                        if self.allocator.should_scrape_post(discovered.subreddit, post_data):
                            # Add to scheduler
                            post = self.scheduler.add_post(
                                discovered.post_id,
                                discovered.url,
                                discovered.subreddit
                            )
                            post.lambda_hat = self.priors.get_lambda(discovered.subreddit)
                            # FIX #16: Update metadata for cost estimation
                            self.scheduler.update_post_metadata(discovered.post_id, discovered.num_comments)
                            self.pending_additions.add(discovered.post_id)
                    
                    # Record idle discovery for telemetry
                    self.telemetry.idle_discoveries.append(time.time())
                    
                    last_discovery_time = time.time()
                    
                    # Recompute queue after adding posts
                    queue = self.scheduler.control_tick(now, instantaneous_rps=instantaneous_rps)
                    ready_posts = self.scheduler.get_next_posts(limit=batch_size)
            
            if not ready_posts:
                # HEARTBEAT FAILSAFE: Force at least one scrape
                if self.scheduler.posts:
                    # Pick least recently scraped post
                    oldest = min(self.scheduler.posts.values(), 
                                key=lambda p: p.last_scrape_ts or datetime.min.replace(tzinfo=timezone.utc))
                    ready_posts = [oldest.post_id]
                    print(f"💓 Heartbeat scrape: forcing {oldest.post_id}")
                else:
                    # No posts at all, wait briefly
                    time.sleep(0.5)
                    prev_request_count = current_request_count
                    continue
            
            # === BURST EXECUTION: Process multiple posts per loop (FIX #8) ===
            batch_start_time = time.time()
            posts_scraped_this_loop = 0
            deferrals_this_batch = 0  # FIX 16B: Track deferrals per batch
            
            # FIX 16D: Budget floor protection with streak-based deep sleep
            available_budget = self.rate_limiter.available_budget()
            conserve_budget = available_budget < max(50, int(self.rate_limiter.max_requests * 0.2))
            self.scheduler.set_budget_conservation(conserve_budget)
            
            # Track budget drift (Fix 16: Budget drift tracker)
            budget_delta = available_budget - self.last_budget
            self.budget_drift = 0.9 * self.budget_drift + 0.1 * budget_delta  # EMA
            self.last_budget = available_budget
            
            # Detect sustained negative drift
            if self.budget_drift < -5 and available_budget < 100:
                print(f"⚠️  Sustained negative drift detected ({self.budget_drift:.1f}/loop), budget={available_budget}")
                print(f"   Slowing scrape tempo by 25% to prevent collapse...")
                self.target_rps *= 0.75
            
            # Critical: Budget completely depleted
            if available_budget == 0:
                self.zero_budget_streak += 1
                if self.zero_budget_streak >= 3:
                    print("💤 Hard budget starvation detected (3+ consecutive zeros)")
                    print("   Full 3-min recovery sleep...")
                    sleep_start = time.time()
                    time.sleep(180)
                    sleep_duration = time.time() - sleep_start
                    
                    # Learn refill rate
                    budget_after = self.rate_limiter.available_budget()
                    refill_gained = budget_after - available_budget
                    measured_refill_rate = refill_gained / max(1, sleep_duration)
                    self.avg_sleep_refill = 0.8 * self.avg_sleep_refill + 0.2 * measured_refill_rate
                    
                    print(f"   Refilled {refill_gained} requests in {sleep_duration:.0f}s (rate={measured_refill_rate:.2f}/s)")
                    self.zero_budget_streak = 0
                else:
                    print(f"🛑 Budget depleted (streak={self.zero_budget_streak}), sleeping 60s...")
                    sleep_start = time.time()
                    time.sleep(60)
                    sleep_duration = time.time() - sleep_start
                    
                    # Learn refill rate
                    budget_after = self.rate_limiter.available_budget()
                    refill_gained = budget_after - available_budget
                    measured_refill_rate = refill_gained / max(1, sleep_duration)
                    self.avg_sleep_refill = 0.8 * self.avg_sleep_refill + 0.2 * measured_refill_rate
                    
                    print(f"   Refilled {refill_gained} requests in {sleep_duration:.0f}s (rate={measured_refill_rate:.2f}/s)")
                continue
            else:
                self.zero_budget_streak = 0
            
            # Warning: Budget very low
            if available_budget < 30:
                print(f"⚠️  Budget very low ({available_budget}), sleeping 30s to refill...")
                sleep_start = time.time()
                time.sleep(30)
                sleep_duration = time.time() - sleep_start
                
                # Learn refill rate
                budget_after = self.rate_limiter.available_budget()
                refill_gained = budget_after - available_budget
                measured_refill_rate = refill_gained / max(1, sleep_duration)
                self.avg_sleep_refill = 0.8 * self.avg_sleep_refill + 0.2 * measured_refill_rate
                
                print(f"   Refilled {refill_gained} requests in {sleep_duration:.0f}s (rate={measured_refill_rate:.2f}/s)")
            
            # Reset deferral tracking for this batch
            self.deferred_count = 0
            self.attempted_count = 0
            
            for post_id in ready_posts:
                # Safety: limit burst duration to ~1 second
                if time.time() - batch_start_time > 1.0 and posts_scraped_this_loop > 0:
                    break
                
                if post_id not in self.scheduler.posts:
                    continue  # Post might have been removed
                
                post = self.scheduler.posts[post_id]
                
                # === SCRAPING PHASE ===
            # FIX #16: Pre-scrape cost estimation and budget validation
            
            # 1. Get post metadata
                post_metadata = self.scheduler.get_post_metadata(post_id)
                num_comments = post_metadata.get('num_comments', 0)
                
                # 2. Get depth mode (Refinement #6: fallback to medium)
                depth_mode = self.depth_advisor.get_depth_mode(post_id)
                if depth_mode is None:
                    depth_mode = MEDIUM
                
                # 3. Estimate cost BEFORE scraping
                estimated_cost = self.cost_predictor.predict(num_comments, depth_mode.name.lower())
                
            # 4. Check budget availability
            available_budget = self.rate_limiter.available_budget()
            
            # 5. Soft guard: if almost empty, pause briefly before retrying.
            buffer_tokens = max(5, int(self.rate_limiter.max_requests * 0.02))
            if available_budget < buffer_tokens:
                deficit = buffer_tokens - available_budget
                wait_seconds = max(1.0, self.rate_limiter.wait_time())
                print(f"⏸️  Tokens nearly exhausted ({available_budget} remaining, need {buffer_tokens}). Waiting {wait_seconds:.1f}s to refill...")
                time.sleep(wait_seconds)
                continue
            
            # Track attempts for recovery mode
            self.attempted_count += 1
            
            # Display status
            elapsed_mins = (time.time() - start_time) / 60
            remaining_mins = (end_time - time.time()) / 60
            
            print(f"[{elapsed_mins:.0f}:{remaining_mins:.0f}] "
                  f"🎯 {post_id} r/{post.subreddit} "
                  f"(T={post.temperature:.2f}, depth={depth_mode.name})...")
            
            # Prepare output
            post_dir = f'{self.temporal_dir}/{post_id}/raw_scrapes'
            os.makedirs(post_dir, exist_ok=True)
            
            existing_scrapes = [f for f in os.listdir(post_dir) 
                              if f.startswith('scrape_') and f.endswith('.json')]
            scrape_num = len(existing_scrapes) + 1
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f'{post_dir}/scrape_{scrape_num:03d}_{timestamp}.json'
            
            # Scrape with appropriate session
            try:
                # Track budget before scrape
                budget_before = available_budget
                
                result = scrape_reddit_post_api(
                    post.url, 
                    output_file,
                    session=self.session
                )
                
                if result and 'error' not in result:
                    # Get API request count for this scrape
                    new_request_count = get_request_count()
                    actual_cost = new_request_count - current_request_count
                    
                    # FIX #16: Consume actual API requests from rate limiter
                    if not self.rate_limiter.consume(actual_cost):
                        deficit = max(0, actual_cost - self.rate_limiter.available_budget())
                        wait_seconds = max(1.0, self.rate_limiter.wait_time())
                        print(f"⏸️  Rate limiter empty mid-batch (cost={actual_cost}, deficit≈{deficit}). Waiting {wait_seconds:.1f}s...")
                        time.sleep(wait_seconds)
                        # After refill attempt, ensure tokens are available before continuing
                        if not self.rate_limiter.consume(actual_cost):
                            # RETRY LOGIC: Poll for refill (Smart Wait)
                            # Instead of sleeping 10m blindly, check every 60s
                            max_wait_minutes = 10
                            success = False
                            
                            for m in range(max_wait_minutes):
                                print(f"⏳ Rate limit exhausted. Waiting 60s to refill ({m+1}/{max_wait_minutes}m)...")
                                time.sleep(60)
                                
                                if self.rate_limiter.consume(actual_cost):
                                    print(f"✅ Refilled successfully after {m+1} minutes.")
                                    success = True
                                    break
                            
                            if not success:
                                print("⚠️  Unable to consume tokens after 10m wait; skipping remaining posts in batch.")
                                break
                    
                    budget_after = self.rate_limiter.available_budget()
                    
                    # FIX #16: Record cost for learning
                    self.cost_predictor.record(num_comments, depth_mode.name.lower(), actual_cost)
                    self.cost_predictor.record_prediction_error(estimated_cost, actual_cost)
                    
                    # Compute delta
                    delta = compute_scrape_delta(post_id, result, self.previous_data.get(post_id))
                    delta_info = delta.weighted()
                    
                    # Record in scheduler
                    self.scheduler.record_scrape(post_id, delta)
                    
                    post_state = self.scheduler.posts.get(post_id)
                    if (
                        post_state
                        and post_state.ready_for_retirement
                        and post_state.zero_delta_streak >= max(DORMANCY_ZERO_STREAK, 1)
                    ):
                        print(
                            f"ℹ️ Marked dormant: {post_id} "
                            f"(scrapes={post_state.scrape_count}, zero-Δ streak={post_state.zero_delta_streak})"
                        )
                    
                    # Record in depth advisor (use actual_cost)
                    self.depth_advisor.record_scrape(post_id, delta_info, actual_cost)
                    
                    # FIX #16: Log cost prediction for calibration
                    self.telemetry.log_cost_prediction(
                        post_id=post_id,
                        estimated=estimated_cost,
                        actual=actual_cost,
                        budget_before=budget_before,
                        budget_after=budget_after,
                        p90=50,  # Will be dynamic in P1
                        used_reserve=False,  # Will be dynamic in P2
                        temporal_dir=self.temporal_dir
                    )
                    
                    # Update previous data
                    self.previous_data[post_id] = result
                    
                    # Track for coverage metric
                    self.recent_scrapes.append((now, post_id))
                    
                    # Display result
                    meta = result.get('metadata', {})
                    comment_count = meta.get('total_comments', 0)
                    coverage = meta.get('coverage_percent', 0)
                    efficiency = delta_info / actual_cost if actual_cost > 0 else 0
                    
                    print(f"  ✅ {comment_count} comments ({coverage:.1f}%), "
                          f"ΔInfo={delta_info:.1f}, eff={efficiency:.3f}, "
                          f"reqs={actual_cost} (est={estimated_cost})")
                    
                    # TEST VALIDATION: Log request trace
                    request_entry = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "post_id": post_id,
                        "subreddit": post.subreddit,
                        "depth": depth_mode.name,
                        "requests_used": actual_cost,
                        "estimated_cost": estimated_cost,
                        "delta_info": delta_info,
                        "comments": comment_count,
                        "coverage_pct": coverage,
                        "efficiency": efficiency
                    }
                    try:
                        with open(f'{self.temporal_dir}/request_trace.jsonl', 'a') as f:
                            f.write(json.dumps(request_entry) + '\n')
                    except Exception:
                        pass
                    
                    # Update request counter for next iteration
                    prev_request_count = new_request_count
                    
                    # Count successful scrape
                    posts_scraped_this_loop += 1
                else:
                    print(f"  ❌ Scrape failed")
                    prev_request_count = get_request_count()
            
            except KeyboardInterrupt:
                print("\n⚠️  Interrupted by user")
                break
            except Exception as e:
                print(f"  ❌ Error: {e}")
                prev_request_count = get_request_count()
            
            # FIX 16: Deferred-recovery mode + Predictive cooldown
            if posts_scraped_this_loop == 0 and deferrals_this_batch > 0:
                # Calculate deferral ratio
                deferral_ratio = self.deferred_count / max(1, self.attempted_count)
                
                # Enter recovery mode if >50% deferred
                if deferral_ratio > 0.5 and not self.recovery_mode:
                    self.recovery_mode = True
                    gain = getattr(self.scheduler.controller, 'g', 1.0)
                    gain *= 0.8
                    self.target_rps = max(1.0, self.target_rps * 0.5)
                    print(f"🪫 Recovery mode ACTIVATED: {deferral_ratio:.0%} deferred, gain={gain:.2f}, RPS={self.target_rps:.1f}")
                
                # Exit recovery mode if <30% deferred
                elif deferral_ratio < 0.3 and self.recovery_mode:
                    self.recovery_mode = False
                    self.target_rps = min(10.0, self.target_rps * 2.0)  # Restore RPS
                    print(f"✅ Recovery mode EXITED: {deferral_ratio:.0%} deferred, RPS={self.target_rps:.1f}")
                
                # Predictive cooldown based on budget deficit
                available_budget = self.rate_limiter.available_budget()
                safe_threshold = 50
                needed_refill = max(0, safe_threshold - available_budget)
                
                # Calculate sleep time using learned refill rate
                predicted_sleep = needed_refill / max(0.8, self.avg_sleep_refill)
                cooldown = max(15, min(120, predicted_sleep))  # 15s-120s range
                
                print(f"⏳ All {deferrals_this_batch} posts deferred")
                print(f"   Budget: {available_budget}/{safe_threshold}, cooling down {cooldown:.0f}s (refill rate={self.avg_sleep_refill:.2f}/s)")
                
                sleep_start = time.time()
                time.sleep(cooldown)
                sleep_duration = time.time() - sleep_start
                
                # Learn refill rate from this cooldown
                budget_after = self.rate_limiter.available_budget()
                refill_gained = budget_after - available_budget
                measured_refill_rate = refill_gained / max(1, sleep_duration)
                self.avg_sleep_refill = 0.8 * self.avg_sleep_refill + 0.2 * measured_refill_rate
                
                print(f"   Refilled {refill_gained} requests in {sleep_duration:.0f}s (learned rate={self.avg_sleep_refill:.2f}/s)")
            
            # Log loop telemetry (FIX #8 + FIX #14)
            loop_duration = time.time() - batch_start_time
            instant_rps_loop = None
            if posts_scraped_this_loop > 0:
                instant_rps_loop = posts_scraped_this_loop / loop_duration
                tokens = self.rate_limiter.available_budget()
                print(f"  📦 Batch: {posts_scraped_this_loop}/{len(ready_posts)} posts in {loop_duration:.1f}s")
                print(f"  ⚡ Instant RPS: {instant_rps_loop:.2f}, tokens available: {tokens}")
            
            # === TELEMETRY PHASE ===
            if time.time() - last_telemetry_time >= telemetry_interval:
                # Compute coverage for top subreddits
                top_subs = self.allocator.rank_order[:10] if len(self.allocator.rank_order) >= 10 else self.allocator.rank_order
                
                # Count recent scrapes from last 6h
                six_hours_ago = now - timedelta(hours=6)
                posts_6h = set(pid for (ts, pid) in self.recent_scrapes if ts > six_hours_ago)
                
                # Compute waste rate from scheduler
                recent_deltas = []
                for post in self.scheduler.posts.values():
                    if post.deltas:
                        recent_deltas.extend([d.weighted() for d in post.deltas[-10:]])
                
                waste_rate = sum(1 for d in recent_deltas if d == 0) / len(recent_deltas) if recent_deltas else 0.0
                
                # Collect snapshot
                snapshot = self.telemetry.collect_snapshot(
                    instantaneous_rps=instantaneous_rps,
                    rate_ema=self.scheduler.controller.rate_ema,
                    global_gain=self.scheduler.controller.g,
                    avg_lateness=0.0,  # TODO: compute from scheduler
                    total_scrapes=self.scheduler.total_scrapes,
                    total_delta_info=self.scheduler.total_delta_info,
                    active_posts=len(self.scheduler.posts),
                    posts_scraped_6h=len(posts_6h),
                    waste_rate=waste_rate,
                    coverage_top_subs=1.0,  # TODO: compute actual
                    scheduler=self.scheduler,  # FIX #6: Pass scheduler for interval metrics
                    # FIX #14: Enhanced throughput telemetry
                    instant_rps=instant_rps_loop,
                    batch_size=batch_size,
                    loop_duration=loop_duration if posts_scraped_this_loop > 0 else None,
                    available_tokens=self.rate_limiter.available_budget(),
                    ready_queue_size=ready_count
                )
                
                # Log and print
                self.telemetry.log_snapshot(snapshot)
                self.telemetry.print_snapshot(snapshot, verbose=False)
                
                # Print alerts if any
                if snapshot.alerts:
                    for alert in snapshot.alerts:
                        print(f"  {alert}")
                
                # FIX #6: Diagnostic logging for interval health
                queue_len = len(self.scheduler.posts)
                ready_count = len(self.scheduler.get_next_posts(limit=999))
                print(f"[DIAG] queue={queue_len}, ready={ready_count}, "
                      f"median_interval={snapshot.interval_median_s:.0f}s, "
                      f"p90={snapshot.interval_p90_s:.0f}s, "
                      f"max={snapshot.interval_max_s:.0f}s, "
                      f"soonest_in={snapshot.soonest_next_scrape_delta_s:.0f}s")
                
                last_telemetry_time = time.time()
            
            # TEST VALIDATION: Telemetry snapshots (every 60s)
            if time.time() - last_telemetry_snapshot >= telemetry_interval:
                snapshot_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "rate_ema": self.scheduler.controller.rate_ema,
                    "gain": self.scheduler.controller.g,
                    "idle_discovery_rate": self.telemetry._compute_idle_discovery_rate(),
                    "coverage_skew_avg": self.telemetry._compute_avg_coverage_skew(),
                    "top_10_share": self.telemetry._compute_top_k_share(10, self.allocator),
                    "deep_work_share": self.telemetry._compute_depth_share("deep"),
                    "rps_instant": instantaneous_rps,
                    "utilization": (self.scheduler.controller.rate_ema / self.target_rps) * 100 if self.target_rps > 0 else 0,
                    "waste_rate": waste_rate
                }
                try:
                    with open(f'{self.temporal_dir}/telemetry_snapshots.jsonl', 'a') as f:
                        f.write(json.dumps(snapshot_entry) + '\n')
                except Exception:
                    pass
                last_telemetry_snapshot = time.time()
            
            # TEST VALIDATION: Controller state logging (every 10 min)
            if time.time() - last_controller_log >= controller_log_interval:
                controller_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "gain": self.scheduler.controller.g,
                    "rate_ema": self.scheduler.controller.rate_ema,
                    "target_rps": self.target_rps,
                    "instantaneous_rps": instantaneous_rps,
                    "active_posts": len(self.scheduler.posts),
                    "queue_size": len(queue) if 'queue' in locals() else 0
                }
                try:
                    with open(f'{self.temporal_dir}/controller_state.jsonl', 'a') as f:
                        f.write(json.dumps(controller_entry) + '\n')
                except Exception:
                    pass
                last_controller_log = time.time()
            
            # === MAINTENANCE PHASE ===
            # Retire dormant posts periodically
            if self.scheduler.total_scrapes % 20 == 0:
                self.scheduler.retire_dormant_posts()
            
            # Save state periodically
            if self.scheduler.total_scrapes % 10 == 0:
                self.scheduler._save_state()
        
        # === FINAL SUMMARY ===
        self._print_final_summary(start_time)
    
    def _print_final_summary(self, start_time: float):
        """Print final summary statistics."""
        elapsed_total = (time.time() - start_time) / 60
        
        print()
        print("="*80)
        print("📊 FINAL SUMMARY")
        print("="*80)
        print()
        
        # Scheduler metrics
        status = self.scheduler.get_status()
        print(f"Scraping:")
        print(f"  ├─ Duration: {elapsed_total:.1f} minutes")
        print(f"  ├─ Total scrapes: {status['total_scrapes']}")
        print(f"  ├─ Total ΔInfo: {status['total_delta_info']:.1f}")
        print(f"  ├─ Avg ΔInfo/scrape: {status['avg_delta_info_per_scrape']:.2f}")
        print(f"  └─ Throughput: {status['total_scrapes']/elapsed_total:.2f} scrapes/min")
        print()
        
        # Controller metrics
        ctrl = status['controller']
        print(f"Rate Controller:")
        print(f"  ├─ Global Gain: {ctrl['global_gain']:.3f}")
        print(f"  ├─ Rate EMA: {ctrl['rate_ema']:.2f} rps")
        print(f"  └─ Utilization: {ctrl['utilization_pct']:.1f}%")
        print()
        
        # Discovery metrics
        disc_status = self.poller.get_status()
        print(f"Discovery:")
        print(f"  ├─ Total polls: {disc_status['total_polls']}")
        print(f"  ├─ Posts discovered: {disc_status['total_discovered']}")
        print(f"  └─ Avg per poll: {disc_status['avg_posts_per_poll']:.1f}")
        print()
        
        # Depth advisor metrics
        depth_status = self.depth_advisor.get_status()
        print(f"Depth Distribution:")
        print(f"  ├─ Shallow: {depth_status['shallow']}")
        print(f"  ├─ Medium: {depth_status['medium']}")
        print(f"  ├─ Deep: {depth_status['deep']}")
        print(f"  └─ Avg efficiency: {depth_status['avg_efficiency']:.3f} ΔInfo/req")
        print()
        
        # Telemetry metrics
        print(f"Telemetry:")
        print(f"  ├─ Snapshots: {len(self.telemetry.snapshots)}")
        print(f"  └─ Active alerts: {len(self.telemetry.active_alerts)}")
        print()
        
        # Save final state
        self.scheduler._save_state()
        print("💾 State saved")
        print()
        
        print("="*80)
        print("✅ UNIFIED SCRAPER COMPLETE")
        print("="*80)


if __name__ == '__main__':
    import sys
    
    # Parse arguments
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    target_rps = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    skip_bootstrap = '--no-bootstrap' in sys.argv
    
    # Check for custom temporal directory
    temporal_dir = 'temporal_test'
    for arg in sys.argv:
        if arg.startswith('--dir='):
            temporal_dir = arg.split('=')[1]
    
    # Create and run unified scraper
    scraper = UnifiedScraper(
        target_rps=target_rps, 
        skip_bootstrap=skip_bootstrap,
        temporal_dir=temporal_dir
    )
    scraper.run(duration_minutes=duration)

