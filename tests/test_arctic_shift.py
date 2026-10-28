import datetime

import pytest
import requests

from conftest import FakeResponse
from reddit_analyzer.api import arctic_shift

USER_ROW = {'data': [{'author': 'spez', 'id': '1w72', '_meta': {
    'earliest_post_at': 1119552314, 'earliest_comment_at': 1134392748,
    'last_post_at': 1751475161, 'last_comment_at': 1729645028}}]}


class FakeSession:
    """Replays a scripted list of responses (or exceptions) for Arctic Shift GETs."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, params=None, timeout=None):
        self.requests.append((url, params))
        item = self.responses.pop(0) if self.responses else FakeResponse(200, {'data': []})
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def session(monkeypatch):
    def install(*responses):
        fake = FakeSession(*responses)
        monkeypatch.setattr(arctic_shift, 'SESSION', fake)
        return fake
    return install


def test_user_index_parses_dates_and_id(session, fake_clock):
    session(FakeResponse(200, USER_ROW))
    assert arctic_shift.fetch_user_index('SPEZ') == (
        '1w72', datetime.date(2005, 6, 23), datetime.date(2025, 7, 2))


def test_requests_are_paced_at_the_configured_rate(session, fake_clock):
    fake = session()
    started = fake_clock()
    for name in ('a1', 'a2', 'a3', 'a4', 'a5'):
        arctic_shift.fetch_user_index(name)
    assert len(fake.requests) == 5
    assert fake_clock() - started == pytest.approx(4 / arctic_shift.ARCTIC_SHIFT_MAX_RPS)


def test_429_waits_for_the_reset_header_then_retries(session, fake_clock):
    fake = session(FakeResponse(429, {'error': 'rate limited'}, {'x-ratelimit-reset': '42'}),
                   FakeResponse(200, USER_ROW))
    started = fake_clock()
    assert arctic_shift.fetch_user_index('spez')[0] == '1w72'
    assert len(fake.requests) == 2
    assert fake_clock() - started >= 42


def test_429_with_only_reset_at_header(session, fake_clock, monkeypatch):
    monkeypatch.setattr(arctic_shift.time, 'time', lambda: 1_000_000.0)
    resp = FakeResponse(429, {}, {'x-ratelimit-reset-at': str(int((1_000_000 + 17) * 1000))})
    assert arctic_shift._rate_limit_wait(resp) == pytest.approx(17)


def test_server_errors_back_off_and_retry(session, fake_clock):
    fake = session(FakeResponse(500, {}), requests.ConnectionError('reset'), FakeResponse(200, USER_ROW))
    started = fake_clock()
    assert arctic_shift.fetch_user_index('spez')[0] == '1w72'
    assert len(fake.requests) == 3
    assert fake_clock() - started >= 2 + 4          # exponential backoff between attempts
    assert arctic_shift._failure_streak == 0        # reset by the success


def test_gives_up_after_max_retries(session, fake_clock):
    fake = session(*[FakeResponse(503, {})] * 10)
    assert arctic_shift.fetch_user_index('spez') == (None, None, None)
    assert len(fake.requests) == arctic_shift.ARCTIC_SHIFT_MAX_RETRIES + 1


def test_repeated_failures_pause_all_requests(session, fake_clock):
    fake = session(*[FakeResponse(500, {})] * 20)
    for name in ('a1', 'a2', 'a3'):
        arctic_shift.fetch_user_index(name)
    sent = len(fake.requests)
    assert sent == arctic_shift.ARCTIC_SHIFT_OUTAGE_FAILURES
    assert not arctic_shift.is_available()
    # While paused, lookups return at once without sending anything
    assert arctic_shift.fetch_user_index('a4') == (None, None, None)
    assert arctic_shift.fetch_first_activity('a4') is None
    assert len(fake.requests) == sent
    # After the pause, requests resume
    fake_clock.now += arctic_shift.ARCTIC_SHIFT_OUTAGE_PAUSE
    fake.responses = [FakeResponse(200, USER_ROW)]
    assert arctic_shift.is_available()
    assert arctic_shift.fetch_user_index('spez')[0] == '1w72'


def test_request_waiting_for_its_turn_is_dropped_if_a_pause_starts(session, fake_clock, monkeypatch):
    from contextlib import contextmanager
    fake = session(FakeResponse(200, USER_ROW))

    @contextmanager
    def turn_arrives_after_outage_began():
        # Another thread tripped the outage pause while this one was waiting
        arctic_shift._outage_until = fake_clock() + 60
        yield
    monkeypatch.setattr(arctic_shift.LIMITER, 'request', turn_arrives_after_outage_began)
    assert arctic_shift.fetch_user_index('spez') == (None, None, None)
    assert fake.requests == []


def test_client_errors_are_not_retried(session, fake_clock):
    fake = session(FakeResponse(400, {'error': "'author' must be 2-30 characters long"}))
    assert arctic_shift.fetch_user_index('x') == (None, None, None)
    assert len(fake.requests) == 1 and arctic_shift._failure_streak == 0


def test_first_activity_uses_earliest_of_posts_and_comments(session, fake_clock):
    session(FakeResponse(200, {'data': [{'created_utc': 1420077600}]}),
            FakeResponse(200, {'data': [{'created_utc': 1388534400}]}))
    assert arctic_shift.fetch_first_activity('someone') == datetime.date(2014, 1, 1)
