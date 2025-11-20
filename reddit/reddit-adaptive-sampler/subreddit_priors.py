#!/usr/bin/env python3
"""
Subreddit-Adaptive Priors
Maintains learned behavior per subreddit for new post initialization.
Based on reference_books/adaptive_scheduler_reference.ipynb
"""

from collections import defaultdict, deque
from typing import Dict, Optional
import statistics


class SubredditPriors:
    """
    Tracks and provides subreddit-specific priors for post initialization.
    
    New posts inherit λ (decay rate) and other metrics from their subreddit's
    historical average, enabling better initial scheduling.
    """
    
    def __init__(self, max_history: int = 200):
        """
        Initialize subreddit priors tracker.
        
        Args:
            max_history: Maximum number of posts to track per subreddit
        """
        self.max_history = max_history
        
        # Store rolling history per subreddit
        self.lambda_history = defaultdict(lambda: deque(maxlen=max_history))
        self.half_life_history = defaultdict(lambda: deque(maxlen=max_history))
        self.waste_rate_history = defaultdict(lambda: deque(maxlen=max_history))
        
        # Cached priors (computed from history)
        self.lambda_prior = defaultdict(lambda: 0.15)  # Default λ
        self.half_life_prior = defaultdict(lambda: 4.0)  # Default half-life (hours)
        self.waste_rate_prior = defaultdict(lambda: 0.1)  # Default waste rate
        
        # Track post count per subreddit
        self.post_count = defaultdict(int)
    
    def record_post(self, subreddit: str, 
                   lambda_est: float,
                   half_life_h: Optional[float] = None,
                   waste_rate: Optional[float] = None):
        """
        Record metrics from a post that has reached dormancy/retirement.
        
        Updates rolling averages for the subreddit.
        
        Args:
            subreddit: Subreddit name (e.g., "news")
            lambda_est: Estimated decay rate (λ) for this post
            half_life_h: Optional half-life in hours
            waste_rate: Optional waste rate (fraction of zero-Δ scrapes)
        """
        # Add to history
        self.lambda_history[subreddit].append(lambda_est)
        
        if half_life_h is not None:
            self.half_life_history[subreddit].append(half_life_h)
        
        if waste_rate is not None:
            self.waste_rate_history[subreddit].append(waste_rate)
        
        # Update post count
        self.post_count[subreddit] += 1
        
        # Recompute priors (rolling mean)
        self._update_priors(subreddit)
    
    def _update_priors(self, subreddit: str):
        """
        Recompute cached priors from history.
        Uses mean for most metrics.
        """
        # Lambda (decay rate)
        if self.lambda_history[subreddit]:
            vals = list(self.lambda_history[subreddit])
            self.lambda_prior[subreddit] = statistics.mean(vals)
        
        # Half-life
        if self.half_life_history[subreddit]:
            vals = list(self.half_life_history[subreddit])
            self.half_life_prior[subreddit] = statistics.mean(vals)
        
        # Waste rate
        if self.waste_rate_history[subreddit]:
            vals = list(self.waste_rate_history[subreddit])
            self.waste_rate_prior[subreddit] = statistics.mean(vals)
    
    def get_lambda(self, subreddit: str) -> float:
        """
        Get prior λ (decay rate) for a subreddit.
        
        Args:
            subreddit: Subreddit name
        
        Returns:
            Prior λ value (default 0.15 if no history)
        """
        return self.lambda_prior[subreddit]
    
    def get_half_life(self, subreddit: str) -> float:
        """
        Get prior half-life for a subreddit.
        
        Args:
            subreddit: Subreddit name
        
        Returns:
            Prior half-life in hours (default 4.0 if no history)
        """
        return self.half_life_prior[subreddit]
    
    def get_waste_rate(self, subreddit: str) -> float:
        """
        Get expected waste rate for a subreddit.
        
        Args:
            subreddit: Subreddit name
        
        Returns:
            Prior waste rate (default 0.1 if no history)
        """
        return self.waste_rate_prior[subreddit]
    
    def get_stats(self, subreddit: str) -> Dict:
        """
        Get all available stats for a subreddit.
        
        Args:
            subreddit: Subreddit name
        
        Returns:
            Dict with all priors and sample size
        """
        return {
            "subreddit": subreddit,
            "n_posts": self.post_count[subreddit],
            "lambda_mean": self.lambda_prior[subreddit],
            "half_life_mean": self.half_life_prior[subreddit],
            "waste_rate_mean": self.waste_rate_prior[subreddit],
            "has_history": self.post_count[subreddit] > 0,
        }
    
    def get_all_subreddits(self) -> list:
        """
        Get list of all tracked subreddits.
        
        Returns:
            List of subreddit names
        """
        return list(self.post_count.keys())
    
    def export_priors(self) -> Dict:
        """
        Export all priors for persistence/analysis.
        
        Returns:
            Dict mapping subreddit → stats
        """
        return {
            sub: self.get_stats(sub)
            for sub in self.get_all_subreddits()
        }


if __name__ == '__main__':
    print("="*80)
    print("🎯 SUBREDDIT PRIORS - Demo")
    print("="*80)
    print()
    
    priors = SubredditPriors()
    
    # Simulate recording posts from r/news
    print("Recording posts from r/news...")
    news_posts = [
        (0.3, 5.0, 0.05),
        (0.25, 4.5, 0.08),
        (0.35, 3.8, 0.12),
        (0.28, 4.2, 0.06),
        (0.32, 4.7, 0.07),
    ]
    
    for lam, half_life, waste in news_posts:
        priors.record_post("news", lam, half_life, waste)
    
    print(f"  ✓ Recorded {len(news_posts)} posts")
    print()
    
    # Simulate recording posts from r/worldnews
    print("Recording posts from r/worldnews...")
    worldnews_posts = [
        (0.5, 2.5, 0.03),
        (0.48, 2.8, 0.04),
        (0.52, 2.3, 0.02),
    ]
    
    for lam, half_life, waste in worldnews_posts:
        priors.record_post("worldnews", lam, half_life, waste)
    
    print(f"  ✓ Recorded {len(worldnews_posts)} posts")
    print()
    
    # Display priors
    print("="*80)
    print("LEARNED PRIORS")
    print("="*80)
    print()
    
    for sub in priors.get_all_subreddits():
        stats = priors.get_stats(sub)
        print(f"r/{sub}:")
        print(f"  ├─ Posts tracked: {stats['n_posts']}")
        print(f"  ├─ λ (decay): {stats['lambda_mean']:.3f}")
        print(f"  ├─ Half-life: {stats['half_life_mean']:.1f}h")
        print(f"  └─ Waste rate: {stats['waste_rate_mean']*100:.1f}%")
        print()
    
    # Demo: Get prior for new post
    print("="*80)
    print("NEW POST INITIALIZATION")
    print("="*80)
    print()
    
    print("New post in r/news:")
    print(f"  → Inherits λ = {priors.get_lambda('news'):.3f}")
    print()
    
    print("New post in r/technology (no history):")
    print(f"  → Uses default λ = {priors.get_lambda('technology'):.3f}")
    print()
    
    print("="*80)

