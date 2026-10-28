"""Arctic Shift (photon-reddit) client: account ids and first/last activity dates.

Arctic Shift archives Reddit posts and comments, so it knows when an account
was first and last active even when Reddit itself won't answer.

It is a free service, so every request goes through one shared RateLimiter
(see the ARCTIC_SHIFT_* settings in config.py): a steady pace, a cap on
requests in flight, waiting out 429s as the X-RateLimit-Reset headers say,
backing off after server errors, and pausing entirely while it is struggling.
"""

import time
import threading

import requests
from reddit_analyzer.config import (SESSION, REQUEST_TIMEOUT, ARCTIC_SHIFT_URL, ARCTIC_SHIFT_MAX_RPS,
                                    ARCTIC_SHIFT_MAX_CONCURRENT, ARCTIC_SHIFT_MAX_RETRIES,
                                    ARCTIC_SHIFT_MAX_BACKOFF, ARCTIC_SHIFT_OUTAGE_FAILURES,
                                    ARCTIC_SHIFT_OUTAGE_PAUSE)
from reddit_analyzer.core.rate_limit import RateLimiter
from reddit_analyzer.core.timestamps import parse_timestamp_utc

LIMITER = RateLimiter(ARCTIC_SHIFT_MAX_RPS, ARCTIC_SHIFT_MAX_CONCURRENT)
# Longest wait honoured from a 429's reset headers
MAX_RATE_LIMIT_WAIT = 300

_state_lock = threading.Lock()
# Failed requests in a row (429, 5xx, network errors), across all threads
_failure_streak = 0
# Until this _clock() time, Arctic Shift is treated as down and no requests are sent
_outage_until = 0.0
# Monotonic clock for the outage pause (replaceable in tests)
_clock = time.monotonic


def _rate_limit_wait(resp):
    """Seconds a 429 response says to wait, from X-RateLimit-Reset or X-RateLimit-Reset-At."""
    try:
        return min(float(resp.headers['x-ratelimit-reset']), MAX_RATE_LIMIT_WAIT)
    except (KeyError, TypeError, ValueError):
        pass
    try:
        reset_at = float(resp.headers['x-ratelimit-reset-at']) / 1000  # milliseconds since the epoch
        return min(max(reset_at - time.time(), 1.0), MAX_RATE_LIMIT_WAIT)
    except (KeyError, TypeError, ValueError):
        return 60.0


def _record_success():
    global _failure_streak
    with _state_lock:
        _failure_streak = 0


def _record_failure(resp):
    """Pause every caller after a failed request; returns False once Arctic Shift counts as down."""
    global _failure_streak, _outage_until
    with _state_lock:
        _failure_streak += 1
        streak = _failure_streak
        if streak >= ARCTIC_SHIFT_OUTAGE_FAILURES:
            _outage_until = _clock() + ARCTIC_SHIFT_OUTAGE_PAUSE
            _failure_streak = 0
    if streak >= ARCTIC_SHIFT_OUTAGE_FAILURES:
        return False
    if resp is not None and resp.status_code == 429:
        LIMITER.pause(_rate_limit_wait(resp))
    else:
        # 2s, 4s, 8s, ... while errors keep coming
        LIMITER.pause(min(2 ** streak, ARCTIC_SHIFT_MAX_BACKOFF))
    return True


def is_available():
    """False while Arctic Shift is paused after repeated failures."""
    return _clock() >= _outage_until


def _get(path, params):
    """GET an Arctic Shift endpoint within the shared limits.

    Retries after 429s, server errors and network errors. Returns the
    response (which may still be an error), or None if no answer came back.
    """
    resp = None
    for attempt in range(ARCTIC_SHIFT_MAX_RETRIES + 1):
        if not is_available():
            return None
        with LIMITER.request():
            # The service may have been paused while this thread waited for its turn
            if not is_available():
                return None
            try:
                resp = SESSION.get(f'{ARCTIC_SHIFT_URL}{path}', params=params, timeout=REQUEST_TIMEOUT)
            except requests.RequestException:
                resp = None
        if resp is not None and resp.status_code != 429 and resp.status_code < 500:
            _record_success()
            return resp
        if not _record_failure(resp):
            return resp
    return resp


def fetch_user_index(author: str):
    """Return (account_id, first_seen, last_seen) from Arctic Shift's user index.

    One request covers both posts and comments. account_id is the base-36 id
    without 't2_'. Any value is None if unknown.
    """
    resp = _get('/api/users/search', {'author': author})
    try:
        if resp is None or not resp.ok:
            return None, None, None
        rows = resp.json().get('data') or []
    except (ValueError, AttributeError):
        return None, None, None
    for row in rows:
        if str(row.get('author', '')).lower() != author.lower():
            continue
        meta = row.get('_meta') or {}
        firsts = [parse_timestamp_utc(meta.get(k)) for k in ('earliest_post_at', 'earliest_comment_at')]
        lasts = [parse_timestamp_utc(meta.get(k)) for k in ('last_post_at', 'last_comment_at')]
        firsts = [dt.date() for dt in firsts if dt]
        lasts = [dt.date() for dt in lasts if dt]
        return row.get('id') or None, (min(firsts) if firsts else None), (max(lasts) if lasts else None)
    return None, None, None


def fetch_first_activity(author: str):
    """Return the earliest post or comment date from Arctic Shift search, or None.

    Fallback for users missing from the user index, which is only updated infrequently.
    """
    dates = []
    for kind in ('posts', 'comments'):
        resp = _get(f'/api/{kind}/search', {'author': author, 'sort': 'asc', 'limit': 1})
        try:
            if resp is None or not resp.ok:
                continue
            payload = resp.json()
            items = payload.get('data', payload) if isinstance(payload, dict) else payload
            if isinstance(items, list) and items:
                ts = items[0].get('created_utc') or items[0].get('created') or items[0].get('timestamp')
                dt = parse_timestamp_utc(ts)
                if dt:
                    dates.append(dt.date())
        except (ValueError, AttributeError):
            continue
    return min(dates) if dates else None
