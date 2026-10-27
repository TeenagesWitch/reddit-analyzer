"""Configuration constants for the Reddit Analyzer application."""

import requests
from requests.adapters import HTTPAdapter

from reddit_analyzer.paths import data_file

# Network configuration
REQUEST_TIMEOUT = 6
MAX_WORKERS = 12


def make_session():
    """A requests Session whose connection pool fits every worker thread.

    The default pool keeps only 10 connections per host, so extra threads
    would open (and then throw away) a fresh TLS connection per request.
    Room for two batches covers a page load overlapping a background prefetch.
    """
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=MAX_WORKERS * 2)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


SESSION = make_session()
SESSION.headers.update({'User-Agent': 'AuthorTools/0.1'})
ARCTIC_SHIFT_URL = 'https://arctic-shift.photon-reddit.com'
# Seconds to stop trying Reddit's public JSON after it refuses a request (403/429)
PUBLIC_API_BACKOFF = 600

# Application configuration
PAGE_SIZE = 1000
# Data files live in the data folder (see paths.py)
CACHE_FILE = data_file('creation_cache.json')
CACHE_SAVE_INTERVAL = 30  # seconds between cache writes during a batch of lookups
# Days to reuse a lookup Reddit didn't answer before retrying it
UNKNOWN_RETRY_DAYS = 7
SKIP_LIST_FILE = data_file('skip_list.txt')
# Optional Reddit OAuth app credentials, edited in the Settings tab. Keep out of version control.
CREDENTIALS_FILE = data_file('reddit_credentials.json')

# Status codes
# 'unknown' means Reddit gave no definitive answer (blocked, rate limited, server error, timeout).
STATUS_CODES = {'deleted': 0, 'active': 1, 'suspended': 2, 'unknown': 3}
STATUS_LABELS = {v: k for k, v in STATUS_CODES.items()}
