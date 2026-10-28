# Development Guide

## Setting Up Development Environment

1. **Clone the repository**

2. **Create and activate a virtual environment** (or run `scripts/setup_env.bat` / `scripts/setup_env.sh`):
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # Linux/macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install -r requirements-dev.txt   # pytest, for the tests
   ```

## Project Structure

```
reddit-analyzer/
├── reddit.py                        # Entry point: python reddit.py
├── reddit_analyzer/                 # The application package
│   ├── config.py                    # Constants, HTTP session, data file paths
│   ├── paths.py                     # Locates data/ and moves files left by older versions
│   ├── core/
│   │   ├── cache.py                 # Persistent account cache (creation_cache.json)
│   │   ├── rate_limit.py            # Thread-safe request pacing (RateLimiter)
│   │   ├── skip_list.py             # Usernames to ignore (skip_list.txt)
│   │   └── timestamps.py            # Unix/ISO timestamp parsing to UTC
│   ├── api/
│   │   ├── accounts.py              # get_account_info / lookup_accounts: status + creation date
│   │   ├── arctic_shift.py          # Arctic Shift client, rate limited: account ids, first/last activity
│   │   └── reddit_oauth.py          # Optional Reddit OAuth login, rate limiting, bulk lookups
│   └── gui/
│       ├── main_app.py              # Main window with the tabbed interface
│       ├── widgets/
│       │   └── activity_views.py    # Activity calendar + posting-hours heatmap (shared mixin)
│       └── tabs/
│           ├── subreddit_analysis_tab.py
│           ├── user_analysis_tab.py
│           ├── creation_year_tab.py
│           ├── overlapping_users_tab.py
│           └── settings_tab.py
├── data/                            # Runtime data, not in git (see below)
├── tests/                           # pytest suite
├── scripts/                         # setup_env.bat, setup_env.sh
├── docs/DEVELOPMENT.md              # This file
├── requirements.txt                 # Runtime dependencies
└── requirements-dev.txt             # Test dependencies
```

Modules import each other through the package, e.g. `from reddit_analyzer.core.cache import CACHE`.

## Data Files

`reddit_analyzer/paths.py` puts runtime data in `data/` next to `reddit.py` (next to the `.exe` when
built with PyInstaller), regardless of the folder the app is started from:

| File | Contents |
|------|----------|
| `creation_cache.json` | Cached account lookups |
| `skip_list.txt` | Usernames to ignore, edited in Settings |
| `reddit_credentials.json` | Optional Reddit OAuth login, edited in Settings (contains a secret) |

Older versions wrote these to the current folder. On first start they are moved into `data/`.
Set the `REDDIT_ANALYZER_DATA_DIR` environment variable to use another folder; then nothing is moved.

## External Services

Every request to an outside service goes through its client module, never through `SESSION` directly:

- **Arctic Shift** (`api/arctic_shift.py`): free service, so all calls go through `_get()`, which
  uses one shared `RateLimiter` (2 requests/second, 2 in flight), waits out 429s using the
  `X-RateLimit-Reset` headers, backs off on 5xx/network errors and pauses for 5 minutes after
  6 failures in a row. Tune with the `ARCTIC_SHIFT_*` settings in `config.py`.
- **Reddit OAuth** (`api/reddit_oauth.py`): follows Reddit's `x-ratelimit-*` headers (about 100
  requests a minute per app).

## Testing

```bash
python -m pytest
```

The tests run offline: Reddit and Arctic Shift are replaced with fakes, and each test session uses
a temporary data folder, so your real cache and login are never touched. The GUI tests are skipped
when no display is available.

## Code Style

- Follow PEP 8 style guidelines
- Keep Python 3.8 compatibility (no `X | None` annotations at runtime, no `str.removeprefix`)
- Document functions and classes with docstrings
- Keep functions focused and modular

## Adding New Features

1. Create the tab class in `reddit_analyzer/gui/tabs/`
2. Import and add it to `reddit_analyzer/gui/tabs/__init__.py`
3. Register it in `reddit_analyzer/gui/main_app.py`
4. Add tests in `tests/`
5. Update `README.md` with the feature documentation

## Dependencies

- **requests**: HTTP library for Reddit and Arctic Shift
- **pytz**: Timezone support
- **tkinter**: GUI framework (standard library)
- **pytest** (development only): test runner

To add a new dependency:
1. Add it to `requirements.txt` (or `requirements-dev.txt` for test-only tools) with version constraints
2. Update this documentation if needed
3. Test installation in a fresh virtual environment

## Building Executable

To create a standalone executable using PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed reddit.py
```

The executable will be in the `dist/` directory. It keeps its data in a `data/` folder beside it.
