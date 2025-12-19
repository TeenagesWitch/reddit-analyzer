"""Reddit API functions for fetching account information."""

import datetime
import requests
from config import SESSION, REQUEST_TIMEOUT, STATUS_CODES
from cache import CACHE, CACHE_LOCK, save_persistent_cache


def _try_parse_timestamp_to_date(ts) -> datetime.date | None:
    """Parse various timestamp formats to a date object."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(ts).date()
        except Exception:
            return None
    if isinstance(ts, str):
        try:
            return datetime.datetime.fromisoformat(ts.rstrip('Z')).date()
        except Exception:
            return None
    return None


def _fetch_about_json(author: str):
    """Fetch user about.json from Reddit API."""
    try:
        resp = SESSION.get(f'https://www.reddit.com/user/{author}/about.json', timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json().get('data', {}), 200
        return None, resp.status_code
    except requests.RequestException:
        return None, None


def _fetch_photon_earliest(author: str):
    """Fetch earliest post/comment timestamp from Photon API."""
    timestamps = []
    for endpoint in (
        f'https://arctic-shift.photon-reddit.com/api/posts/search?author={author}&sort=asc',
        f'https://arctic-shift.photon-reddit.com/api/comments/search?author={author}&sort=asc',
    ):
        try:
            resp = SESSION.get(endpoint, timeout=REQUEST_TIMEOUT)
            if not resp.ok:
                continue
            payload = resp.json()
            items = payload.get('data', payload) if isinstance(payload, dict) else payload
            if isinstance(items, list) and items:
                ts = items[0].get('created_utc') or items[0].get('created') or items[0].get('timestamp')
                dt = _try_parse_timestamp_to_date(ts)
                if dt:
                    timestamps.append(dt)
        except requests.RequestException:
            continue
    if timestamps:
        return min(timestamps)
    return None


def get_account_info(author: str):
    """Return (status_code:int, birth_date_str, last_activity_str, source)
    
    source: 'True' if created_utc used, 'Estimated' if fallback used, 'Unknown' otherwise.
    Persistent global CACHE used.
    """
    lower = author.lower()
    with CACHE_LOCK:
        if lower in CACHE:
            e = CACHE[lower]
            return (
                e.get('status_code', STATUS_CODES['active']),
                e.get('birth_date', 'Unknown'),
                e.get('last_activity', 'Unknown'),
                e.get('source', 'Unknown')
            )

    birth_date = 'Unknown'
    last_activity = 'Unknown'
    source = 'Unknown'

    data, status_code_raw = _fetch_about_json(author)
    if status_code_raw == 200 and isinstance(data, dict):
        status_code = STATUS_CODES['suspended'] if data.get('is_suspended') else STATUS_CODES['active']
    elif status_code_raw == 404:
        status_code = STATUS_CODES['deleted']
    else:
        status_code = STATUS_CODES['active']

    if status_code_raw == 200 and isinstance(data, dict):
        ts = data.get('created_utc')
        dt = _try_parse_timestamp_to_date(ts)
        if dt:
            birth_date = dt.strftime('%Y-%m-%d')
            source = 'True'

    if birth_date == 'Unknown':
        earliest = _fetch_photon_earliest(author)
        if earliest:
            birth_date = earliest.strftime('%Y-%m-%d')
            source = 'Estimated'

    last_ts = []
    for endpoint in (
        f'https://arctic-shift.photon-reddit.com/api/posts/search?author={author}&sort=desc',
        f'https://arctic-shift.photon-reddit.com/api/comments/search?author={author}&sort=desc',
    ):
        try:
            resp = SESSION.get(endpoint, timeout=REQUEST_TIMEOUT)
            if not resp.ok:
                continue
            payload = resp.json()
            items = payload.get('data', payload) if isinstance(payload, dict) else payload
            if isinstance(items, list) and items:
                ts = items[0].get('created_utc') or items[0].get('created') or items[0].get('timestamp')
                dt = _try_parse_timestamp_to_date(ts)
                if dt:
                    last_ts.append(dt)
        except requests.RequestException:
            continue
    if last_ts:
        last_activity = max(last_ts).strftime('%Y-%m-%d')

    with CACHE_LOCK:
        CACHE[lower] = {
            'status_code': status_code,
            'birth_date': birth_date,
            'last_activity': last_activity,
            'source': source
        }
        try:
            save_persistent_cache(CACHE)
        except Exception:
            pass

    return status_code, birth_date, last_activity, source

