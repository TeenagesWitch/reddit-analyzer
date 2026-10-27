"""Reddit API functions for fetching account information."""

import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import reddit_auth
from config import (SESSION, REQUEST_TIMEOUT, STATUS_CODES, ARCTIC_SHIFT_URL, PUBLIC_API_BACKOFF,
                    MAX_WORKERS)
from cache import CACHE, CACHE_LOCK, is_reusable_entry, store_entry
from timestamps import parse_timestamp_utc

# Until this time.time(), skip Reddit's public JSON: it refused a recent request
_public_api_blocked_until = 0.0
# What get_account_info returns when a lookup fails outright
UNKNOWN_INFO = (STATUS_CODES['unknown'], 'Unknown', 'Unknown', 'Unknown')


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
    """Return (account_id, first_seen, last_seen) from Arctic Shift's user index.

    One request covers both posts and comments. account_id is the base-36 id
    without 't2_'. Any value is None if unknown.
    """
    try:
        resp = SESSION.get(f'{ARCTIC_SHIFT_URL}/api/users/search', params={'author': author},
                           timeout=REQUEST_TIMEOUT)
        if not resp.ok:
            return None, None, None
        rows = resp.json().get('data') or []
    except (requests.RequestException, ValueError, AttributeError):
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


def _fetch_arctic_first_activity(author: str):
    """Return the earliest post or comment date from Arctic Shift search, or None.

    Fallback for users missing from the user index, which is only updated infrequently.
    """
    dates = []
    for kind in ('posts', 'comments'):
        try:
            resp = SESSION.get(f'{ARCTIC_SHIFT_URL}/api/{kind}/search',
                               params={'author': author, 'sort': 'asc', 'limit': 1}, timeout=REQUEST_TIMEOUT)
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
    return min(dates) if dates else None


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


def _finish_lookup(author, status_code, created_date, definitive, arctic, used_oauth):
    """Fill in an estimate if Reddit gave no date, cache the result, and return the info tuple.

    arctic is (account_id, first_seen, last_seen) from the user index, or None
    if it hasn't been fetched. It is only fetched when the date is still missing.
    """
    birth_date, source, last_activity = 'Unknown', 'Unknown', 'Unknown'
    if created_date:
        birth_date, source = created_date.strftime('%Y-%m-%d'), 'True'
    else:
        if arctic is None:
            arctic = _fetch_arctic_user(author)
        first_seen = arctic[1] or _fetch_arctic_first_activity(author)
        if first_seen:
            birth_date, source = first_seen.strftime('%Y-%m-%d'), 'Estimated'
    if arctic and arctic[2]:
        last_activity = arctic[2].strftime('%Y-%m-%d')

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


def _lookup_uncached(author, arctic=None):
    """Look up one account with a per-user Reddit request (plus Arctic Shift if needed)."""
    used_oauth = reddit_auth.has_credentials()
    data, status_code_raw = _fetch_reddit_about(author)
    # Only a 200 or 404 from Reddit tells us the account's real status.
    definitive = status_code_raw == 404 or (status_code_raw == 200 and isinstance(data, dict))
    created = None
    if status_code_raw == 200 and isinstance(data, dict):
        status_code = STATUS_CODES['suspended'] if data.get('is_suspended') else STATUS_CODES['active']
        dt = parse_timestamp_utc(data.get('created_utc'))
        created = dt.date() if dt else None
    elif status_code_raw == 404:
        status_code = STATUS_CODES['deleted']
    else:
        status_code = STATUS_CODES['unknown']
    return _finish_lookup(author, status_code, created, definitive, arctic, used_oauth)


def _safe_lookup(author, arctic=None):
    try:
        return _lookup_uncached(author, arctic)
    except Exception:
        return UNKNOWN_INFO


def _lookup_from_bulk(author, data, arctic):
    """Build the info tuple from a user_data_by_account_ids entry, or None if it can't be trusted."""
    if str(data.get('name', '')).lower() != author.lower():
        return None
    dt = parse_timestamp_utc(data.get('created_utc'))
    if dt is None:
        return None
    status_code = STATUS_CODES['suspended'] if data.get('is_suspended') else STATUS_CODES['active']
    return _finish_lookup(author, status_code, dt.date(), True, arctic, True)


def get_account_info(author: str):
    """Return (status_code:int, birth_date_str, last_activity_str, source)

    source: 'True' if Reddit's created_utc was used, 'Estimated' if the date is
    the first known activity, 'Unknown' otherwise.
    status is 'unknown' unless Reddit answered (200 or 404). Results are kept in
    the global CACHE; call cache.flush_cache() after a batch to save the rest.
    """
    return get_cached_account_info(author) or _lookup_uncached(author)


def lookup_accounts(usernames, on_result, cancel=None, max_workers=MAX_WORKERS):
    """Look up many accounts, calling on_result(username, info) as each one is known.

    info is the get_account_info tuple. on_result runs on worker threads.
    Cached accounts are reported first. When logged in, accounts are looked up
    100 at a time through Reddit's bulk endpoint, using ids from Arctic Shift;
    accounts it can't answer fall back to one request each. cancel is an
    optional threading.Event that stops the batch early. Returns False if it
    was cancelled.
    """
    def cancelled():
        return cancel is not None and cancel.is_set()

    pending = []
    for u in usernames:
        if cancelled():
            return False
        cached = get_cached_account_info(u)
        if cached:
            on_result(u, cached)
        else:
            pending.append(u)
    if not pending:
        return True

    with ThreadPoolExecutor(max_workers=min(max_workers, len(pending))) as ex:
        # Bulk chunks, for as long as Reddit accepts the bulk endpoint
        while pending and reddit_auth.bulk_available():
            if cancelled():
                return False
            chunk, pending = pending[:reddit_auth.BULK_MAX_IDS], pending[reddit_auth.BULK_MAX_IDS:]
            arctic = dict(zip(chunk, ex.map(_fetch_arctic_user, chunk)))
            ids = [a[0] for a in arctic.values() if a[0]]
            bulk = (reddit_auth.fetch_users_by_ids(ids) if ids else None) or {}
            leftovers = []
            for u in chunk:
                data = bulk.get(arctic[u][0]) if arctic[u][0] else None
                info = None
                if data:
                    try:
                        info = _lookup_from_bulk(u, data, arctic[u])
                    except Exception:
                        info = None
                if info:
                    on_result(u, info)
                else:
                    leftovers.append(u)
            futures = {ex.submit(_safe_lookup, u, arctic[u]): u for u in leftovers}
            for fut in as_completed(futures):
                on_result(futures[fut], fut.result())

        # One request per user: not logged in, or bulk lookups unavailable
        futures = {ex.submit(_safe_lookup, u): u for u in pending}
        for fut in as_completed(futures):
            if cancelled():
                for f in futures:
                    f.cancel()
                return False
            on_result(futures[fut], fut.result())
    return True
