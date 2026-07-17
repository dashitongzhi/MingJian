"""Bounded in-memory throttling for repeated authentication failures."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable


@dataclass(frozen=True)
class _AttemptWindow:
    failures: int
    expires_at: float


class LoginAttemptLimiter:
    """Limit password guessing without allowing arbitrary keys to exhaust memory."""

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: int = 300,
        max_entries: int = 10_000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_failures < 1 or window_seconds < 1 or max_entries < 1:
            raise ValueError("Login throttle limits must be positive")
        self._max_failures = max_failures
        self._window_seconds = window_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._attempts: OrderedDict[str, _AttemptWindow] = OrderedDict()
        self._lock = Lock()

    def retry_after(self, key: str) -> int | None:
        """Return seconds until the key may retry, or ``None`` when allowed."""
        now = self._clock()
        with self._lock:
            self._discard_expired(now)
            window = self._attempts.get(key)
            if window is None or window.failures < self._max_failures:
                return None
            self._attempts.move_to_end(key)
            return max(1, int(window.expires_at - now + 0.999))

    def record_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            self._discard_expired(now)
            current = self._attempts.get(key)
            if current is None:
                self._attempts[key] = _AttemptWindow(
                    failures=1,
                    expires_at=now + self._window_seconds,
                )
            else:
                self._attempts[key] = _AttemptWindow(
                    failures=current.failures + 1,
                    expires_at=current.expires_at,
                )
                self._attempts.move_to_end(key)
            while len(self._attempts) > self._max_entries:
                self._attempts.popitem(last=False)

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def _discard_expired(self, now: float) -> None:
        expired = [key for key, window in self._attempts.items() if window.expires_at <= now]
        for key in expired:
            self._attempts.pop(key, None)
