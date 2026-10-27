import time

import pytest

from conftest import FakeResponse
from reddit_analyzer.api import reddit_oauth


class FakeReddit:
    """Stands in for reddit_oauth._session: a token endpoint and /user/<name>/about."""

    def __init__(self):
        self.token_requests = []
        self.about_requests = []
        self.expire_next = False
        self.remaining = 100.0

    def post(self, url, auth=None, data=None, headers=None, timeout=None):
        self.token_requests.append((auth[0], data['grant_type']))
        if auth[0] == 'bad':
            return FakeResponse(401, {'error': 'invalid_grant'})
        return FakeResponse(200, {'access_token': f'tok{len(self.token_requests)}', 'expires_in': 86400})

    def get(self, url, params=None, headers=None, timeout=None):
        name = url.rsplit('/user/', 1)[1].split('/')[0]
        self.about_requests.append((name, headers['Authorization'], headers['User-Agent']))
        if self.expire_next:
            self.expire_next = False
            return FakeResponse(401, {'error': 401})
        self.remaining -= 1
        limits = {'x-ratelimit-remaining': str(self.remaining), 'x-ratelimit-reset': '1'}
        if name == 'alive':
            return FakeResponse(200, {'data': {'created_utc': 1420077600}}, limits)
        return FakeResponse(404, {'error': 404}, limits)


@pytest.fixture
def reddit(monkeypatch):
    fake = FakeReddit()
    monkeypatch.setattr(reddit_oauth, '_session', fake)
    reddit_oauth.set_credentials({'client_id': 'good', 'client_secret': 's3cret', 'username': 'tester'})
    return fake


def test_token_is_reused_and_user_agent_names_the_user(reddit):
    assert reddit_oauth.fetch_user_about('alive') == ({'created_utc': 1420077600}, 200)
    assert reddit_oauth.fetch_user_about('gone') == (None, 404)
    assert len(reddit.token_requests) == 1
    assert reddit.about_requests[-1][2].endswith(':reddit-analyzer:1.0 (by /u/tester)')


def test_expired_token_is_refreshed_once(reddit):
    reddit.expire_next = True
    assert reddit_oauth.fetch_user_about('alive')[1] == 200
    assert len(reddit.token_requests) == 2


def test_installed_app_without_secret_uses_installed_client_grant(reddit):
    reddit_oauth.set_credentials({'client_id': 'good', 'client_secret': '', 'username': ''})
    reddit_oauth.fetch_user_about('alive')
    assert reddit.token_requests[-1][1] == 'https://oauth.reddit.com/grants/installed_client'


def test_rejected_credentials_are_not_retried_per_lookup(reddit):
    reddit_oauth.set_credentials({'client_id': 'bad', 'client_secret': 'x', 'username': ''})
    for _ in range(3):
        assert reddit_oauth.fetch_user_about('alive') == (None, None)
    assert len(reddit.token_requests) == 1
    ok, message = reddit_oauth.check_connection()
    assert not ok and 'invalid_grant' in message


def test_waits_for_rate_limit_reset_instead_of_sending(reddit):
    reddit.remaining = 1.0
    reddit_oauth.fetch_user_about('alive')          # leaves 0 requests, window resets in 1s
    started = time.time()
    reddit_oauth.fetch_user_about('alive')
    assert 0.5 < time.time() - started < 3


def test_check_connection_without_credentials():
    ok, message = reddit_oauth.check_connection()
    assert not ok and 'No client ID' in message


def test_save_credentials_writes_file_and_applies_them(tmp_path, reddit):
    path = tmp_path / 'creds.json'
    reddit_oauth.save_credentials({'client_id': 'new', 'client_secret': '', 'username': 'me'}, str(path))
    assert reddit_oauth.load_credentials(str(path)) == {'client_id': 'new', 'client_secret': '', 'username': 'me'}
    assert reddit_oauth.has_credentials() and reddit_oauth.user_agent().endswith('(by /u/me)')
