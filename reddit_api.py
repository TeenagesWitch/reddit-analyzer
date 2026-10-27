"""Reddit API functions for fetching account information."""

import time
import datetime

import requests
import reddit_auth
from config import SESSION, REQUEST_TIMEOUT, STATUS_CODES, ARCTIC_SHIFT_URL, PUBLIC_API_BACKOFF
from cache import CACHE, CACHE_LOCK, is_reusable_entry, store_entry
from timestamps import parse_timestamp_utc

# Until this time.time(), skip Reddit's public JSON: it refused a recent request
_public_api_blocked_until = 0.0


def _fetch_about_json(author: str):
    """Fetch user about.json from Reddit's public (anonymous) API."""
    try:
        resp = SESSION.get(f'https://www.reddit.com/user/{author}/about.json', timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json().get('data', {}), 200
        return None, resp.status_code
    except (requests.RequestException, ValueError):
        return None, None


def _fetch_reddit_about(author: str):
    """Return (data, http_status) from Reddit, through OAuth when credentials are set.

    Reddit refuses most anonymous requests, so after a 403/429 the public API
    is skipped for PUBLIC_API_BACKOFF seconds instead of being retried per user.
    """
    global _public_api_blocked_until
    if reddit_auth.has_credentials():
        return reddit_auth.fetch_user_about(author)
    if time.time() < _public_api_blocked_until:
        return None, None
    data, status = _fetch_about_json(author)
    if status in (403, 429):
        _public_api_blocked_until = time.time() + PUBLIC_API_BACKOFF
    return data, status


def _fetch_arctic_user(author: str):
    """Return (first_seen, last_seen) activity dates from Arctic Shift's user index.

    One request covers both posts and comments. Either date is None if unknown.
    """
    try:
        resp = SESSION.get(f'{ARCTIC_SHIFT_URL}/api/users/search', params={'author': author},
                           timeout=REQUEST_TIMEOUT)
        if not resp.ok:
            return None, None
        rows = resp.json().get('data') or []
    except (requests.RequestException, ValueError, AttributeError):
        return None, None
    for row in rows:
        if str(row.get('author', '')).lower() != author.lower():
            continue
        meta = row.get('_meta') or {}
        firsts = [parse_timestamp_utc(meta.get(k)) for k in ('earliest_post_at', 'earliest_comment_at')]
        lasts = [parse_timestamp_utc(meta.get(k)) for k in ('last_post_at', 'last_comment_at')]
        firsts = [dt.date() for dt in firsts if dt]
        lasts = [dt.date() for dt in lasts if dt]
        return (min(firsts) if firsts else None), (max(lasts) if lasts else None)
    return None, None


def _fetch_arctic_activity_dates(author: str, sort: str):
    """Fetch the first post and comment dates from Arctic Shift search in the given sort order ('asc' or 'desc').

    Fallback for users missing from the user index, which is only updated infrequently.
    """
    dates = []
    for kind in ('posts', 'comments'):
        try:
            resp = SESSION.get(f'{ARCTIC_SHIFT_URL}/api/{kind}/search',
                               params={'author': author, 'sort': sort, 'limit': 1}, timeout=REQUEST_TIMEOUT)
            if not resp.ok:
                continue
            payload = resp.json()
            items = payload.get('data', payload) if isinstance(payload, dict) else payload
            if isinstance(items, list) and items:
                ts = items[0].get('created_utc') or items[0].get('created') or items[0].get('timestamp')
                dt = parse_timestamp_utc(ts)
                if dt:
                    dates.append(dt.date())
        except (requests.RequestException, ValueError):
            continue
    return dates


def describe_creation_date(birth_date: str, source: str) -> str:
    """Text for a creation date that says how much it can be trusted.

    An estimated date is the account's first known post or comment, so the
    account was created on or before it.
    """
    if not birth_date or birth_date == 'Unknown':
        return 'Unknown'
    if source == 'True':
        return birth_date
    return f'≤ {birth_date} (first activity)'


def get_cached_account_info(author: str):
    """Return the cached (status_code, birth_date, last_activity, source), or None if it needs a new lookup."""
    with CACHE_LOCK:
        e = CACHE.get(author.lower())
        if not is_reusable_entry(e, reddit_auth.has_credentials()):
            return None
        return (
            e.get('status_code', STATUS_CODES['unknown']),
            e.get('birth_date', 'Unknown'),
            e.get('last_activity', 'Unknown'),
            e.get('source', 'Unknown')
        )


def get_account_info(author: str):
    """Return (status_code:int, birth_date_str, last_activity_str, source)

    source: 'True' if Reddit's created_utc was used, 'Estimated' if the date is
    the first known activity, 'Unknown' otherwise.
    status is 'unknown' unless Reddit answered (200 or 404). Results are kept in
    the global CACHE; call cache.flush_cache() after a batch to save the rest.
    """
    cached = get_cached_account_info(author)
    if cached:
        return cached

    birth_date = 'Unknown'
    last_activity = 'Unknown'
    source = 'Unknown'
    used_oauth = reddit_auth.has_credentials()

    data, status_code_raw = _fetch_reddit_about(author)
    # Only a 200 or 404 from Reddit tells us the account's real status.
    definitive = status_code_raw == 404 or (status_code_raw == 200 and isinstance(data, dict))
    if status_code_raw == 200 and isinstance(data, dict):
        status_code = STATUS_CODES['suspended'] if data.get('is_suspended') else STATUS_CODES['active']
        dt = parse_timestamp_utc(data.get('created_utc'))
        if dt:
            birth_date = dt.strftime('%Y-%m-%d')
            source = 'True'
    elif status_code_raw == 404:
        status_code = STATUS_CODES['deleted']
    else:
        status_code = STATUS_CODES['unknown']

    first_seen, last_seen = _fetch_arctic_user(author)
    if first_seen is None and source != 'True':
        earliest = _fetch_arctic_activity_dates(author, 'asc')
        first_seen = min(earliest) if earliest else None
    if last_seen is None:
        latest = _fetch_arctic_activity_dates(author, 'desc')
        last_seen = max(latest) if latest else None

    if source != 'True' and first_seen:
        birth_date = first_seen.strftime('%Y-%m-%d')
        source = 'Estimated'
    if last_seen:
        last_activity = last_seen.strftime('%Y-%m-%d')

    # A lookup with neither a Reddit answer nor an activity date is likely a
    # temporary failure and not worth keeping.
    if definitive or source == 'Estimated':
        with CACHE_LOCK:
            store_entry(author.lower(), {
                'status_code': status_code,
                'birth_date': birth_date,
                'last_activity': last_activity,
                'source': source,
                'checked_at': datetime.date.today().isoformat(),
                'checked_with_oauth': used_oauth,
            })

    return status_code, birth_date, last_activity, source
