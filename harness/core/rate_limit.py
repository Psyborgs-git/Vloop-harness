"""
Rate limiting module for API endpoints.

Implements token bucket and sliding window rate limiting algorithms.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""
    
    capacity: int
    refill_rate: float  # tokens per second
    tokens: float = field(default_factory=lambda: 1.0)
    last_refill: float = field(default_factory=time.time)
    
    def consume(self, tokens: int = 1) -> bool:
        """Consume tokens if available."""
        now = time.time()
        elapsed = now - self.last_refill
        
        # Refill tokens
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def reset(self) -> None:
        """Reset the bucket."""
        self.tokens = float(self.capacity)
        self.last_refill = time.time()


@dataclass
class SlidingWindow:
    """Sliding window rate limiter."""
    
    window_size: float  # in seconds
    max_requests: int
    requests: deque = field(default_factory=deque)
    
    def allow_request(self) -> bool:
        """Check if request is allowed."""
        now = time.time()
        
        # Remove old requests outside the window
        while self.requests and self.requests[0] < now - self.window_size:
            self.requests.popleft()
        
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False
    
    def reset(self) -> None:
        """Reset the window."""
        self.requests.clear()


class RateLimiter:
    """Rate limiter using token bucket and sliding window."""
    
    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        
        # Per-client rate limiters
        self._minute_buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                capacity=self.config.requests_per_minute,
                refill_rate=self.config.requests_per_minute / 60.0,
            )
        )
        self._hour_windows: dict[str, SlidingWindow] = defaultdict(
            lambda: SlidingWindow(
                window_size=3600,
                max_requests=self.config.requests_per_hour,
            )
        )
        self._day_windows: dict[str, SlidingWindow] = defaultdict(
            lambda: SlidingWindow(
                window_size=86400,
                max_requests=self.config.requests_per_day,
            )
        )
    
    def is_allowed(self, client_id: str) -> tuple[bool, str | None]:
        """Check if a request from a client is allowed."""
        # Check minute limit (token bucket)
        minute_bucket = self._minute_buckets[client_id]
        if not minute_bucket.consume():
            return False, "Rate limit exceeded: too many requests per minute"
        
        # Check hour limit (sliding window)
        hour_window = self._hour_windows[client_id]
        if not hour_window.allow_request():
            return False, "Rate limit exceeded: too many requests per hour"
        
        # Check day limit (sliding window)
        day_window = self._day_windows[client_id]
        if not day_window.allow_request():
            return False, "Rate limit exceeded: too many requests per day"
        
        return True, None
    
    def get_remaining(self, client_id: str) -> dict[str, int]:
        """Get remaining requests for each limit."""
        minute_bucket = self._minute_buckets[client_id]
        hour_window = self._hour_windows[client_id]
        day_window = self._day_windows[client_id]
        
        return {
            "minute_remaining": int(minute_bucket.tokens),
            "minute_limit": self.config.requests_per_minute,
            "hour_remaining": self.config.requests_per_hour - len(hour_window.requests),
            "hour_limit": self.config.requests_per_hour,
            "day_remaining": self.config.requests_per_day - len(day_window.requests),
            "day_limit": self.config.requests_per_day,
        }
    
    def reset_client(self, client_id: str) -> None:
        """Reset rate limits for a client."""
        if client_id in self._minute_buckets:
            self._minute_buckets[client_id].reset()
        if client_id in self._hour_windows:
            self._hour_windows[client_id].reset()
        if client_id in self._day_windows:
            self._day_windows[client_id].reset()
    
    def cleanup_old_clients(self, max_age_seconds: int = 3600) -> int:
        """Remove clients that haven't made requests recently."""
        now = time.time()
        removed = 0
        
        clients_to_remove = []
        for client_id, bucket in self._minute_buckets.items():
            if now - bucket.last_refill > max_age_seconds:
                clients_to_remove.append(client_id)
        
        for client_id in clients_to_remove:
            del self._minute_buckets[client_id]
            if client_id in self._hour_windows:
                del self._hour_windows[client_id]
            if client_id in self._day_windows:
                del self._day_windows[client_id]
            removed += 1
        
        return removed


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter(config: RateLimitConfig | None = None) -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(config)
    return _rate_limiter
