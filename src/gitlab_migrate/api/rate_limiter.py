"""Rate limiting implementation for GitLab API calls."""

import asyncio
import time
from typing import Optional, Type


class RateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, requests_per_second: float = 10.0):
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second allowed
        """
        self.requests_per_second = requests_per_second
        self.tokens = requests_per_second
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token for making a request (async version).

        Blocks until a token is available.
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update

            # Add tokens based on elapsed time
            self.tokens = min(
                self.requests_per_second,
                self.tokens + elapsed * self.requests_per_second,
            )
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return
            else:
                # Calculate sleep time needed
                sleep_time = (1 - self.tokens) / self.requests_per_second
                await asyncio.sleep(sleep_time)
                self.tokens = 0

    def acquire_sync(self) -> None:
        """Acquire a token for making a request (synchronous version).

        Blocks until a token is available.
        """
        now = time.time()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        self.tokens = min(
            self.requests_per_second, self.tokens + elapsed * self.requests_per_second
        )
        self.last_update = now

        if self.tokens >= 1:
            self.tokens -= 1
            return
        else:
            # Calculate sleep time needed
            sleep_time = (1 - self.tokens) / self.requests_per_second
            time.sleep(sleep_time)
            self.tokens = 0

    def can_proceed(self) -> bool:
        """Check if a request can proceed without blocking.

        Returns:
            True if a token is available, False otherwise
        """
        now = time.time()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        tokens = min(
            self.requests_per_second, self.tokens + elapsed * self.requests_per_second
        )

        return tokens >= 1

    def time_until_next_request(self) -> float:
        """Get time until next request can be made.

        Returns:
            Seconds until next request is allowed
        """
        if self.can_proceed():
            return 0.0

        return (1 - self.tokens) / self.requests_per_second


class CircuitBreaker:
    """Circuit breaker pattern for handling API failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before trying again
            expected_exception: Exception type that triggers circuit breaker
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED

    async def call(self, func, *args, **kwargs):
        """Call function with circuit breaker protection.

        Args:
            func: Function to call
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If function fails
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                time_remaining = self.timeout - (
                    time.time() - (self.last_failure_time or 0)
                )
                raise CircuitBreakerOpenError(
                    f'Circuit breaker is open. Try again in '
                    f'{time_remaining:.1f} seconds'
                )

        try:
            result = (
                await func(*args, **kwargs)
                if asyncio.iscoroutinefunction(func)
                else func(*args, **kwargs)
            )
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt to reset."""
        return (
            self.last_failure_time is not None
            and time.time() - self.last_failure_time >= self.timeout
        )

    def _on_success(self) -> None:
        """Handle successful function call."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        """Handle failed function call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN


class CircuitState:
    """Circuit breaker states."""

    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""

    pass
