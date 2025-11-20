#!/usr/bin/env python3
"""
Discovery Poller - Adaptive Multi-Subreddit Post Discovery
Periodically polls /r/<sub>/new for fresh posts with adaptive cadence.
Based on reference_books/architecture.md §2.1 and §6
"""

import requests
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field

from coverage_allocator import PriorityCoverageAllocator, SubredditConfig


@dataclass
class DiscoveredPost:
    """A newly discovered post from /r/<sub>/new"""
    post_id: str
    url: str
    subreddit: str
    title: str
    score: int
    num_comments: int
    created_utc: float
    discovered_at: datetime
    author: str = ""


class DiscoveryPoller:
    """
    Adaptive poller for discovering new posts across multiple subreddits.
    
    Polling frequency adapts based on:
    - Subreddit priority rank
    - Coverage fraction F_i
    - Global gain g
    """
    
    def __init__(self, 
                 allocator: PriorityCoverageAllocator,
                 session: Optional[requests.Session] = None,
                 base_poll_interval: float = 300.0):
        """
        Initialize discovery poller.
        
        Args:
            allocator: PriorityCoverageAllocator instance
            session: Optional authenticated session for higher rate limits
            base_poll_interval: Base polling interval in seconds (default 300 = 5 min)
        """
        self.allocator = allocator
        self.session = session
        self.base_poll_interval = base_poll_interval
        
        # Track last poll time per subreddit
        self.last_poll: Dict[str, datetime] = {}
        
        # Track discovered post IDs (to avoid duplicates)
        self.seen_post_ids: Set[str] = set()
        
        # Metrics
        self.total_polls = 0
        self.total_discovered = 0
        self.polls_per_subreddit: Dict[str, int] = {}
        
        # FIX #5: Discovery history for rate tracking
        from collections import deque
        self.discovery_history: deque = deque(maxlen=1000)  # (timestamp, subreddit, post_id)
    
    def compute_poll_interval(self, subreddit: str, global_gain: float = 1.0) -> float:
        """
        Compute adaptive poll interval for a subreddit.
        
        Higher priority → shorter interval (more frequent polling)
        Lower priority → longer interval (less frequent)
        
        FIX #3: Rank-based polling independent of coverage fraction.
        This ensures discovery stays fresh even when coverage fraction is low.
        
        Args:
            subreddit: Subreddit name
            global_gain: Global gain from rate controller (unused in new version)
        
        Returns:
            Poll interval in seconds
        """
        # Rank-based polling independent of coverage fraction
        rank = self.allocator.get_rank(subreddit)
        if rank is None:
            return self.base_poll_interval
        
        # Linear scaling: top ranks poll every 30s, lower ranks less frequently
        interval = 30.0 + (5.0 * rank)  # +5s per rank
        
        # Clamp to reasonable bounds (20s to 5min)
        interval = max(20.0, min(300.0, interval))
        
        return interval
    
    def should_poll(self, subreddit: str, now: datetime, global_gain: float = 1.0) -> bool:
        """
        Check if it's time to poll a subreddit.
        
        Args:
            subreddit: Subreddit name
            now: Current time
            global_gain: Global gain from rate controller
        
        Returns:
            True if should poll now
        """
        last_poll_time = self.last_poll.get(subreddit)
        
        if last_poll_time is None:
            return True  # Never polled, do it now
        
        interval = self.compute_poll_interval(subreddit, global_gain)
        elapsed = (now - last_poll_time).total_seconds()
        
        return elapsed >= interval
    
    def poll_subreddit(self, subreddit: str, limit: int = 25) -> List[DiscoveredPost]:
        """
        Poll /r/<sub>/new for fresh posts.
        
        Args:
            subreddit: Subreddit name (without r/ prefix)
            limit: Number of posts to fetch (default 25)
        
        Returns:
            List of newly discovered posts
        """
        # Clean subreddit name
        subreddit = subreddit.replace('r/', '').strip()
        
        url = f'https://oauth.reddit.com/r/{subreddit}/new' if self.session else f'https://www.reddit.com/r/{subreddit}/new.json'
        
        params = {'limit': limit}
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; RedditTemporalScraper/1.0)'
        }
        
        try:
            if self.session:
                response = self.session.get(url, params=params, timeout=10)
            else:
                response = requests.get(url, headers=headers, params=params, timeout=10)
            
            response.raise_for_status()
            data = response.json()
            
            discovered = []
            now = datetime.now(timezone.utc)
            
            for post_wrapper in data['data']['children']:
                post_data = post_wrapper['data']
                post_id = post_data.get('id', '')
                
                # Skip if already seen
                if post_id in self.seen_post_ids:
                    continue
                
                # Create DiscoveredPost
                permalink = post_data.get('permalink', '')
                full_url = f"https://www.reddit.com{permalink}"
                
                discovered_post = DiscoveredPost(
                    post_id=post_id,
                    url=full_url,
                    subreddit=subreddit,
                    title=post_data.get('title', ''),
                    score=post_data.get('score', 0),
                    num_comments=post_data.get('num_comments', 0),
                    created_utc=post_data.get('created_utc', 0),
                    discovered_at=now,
                    author=post_data.get('author', '')
                )
                
                discovered.append(discovered_post)
                self.seen_post_ids.add(post_id)
                
                # FIX #5: Record in discovery history for rate tracking
                self.discovery_history.append((now, subreddit, post_id))
            
            # Update metrics
            self.last_poll[subreddit] = now
            self.total_polls += 1
            self.total_discovered += len(discovered)
            self.polls_per_subreddit[subreddit] = self.polls_per_subreddit.get(subreddit, 0) + 1
            
            if discovered:
                print(f"🔍 r/{subreddit}: Found {len(discovered)} new posts")
            
            return discovered
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print(f"⏳ r/{subreddit}: Rate limited (429)")
            else:
                print(f"❌ r/{subreddit}: HTTP error {e.response.status_code}")
            return []
        except Exception as e:
            print(f"❌ r/{subreddit}: Error during poll: {e}")
            return []
    
    def poll_all_due(self, global_gain: float = 1.0) -> List[DiscoveredPost]:
        """
        Poll all subreddits that are due for polling.
        
        Args:
            global_gain: Global gain from rate controller
        
        Returns:
            List of all newly discovered posts across all subreddits
        """
        now = datetime.now(timezone.utc)
        all_discovered = []
        
        for subreddit in self.allocator.rank_order:
            if self.should_poll(subreddit, now, global_gain):
                discovered = self.poll_subreddit(subreddit)
                all_discovered.extend(discovered)
                
                # Small delay between polls to avoid bursts
                time.sleep(0.5)
        
        return all_discovered
    
    def poll_top_k_due(self, K: int, global_gain: float = 1.0) -> List[DiscoveredPost]:
        """
        FIX #4: Poll the K most-due subreddits (longest time since last poll).
        
        Used for opportunistic discovery when scraper is idle.
        
        Args:
            K: Number of subreddits to poll
            global_gain: Global gain from rate controller
        
        Returns:
            List of all newly discovered posts
        """
        now = datetime.now(timezone.utc)
        
        # Sort by time since last poll (longest ago first)
        due_order = sorted(
            self.allocator.rank_order,
            key=lambda s: (now - self.last_poll.get(s, datetime.min.replace(tzinfo=timezone.utc))).total_seconds(),
            reverse=True
        )
        
        all_discovered = []
        for subreddit in due_order[:K]:
            discovered = self.poll_subreddit(subreddit, limit=25)
            all_discovered.extend(discovered)
            time.sleep(0.5)  # Small delay between polls
        
        return all_discovered
    
    def get_recent_discovery_rates(self, window_minutes: int = 10) -> Dict[str, float]:
        """
        FIX #5: Compute recent discovery rate (posts/hour) per subreddit.
        
        Used by coverage allocator to weight budget by activity level.
        
        Args:
            window_minutes: Time window to average over
        
        Returns:
            Dict mapping subreddit → posts per hour
        """
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=window_minutes)
        
        rates = {}
        for sub in self.allocator.rank_order:
            # Count posts from this sub in time window
            count = sum(1 for (ts, s, _) in self.discovery_history 
                        if s == sub and ts > cutoff)
            
            # Convert to rate (posts/hour)
            rates[sub] = count / (window_minutes / 60.0)
        
        return rates
    
    def get_status(self) -> Dict:
        """
        Get poller status for monitoring.
        
        Returns:
            Dict with metrics
        """
        now = datetime.now(timezone.utc)
        
        # Compute next poll times
        next_polls = {}
        for subreddit in self.allocator.rank_order:
            last = self.last_poll.get(subreddit)
            interval = self.compute_poll_interval(subreddit, global_gain=1.0)
            
            if last and interval != float('inf'):
                next_poll = last + timedelta(seconds=interval)
                minutes_until = (next_poll - now).total_seconds() / 60.0
                next_polls[subreddit] = f"{minutes_until:.1f} min"
            else:
                next_polls[subreddit] = "never polled" if not last else "inf"
        
        return {
            "total_subreddits": len(self.allocator.rank_order),
            "total_polls": self.total_polls,
            "total_discovered": self.total_discovered,
            "avg_posts_per_poll": self.total_discovered / self.total_polls if self.total_polls > 0 else 0,
            "seen_post_ids": len(self.seen_post_ids),
            "next_polls": next_polls,
        }


if __name__ == '__main__':
    print("="*80)
    print("🔍 DISCOVERY POLLER - Demo")
    print("="*80)
    print()
    
    # Load allocator
    allocator = PriorityCoverageAllocator()
    allocator.load_from_file('subreddit_priorities.txt')
    
    # Compute coverage fractions
    allocator.compute_coverage_fractions(global_gain=1.0)
    
    print()
    
    # Create poller
    poller = DiscoveryPoller(allocator, session=None)
    
    print("="*80)
    print("POLLING SCHEDULE")
    print("="*80)
    print()
    
    # Show poll intervals for each subreddit
    print(f"{'Rank':<6} {'Subreddit':<25} {'F':<10} {'Poll Every':<15}")
    print("-"*80)
    
    for name in allocator.rank_order[:15]:  # Show first 15
        config = allocator.subreddits[name]
        F = allocator.coverage_fractions[name]
        interval = poller.compute_poll_interval(name, global_gain=1.0)
        
        if interval == float('inf'):
            interval_str = "Never"
        else:
            interval_str = f"{interval/60:.1f} min"
        
        print(f"{config.rank:<6} r/{name:<24} {F:<10.3f} {interval_str:<15}")
    
    if len(allocator.rank_order) > 15:
        print(f"... and {len(allocator.rank_order) - 15} more")
    
    print()
    print("="*80)
    print()
    
    print("💡 Note: Actual polling requires authenticated session for /new access.")
    print("   Run with OAuth to test live discovery.")
    print()

