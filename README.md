# Reddit Analyzer

A simple Reddit analysis tool designed for OSINT (Open Source Intelligence) purposes. Analyze subreddit activity, user behavior, account creation patterns, and find overlapping users across multiple datasets.

## Features

### 1. Subreddit Analysis

Analyze activity and contributors within a specific subreddit using posts and comments JSONL files.

**Input Requirements:**
- **File A (Posts)**: JSONL file containing Reddit posts from a single subreddit
- **File B (Comments)**: JSONL file containing Reddit comments from the same subreddit
- Both files must be from the same subreddit (validated automatically)

**Features:**
- **Unique Usernames**: Extract and display all unique usernames with export to TXT functionality
- **Top 20 Contributors**: View the most active contributors ranked by post/comment count
- **Activity Tracker**: GitHub-style contribution calendar showing daily activity levels
  - Filter by year
  - Displays all 365/366 days of the selected year
  - Horizontal layout (weeks as columns, days as rows)
- **Day-by-Day Posting Hours Heatmap**: Visualize posting patterns by hour and day of week
  - Timezone adjustment support (UTC, US timezones, UK, Europe, Japan, Australia)
  - Color-coded intensity levels
- **Exploratory Statistics**:
  - Posts per Day (PPD)
  - Posts per Hour (PPH)
  - Total posts/comments count
  - Unique usernames count
  - Date range
  - Average posts per user

### 2. User Analysis

Analyze individual Reddit user activity patterns across multiple subreddits.

**Input Requirements:**
- **File A (Posts)**: JSONL file containing posts from a single Reddit user
- **File B (Comments)**: JSONL file containing comments from the same Reddit user
- Both files must be from the same user (validated automatically)
- User can have activity across multiple subreddits

**Features:**
- **Exploratory Statistics**:
  - Username
  - Total posts and comments count
  - Posts vs comments ratio (percentage breakdown)
  - Unique subreddits count
  - Posts per Day (PPD)
  - Posts per Hour (PPH)
  - Date range of activity
  - Average activity per subreddit
- **Subreddit Frequency List**: View all subreddits the user participates in, sorted by activity frequency
- **Activity Tracker**: GitHub-style contribution calendar
  - Filter by year
  - Displays all 365/366 days of the selected year
  - Horizontal layout matching GitHub's style
- **Day-by-Day Posting Hours Heatmap**: Analyze posting time patterns
  - Timezone adjustment support
  - Interactive cells showing day, hour, and activity count

### 3. Creation Year Distribution

Analyze the distribution of account creation years for a list of Reddit usernames.

**Input Requirements:**
- TXT file with one username per line

**Features:**
- **Pagination**: Process and display results in pages of 1000 users
- **Persistent Caching**: API responses are cached to avoid redundant requests
- **Year Distribution**: Visualize how many accounts were created in each year
- **Filter by Year**: View detailed breakdown for specific years
- **Progress Tracking**: Real-time progress bar and status updates
- **Account Status**: Shows account status (active, suspended, deleted, etc.)
- **Clickable Results**: Click usernames to open their Reddit profile in browser

### 4. Overlapping Users

Find users that appear in all submitted files (set intersection).

**Input Requirements:**
- 2 to 5 TXT files, each containing Reddit usernames (one per line)

**Features:**
- **Multi-File Analysis**: Find users present in ALL submitted files
- **Account Information**: Fetches creation dates and account status via Reddit API (see below for the optional login)
- **Year Filtering**: Filter results by account creation year
- **Progress Tracking**: Real-time progress updates during API calls
- **Export Results**: View and export overlapping users with their account details
- **Clickable Usernames**: Open user profiles directly from results

### 5. Settings

Configuration and application settings.

- **Skip List**: Usernames to ignore in every tab
- **Reddit API login (optional)**: Client ID and secret of your own Reddit app, used for account lookups

### Account dates and status: with and without a Reddit login

Reddit refuses most anonymous requests, so without a login the Creation Year and Overlapping Users tabs
can't get real creation dates or account status:

- **Creation date** falls back to the account's first known post or comment (from Arctic Shift),
  shown as `≤ 2019-03-11 (first activity)`: the account was created on or before that date.
  The Year Distribution's **Confirmed** column counts only dates that came from Reddit.
- **Status** is shown as `unknown`. Lookups Reddit didn't answer are retried after 7 days.

To get real dates and status (deleted, suspended, active):

1. Go to https://www.reddit.com/prefs/apps and create an app of type **script**
   (any name; the redirect URI can be `http://localhost:8080`).
2. In the **Settings** tab, enter the app's client ID (the string under the app name) and secret,
   plus your Reddit username, then click **Save & Test**.

The login is stored in `data/reddit_credentials.json` (excluded from git). Once it's set,
accounts that only had estimates are looked up again. Reddit allows about 100 requests a minute; when
its bulk endpoint is available (Save & Test says so), one request covers up to 100 accounts, and only
accounts it can't answer fall back to one request each.

While you view a page of the Creation Year Distribution, the next page is looked up in the
background, so **Next** is usually instant.

### Being considerate to Arctic Shift

Arctic Shift is a free service, and its documentation asks clients to stay at "a couple requests per
second". The app keeps to that across all its threads:

- At most 2 requests per second, evenly spaced, with no more than 2 in flight at once
- After a `429 Too Many Requests` it waits as long as the `X-RateLimit-Reset` header says, then retries
- After server or network errors it backs off (2s, 4s, 8s...), and after 6 failures in a row it stops
  asking Arctic Shift for 5 minutes; lookups in the meantime are left unknown and retried later
- Only the next page is prefetched, never the whole list

This means an uncached account takes about half a second, so a 1,000-user page with no cache hits
takes roughly 8–10 minutes. Cached accounts need no requests at all. The limits are the
`ARCTIC_SHIFT_*` settings in `reddit_analyzer/config.py`.

## File Format Requirements

### JSONL Files (Subreddit Analysis & User Analysis)

Each line must be a valid JSON object representing a Reddit post or comment. They can be obtained from [arctic-shift](https://arctic-shift.photon-reddit.com/).

**Post objects should contain:**
- `subreddit` or `subreddit_name_prefixed`
- `author`
- `created_utc` or `created`
- `title` or `is_self` (post-specific fields)

**Comment objects should contain:**
- `subreddit` or `subreddit_name_prefixed`
- `author`
- `created_utc` or `created`
- `body` and `link_id` (comment-specific fields)

### TXT Files (Creation Year & Overlapping Users)

Plain text files with one Reddit username per line:
```
username1
username2
username3
```

## Validation

The application includes comprehensive validation:

- **Subreddit Analysis**: Ensures both files are from the same subreddit
- **User Analysis**: Ensures both files are from the same Reddit user
- **File Type Validation**: Verifies posts vs comments structure
- **Required Fields**: Checks for necessary JSON fields
- **File Format**: Validates JSONL structure

## Requirements

- Python 3.8 or higher
- `tkinter` - GUI framework (usually included with Python)
  - On Linux: may need to install `python3-tk` package
  - On macOS with Homebrew Python: included by default
  - On Windows: included with Python

## Installation

### Using Virtual Environment (Recommended)

For reproducibility and to avoid conflicts with system packages, use a virtual environment:

#### Windows:
```bash
# Run the setup script
scripts\setup_env.bat

# Or manually:
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

#### Linux/macOS:
```bash
# Make the script executable (first time only)
chmod +x scripts/setup_env.sh

# Run the setup script
./scripts/setup_env.sh

# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Manual Installation (Without Virtual Environment)

If you prefer not to use a virtual environment:

```bash
pip install -r requirements.txt
```

**Note:** This is not recommended as it may conflict with other Python projects.

## Usage

1. **Activate the virtual environment** (if using one):
   - Windows: `venv\Scripts\activate`
   - Linux/macOS: `source venv/bin/activate`

2. **Run the application**:
   ```bash
   python reddit.py
   ```

3. Select the appropriate tab for your analysis type

4. Load your JSONL or TXT files using the file browser

5. Click "Analyze" to process the data

6. Explore the results using the interactive visualizations and filters


## Notes

- API requests are cached to improve performance and reduce rate limiting
- The cache, skip list and Reddit login are kept in the `data/` folder next to `reddit.py`
  (excluded from git). Files left in the project folder by older versions are moved there on first start.
  Set `REDDIT_ANALYZER_DATA_DIR` to keep them somewhere else.
- Large datasets are processed efficiently with pagination
- All timestamps are handled in UTC and can be converted to local timezones
- The application validates file structure before processing to prevent errors

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the project layout and how to run the tests.
