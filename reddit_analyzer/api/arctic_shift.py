"""Arctic Shift (photon-reddit) client: account ids and first/last activity dates.

Arctic Shift archives Reddit posts and comments, so it knows when an account
was first and last active even when Reddit itself won't answer.
"""

import requests
from reddit_analyzer.config import SESSION, REQUEST_TIMEOUT, ARCTIC_SHIFT_URL
from reddit_analyzer.core.timestamps import parse_timestamp_utc


def fetch_user_index(author: str):
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


def fetch_first_activity(author: str):
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
