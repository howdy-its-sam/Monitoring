"""
Cost estimation for Reddit scrapes.

Predicts API request costs before scraping to enable proactive budget management
and prevent 429 errors.

Two estimation strategies:
1. Heuristic model (immediate, no history required)
2. Telemetry-based model (learns from actual scrape costs)
"""

import time
from collections import deque
from typing import Optional, Dict, Tuple


def estimate_scrape_cost_heuristic(num_comments: int, depth_mode: str) -> int:
    """
    Estimate API requests based on comment count and depth mode.
    
    Depth scaling ratios (from 10-hour test analysis):
    - SHALLOW: ~1 req per 100 comments (minimal expansion)
    - MEDIUM: ~1 req per 50 comments (moderate expansion)  
    - DEEP: ~1 req per 10 comments (full expansion)
    
    Args:
        num_comments: Estimated number of comments on post
        depth_mode: "shallow", "medium", or "deep"
    
    Returns:
        Estimated number of API requests needed
    """
    if depth_mode == "shallow":
        base_cost = max(1, num_comments // 100)
        return min(10, base_cost + 1)  # Cap at 10
    elif depth_mode == "medium":
        base_cost = max(1, num_comments // 50)
        return min(30, base_cost + 2)  # Cap at 30
    else:  # deep
        base_cost = max(1, num_comments // 10)
        return min(150, base_cost + 5)  # Cap at 150


class CostPredictor:
    """
    Learns from actual scrape costs to improve prediction accuracy over time.
    
    Uses historical data to predict costs for similar posts, falling back to
    heuristic model when insufficient data available.
    
    Refinement #3: Periodically resets history to stay adaptive during long runs.
    """
    
    def __init__(self, history_size: int = 500):
        """
        Initialize cost predictor.
        
        Args:
            history_size: Maximum number of historical scrapes to track
        """
        self.history = deque(maxlen=history_size)
        self.depth_stats = {
            "shallow": deque(maxlen=200),
            "medium": deque(maxlen=200),
            "deep": deque(maxlen=100),
            # New intensity profiles
            "aggressive": deque(maxlen=200),
            "balanced": deque(maxlen=200),
            "conservative": deque(maxlen=200)
        }
        self.total_predictions = 0
        self.total_error = 0.0
    
    def record(self, num_comments: int, depth_mode: str, actual_cost: int):
        """
        Record actual scrape cost for calibration.
        
        Args:
            num_comments: Actual comment count
            depth_mode: Depth mode used
            actual_cost: Actual API requests consumed
        """
        record = {
            "comments": num_comments,
            "depth": depth_mode,
            "cost": actual_cost,
            "timestamp": time.time()
        }
        
        self.history.append(record)
        # Handle unknown depth modes gracefully
        if depth_mode in self.depth_stats:
            self.depth_stats[depth_mode].append((num_comments, actual_cost))
        
        # Refinement #3: Clear history when full to prevent staleness
        if len(self.history) == self.history.maxlen:
            # Keep 50% of most recent data
            keep = self.history.maxlen // 2
            self.history = deque(list(self.history)[-keep:], maxlen=self.history.maxlen)
    
    def predict(self, num_comments: int, depth_mode: str) -> int:
        """
        Predict cost using historical data or heuristic fallback.
        
        Uses 75th percentile of similar scrapes for conservative estimates.
        
        Args:
            num_comments: Estimated comment count
            depth_mode: Depth mode to use
        
        Returns:
            Estimated API requests needed
        """
        # Fall back to heuristic if insufficient data
        if len(self.depth_stats[depth_mode]) < 10:
            return estimate_scrape_cost_heuristic(num_comments, depth_mode)
        
        # Find similar scrapes (±20% comment count)
        similar = [
            cost for comments, cost in self.depth_stats[depth_mode]
            if abs(comments - num_comments) / max(1, num_comments) < 0.2
        ]
        
        if similar:
            # Use 75th percentile for conservative estimate
            sorted_similar = sorted(similar)
            idx = int(len(sorted_similar) * 0.75)
            return sorted_similar[idx]
        
        # Fall back to heuristic
        return estimate_scrape_cost_heuristic(num_comments, depth_mode)
    
    def record_prediction_error(self, estimated: int, actual: int):
        """
        Track prediction accuracy for calibration analysis.
        
        Refinement #9: Uses absolute error for unbiased statistics.
        
        Args:
            estimated: Predicted cost
            actual: Actual cost
        """
        if actual > 0:
            error = abs(actual - estimated) / actual
            self.total_error += error
            self.total_predictions += 1
    
    def get_average_error(self) -> float:
        """
        Get average prediction error as percentage.
        
        Returns:
            Average error (0.0 to 1.0, where 0.3 = 30% error)
        """
        if self.total_predictions == 0:
            return 0.0
        return self.total_error / self.total_predictions
    
    def get_stats(self) -> Dict[str, any]:
        """
        Get predictor statistics for debugging.
        
        Returns:
            Dictionary with predictor stats
        """
        return {
            "total_predictions": self.total_predictions,
            "average_error_pct": self.get_average_error() * 100,
            "history_size": len(self.history),
            "shallow_samples": len(self.depth_stats["shallow"]),
            "medium_samples": len(self.depth_stats["medium"]),
            "deep_samples": len(self.depth_stats["deep"])
        }

