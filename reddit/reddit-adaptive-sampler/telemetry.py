#!/usr/bin/env python3
"""
Telemetry & Observability
Comprehensive metrics collection and alerting for the adaptive scraper.
Based on reference_books/architecture.md §2.12 and §9
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from collections import deque


@dataclass
class TelemetrySnapshot:
    """Single point-in-time telemetry snapshot."""
    timestamp: str
    
    # Global metrics
    instantaneous_rps: float
    rate_ema: float
    global_gain: float
    avg_lateness: float
    
    # Throughput metrics
    total_scrapes: int
    total_delta_info: float
    avg_delta_info_per_scrape: float
    
    # Coverage metrics
    active_posts: int
    posts_scraped_last_6h: int
    coverage_pct_top_subs: float
    
    # Efficiency metrics
    waste_rate: float  # Fraction of zero-ΔInfo scrapes
    api_utilization_pct: float
    
    # Alerts
    alerts: List[str]
    
    # Interval metrics (FIX #6)
    interval_median_s: float = 0.0
    interval_p90_s: float = 0.0
    interval_max_s: float = 0.0
    soonest_next_scrape_delta_s: float = 0.0
    
    # Throughput metrics (FIX #14)
    instant_rps: Optional[float] = None
    batch_size: Optional[int] = None
    loop_duration: Optional[float] = None
    available_tokens: Optional[int] = None
    ready_queue_size: Optional[int] = None


class TelemetryCollector:
    """
    Collects and logs telemetry data with alerting.
    
    Tracks:
    - Global: RPS, gain, lateness, utilization
    - Per-post: ΔInfo, T, Δt, φ, λ
    - Per-subreddit: Coverage realized vs target
    
    Emits alerts when:
    - waste_rate > 0.7
    - coverage < 0.5 for top-ranked subs
    - g pinned at bounds for >5 minutes
    """
    
    def __init__(self, 
                 alert_waste_threshold: float = 0.7,
                 alert_coverage_threshold: float = 0.5,
                 alert_gain_pin_minutes: int = 5,
                 history_size: int = 1000):
        """
        Initialize telemetry collector.
        
        Args:
            alert_waste_threshold: Alert if waste rate exceeds this (default 0.7)
            alert_coverage_threshold: Alert if coverage below this for top subs (default 0.5)
            alert_gain_pin_minutes: Alert if gain pinned at bound for this long (default 5 min)
            history_size: Number of snapshots to retain (default 1000)
        """
        self.alert_waste_threshold = alert_waste_threshold
        self.alert_coverage_threshold = alert_coverage_threshold
        self.alert_gain_pin_minutes = alert_gain_pin_minutes
        self.history_size = history_size
        
        # Telemetry history
        self.snapshots: deque = deque(maxlen=history_size)
        
        # Alert tracking
        self.active_alerts: Dict[str, datetime] = {}  # alert_key → first_occurrence
        self.alert_cooldown: Dict[str, datetime] = {}  # alert_key → last_triggered
        
        # Gain pinning detection
        self.gain_history: deque = deque(maxlen=100)
        
        # FIX #7: Enhanced observability tracking
        self.request_history: deque = deque(maxlen=1000)  # (timestamp, subreddit, depth, requests)
        self.idle_discoveries: deque = deque(maxlen=100)  # timestamps of idle-triggered discoveries
        self.coverage_history: deque = deque(maxlen=200)  # (timestamp, subreddit, F_target, F_realized)
    
    def collect_snapshot(self,
                        instantaneous_rps: float,
                        rate_ema: float,
                        global_gain: float,
                        avg_lateness: float,
                        total_scrapes: int,
                        total_delta_info: float,
                        active_posts: int,
                        posts_scraped_6h: int,
                        waste_rate: float,
                        coverage_top_subs: float = 1.0,
                        scheduler=None,
                        instant_rps: Optional[float] = None,
                        batch_size: Optional[int] = None,
                        loop_duration: Optional[float] = None,
                        available_tokens: Optional[int] = None,
                        ready_queue_size: Optional[int] = None) -> TelemetrySnapshot:
        """
        Collect current metrics into a snapshot.
        
        Returns:
            TelemetrySnapshot with all current metrics
        """
        now = datetime.now(timezone.utc)
        
        # Compute derived metrics
        avg_delta_info = total_delta_info / total_scrapes if total_scrapes > 0 else 0.0
        api_util = (rate_ema / 10.0) * 100 if rate_ema > 0 else 0.0  # Assume 10 rps target
        
        # Check for alerts
        alerts = self._check_alerts(
            waste_rate, 
            coverage_top_subs, 
            global_gain, 
            now
        )
        
        # FIX #6: Compute interval metrics if scheduler provided
        interval_median_s = 0.0
        interval_p90_s = 0.0
        interval_max_s = 0.0
        soonest_delta_s = 0.0
        
        if scheduler is not None:
            interval_median_s = self._compute_interval_median(scheduler)
            interval_p90_s = self._compute_interval_p90(scheduler)
            interval_max_s = self._compute_interval_max(scheduler)
            soonest_delta_s = self._compute_soonest_delta(scheduler)
        
        snapshot = TelemetrySnapshot(
            timestamp=now.isoformat(),
            instantaneous_rps=instantaneous_rps,
            rate_ema=rate_ema,
            global_gain=global_gain,
            avg_lateness=avg_lateness,
            total_scrapes=total_scrapes,
            total_delta_info=total_delta_info,
            avg_delta_info_per_scrape=avg_delta_info,
            active_posts=active_posts,
            posts_scraped_last_6h=posts_scraped_6h,
            coverage_pct_top_subs=coverage_top_subs * 100,
            waste_rate=waste_rate,
            api_utilization_pct=api_util,
            interval_median_s=interval_median_s,
            interval_p90_s=interval_p90_s,
            interval_max_s=interval_max_s,
            soonest_next_scrape_delta_s=soonest_delta_s,
            alerts=alerts,
            # FIX #14: Enhanced throughput metrics
            instant_rps=instant_rps,
            batch_size=batch_size,
            loop_duration=loop_duration,
            available_tokens=available_tokens,
            ready_queue_size=ready_queue_size
        )
        
        self.snapshots.append(snapshot)
        self.gain_history.append((now, global_gain))
        
        return snapshot
    
    def _check_alerts(self, 
                     waste_rate: float,
                     coverage_top: float,
                     gain: float,
                     now: datetime) -> List[str]:
        """
        Check for alert conditions.
        
        Returns:
            List of active alert messages
        """
        alerts = []
        cooldown_minutes = 15  # Don't repeat same alert within 15 min
        
        # Alert 1: High waste rate
        if waste_rate > self.alert_waste_threshold:
            alert_key = "high_waste"
            if self._should_alert(alert_key, now, cooldown_minutes):
                alerts.append(f"⚠️  HIGH WASTE: {waste_rate*100:.0f}% of scrapes returning zero ΔInfo")
                self._trigger_alert(alert_key, now)
        else:
            self._clear_alert("high_waste")
        
        # Alert 2: Low coverage for top subreddits
        if coverage_top < self.alert_coverage_threshold:
            alert_key = "low_coverage"
            if self._should_alert(alert_key, now, cooldown_minutes):
                alerts.append(f"⚠️  LOW COVERAGE: Only {coverage_top*100:.0f}% of top-ranked subreddit posts covered")
                self._trigger_alert(alert_key, now)
        else:
            self._clear_alert("low_coverage")
        
        # Alert 3: Gain pinned at bounds
        if len(self.gain_history) >= 10:
            recent_gains = [g for _, g in list(self.gain_history)[-10:]]
            
            # Check if pinned at max
            if all(abs(g - 3.0) < 0.01 for g in recent_gains):
                alert_key = "gain_pinned_max"
                first_pin_time = self.active_alerts.get(alert_key, now)
                minutes_pinned = (now - first_pin_time).total_seconds() / 60
                
                if minutes_pinned > self.alert_gain_pin_minutes:
                    if self._should_alert(alert_key, now, cooldown_minutes):
                        alerts.append(f"⚠️  GAIN PINNED MAX: g=3.0 for {minutes_pinned:.0f} min (insufficient bandwidth)")
                        self._trigger_alert(alert_key, now)
                elif alert_key not in self.active_alerts:
                    self.active_alerts[alert_key] = now
            else:
                self._clear_alert("gain_pinned_max")
            
            # Check if pinned at min
            if all(abs(g - 0.5) < 0.01 for g in recent_gains):
                alert_key = "gain_pinned_min"
                first_pin_time = self.active_alerts.get(alert_key, now)
                minutes_pinned = (now - first_pin_time).total_seconds() / 60
                
                if minutes_pinned > self.alert_gain_pin_minutes:
                    if self._should_alert(alert_key, now, cooldown_minutes):
                        alerts.append(f"⚠️  GAIN PINNED MIN: g=0.5 for {minutes_pinned:.0f} min (excess bandwidth)")
                        self._trigger_alert(alert_key, now)
                elif alert_key not in self.active_alerts:
                    self.active_alerts[alert_key] = now
            else:
                self._clear_alert("gain_pinned_min")
        
        # FIX #7: NEW ALERTS from PATCH_NOTES
        # Alert 4: Top-heavy allocation
        # (This would need allocator parameter - skipping for now, can add to collect_snapshot)
        
        # Alert 5: Deep bias
        # (This would need depth stats - skipping for now, can add to collect_snapshot)
        
        # Alert 6: Idle underutilization  
        # (This would need idle discovery rate - skipping for now, can add to collect_snapshot)
        
        # Alert 7: Coverage drift
        # (This would need coverage history - skipping for now, can add to collect_snapshot)
        
        return alerts
    
    def _should_alert(self, alert_key: str, now: datetime, cooldown_minutes: int) -> bool:
        """Check if alert should be triggered (respecting cooldown)."""
        last_trigger = self.alert_cooldown.get(alert_key)
        
        if last_trigger is None:
            return True
        
        minutes_since = (now - last_trigger).total_seconds() / 60
        return minutes_since >= cooldown_minutes
    
    def _trigger_alert(self, alert_key: str, now: datetime):
        """Record alert trigger time."""
        self.alert_cooldown[alert_key] = now
        if alert_key not in self.active_alerts:
            self.active_alerts[alert_key] = now
    
    def _clear_alert(self, alert_key: str):
        """Clear an active alert."""
        self.active_alerts.pop(alert_key, None)
    
    def _compute_top_k_share(self, k: int, allocator) -> float:
        """
        FIX #7: Compute % of requests to top K ranked subreddits.
        
        Args:
            k: Number of top subreddits to consider
            allocator: PriorityCoverageAllocator instance
        
        Returns:
            Fraction of recent requests to top K subs
        """
        if not self.request_history or not hasattr(allocator, 'rank_order'):
            return 0.0
        
        # Get top K subreddits by rank
        top_k_subs = set(allocator.rank_order[:k])
        
        # Count requests to top K in recent window (10 min)
        recent = [r for r in self.request_history if r["timestamp"] > time.time() - 600]
        if not recent:
            return 0.0
        
        top_k_count = sum(1 for r in recent if r.get("subreddit") in top_k_subs)
        
        return top_k_count / len(recent)
    
    def _compute_depth_share(self, depth: str) -> float:
        """
        FIX #7: Compute % of requests using specified depth.
        
        Args:
            depth: Depth to check ("shallow", "medium", "deep")
        
        Returns:
            Fraction of recent requests using this depth
        """
        if not self.request_history:
            return 0.0
        
        recent = [r for r in self.request_history if r["timestamp"] > time.time() - 600]
        if not recent:
            return 0.0
        
        depth_count = sum(1 for r in recent if r.get("depth") == depth)
        
        return depth_count / len(recent)
    
    def _compute_idle_discovery_rate(self) -> float:
        """
        FIX #7: Compute idle-triggered discovery bursts per minute.
        
        Returns:
            Discovery bursts per minute (last 5 min)
        """
        if not self.idle_discoveries:
            return 0.0
        
        # Count idle discoveries in last 5 minutes
        recent = [d for d in self.idle_discoveries if d > time.time() - 300]
        return len(recent) / 5.0  # Per minute
    
    def _compute_avg_coverage_skew(self) -> float:
        """
        FIX #7: Compute average absolute deviation between target and realized coverage.
        
        Returns:
            Average |F_target - F_realized| across recent coverage measurements
        """
        if not self.coverage_history:
            return 0.0
        
        # Get recent coverage measurements (10 min)
        recent = [c for c in self.coverage_history if c["timestamp"] > time.time() - 600]
        
        if not recent:
            return 0.0
        
        skews = [abs(c["F_target"] - c["F_realized"]) for c in recent]
        return sum(skews) / len(skews)
    
    def log_coverage_metrics(self,
                            subreddit: str,
                            F_target: float,
                            discovered: int,
                            sampled: int,
                            requests_used: int):
        """
        FIX #7: Log coverage metrics per subreddit.
        
        Tracks:
        - Target coverage fraction F_target
        - Realized coverage F_realized = sampled / discovered
        - Request efficiency
        
        Args:
            subreddit: Subreddit name
            F_target: Target coverage fraction
            discovered: Number of posts discovered
            sampled: Number of posts actually scraped
            requests_used: Total API requests consumed
        """
        F_realized = sampled / max(discovered, 1)
        
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subreddit": subreddit,
            "F_target": F_target,
            "F_realized": F_realized,
            "discovered": discovered,
            "sampled": sampled,
            "requests": requests_used,
            "coverage_drift": F_realized - F_target
        }
        
        # Append to coverage log
        try:
            with open('coverage_metrics.jsonl', 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            print(f"⚠️  Failed to log coverage metrics: {e}")
    
    def log_snapshot(self, snapshot: TelemetrySnapshot, filepath: str = "telemetry.jsonl"):
        """
        Append snapshot to JSONL log file.
        
        Args:
            snapshot: TelemetrySnapshot to log
            filepath: Path to append-only log file
        """
        try:
            with open(filepath, 'a') as f:
                f.write(json.dumps(asdict(snapshot)) + '\n')
        except Exception as e:
            print(f"⚠️  Failed to log telemetry: {e}")
    
    def print_snapshot(self, snapshot: TelemetrySnapshot, verbose: bool = False):
        """
        Print formatted snapshot to console.
        
        Args:
            snapshot: TelemetrySnapshot to display
            verbose: If True, show all metrics; if False, show compact summary
        """
        if verbose:
            print("="*80)
            print(f"📊 TELEMETRY SNAPSHOT - {snapshot.timestamp}")
            print("="*80)
            print()
            print(f"Global Metrics:")
            print(f"  ├─ Instantaneous RPS: {snapshot.instantaneous_rps:.2f}")
            print(f"  ├─ Rate EMA: {snapshot.rate_ema:.2f}")
            print(f"  ├─ Global Gain: {snapshot.global_gain:.3f}")
            print(f"  └─ Avg Lateness: {snapshot.avg_lateness*100:.1f}%")
            print()
            print(f"Throughput:")
            print(f"  ├─ Total Scrapes: {snapshot.total_scrapes}")
            print(f"  ├─ Total ΔInfo: {snapshot.total_delta_info:.1f}")
            print(f"  └─ Avg ΔInfo/scrape: {snapshot.avg_delta_info_per_scrape:.2f}")
            print()
            print(f"Coverage:")
            print(f"  ├─ Active Posts: {snapshot.active_posts}")
            print(f"  ├─ Scraped (6h): {snapshot.posts_scraped_last_6h}")
            print(f"  └─ Top Subs: {snapshot.coverage_pct_top_subs:.1f}%")
            print()
            print(f"Efficiency:")
            print(f"  ├─ Waste Rate: {snapshot.waste_rate*100:.1f}%")
            print(f"  └─ API Util: {snapshot.api_utilization_pct:.1f}%")
            
            if snapshot.alerts:
                print()
                print("🚨 ALERTS:")
                for alert in snapshot.alerts:
                    print(f"  {alert}")
            
            print()
            print("="*80)
        else:
            # Compact format
            print(f"[{snapshot.timestamp[11:19]}] "
                  f"RPS={snapshot.instantaneous_rps:.1f} "
                  f"EMA={snapshot.rate_ema:.1f} "
                  f"g={snapshot.global_gain:.2f} "
                  f"ΔInfo/sc={snapshot.avg_delta_info_per_scrape:.1f} "
                  f"waste={snapshot.waste_rate*100:.0f}%", end="")
            
            if snapshot.alerts:
                print(f" 🚨 {len(snapshot.alerts)} alerts", end="")
            
            print()
    
    def _compute_interval_median(self, scheduler) -> float:
        """
        FIX #6: Median interval across all tracked posts (in seconds).
        """
        if not hasattr(scheduler, 'posts') or not scheduler.posts:
            return 0.0
        intervals = [p.interval_hours * 3600 for p in scheduler.posts.values()]
        intervals.sort()
        return intervals[len(intervals) // 2] if intervals else 0.0
    
    def _compute_interval_p90(self, scheduler) -> float:
        """
        FIX #6: 90th percentile interval (in seconds).
        """
        if not hasattr(scheduler, 'posts') or not scheduler.posts:
            return 0.0
        intervals = [p.interval_hours * 3600 for p in scheduler.posts.values()]
        intervals.sort()
        if not intervals:
            return 0.0
        idx = int(len(intervals) * 0.9)
        return intervals[min(idx, len(intervals) - 1)]
    
    def _compute_interval_max(self, scheduler) -> float:
        """
        FIX #6: Maximum interval (in seconds).
        """
        if not hasattr(scheduler, 'posts') or not scheduler.posts:
            return 0.0
        intervals = [p.interval_hours * 3600 for p in scheduler.posts.values()]
        return max(intervals) if intervals else 0.0
    
    def _compute_soonest_delta(self, scheduler) -> float:
        """
        FIX #6: Seconds until soonest next scrape.
        """
        if not hasattr(scheduler, 'posts_queue') or not scheduler.posts_queue:
            return float('inf')
        now = datetime.now(timezone.utc)
        soonest = min(scheduler.posts_queue, key=lambda e: e.next_time)
        delta = (soonest.next_time - now).total_seconds()
        return max(0.0, delta)
    
    def log_cost_prediction(self, post_id: str, estimated: int, actual: int, 
                           budget_before: int, budget_after: int, p90: int, 
                           used_reserve: bool, temporal_dir: Optional[str] = None):
        """
        Log cost prediction for calibration analysis (FIX #16).
        
        Tracks estimated vs actual API request costs to calibrate the
        cost prediction model.
        
        Refinement #9: Uses absolute error for unbiased statistics.
        
        Args:
            post_id: Reddit post ID
            estimated: Estimated cost
            actual: Actual cost
            budget_before: Available budget before scrape
            budget_after: Available budget after scrape
            p90: P90 cost threshold
            used_reserve: Whether reserved budget was accessed
            temporal_dir: Optional directory for logging (uses self.temporal_dir if not specified)
        """
        # Refinement #9: Absolute error
        error_pct = (abs(actual - estimated) / max(1, actual)) * 100 if actual > 0 else 0
        
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "post_id": post_id,
            "estimated_cost": estimated,
            "actual_cost": actual,
            "error_pct": round(error_pct, 2),
            "budget_before": budget_before,
            "budget_after": budget_after,
            "p90_threshold": p90,
            "used_reserve": used_reserve,
            "over_estimate": estimated > actual,
            "under_estimate": estimated < actual
        }
        
        # Append to cost_predictions.jsonl
        if temporal_dir is None:
            temporal_dir = getattr(self, 'temporal_dir', 'temporal_test')
        
        from pathlib import Path
        log_path = Path(temporal_dir) / "cost_predictions.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")


if __name__ == '__main__':
    print("="*80)
    print("📊 TELEMETRY COLLECTOR - Demo")
    print("="*80)
    print()
    
    collector = TelemetryCollector()
    
    print("Simulating telemetry collection...")
    print()
    
    # Simulate normal operation
    snapshot1 = collector.collect_snapshot(
        instantaneous_rps=9.5,
        rate_ema=9.2,
        global_gain=1.0,
        avg_lateness=0.12,
        total_scrapes=100,
        total_delta_info=2000.0,
        active_posts=50,
        posts_scraped_6h=45,
        waste_rate=0.08,
        coverage_top_subs=0.95
    )
    
    print("Normal operation:")
    collector.print_snapshot(snapshot1, verbose=False)
    print()
    
    # Simulate high waste scenario
    snapshot2 = collector.collect_snapshot(
        instantaneous_rps=8.0,
        rate_ema=8.5,
        global_gain=1.2,
        avg_lateness=0.18,
        total_scrapes=150,
        total_delta_info=2050.0,
        active_posts=50,
        posts_scraped_6h=40,
        waste_rate=0.75,  # HIGH WASTE
        coverage_top_subs=0.40  # LOW COVERAGE
    )
    
    print("High waste + low coverage:")
    collector.print_snapshot(snapshot2, verbose=False)
    print()
    
    # Simulate gain pinned
    now = datetime.now(timezone.utc)
    for i in range(15):
        collector.gain_history.append((now, 3.0))  # Pinned at max
    
    snapshot3 = collector.collect_snapshot(
        instantaneous_rps=5.0,
        rate_ema=5.2,
        global_gain=3.0,  # PINNED MAX
        avg_lateness=0.25,
        total_scrapes=200,
        total_delta_info=2100.0,
        active_posts=50,
        posts_scraped_6h=35,
        waste_rate=0.15,
        coverage_top_subs=0.85
    )
    
    print("Gain pinned at max:")
    collector.print_snapshot(snapshot3, verbose=False)
    print()
    
    # Show verbose snapshot
    print()
    collector.print_snapshot(snapshot3, verbose=True)
    
    # Show status
    print("="*80)
    print("COLLECTOR STATUS")
    print("="*80)
    print()
    print(f"Total snapshots: {len(collector.snapshots)}")
    print(f"Active alerts: {len(collector.active_alerts)}")
    if collector.active_alerts:
        for alert_key, first_time in collector.active_alerts.items():
            duration = (now - first_time).total_seconds() / 60
            print(f"  ├─ {alert_key}: active for {duration:.1f} min")
    print()

