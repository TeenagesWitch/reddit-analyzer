"""Skip list management for filtering usernames."""

import os
from config import SKIP_LIST_FILE

DEFAULT_SKIPS = set()


def load_skip_list(path=SKIP_LIST_FILE):
    """Load skip list from file, creating default if it doesn't exist."""
    if not os.path.isfile(path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write("[deleted]\nautomoderator\n")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return set(line.strip().lower() for line in f if line.strip())
    except Exception:
        return set()


# Initialize skip list on import
DEFAULT_SKIPS.update(load_skip_list())

