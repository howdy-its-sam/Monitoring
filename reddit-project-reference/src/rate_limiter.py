#!/usr/bin/env python3
"""
Adaptive token-bucket rate limiter for Reddit API compliance.

Self-adjusts based on Reddit's X-RateLimit-* response headers to handle:
- OAuth authentication status changes (100 req/min → 10 req/min)
- Reddit API limit changes (future-proof)
- Conservative initial limits that adjust to actual capacity
"""
import time
from collections import deque
from typing import Optional, Dict


class RateLimiter:
    """
    Adaptive token-bucket rate limiter that learns Reddit's actual limits.

    Reddit's rate limits vary by authentication:
    - OAuth authenticated: ~100 requests per minute (as of 2024-2025)
    - Unauthenticated: ~10 requests per minute

    This limiter auto-discovers the actual limit from API response headers,
    providing graceful degradation if OAuth stops working and automatic
    scaling if Reddit increases limits.

    Starting assumption: 90 req/10min (conservative, corrected from headers)
    """

    def __init__(self, max_requests: int = 90, window_seconds: float = 600):
        """
        Initialize adaptive rate limiter.

        Args:
            max_requests: Initial max requests (default: 90, will auto-adjust from headers)
            window_seconds: Rolling window in seconds (default: 600 = 10 min)
        """
        self.max_requests = max_requests  # Dynamic, updated from headers
        self.window_seconds = window_seconds
        self.timestamps = deque()

        # Track header observations for confidence
        self.observed_limits = []
        self.header_update_count = 0

        # Track last request time for adaptive interval pacing
        self.last_request_time = 0

        # Track token waste (tokens that expired unused when Reddit's window reset)
        self.last_remaining = None
        self.last_used = None
        self.total_wasted_tokens = 0
        self.window_reset_count = 0
    
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

    def get_adaptive_interval(self) -> float:
        """
        Calculate adaptive interval based on current buffer size.

        Creates a self-dampening feedback loop:
        - High buffer → fast consumption → buffer shrinks
        - Low buffer → slow consumption → matches refill rate

        This prevents token expiration waste while maintaining dynamic scaling.

        Returns:
            Minimum seconds to wait between requests
        """
        available = self.available_budget()
        base_interval = self.window_seconds / self.max_requests  # ~6s for 100/10min

        # Scale interval inversely with buffer size
        # High buffer = short interval (fast consumption)
        # Low buffer = long interval (slow consumption, match refill)
        if available >= 50:
            return 0.5  # Very fast: 2 req/sec when buffer is high
        elif available >= 25:
            return 2.0  # Fast: 0.5 req/sec
        elif available >= 10:
            return 4.0  # Medium: 0.25 req/sec
        else:
            return base_interval  # Slow: match refill rate (~0.16 req/sec)

    def update_from_headers(self, response_headers: Dict[str, str]) -> None:
        """
        Update rate limit from Reddit's response headers.

        Call this after EVERY API request to allow the limiter to learn
        Reddit's actual rate limit and adapt to changes.

        Reddit provides these headers:
        - X-RateLimit-Used: Requests used in current window
        - X-RateLimit-Remaining: Requests remaining in current window
        - X-RateLimit-Reset: Unix timestamp when limit resets

        Args:
            response_headers: Dictionary of HTTP response headers
        """
        try:
            # Read Reddit's actual limit from headers
            remaining = response_headers.get('X-RateLimit-Remaining')
            used = response_headers.get('X-RateLimit-Used')

            if remaining is None or used is None:
                return  # Headers not present (e.g., error response)

            remaining = int(float(remaining))  # Reddit returns "997.0" format
            used = int(float(used))

            if remaining < 0 or used < 0:
                return  # Invalid values

            # Detect window reset: used drops significantly (new window started)
            # When Reddit's window resets, 'used' goes back to low values
            if self.last_used is not None and used < self.last_used - 5:
                # Window reset detected - last_remaining tokens were wasted
                wasted = self.last_remaining
                self.total_wasted_tokens += wasted
                self.window_reset_count += 1

                # Calculate waste percentage for this window
                limit = self.max_requests
                used_in_window = limit - wasted
                waste_pct = (wasted / limit) * 100 if limit > 0 else 0

                if wasted > 0:
                    print(f"⚠️  TOKEN WASTE: {wasted} tokens expired unused "
                          f"({waste_pct:.1f}% of window capacity)")
                    print(f"    Window #{self.window_reset_count}: used {used_in_window}/{limit}, "
                          f"cumulative waste: {self.total_wasted_tokens}")

            # Update tracking for next comparison
            self.last_remaining = remaining
            self.last_used = used

            # Calculate Reddit's actual limit
            observed_limit = remaining + used
            self.observed_limits.append(observed_limit)
            self.header_update_count += 1

            # Keep last 10 observations for rolling median
            if len(self.observed_limits) > 10:
                self.observed_limits.pop(0)

            # Update max_requests with median of observations (robust to outliers)
            # Require at least 3 observations before adjusting
            if len(self.observed_limits) >= 3:
                new_limit = sorted(self.observed_limits)[len(self.observed_limits) // 2]

                if new_limit != self.max_requests:
                    old_limit = self.max_requests
                    self.max_requests = new_limit

                    # Convert to per-minute for readability
                    old_rpm = old_limit / (self.window_seconds / 60)
                    new_rpm = new_limit / (self.window_seconds / 60)

                    print(f"📊 Rate limit adjusted: {old_rpm:.0f} → {new_rpm:.0f} req/min "
                          f"({old_limit} → {new_limit} per {self.window_seconds/60:.0f}min)")

                    # Detect significant changes that indicate OAuth status
                    if old_limit > 50 and new_limit < 20:
                        print("⚠️  ALERT: Rate limit dropped significantly!")
                        print("    OAuth authentication may have stopped working.")
                        print("    Limit fell to unauthenticated level (~10 req/min).")

                    elif old_limit < 20 and new_limit > 50:
                        print("✅ Rate limit increased significantly!")
                        print("    OAuth authentication detected or restored.")
                        print(f"    Now operating at ~{new_rpm:.0f} req/min.")

        except (ValueError, KeyError, TypeError) as e:
            # Headers missing, malformed, or wrong type - silently skip
            pass

    def get_status(self) -> Dict:
        """
        Get rate limiter status for monitoring and debugging.

        Returns:
            Dictionary with current state metrics
        """
        return {
            'max_requests': self.max_requests,
            'window_seconds': self.window_seconds,
            'available_budget': self.available_budget(),
            'utilization_pct': ((self.max_requests - self.available_budget()) / self.max_requests * 100) if self.max_requests > 0 else 0,
            'refill_rate_per_sec': self.refill_rate(),
            'observed_limits': self.observed_limits.copy(),
            'header_updates': self.header_update_count,
            # Token waste tracking
            'total_wasted_tokens': self.total_wasted_tokens,
            'window_reset_count': self.window_reset_count,
            'waste_rate_pct': (self.total_wasted_tokens / (self.window_reset_count * self.max_requests) * 100) if self.window_reset_count > 0 else 0
        }

    # === CENTRALIZED REQUEST SCHEDULING ===

    def wait_for_budget(self, num_requests: int = 1) -> float:
        """
        Block until sufficient budget is available for N requests.

        This is the core method for paced request execution. It:
        1. Waits for budget to be available
        2. Applies adaptive interval pacing based on buffer size

        The adaptive interval creates a self-dampening feedback loop:
        - High buffer → fast consumption → buffer drops → slows down
        - Low buffer → slow consumption → matches refill rate

        Args:
            num_requests: Number of requests to wait for budget

        Returns:
            Actual time waited in seconds (0.0 if no wait needed)
        """
        start_time = time.time()

        # First, wait for budget to be available
        while not self.would_allow(num_requests):
            # Calculate time until enough budget is available
            wait_time = self._time_until_budget(num_requests)

            if wait_time > 0:
                time.sleep(min(wait_time, 1.0))  # Sleep max 1s at a time for responsiveness

        # Then, apply adaptive interval pacing based on current buffer
        interval = self.get_adaptive_interval()
        time_since_last = time.time() - self.last_request_time

        if time_since_last < interval:
            time.sleep(interval - time_since_last)

        # Update last request time
        self.last_request_time = time.time()

        return time.time() - start_time

    def _time_until_budget(self, num_requests: int) -> float:
        """
        Calculate seconds until N requests worth of budget will be available.

        Args:
            num_requests: Number of requests needed

        Returns:
            Seconds until sufficient budget available
        """
        now = time.time()

        # Clean expired timestamps
        active_timestamps = [ts for ts in self.timestamps if ts >= now - self.window_seconds]

        current_used = len(active_timestamps)
        available = self.max_requests - current_used

        if available >= num_requests:
            return 0.0  # Budget available now

        # Need to wait for oldest timestamps to expire
        needed_to_expire = num_requests - available

        if needed_to_expire > len(active_timestamps):
            # Need more budget than exists in window - wait for full refill
            return self.window_seconds

        # Find the Nth oldest timestamp that needs to expire
        sorted_timestamps = sorted(active_timestamps)
        target_timestamp = sorted_timestamps[needed_to_expire - 1]

        # Time until that timestamp expires
        expires_at = target_timestamp + self.window_seconds
        wait_time = expires_at - now

        return max(0.0, wait_time)

    def next_slot_time(self, num_requests: int = 1) -> float:
        """
        Calculate when N requests can execute (without blocking).

        Use this to schedule work without blocking the current thread.
        Returns absolute timestamp (from time.time()) when execution can proceed.

        Args:
            num_requests: Number of requests to schedule

        Returns:
            Unix timestamp when execution can begin
        """
        wait_time = self._time_until_budget(num_requests)
        return time.time() + wait_time

    def execute_when_ready(self, request_fn, num_requests: int = 1):
        """
        Execute a function when sufficient budget is available.

        This is the high-level API for paced request execution. It:
        1. Waits for budget to be available
        2. Executes the function
        3. Consumes the budget
        4. Returns the result

        Args:
            request_fn: Callable to execute (should make API request)
            num_requests: Number of requests this call will consume

        Returns:
            Result of request_fn()

        Example:
            result = limiter.execute_when_ready(
                lambda: reddit.get_post(post_id),
                num_requests=1
            )
        """
        # Wait for budget
        wait_time = self.wait_for_budget(num_requests)

        if wait_time > 0.1:  # Log significant waits
            print(f"⏸️  Waited {wait_time:.1f}s for budget (need {num_requests} req)")

        # Execute request
        try:
            result = request_fn()

            # Consume budget
            self.consume(num_requests)

            return result

        except Exception as e:
            # Still consume budget on errors (API call was made)
            self.consume(num_requests)
            raise

