"""Client-side rate limiting: a sliding per-minute window plus a persisted per-day counter.

Free-tier Gemini quotas are enforced per model as requests-per-minute (RPM) and requests-per-day
(RPD). The limiter never lets more than `rpm` calls start inside any 60-second window and never
lets the UTC-day counter (stored in the shared SQLite cache) exceed `rpd`.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from cadence.llm.base import QuotaExhausted
from cadence.llm.cache import LLMCache, utc_day
from cadence.utils.log import get_logger

log = get_logger(__name__)

WINDOW_SECONDS: float = 60.0


class RateLimiter:
    """Blocks callers so that a model's RPM and RPD limits are respected.

    `clock` and `sleeper` are injectable so that the blocking behaviour is unit-testable with a
    fake clock; `today` is injectable so that day rollover can be tested as well.
    """

    def __init__(
        self,
        rpm: int,
        rpd: int,
        cache: LLMCache,
        model: str,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        today: Callable[[], str] = utc_day,
    ) -> None:
        if rpm < 1 or rpd < 1:
            raise ValueError(f"rpm and rpd must be >= 1 (got rpm={rpm}, rpd={rpd})")
        self.rpm = int(rpm)
        self.rpd = int(rpd)
        self.cache = cache
        self.model = model
        self._clock = clock
        self._sleep = sleeper
        self._today = today
        self._lock = threading.Lock()
        self._window: deque[float] = deque()

    def _prune(self, now: float) -> None:
        """Drop timestamps that fell out of the 60-second window."""
        while self._window and now - self._window[0] >= WINDOW_SECONDS:
            self._window.popleft()

    def _wait_for_window(self) -> None:
        """Sleep until fewer than `rpm` requests were started in the last minute."""
        while True:
            now = self._clock()
            self._prune(now)
            if len(self._window) < self.rpm:
                return
            wait = WINDOW_SECONDS - (now - self._window[0])
            log.info("rate limit: %s at %d req/min, sleeping %.1fs", self.model, self.rpm, wait)
            self._sleep(max(wait, 0.0))

    def remaining_today(self) -> int:
        """Requests still allowed today for this model (never negative)."""
        return max(self.rpd - self.cache.quota_get(self.model, self._today()), 0)

    def acquire(self) -> int:
        """Block until a request may start, count it against today's quota, and return today's count.

        Raises `QuotaExhausted` (before sleeping) when the persisted daily counter has reached `rpd`.
        """
        with self._lock:
            day = self._today()
            used = self.cache.quota_get(self.model, day)
            if used >= self.rpd:
                raise QuotaExhausted(
                    f"daily quota exhausted for {self.model}: {used}/{self.rpd} requests on {day} (UTC). "
                    "Wait for the UTC day to roll over, lower the workload, or run with CADENCE_CACHE_ONLY=1."
                )
            self._wait_for_window()
            self._window.append(self._clock())
            return self.cache.quota_incr(self.model, day)


__all__ = ["RateLimiter", "WINDOW_SECONDS"]
