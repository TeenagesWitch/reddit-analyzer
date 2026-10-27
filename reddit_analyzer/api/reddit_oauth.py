"""Optional Reddit OAuth (app-only) access for account lookups.

Reddit refuses most anonymous requests, so real creation dates and account
status need a registered Reddit app. Credentials are entered in the Settings
tab and stored in CREDENTIALS_FILE.
"""

import os
import json
import time
import platform
import threading

import requests
from reddit_analyzer.config import CREDENTIALS_FILE, REQUEST_TIMEOUT, make_session

TOKEN_URL = 'https://www.reddit.com/api/v1/access_token'
OAUTH_URL = 'https://oauth.reddit.com'
# Seconds to wait before asking for a token again after Reddit rejects the credentials
AUTH_RETRY_DELAY = 300
# Most accounts one user_data_by_account_ids request may ask for
BULK_MAX_IDS = 100

# One kept-alive session, so OAuth requests don't each open a new TLS connection
_session = make_session()
_lock = threading.Lock()
_credentials = {}
_token = None
_token_expires = 0.0
_auth_error = None
_auth_retry_at = 0.0
# Requests left in Reddit's current rate-limit window, from the x-ratelimit-* headers.
# None means unknown (no response seen since the window reset).
_rate_remaining = None
_rate_reset_at = 0.0
# Set when Reddit refuses the bulk endpoint, so lookups go back to one request per user
_bulk_disabled = False


class AuthError(Exception):
    """Reddit rejected the configured credentials."""


def load_credentials(path=CREDENTIALS_FILE):
    """Read credentials from disk; missing fields are empty strings."""
    creds = {'client_id': '', 'client_secret': '', 'username': ''}
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict):
                for key in creds:
                    creds[key] = str(d.get(key) or '').strip()
        except Exception:
            pass
    return creds


def save_credentials(creds, path=CREDENTIALS_FILE):
    """Write credentials to disk and start using them."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(creds, f, indent=2)
    set_credentials(creds)


def set_credentials(creds):
    """Use these credentials from now on, discarding any token from the old ones."""
    global _credentials, _token, _token_expires, _auth_error, _auth_retry_at, _bulk_disabled
    with _lock:
        _credentials = dict(creds)
        _token = None
        _token_expires = 0.0
        _auth_error = None
        _auth_retry_at = 0.0
        _bulk_disabled = False


def has_credentials():
    return bool(_credentials.get('client_id'))


def bulk_available():
    """True if lookups may use the bulk endpoint (logged in, and Reddit hasn't refused it)."""
    return has_credentials() and not _bulk_disabled


def user_agent():
    """User-Agent in the format Reddit's API rules ask for."""
    username = _credentials.get('username')
    by = f' (by /u/{username})' if username else ''
    return f'{platform.system().lower()}:reddit-analyzer:1.0{by}'


def _get_token():
    """Return a valid app-only access token, requesting a new one if needed.

    Raises AuthError if Reddit rejects the credentials, and
    requests.RequestException on network errors.
    """
    global _token, _token_expires, _auth_error, _auth_retry_at
    with _lock:
        if _token and time.time() < _token_expires - 60:
            return _token
        if _auth_error and time.time() < _auth_retry_at:
            raise AuthError(_auth_error)
        client_id = _credentials.get('client_id', '')
        secret = _credentials.get('client_secret', '')
        if secret:
            data = {'grant_type': 'client_credentials'}
        else:
            # "Installed app" credentials have no secret
            data = {'grant_type': 'https://oauth.reddit.com/grants/installed_client',
                    'device_id': 'DO_NOT_TRACK_THIS_DEVICE'}
        resp = _session.post(TOKEN_URL, auth=(client_id, secret), data=data,
                             headers={'User-Agent': user_agent()}, timeout=REQUEST_TIMEOUT)
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code != 200 or 'access_token' not in payload:
            detail = payload.get('error') or f'HTTP {resp.status_code}'
            _auth_error = f'Reddit rejected the credentials ({detail})'
            _auth_retry_at = time.time() + AUTH_RETRY_DELAY
            raise AuthError(_auth_error)
        _token = payload['access_token']
        _token_expires = time.time() + float(payload.get('expires_in', 3600))
        _auth_error = None
        return _token


def _acquire_request_slot():
    """Block until Reddit's rate limit allows another request, and reserve it."""
    global _rate_remaining
    while True:
        with _lock:
            now = time.time()
            if _rate_remaining is not None and now >= _rate_reset_at:
                _rate_remaining = None
            if _rate_remaining is None:
                return
            if _rate_remaining >= 1:
                _rate_remaining -= 1
                return
            wait = _rate_reset_at - now
        time.sleep(min(wait, 5))


def _record_rate_limit(resp):
    global _rate_remaining, _rate_reset_at
    try:
        remaining = float(resp.headers['x-ratelimit-remaining'])
        reset = float(resp.headers['x-ratelimit-reset'])
    except (KeyError, TypeError, ValueError):
        if resp.status_code != 429:
            return
        remaining, reset = 0.0, 60.0
    with _lock:
        _rate_remaining = remaining
        _rate_reset_at = time.time() + reset


def _oauth_get(path, params=None):
    """Rate-limited GET on oauth.reddit.com, refreshing the token once on a 401.

    Returns the response, or None if no request could be made or it failed
    without an answer (bad credentials, network error).
    """
    global _token
    for attempt in range(2):
        try:
            token = _get_token()
        except (AuthError, requests.RequestException):
            return None
        _acquire_request_slot()
        try:
            resp = _session.get(f'{OAUTH_URL}{path}', params=params,
                                headers={'Authorization': f'bearer {token}', 'User-Agent': user_agent()},
                                timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            return None
        _record_rate_limit(resp)
        if resp.status_code == 401 and attempt == 0:
            # Token expired or revoked; get a fresh one and retry once
            with _lock:
                _token = None
            continue
        return resp
    return None


def fetch_user_about(author):
    """GET /user/<author>/about through OAuth.

    Returns (data dict or None, HTTP status or None). None status means the
    lookup failed without an answer from Reddit (bad credentials, network error).
    """
    resp = _oauth_get(f'/user/{author}/about', {'raw_json': 1})
    if resp is None:
        return None, None
    if resp.status_code == 200:
        try:
            return resp.json().get('data', {}), 200
        except (ValueError, AttributeError):
            return None, None
    return None, resp.status_code


def fetch_users_by_ids(account_ids):
    """Look up to BULK_MAX_IDS accounts in one request via /api/user_data_by_account_ids.

    account_ids are base-36 ids without the 't2_' prefix. Returns {id: data}
    for the accounts Reddit returned, or None if the request failed. Accounts
    Reddit leaves out (suspended, deleted, unknown) are simply missing.
    If Reddit refuses the endpoint itself, bulk lookups are switched off.
    """
    global _bulk_disabled
    if not account_ids:
        return {}
    ids = ','.join(f't2_{i}' for i in account_ids[:BULK_MAX_IDS])
    resp = _oauth_get('/api/user_data_by_account_ids', {'ids': ids})
    if resp is None:
        return None
    if resp.status_code in (400, 403, 404, 405):
        _bulk_disabled = True
        return None
    if resp.status_code != 200:
        return None
    try:
        payload = resp.json()
    except ValueError:
        return None
    if not isinstance(payload, dict) or 'error' in payload:
        _bulk_disabled = True
        return None
    return {key[3:] if key.startswith('t2_') else key: value
            for key, value in payload.items() if isinstance(value, dict)}


def check_connection():
    """Check the current credentials with a token request and lookups. Returns (ok, message)."""
    if not has_credentials():
        return False, 'No client ID set. Lookups use Reddit\'s public API, which usually refuses them.'
    try:
        _get_token()
    except AuthError as e:
        return False, str(e)
    except requests.RequestException as e:
        return False, f'Could not reach Reddit: {e}'
    data, status = fetch_user_about('reddit')
    if not (status == 200 and data and data.get('created_utc')):
        return False, f'Got a token, but the test lookup failed (HTTP {status}).'
    message = 'Connected. Lookups will use real creation dates and status from Reddit.'
    # u/spez is account t2_1w72
    bulk = fetch_users_by_ids(['1w72'])
    if bulk and (bulk.get('1w72') or {}).get('created_utc'):
        message += ' Bulk lookups work (up to 100 accounts per request).'
    else:
        message += ' Bulk lookups are unavailable, so each account takes one request.'
    return True, message


# Initialize credentials on import
set_credentials(load_credentials())
