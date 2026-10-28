"""Shared test setup.

The data folder is pointed at a temporary directory before anything from
reddit_analyzer is imported, so tests never read or move the real cache,
skip list or Reddit login.
"""

import os
import tempfile

os.environ['REDDIT_ANALYZER_DATA_DIR'] = tempfile.mkdtemp(prefix='reddit-analyzer-tests-')

import pytest  # noqa: E402

from reddit_analyzer.api import accounts, arctic_shift, reddit_oauth  # noqa: E402
from reddit_analyzer.core import cache  # noqa: E402
from reddit_analyzer.core.rate_limit import RateLimiter  # noqa: E402


class FakeClock:
    """A clock whose sleep() advances time instantly, for rate-limit tests."""

    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class FakeResponse:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self.ok = status < 400
        self.headers = headers or {}
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError('no JSON body')
        return self._payload


@pytest.fixture(autouse=True)
def clean_state():
    """Reset module-level state so tests don't leak into each other."""
    cache.CACHE.clear()
    reddit_oauth.set_credentials({'client_id': '', 'client_secret': '', 'username': ''})
    reddit_oauth._rate_remaining = None
    reddit_oauth._rate_reset_at = 0.0
    accounts._public_api_blocked_until = 0.0
    arctic_shift._failure_streak = 0
    arctic_shift._outage_until = 0.0
    yield
    cache.CACHE.clear()


@pytest.fixture
def fake_clock(monkeypatch):
    """Arctic Shift limiter and outage timer on a fake clock, so waits take no real time."""
    clock = FakeClock()
    monkeypatch.setattr(arctic_shift, 'LIMITER', RateLimiter(
        arctic_shift.ARCTIC_SHIFT_MAX_RPS, arctic_shift.ARCTIC_SHIFT_MAX_CONCURRENT,
        clock=clock, sleep=clock.sleep))
    monkeypatch.setattr(arctic_shift, '_clock', clock)
    return clock
