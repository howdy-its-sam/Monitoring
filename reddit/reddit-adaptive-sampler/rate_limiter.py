#!/usr/bin/env python3
"""
Token-bucket rate limiter for Reddit API compliance.
"""
import time
from collections import deque
from typing import Optional


class RateLimiter:
    """
    Token-bucket rate limiter.
    
    Ensures we don't exceed Reddit's rate limits (600 requests per 10 minutes).
    Uses conservative limit of 540 req/10min for safety margin.
    """
    
    def __init__(self, max_requests: int = 540, window_seconds: float = 600):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum requests allowed in window (default: 540 for safety)
            window_seconds: Rolling window in seconds (default: 600 = 10 min)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.timestamps = deque()
    
    def allow(self) -> bool:
        """
        DEPRECATED: Use consume() instead for accurate request tracking.
        
        This method exists for backwards compatibility but should not be used
        for production code as it doesn't track actual API request counts.
        
        Returns:
            True if request can proceed, False if limit exceeded
        """
        now = time.time()
        
        # Remove timestamps outside window
        while self.timestamps and self.timestamps[0] < now - self.window_seconds:
            self.timestamps.popleft()
        
        # Check if under limit
        if len(self.timestamps) < self.max_requests:
            return True
        
        return False
    
    def consume(self, num_requests: int) -> bool:
        """
        Consume N API request tokens from the rate limiter budget.
        
        This is the primary method for tracking actual Reddit API usage.
        Call this AFTER scraping with the actual number of requests used.
        
        Args:
            num_requests: Number of API requests to consume from budget
            
        Returns:
            True if requests were successfully consumed, False if would exceed limit
        """
        now = time.time()
        
        # Remove timestamps outside window
        while self.timestamps and self.timestamps[0] < now - self.window_seconds:
            self.timestamps.popleft()
        
        # Check if we have budget for N requests
        if len(self.timestamps) + num_requests <= self.max_requests:
            # Add N timestamps (representing N API requests)
            for _ in range(num_requests):
                self.timestamps.append(now)
            return True
        
        return False
    
    def would_allow(self, num_requests: int) -> bool:
        """
        Check if N requests WOULD be allowed without consuming tokens.
        
        Use this to preview if a scrape can proceed before starting it.
        
        Args:
            num_requests: Number of requests to check
            
        Returns:
            True if N requests would be allowed, False if would exceed limit
        """
        now = time.time()
        
        # Remove timestamps outside window (non-destructive - doesn't modify deque)
        temp_count = 0
        for ts in self.timestamps:
            if ts >= now - self.window_seconds:
                temp_count += 1
        
        return temp_count + num_requests <= self.max_requests
    
    def wait_time(self) -> float:
        """
        Calculate seconds to wait before next request allowed.
        
        Returns:
            Seconds until capacity available (0.0 if immediate capacity)
        """
        if len(self.timestamps) < self.max_requests:
            return 0.0
        
        now = time.time()
        oldest = self.timestamps[0]
        wait = self.window_seconds - (now - oldest)
        return max(0.0, wait)
    
    def available_budget(self) -> int:
        """
        Get current available request budget.
        
        Returns:
            Number of requests available before hitting limit
        """
        now = time.time()
        
        # Clean old timestamps
        while self.timestamps and self.timestamps[0] < now - self.window_seconds:
            self.timestamps.popleft()
        
        return max(0, self.max_requests - len(self.timestamps))
    
    def refill_rate(self) -> float:
        """
        Get refill rate for analytics.
        
        Returns:
            Requests per second refill rate
        """
        return self.max_requests / self.window_seconds

