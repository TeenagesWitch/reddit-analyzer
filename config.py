"""Configuration constants for the Reddit Analyzer application."""

import requests

# Network configuration
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'AuthorTools/0.1'})
REQUEST_TIMEOUT = 6
MAX_WORKERS = 12

# Application configuration
PAGE_SIZE = 1000
CACHE_FILE = 'creation_cache.json'
SKIP_LIST_FILE = 'skip_list.txt'

# Status codes
STATUS_CODES = {'deleted': 0, 'active': 1, 'suspended': 2}
STATUS_LABELS = {v: k for k, v in STATUS_CODES.items()}

