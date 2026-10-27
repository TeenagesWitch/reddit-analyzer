"""Where the app keeps its data files.

Data lives in a 'data' folder next to the app (next to the .exe when built
with PyInstaller), so it doesn't depend on which folder the app is started
from. Set REDDIT_ANALYZER_DATA_DIR to use another folder.

Older versions wrote these files to the current folder. On first start they
are moved into the data folder.
"""

import os
import sys
import shutil
from pathlib import Path

DATA_DIR_ENV = 'REDDIT_ANALYZER_DATA_DIR'
# Files older versions kept in the folder the app was started from
LEGACY_DATA_FILES = ('creation_cache.json', 'skip_list.txt', 'reddit_credentials.json')


def app_dir() -> Path:
    """The folder the app runs from: the .exe's folder, or the project root."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def move_legacy_data_files(data_dir: Path, old_dirs) -> list:
    """Move data files from old_dirs into data_dir unless data_dir already has them.

    Returns the list of files moved. A file that can't be moved stays where it
    is, and the app starts with a fresh one.
    """
    moved = []
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in LEGACY_DATA_FILES:
        target = data_dir / name
        if target.exists():
            continue
        for old_dir in old_dirs:
            source = Path(old_dir) / name
            try:
                if source.is_file() and source.resolve() != target.resolve():
                    shutil.move(str(source), str(target))
                    moved.append(name)
                    break
            except OSError:
                continue
    return moved


def _resolve_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        # An explicit folder (tests, portable setups) never pulls in files from elsewhere
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    path = app_dir() / 'data'
    move_legacy_data_files(path, [app_dir(), Path.cwd()])
    return path


DATA_DIR = _resolve_data_dir()


def data_file(name: str) -> str:
    """Path of a file in the data folder, as a string."""
    return str(DATA_DIR / name)
