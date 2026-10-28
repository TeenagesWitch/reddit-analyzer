"""Thread-safe request pacing shared by every worker thread that calls one service."""

import time
import threading
from contextlib import contextmanager


class RateLimiter:
    """Spaces out request starts, caps requests in flight, and supports a shared pause.

    - At most `rate` requests start per second, evenly spaced (no bursts).
    - At most `max_concurrent` requests run at once.
    - pause(seconds) holds back every caller, e.g. after the server says to wait.

    clock and sleep are injectable for tests.
    """

    def __init__(self, rate, max_concurrent, clock=time.monotonic, sleep=time.sleep):
        self._interval = 1.0 / rate
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._next_start = 0.0
        self._paused_until = 0.0

    @contextmanager
    def request(self):
        """Wait for a turn, then hold a concurrency slot for the duration of the block."""
        self._slots.acquire()
        try:
            self._wait_turn()
            yield
        finally:
            self._slots.release()

    def _wait_turn(self):
        while True:
            with self._lock:
                now = self._clock()
                start = max(now, self._next_start, self._paused_until)
                if start <= now:
                    self._next_start = now + self._interval
                    return
                wait = start - now
            # Sleep in short steps so a pause added meanwhile is noticed
            self._sleep(min(wait, 1.0))

    def pause(self, seconds):
        """Hold back all requests for at least `seconds` from now."""
        with self._lock:
            self._paused_until = max(self._paused_until, self._clock() + seconds)

    def paused_for(self):
        """Seconds left in the current pause (0 if none)."""
        with self._lock:
            return max(0.0, self._paused_until - self._clock())
