"""Configuration constants for the Reddit Analyzer application."""

import requests

# Network configuration
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'AuthorTools/0.1'})
REQUEST_TIMEOUT = 6
MAX_WORKERS = 12
ARCTIC_SHIFT_URL = 'https://arctic-shift.photon-reddit.com'
# Seconds to stop trying Reddit's public JSON after it refuses a request (403/429)
PUBLIC_API_BACKOFF = 600

# Application configuration
PAGE_SIZE = 1000
CACHE_FILE = 'creation_cache.json'
CACHE_SAVE_INTERVAL = 30  # seconds between cache writes during a batch of lookups
# Days to reuse a lookup Reddit didn't answer before retrying it
UNKNOWN_RETRY_DAYS = 7
SKIP_LIST_FILE = 'skip_list.txt'
# Optional Reddit OAuth app credentials, edited in the Settings tab. Keep out of version control.
CREDENTIALS_FILE = 'reddit_credentials.json'

# Status codes
# 'unknown' means Reddit gave no definitive answer (blocked, rate limited, server error, timeout).
STATUS_CODES = {'deleted': 0, 'active': 1, 'suspended': 2, 'unknown': 3}
STATUS_LABELS = {v: k for k, v in STATUS_CODES.items()}
