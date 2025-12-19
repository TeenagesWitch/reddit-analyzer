"""Cache management for Reddit account information."""

import os
import json
import threading
from config import CACHE_FILE

# Global cache and lock
CACHE = {}
CACHE_LOCK = threading.Lock()


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
    """Save cache to disk."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
    except Exception:
        pass


# Initialize cache on import
CACHE.update(load_persistent_cache())

