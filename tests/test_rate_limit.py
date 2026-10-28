import threading
import time

from conftest import FakeClock
from reddit_analyzer.core.rate_limit import RateLimiter


def start_times(limiter, clock, n):
    starts = []
    for _ in range(n):
        with limiter.request():
            starts.append(clock())
    return starts


def test_requests_are_evenly_spaced():
    clock = FakeClock()
    limiter = RateLimiter(2.0, 2, clock=clock, sleep=clock.sleep)
    starts = start_times(limiter, clock, 5)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert gaps == [0.5, 0.5, 0.5, 0.5]


def test_pause_holds_back_the_next_request():
    clock = FakeClock()
    limiter = RateLimiter(10.0, 2, clock=clock, sleep=clock.sleep)
    with limiter.request():
        pass
    limiter.pause(30)
    assert limiter.paused_for() == 30
    started = clock()
    with limiter.request():
        assert clock() - started >= 30
    assert limiter.paused_for() == 0


def test_pause_never_shortens_a_longer_one():
    clock = FakeClock()
    limiter = RateLimiter(10.0, 2, clock=clock, sleep=clock.sleep)
    limiter.pause(60)
    limiter.pause(5)
    assert limiter.paused_for() == 60


def test_concurrency_is_capped_across_threads():
    limiter = RateLimiter(1000.0, 2)          # real clock; pacing is negligible at this rate
    in_flight, peak, lock = [0], [0], threading.Lock()

    def worker():
        with limiter.request():
            with lock:
                in_flight[0] += 1
                peak[0] = max(peak[0], in_flight[0])
            time.sleep(0.05)
            with lock:
                in_flight[0] -= 1

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 2
