"""Shared test setup.

The data folder is pointed at a temporary directory before anything from
reddit_analyzer is imported, so tests never read or move the real cache,
skip list or Reddit login.
"""

import os
import tempfile

os.environ['REDDIT_ANALYZER_DATA_DIR'] = tempfile.mkdtemp(prefix='reddit-analyzer-tests-')

import pytest  # noqa: E402

from reddit_analyzer.api import accounts, reddit_oauth  # noqa: E402
from reddit_analyzer.core import cache  # noqa: E402


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
    yield
    cache.CACHE.clear()
