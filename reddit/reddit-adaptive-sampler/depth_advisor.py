#!/usr/bin/env python3
"""
Depth Advisor - Dynamic Harvest Depth Selection
Chooses shallow/medium/deep scraping based on marginal ΔInfo efficiency.
Based on reference_books/architecture.md §2.10 and §7
"""

import os
from typing import Dict, Optional
from dataclasses import dataclass
from collections import deque


@dataclass
class DepthMode:
    """Scraping depth configuration."""
    name: str
    max_depth: int  # Max comment nesting depth to traverse
    max_more_objects: int  # Max 'more' objects to expand
    estimated_cost: int  # Estimated API requests


# Predefined depth modes
SHALLOW = DepthMode("shallow", max_depth=2, max_more_objects=10, estimated_cost=8)
MEDIUM = DepthMode("medium", max_depth=5, max_more_objects=30, estimated_cost=25)
DEEP = DepthMode("deep", max_depth=10, max_more_objects=100, estimated_cost=80)

DEFAULT_PROMOTE_THRESHOLD = float(os.getenv("SCRAPER_DEPTH_PROMOTE_THRESHOLD", "0.03"))
DEFAULT_DEMOTE_THRESHOLD = float(os.getenv("SCRAPER_DEPTH_DEMOTE_THRESHOLD", "0.02"))
DEFAULT_MAX_CONCURRENT_DEEP = int(os.getenv("SCRAPER_DEPTH_MAX_DEEP", "3"))
FORCE_SHALLOW_ON_ZERO = os.getenv("SCRAPER_DEPTH_FORCE_SHALLOW_ON_ZERO", "true").lower() == "true"


class DepthAdvisor:
    """
    Adaptively chooses scraping depth per post based on marginal efficiency.
    
    Key idea:
    - Start shallow for new posts (low cost)
    - Escalate to medium/deep if ΔInfo/request ≥ promote_threshold
    - De-escalate if ΔInfo/request < demote_threshold
    - Limit concurrent deep harvests to avoid bandwidth spikes
    
    Tracks rolling average of marginal efficiency for each post.
    """
    
    def __init__(self,
                 promote_threshold: Optional[float] = None,
                 demote_threshold: Optional[float] = None,
                 max_concurrent_deep: Optional[int] = None,
                 history_window: int = 3):
        """
        Initialize depth advisor.
        
        Args:
            promote_threshold: ΔInfo/request threshold to escalate depth (defaults to
                SCRAPER_DEPTH_PROMOTE_THRESHOLD or 0.03)
            demote_threshold: ΔInfo/request threshold to de-escalate (defaults to
                SCRAPER_DEPTH_DEMOTE_THRESHOLD or 0.02)
            max_concurrent_deep: Maximum posts in deep mode simultaneously (defaults to
                SCRAPER_DEPTH_MAX_DEEP or 3)
            history_window: Number of recent scrapes to average for efficiency (default 3)
        """
        self.promote_threshold = (
            DEFAULT_PROMOTE_THRESHOLD if promote_threshold is None else promote_threshold
        )
        self.demote_threshold = (
            DEFAULT_DEMOTE_THRESHOLD if demote_threshold is None else demote_threshold
        )
        self.max_concurrent_deep = (
            DEFAULT_MAX_CONCURRENT_DEEP if max_concurrent_deep is None else max_concurrent_deep
        )
        self.history_window = history_window
        
        # Track depth mode per post
        self.depth_modes: Dict[str, DepthMode] = {}  # post_id → DepthMode
        
        # Track efficiency history per post
        self.efficiency_history: Dict[str, deque] = {}  # post_id → deque of (ΔInfo/request)
        
        # Track posts currently in deep mode
        self.deep_posts: set = set()
    
    def get_depth_mode(self, post_id: str) -> DepthMode:
        """
        Get current depth mode for a post.
        
        Args:
            post_id: Reddit post ID
        
        Returns:
            DepthMode (defaults to SHALLOW for new posts)
        """
        return self.depth_modes.get(post_id, SHALLOW)
    
    def record_scrape(self, post_id: str, delta_info: float, api_requests: int):
        """
        Record scrape result and update depth mode.
        
        Args:
            post_id: Reddit post ID
            delta_info: Information gain from this scrape
            api_requests: Number of API requests made
        """
        # Compute marginal efficiency
        efficiency = delta_info / api_requests if api_requests > 0 else 0.0
        
        # Initialize history if needed
        if post_id not in self.efficiency_history:
            self.efficiency_history[post_id] = deque(maxlen=self.history_window)
        
        # Add to history
        self.efficiency_history[post_id].append(efficiency)
        
        # Compute rolling average efficiency
        avg_efficiency = sum(self.efficiency_history[post_id]) / len(self.efficiency_history[post_id])
        
        # Get current depth mode
        current_mode = self.get_depth_mode(post_id)

        if FORCE_SHALLOW_ON_ZERO and delta_info <= 0:
            self.depth_modes[post_id] = SHALLOW
            self.deep_posts.discard(post_id)
            return
        
        # Decide on depth mode update
        new_mode = self._decide_depth_mode(post_id, current_mode, avg_efficiency)
        
        # Update depth mode
        self.depth_modes[post_id] = new_mode
        
        # Update deep posts tracking
        if new_mode == DEEP:
            self.deep_posts.add(post_id)
        else:
            self.deep_posts.discard(post_id)
    
    def _decide_depth_mode(self, post_id: str, current_mode: DepthMode, avg_efficiency: float) -> DepthMode:
        """
        Decide depth mode based on efficiency and constraints.
        
        Rules:
        1. If efficiency ≥ promote_threshold → escalate (shallow→medium→deep)
        2. If efficiency < demote_threshold → de-escalate (deep→medium→shallow)
        3. If trying to go deep but max_concurrent_deep reached → stay at medium
        4. Otherwise → keep current mode
        
        Args:
            post_id: Reddit post ID
            current_mode: Current DepthMode
            avg_efficiency: Rolling average ΔInfo/request
        
        Returns:
            New DepthMode
        """
        # Check for escalation
        if avg_efficiency >= self.promote_threshold:
            if current_mode == SHALLOW:
                return MEDIUM
            elif current_mode == MEDIUM:
                # Check concurrent deep limit
                if len(self.deep_posts) < self.max_concurrent_deep:
                    return DEEP
                else:
                    # At limit, stay medium
                    return MEDIUM
            else:  # Already DEEP
                return DEEP
        
        # Check for de-escalation
        elif avg_efficiency < self.demote_threshold:
            if current_mode == DEEP:
                return MEDIUM
            elif current_mode == MEDIUM:
                return SHALLOW
            else:  # Already SHALLOW
                return SHALLOW
        
        # In between thresholds → maintain current mode
        else:
            return current_mode
    
    def recommend_depth_for_new_post(self, subreddit: Optional[str] = None) -> DepthMode:
        """
        Recommend initial depth mode for a newly discovered post.
        
        Default: SHALLOW (conservative)
        
        Could be enhanced to use subreddit priors.
        
        Args:
            subreddit: Optional subreddit name for prior-based recommendation
        
        Returns:
            DepthMode recommendation
        """
        # For now, always start shallow
        # Future: could use subreddit-specific priors
        return SHALLOW
    
    def get_status(self) -> Dict:
        """
        Get advisor status for monitoring.
        
        Returns:
            Dict with depth distribution and metrics
        """
        # Count posts by depth mode
        shallow_count = sum(1 for m in self.depth_modes.values() if m == SHALLOW)
        medium_count = sum(1 for m in self.depth_modes.values() if m == MEDIUM)
        deep_count = sum(1 for m in self.depth_modes.values() if m == DEEP)
        
        # Compute average efficiency across all posts
        all_efficiencies = []
        for history in self.efficiency_history.values():
            all_efficiencies.extend(history)
        
        avg_efficiency = sum(all_efficiencies) / len(all_efficiencies) if all_efficiencies else 0.0
        
        return {
            "total_posts": len(self.depth_modes),
            "shallow": shallow_count,
            "medium": medium_count,
            "deep": deep_count,
            "deep_limit": self.max_concurrent_deep,
            "deep_available": self.max_concurrent_deep - len(self.deep_posts),
            "avg_efficiency": avg_efficiency,
            "promote_threshold": self.promote_threshold,
            "demote_threshold": self.demote_threshold,
        }


if __name__ == '__main__':
    print("="*80)
    print("🎯 DEPTH ADVISOR - Demo")
    print("="*80)
    print()
    
    advisor = DepthAdvisor(
        promote_threshold=0.03,
        demote_threshold=0.01,
        max_concurrent_deep=5
    )
    
    # Simulate some scrapes
    print("Simulating scrape sequences...")
    print()
    
    # Post 1: High efficiency → should escalate to deep
    print("Post A (high efficiency):")
    advisor.record_scrape("post_a", delta_info=10.0, api_requests=8)
    print(f"  Scrape 1: ΔInfo=10, reqs=8, eff=1.25 → {advisor.get_depth_mode('post_a').name}")
    
    advisor.record_scrape("post_a", delta_info=12.0, api_requests=10)
    print(f"  Scrape 2: ΔInfo=12, reqs=10, eff=1.20 → {advisor.get_depth_mode('post_a').name}")
    
    advisor.record_scrape("post_a", delta_info=15.0, api_requests=12)
    print(f"  Scrape 3: ΔInfo=15, reqs=12, eff=1.25 → {advisor.get_depth_mode('post_a').name}")
    print()
    
    # Post 2: Low efficiency → should stay shallow or de-escalate
    print("Post B (low efficiency):")
    advisor.record_scrape("post_b", delta_info=0.5, api_requests=25)
    print(f"  Scrape 1: ΔInfo=0.5, reqs=25, eff=0.02 → {advisor.get_depth_mode('post_b').name}")
    
    advisor.record_scrape("post_b", delta_info=0.3, api_requests=25)
    print(f"  Scrape 2: ΔInfo=0.3, reqs=25, eff=0.01 → {advisor.get_depth_mode('post_b').name}")
    
    advisor.record_scrape("post_b", delta_info=0.1, api_requests=25)
    print(f"  Scrape 3: ΔInfo=0.1, reqs=25, eff=0.004 → {advisor.get_depth_mode('post_b').name}")
    print()
    
    # Post 3: Medium efficiency → should reach medium and stay
    print("Post C (medium efficiency):")
    advisor.record_scrape("post_c", delta_info=5.0, api_requests=20)
    print(f"  Scrape 1: ΔInfo=5, reqs=20, eff=0.25 → {advisor.get_depth_mode('post_c').name}")
    
    advisor.record_scrape("post_c", delta_info=4.0, api_requests=20)
    print(f"  Scrape 2: ΔInfo=4, reqs=20, eff=0.20 → {advisor.get_depth_mode('post_c').name}")
    
    advisor.record_scrape("post_c", delta_info=3.0, api_requests=20)
    print(f"  Scrape 3: ΔInfo=3, reqs=20, eff=0.15 → {advisor.get_depth_mode('post_c').name}")
    print()
    
    # Display status
    print("="*80)
    print("ADVISOR STATUS")
    print("="*80)
    print()
    
    status = advisor.get_status()
    for key, val in status.items():
        print(f"{key}: {val}")
    
    print()
    print("="*80)

