#!/usr/bin/env python3
"""
Priority Coverage Allocator
Implements smooth bandwidth allocation across prioritized subreddits using sigmoid curve.
Based on reference_books/architecture.md §2.7 and §6
"""

import math
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class SubredditConfig:
    """Configuration for a tracked subreddit."""
    name: str
    rank: int  # Priority rank (0 = highest)
    cost_estimate: float = 25.0  # Avg API requests per post
    lambda_prior: float = 0.15  # Default decay rate
    poll_interval_min: int = 15  # Minutes between discovery polls


class PriorityCoverageAllocator:
    """
    Allocates API bandwidth across prioritized subreddits.
    
    Uses sigmoid curve for smooth degradation:
    - High-priority subs get F ≈ 1.0 (scrape everything)
    - Low-priority subs get F ≈ 0.0 (flex zone, drop most)
    
    Equation:
        f(r) = 1 / (1 + exp(alpha_p * (r - R_c)))
        F_i = scale * f(r_i) * g
    
    Where:
        r_i = priority rank of subreddit i
        R_c = center rank (where F ≈ 0.5)
        alpha_p = steepness (controls flex zone width)
        g = global gain from rate controller
        scale = normalization to stay within budget
    """
    
    def __init__(self,
                 budget_rps: float = 10.0,
                 alpha_p: float = 0.03,
                 R_c: float = 50.0,
                 reserve_fraction: float = 0.15):
        """
        Initialize coverage allocator.
        
        Args:
            budget_rps: Total API budget in requests per second (default 10.0 = 600/min)
            alpha_p: Sigmoid steepness (default 0.03, gentler curve)
            R_c: Center rank where F ≈ 0.5 (default 50)
            reserve_fraction: Reserve budget for bursts (default 15%)
        """
        self.budget_rps = budget_rps
        self.alpha_p = alpha_p
        self.R_c = R_c
        self.reserve_fraction = reserve_fraction
        
        # Subreddit tracking
        self.subreddits: Dict[str, SubredditConfig] = {}
        self.rank_order: List[str] = []  # Ordered list of subreddit names
        
        # Computed coverage fractions (updated when budget or gain changes)
        self.coverage_fractions: Dict[str, float] = {}
        
        # FIX #8: Selection policy (cached)
        self.selection_policy = None
        self.policy_file = "selection_policy.json"
    
    def load_from_file(self, filepath: str = 'subreddit_priorities.txt'):
        """
        Load prioritized subreddit list from file.
        
        File format: One subreddit per line, highest priority first.
        Lines starting with # are ignored.
        
        Args:
            filepath: Path to priorities file
        """
        self.subreddits = {}
        self.rank_order = []
        
        try:
            with open(filepath, 'r') as f:
                rank = 0
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Remove r/ prefix if present
                        subreddit = line.lower().replace('r/', '')
                        
                        config = SubredditConfig(
                            name=subreddit,
                            rank=rank
                        )
                        
                        self.subreddits[subreddit] = config
                        self.rank_order.append(subreddit)
                        rank += 1
            
            print(f"✅ Loaded {len(self.subreddits)} prioritized subreddits")
            
        except FileNotFoundError:
            print(f"⚠️  File not found: {filepath}")
        except Exception as e:
            print(f"⚠️  Error loading priorities: {e}")
    
    def sigmoid_curve(self, rank: int) -> float:
        """
        Compute sigmoid coverage curve value.
        
        f(r) = 1 / (1 + exp(alpha_p * (r - R_c)))
        
        Args:
            rank: Priority rank (0 = highest)
        
        Returns:
            Base coverage fraction ∈ [0, 1]
        """
        return 1.0 / (1.0 + math.exp(self.alpha_p * (rank - self.R_c)))
    
    def compute_coverage_fractions(self, 
                                   global_gain: float = 1.0,
                                   posts_per_subreddit: Optional[Dict[str, float]] = None,
                                   current_rps: Optional[float] = None,
                                   ema_rps: Optional[float] = None):
        """
        Compute coverage fraction F_i for each subreddit.
        
        Accounts for:
        - Sigmoid priority curve
        - Global gain from rate controller
        - Budget constraints
        - Cost per subreddit
        
        Args:
            global_gain: Global gain g from rate controller
            posts_per_subreddit: Optional dict of active post counts per subreddit
            current_rps: Optional current throughput (for budget scaling)
        
        Returns:
            Dict mapping subreddit → coverage fraction
        """
        if not self.subreddits:
            return {}
        
        # Determine current utilisation to decide if we should engage the flex curve.
        usage_rps = None
        if ema_rps is not None:
            usage_rps = ema_rps
        elif current_rps is not None:
            usage_rps = current_rps
        else:
            usage_rps = 0.0
        
        free_budget_threshold = self.budget_rps * 0.85  # High watermark before flexing
        if usage_rps < free_budget_threshold:
            # Budget is comfortably free → discover everything.
            self.coverage_fractions = {name: 1.0 for name in self.subreddits}
            if __debug__:
                for name, fraction in self.coverage_fractions.items():
                    assert fraction == 1.0, f"Coverage fraction drifted for {name} with free budget"
            return self.coverage_fractions
        
        # Budget tight → fall back to sigmoid scaling.
        available_budget = max(self.budget_rps, usage_rps)
        usable_budget = available_budget * (1.0 - self.reserve_fraction)
        
        base_fractions = {name: self.sigmoid_curve(config.rank) for name, config in self.subreddits.items()}
        
        total_demand = 0.0
        for name, config in self.subreddits.items():
            base_fraction = base_fractions[name]
            cost = config.cost_estimate
            rate = posts_per_subreddit.get(name, 1.0) if posts_per_subreddit else 1.0
            total_demand += base_fraction * cost * rate
        
        scale = usable_budget / total_demand if total_demand > 0 else 1.0
        scale = min(scale, 1.0)
        
        self.coverage_fractions = {}
        for name, config in self.subreddits.items():
            base_fraction = base_fractions[name]
            rate = posts_per_subreddit.get(name, 1.0) if posts_per_subreddit else 1.0
            F_i = scale * base_fraction * rate * global_gain
            F_i = max(0.0, min(1.0, F_i))
            self.coverage_fractions[name] = F_i
        
        return self.coverage_fractions
    
    def should_scrape_post(self, subreddit: str, post_data: Optional[dict] = None) -> bool:
        """
        FIX #8: Decide if a discovered post should be tracked.
        
        Uses selection_policy.json to determine filtering strategy.
        Falls back to sigmoid-based probabilistic sampling if no policy.
        
        Args:
            subreddit: Subreddit name
            post_data: Optional dict with post metadata (num_comments, score, created_utc, etc.)
        
        Returns:
            True if post should be added to tracking pool
        """
        rank = self.get_rank(subreddit)
        if rank is None:
            return False
        
        # Load policy
        policy = self._load_selection_policy()
        
        # Find matching rule based on rank
        for rule in policy.get("rules", []):
            rank_range = rule.get("ranks", [0, 999])
            if rank_range[0] <= rank <= rank_range[1]:
                # Store subreddit in rule context for probabilistic method
                rule["subreddit"] = subreddit
                return self._apply_selection_rule(rule, post_data)
        
        # No matching rule - fallback to probabilistic
        import random
        F = self.coverage_fractions.get(subreddit.lower(), 0.0)
        return random.random() < F
    
    def get_coverage_fraction(self, subreddit: str) -> float:
        """
        Get current coverage fraction for a subreddit.
        
        Args:
            subreddit: Subreddit name
        
        Returns:
            Coverage fraction F ∈ [0, 1]
        """
        return self.coverage_fractions.get(subreddit.lower(), 0.0)
    
    def get_rank(self, subreddit: str) -> Optional[int]:
        """
        Get priority rank for a subreddit.
        
        Args:
            subreddit: Subreddit name
        
        Returns:
            Rank (0 = highest) or None if not tracked
        """
        config = self.subreddits.get(subreddit.lower())
        return config.rank if config else None
    
    def _load_selection_policy(self) -> dict:
        """
        Load the intake policy from disk (cached).

        The default configuration (`selection_policy.json`) now admits every
        discovered post so downstream schedulers decide cadence. Optional flex
        rules can be reintroduced by editing the JSON.
        """
        import json
        
        if self.selection_policy is not None:
            return self.selection_policy
        
        try:
            with open(self.policy_file, 'r') as f:
                self.selection_policy = json.load(f)
                print(f"✅ Loaded selection policy: {self.selection_policy.get('strategy', 'default')}")
        except FileNotFoundError:
            # Fallback to probabilistic if no policy file
            self.selection_policy = {"strategy": "probabilistic", "rules": []}
        
        return self.selection_policy
    
    def _apply_selection_rule(self, rule: dict, post_data: Optional[dict] = None) -> bool:
        """
        FIX #8: Apply a selection rule to decide if post should be tracked.
        
        Supported methods:
        - "all": Track everything
        - "sample": Random sampling at specified rate
        - "hot_only": Only posts exceeding comment/score thresholds
        - "probabilistic": Use sigmoid coverage fraction (current behavior)
        
        Args:
            rule: Rule dict with method and parameters
            post_data: Optional post metadata (num_comments, score, etc.)
        
        Returns:
            True if post should be tracked
        """
        import random
        
        method = rule.get("method", "all")
        
        if method == "all":
            return True
        
        elif method == "sample":
            sample_rate = rule.get("sample_rate", 1.0)
            return random.random() < sample_rate
        
        elif method == "hot_only":
            if not post_data:
                # Can't filter without data - default to accept
                return True
            
            comments = post_data.get("num_comments", 0)
            score = post_data.get("score", 0)
            min_comments = rule.get("min_comments", 0)
            min_score = rule.get("min_score", 0)
            
            return comments >= min_comments and score >= min_score
        
        elif method == "probabilistic":
            # Use sigmoid-based coverage fraction
            subreddit = rule.get("subreddit", "")
            F = self.get_coverage_fraction(subreddit)
            return random.random() < F
        
        # Default: accept
        return True
    
    def get_status(self) -> Dict:
        """
        Get allocator status for monitoring.
        
        Returns:
            Dict with configuration and coverage fractions
        """
        return {
            "total_subreddits": len(self.subreddits),
            "budget_rps": self.budget_rps,
            "usable_budget_rps": self.budget_rps * (1.0 - self.reserve_fraction),
            "reserve_fraction": self.reserve_fraction,
            "alpha_p": self.alpha_p,
            "R_c": self.R_c,
            "coverage_fractions": self.coverage_fractions,
        }


def load_subreddit_priorities(filepath: str = 'subreddit_priorities.txt') -> List[str]:
    """
    Load prioritized subreddit list from file.
    
    Args:
        filepath: Path to priorities file
    
    Returns:
        List of subreddit names in priority order
    """
    subreddits = []
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    subreddits.append(line.lower())
    except FileNotFoundError:
        print(f"⚠️  File not found: {filepath}")
    except Exception as e:
        print(f"⚠️  Error reading {filepath}: {e}")
    
    return subreddits


if __name__ == '__main__':
    print("="*80)
    print("🎯 COVERAGE ALLOCATOR - Demo")
    print("="*80)
    print()
    
    # Create allocator
    allocator = PriorityCoverageAllocator(
        budget_rps=10.0,
        alpha_p=0.03,
        R_c=50.0
    )
    
    # Simulate loading priorities
    print("Loading example priorities...")
    
    # Add sample subreddits
    example_subs = ['news', 'worldnews', 'politics', 'technology', 'science', 
                   'askreddit', 'todayilearned', 'explainlikeimfive']
    
    for rank, name in enumerate(example_subs):
        allocator.subreddits[name] = SubredditConfig(name=name, rank=rank)
        allocator.rank_order.append(name)
    
    print(f"  ✓ Added {len(allocator.subreddits)} subreddits")
    print()
    
    # Compute coverage fractions
    print("Computing coverage fractions (g=1.0)...")
    allocator.compute_coverage_fractions(global_gain=1.0)
    print()
    
    # Display results
    print("="*80)
    print("COVERAGE ALLOCATION")
    print("="*80)
    print()
    print(f"{'Rank':<6} {'Subreddit':<20} {'F (Coverage)':<15} {'Sample Rate':<15}")
    print("-"*80)
    
    for name in allocator.rank_order:
        config = allocator.subreddits[name]
        F = allocator.coverage_fractions[name]
        sample_pct = F * 100
        
        print(f"{config.rank:<6} r/{name:<19} {F:<15.3f} {sample_pct:.1f}%")
    
    print()
    
    # Show flex zone behavior
    print("="*80)
    print("FLEX ZONE BEHAVIOR (simulated 100 posts per sub)")
    print("="*80)
    print()
    
    import random
    random.seed(42)
    
    for name in allocator.rank_order[:5]:
        F = allocator.coverage_fractions[name]
        scraped = sum(1 for _ in range(100) if random.random() < F)
        dropped = 100 - scraped
        
        print(f"r/{name:<15} F={F:.3f} → scraped {scraped}/100, dropped {dropped}/100")
    
    print()
    print("="*80)

