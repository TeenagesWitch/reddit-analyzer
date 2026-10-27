"""Cache management for Reddit account information."""

import os
import json
import time
import datetime
import threading
from config import CACHE_FILE, CACHE_SAVE_INTERVAL, STATUS_CODES, UNKNOWN_RETRY_DAYS

# Global cache and lock
CACHE = {}
CACHE_LOCK = threading.Lock()

# Whether CACHE has entries not yet on disk, and when it was last saved.
# Both are guarded by CACHE_LOCK.
_dirty = False
_last_save = time.monotonic()


def load_persistent_cache(path=CACHE_FILE):
    """Load cache from disk."""
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
                if isinstance(d, dict):
                    return d
        except Exception:
            pass
    return {}


def save_persistent_cache(cache, path=CACHE_FILE):
    """Save cache to disk atomically, so an interrupted write never corrupts the existing file."""
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
        os.replace(tmp_path, path)
    except Exception:
        pass


def store_entry(key, entry):
    """Add an entry to CACHE. Must be called with CACHE_LOCK held.

    Saving the whole cache is slow, so during a batch of lookups it is
    written at most once every CACHE_SAVE_INTERVAL seconds. Call
    flush_cache() when the batch ends to save the rest.
    """
    global _dirty
    CACHE[key] = entry
    _dirty = True
    if time.monotonic() - _last_save >= CACHE_SAVE_INTERVAL:
        _save_locked()


def flush_cache():
    """Save any entries added since the last save."""
    with CACHE_LOCK:
        if _dirty:
            _save_locked()


def _save_locked():
    global _dirty, _last_save
    save_persistent_cache(CACHE)
    _dirty = False
    _last_save = time.monotonic()


def is_definitive_entry(entry):
    """Return True if Reddit itself answered this lookup (deleted, suspended, or active with a real creation date)."""
    status = entry.get('status_code')
    if status in (STATUS_CODES['deleted'], STATUS_CODES['suspended']):
        return True
    return status == STATUS_CODES['active'] and entry.get('source') == 'True'


def is_reusable_entry(entry, oauth_available=False):
    """Return True if a cached entry can be used instead of a new lookup.

    Answers from Reddit are reused indefinitely. Anything else is reused only
    until it is UNKNOWN_RETRY_DAYS old, or until OAuth credentials are added
    if it was looked up without them. Entries with no 'checked_at' date come
    from older versions and are looked up again once.
    """
    if not isinstance(entry, dict):
        return False
    if is_definitive_entry(entry):
        return True
    if oauth_available and not entry.get('checked_with_oauth'):
        return False
    try:
        checked = datetime.date.fromisoformat(entry['checked_at'])
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= (datetime.date.today() - checked).days < UNKNOWN_RETRY_DAYS


def _migrate_legacy_entries(cache):
    """Relabel entries older versions marked 'active' without Reddit confirming it.

    Those versions recorded 'active' whenever Reddit didn't answer. A real
    answer for an active account always includes its creation date, so an
    'active' entry without one is really unknown.

    They are stamped as checked today: without OAuth a new lookup would only
    find the same estimate again, and with OAuth is_reusable_entry looks them
    up again anyway, since they weren't checked with it.
    """
    today = datetime.date.today().isoformat()
    for entry in cache.values():
        if (isinstance(entry, dict) and entry.get('status_code') == STATUS_CODES['active']
                and entry.get('source') != 'True'):
            entry['status_code'] = STATUS_CODES['unknown']
            entry.setdefault('checked_at', today)


# Initialize cache on import
CACHE.update(load_persistent_cache())
_migrate_legacy_entries(CACHE)
