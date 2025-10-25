#!/usr/bin/env python3
"""
Author Tools GUI - Extended
Adds a new tab "Creation Year Distribution" that accepts one .txt file of usernames,
fetches account creation dates (via Reddit "about" endpoint / fallback Photon search),
computes a per-year distribution, shows it in a TreeView, provides a dropdown to filter
by year, and allows exporting the filtered usernames to a .txt file.

How to use:
- Run this script (requires Python 3.8+ and `requests`)
- Use the new tab: select a single TXT file containing one username per line, then
  click "Analyze" to fetch creation dates and populate the UI.

Notes:
- Network calls run on a background thread to keep the UI responsive.
- Basic error handling and timeouts are included.
- Re-uses helper functions for account info already present in previous toolset.

"""

import os
import json
import threading
import datetime
import webbrowser
import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration / constants ---
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'AuthorTools/0.1'})
REQUEST_TIMEOUT = 6  # seconds
MAX_WORKERS = 10  # number of concurrent threads for fetching

SKIP_LIST_FILE = 'skip_list.txt'

# Cache for runtime
CACHE = {}

# --- Helper functions (re-usable) ---

def load_skip_list(path=SKIP_LIST_FILE):
    """Load or create a skip-list file and return a set of lowercase usernames."""
    if not os.path.isfile(path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write("[deleted]\nautomoderator\n")
    with open(path, 'r', encoding='utf-8') as f:
        return set(line.strip().lower() for line in f if line.strip())

DEFAULT_SKIPS = load_skip_list()

STATUS_CODES = {'deleted': 0, 'active': 1, 'suspended': 2}
STATUS_LABELS = {v: k for k, v in STATUS_CODES.items()}


def get_account_status(author: str) -> int:
    """Return status_code for a Reddit username using the Reddit about endpoint.
    Returns STATUS_CODES['deleted'] if 404, suspended if flagged, otherwise active.
    """
    try:
        resp = SESSION.get(f'https://www.reddit.com/user/{author}/about.json', timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            return STATUS_CODES['suspended'] if data.get('is_suspended') else STATUS_CODES['active']
        elif resp.status_code == 404:
            return STATUS_CODES['deleted']
    except requests.RequestException:
        pass
    return STATUS_CODES['active']


def _try_parse_timestamp_to_date(ts) -> datetime.date | None:
    """Accept int timestamps (seconds) or ISO strings and return date or None."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(ts).date()
        except Exception:
            return None
    if isinstance(ts, str):
        try:
            # remove trailing Z
            return datetime.datetime.fromisoformat(ts.rstrip('Z')).date()
        except Exception:
            return None
    return None


def get_account_info(author: str) -> tuple:
    """Return (status_code, creation_date_str or 'Unknown', last_activity_str or 'Unknown').
    Uses Reddit about.json where possible; falls back to Photon endpoints to find earliest post/comment.
    """
    birth_date = 'Unknown'
    last_activity = 'Unknown'
    data = {}

    # Try official about endpoint first
    try:
        about = SESSION.get(f'https://www.reddit.com/user/{author}/about.json', timeout=REQUEST_TIMEOUT)
        if about.status_code == 200:
            data = about.json().get('data', {})
            status_code = STATUS_CODES['suspended'] if data.get('is_suspended') else STATUS_CODES['active']
        elif about.status_code == 404:
            status_code = STATUS_CODES['deleted']
        else:
            status_code = STATUS_CODES['active']
    except requests.RequestException:
        status_code = STATUS_CODES['active']

    # If active and created_utc present use it
    if status_code == STATUS_CODES['active']:
        ts = data.get('created_utc')
        dt = _try_parse_timestamp_to_date(ts)
        if dt:
            birth_date = dt.strftime('%Y-%m-%d')

    # If deleted or missing birth info, try Photon endpoints (may return posts/comments)
    if birth_date == 'Unknown':
        timestamps = []
        for endpoint in (
            f'https://arctic-shift.photon-reddit.com/api/posts/search?author={author}&sort=asc',
            f'https://arctic-shift.photon-reddit.com/api/comments/search?author={author}&sort=asc',
        ):
            try:
                resp = SESSION.get(endpoint, timeout=REQUEST_TIMEOUT)
                if not resp.ok:
                    continue
                payload = resp.json()
                items = payload.get('data', payload) if isinstance(payload, dict) else payload
                if isinstance(items, list) and items:
                    ts = items[0].get('created_utc') or items[0].get('created') or items[0].get('timestamp')
                    dt = _try_parse_timestamp_to_date(ts)
                    if dt:
                        timestamps.append(dt)
            except requests.RequestException:
                continue
        if timestamps:
            birth_date = min(timestamps).strftime('%Y-%m-%d')

    # Last activity similar, request descending
    last_ts = []
    for endpoint in (
        f'https://arctic-shift.photon-reddit.com/api/posts/search?author={author}&sort=desc',
        f'https://arctic-shift.photon-reddit.com/api/comments/search?author={author}&sort=desc',
    ):
        try:
            resp = SESSION.get(endpoint, timeout=REQUEST_TIMEOUT)
            if not resp.ok:
                continue
            payload = resp.json()
            items = payload.get('data', payload) if isinstance(payload, dict) else payload
            if isinstance(items, list) and items:
                ts = items[0].get('created_utc') or items[0].get('created') or items[0].get('timestamp')
                dt = _try_parse_timestamp_to_date(ts)
                if dt:
                    last_ts.append(dt)
        except requests.RequestException:
            continue
    if last_ts:
        last_activity = max(last_ts).strftime('%Y-%m-%d')

    return status_code, birth_date, last_activity


def get_account_creation_date(author: str) -> str:
    """Convenience wrapper returning the creation date string (YYYY-MM-DD) or 'Unknown'."""
    _, date, _ = get_account_info(author)
    return date


# --- GUI Application ---
class GUIApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Author Tools GUI - Creation Year Distribution')

        # State
        self.skip_list = list(DEFAULT_SKIPS)
        self.skip_bots_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True)

        # Existing tabs could be re-used; here we add only the new tab requested
        tab = ttk.Frame(notebook)
        notebook.add(tab, text='Creation Year Distribution')
        self._build_creation_tab(tab)

    def _build_creation_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill='both', expand=True)

        # File selection
        top = ttk.Frame(frame)
        top.pack(fill='x', pady=(0,8))
        ttk.Label(top, text='Usernames TXT file (one username per line):').pack(side='left')
        self.creation_txt_path = tk.StringVar()
        ttk.Entry(top, textvariable=self.creation_txt_path, width=60).pack(side='left', padx=8)
        ttk.Button(top, text='Browse...', command=self._browse_creation_txt).pack(side='left')

        # Controls
        ctrl = ttk.Frame(frame)
        ctrl.pack(fill='x', pady=(0,8))
        self.analyze_btn = ttk.Button(ctrl, text='Analyze', command=self._start_analyze)
        self.analyze_btn.pack(side='left')
        self.progress = ttk.Progressbar(ctrl, mode='determinate', length=300)
        self.progress.pack(side='left', padx=8)
        ttk.Checkbutton(ctrl, text='Skip usernames ending with "bot"', variable=self.skip_bots_var).pack(side='left', padx=8)

        # Distribution & filter area
        mid = ttk.Frame(frame)
        mid.pack(fill='both', expand=True)

        # Left: Tree showing distribution
        left = ttk.Frame(mid)
        left.pack(side='left', fill='both', expand=True)
        ttk.Label(left, text='Year Distribution').pack(anchor='w')
        self.dist_columns = ('Year', 'Count')
        self.dist_tree = ttk.Treeview(left, columns=self.dist_columns, show='headings', height=12)
        for c in self.dist_columns:
            self.dist_tree.heading(c, text=c)
            self.dist_tree.column(c, anchor='w')
        self.dist_tree.pack(fill='both', expand=True, padx=(0,8))

        # Right: Detail tree + dropdown filter
        right = ttk.Frame(mid)
        right.pack(side='left', fill='both', expand=True)
        filter_frame = ttk.Frame(right)
        filter_frame.pack(fill='x')
        ttk.Label(filter_frame, text='Filter by year:').pack(side='left')
        self.year_var = tk.StringVar(value='All')
        self.year_dropdown = ttk.Combobox(filter_frame, values=['All'], textvariable=self.year_var, state='readonly', width=12)
        self.year_dropdown.pack(side='left', padx=6)
        ttk.Button(filter_frame, text='Export Filtered', command=self._export_filtered).pack(side='left', padx=6)

        ttk.Label(right, text='Usernames (filtered)').pack(anchor='w', pady=(6,0))
        detail_cols = ('Username', 'Creation Date', 'Status')
        self.detail_tree = ttk.Treeview(right, columns=detail_cols, show='headings', height=12)
        for c in detail_cols:
            self.detail_tree.heading(c, text=c)
            self.detail_tree.column(c, anchor='w')
        self.detail_tree.pack(fill='both', expand=True)

        # Bind dropdown
        self.year_dropdown.bind('<<ComboboxSelected>>', lambda e: self._apply_year_filter())

        # Store fetched results
        self._all_results = []  # list of dicts: {'username','date','year','status'}

        # Sorting
        for col in ('Username', 'Creation Date', 'Status'):
            self.detail_tree.heading(col, text=col, command=lambda c=col: self._sort_detail_tree(c, False))

        # Double-click opens user profile
        self.detail_tree.bind('<Double-1>', self._on_double_click_user)

    def _browse_creation_txt(self):
        path = filedialog.askopenfilename(filetypes=[('Text files', '*.txt')])
        if path:
            self.creation_txt_path.set(path)

    def _start_analyze(self):
        path = self.creation_txt_path.get()
        if not path or not os.path.isfile(path):
            messagebox.showerror('Missing file', 'Select a valid .txt file containing usernames.')
            return
        # read usernames
        usernames = []
        skip_set = set(self.skip_list)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    u = line.strip()
                    if not u:
                        continue
                    if self.skip_bots_var.get() and u.lower().endswith('bot'):
                        continue
                    if u.lower() in skip_set:
                        continue
                    usernames.append(u)
        except Exception as e:
            messagebox.showerror('Error', f'Failed to read file: {e}')
            return

        if not usernames:
            messagebox.showinfo('No users', 'No usernames found after applying skip rules.')
            return

        # Disable analyze button and run background fetch
        self.analyze_btn.config(state='disabled')
        self.progress.config(maximum=len(usernames), value=0)
        self._all_results.clear()
        threading.Thread(target=self._fetch_creation_dates_thread, args=(usernames,), daemon=True).start()

    def _fetch_creation_dates_thread(self, usernames):
        results = []
        # Use ThreadPoolExecutor for controlled concurrency
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(usernames)))) as ex:
            future_to_user = {ex.submit(self._fetch_single_user, u): u for u in usernames}
            completed = 0
            for fut in as_completed(future_to_user):
                user = future_to_user[fut]
                try:
                    res = fut.result()
                except Exception:
                    res = {'username': user, 'date': 'Unknown', 'year': 'Unknown', 'status': 'active'}
                results.append(res)
                completed += 1
                # update progress bar in main thread
                self.root.after(0, lambda c=completed: self.progress.config(value=c))
        # store and update UI
        self._all_results = sorted(results, key=lambda r: (r['year'] if isinstance(r['year'], int) else 9999, r['username'].lower()))
        self.root.after(0, self._on_results_ready)

    def _fetch_single_user(self, username: str) -> dict:
        """Fetch creation date and status for a single user.
        Returns a dict: {'username','date','year','status'}
        """
        status_code, birth, _ = get_account_info(username)
        status_label = STATUS_LABELS.get(status_code, 'active')
        year = 'Unknown'
        if birth and birth != 'Unknown':
            try:
                year = int(birth.split('-')[0])
            except Exception:
                year = 'Unknown'
        return {'username': username, 'date': birth, 'year': year, 'status': status_label}

    def _on_results_ready(self):
        self.analyze_btn.config(state='normal')
        self.progress.config(value=0)
        # compute distribution
        dist = {}
        for r in self._all_results:
            y = r['year']
            if isinstance(y, int):
                dist[y] = dist.get(y, 0) + 1
            else:
                dist['Unknown'] = dist.get('Unknown', 0) + 1
        # populate distribution tree
        self.dist_tree.delete(*self.dist_tree.get_children())
        years_sorted = sorted([k for k in dist.keys() if k != 'Unknown'])
        for y in years_sorted:
            self.dist_tree.insert('', 'end', values=(y, dist[y]))
        if 'Unknown' in dist:
            self.dist_tree.insert('', 'end', values=('Unknown', dist['Unknown']))

        # populate year dropdown
        dropdown_values = ['All'] + [str(y) for y in years_sorted]
        if 'Unknown' in dist:
            dropdown_values.append('Unknown')
        self.year_dropdown.config(values=dropdown_values)
        self.year_dropdown.set('All')

        # populate detail tree with all results
        self._populate_detail_tree(self._all_results)

    def _populate_detail_tree(self, rows):
        self.detail_tree.delete(*self.detail_tree.get_children())
        for r in rows:
            self.detail_tree.insert('', 'end', values=(r['username'], r['date'], r['status']))

    def _apply_year_filter(self):
        sel = self.year_var.get()
        if sel == 'All':
            filtered = self._all_results
        elif sel == 'Unknown':
            filtered = [r for r in self._all_results if r['year'] == 'Unknown']
        else:
            try:
                y = int(sel)
                filtered = [r for r in self._all_results if r['year'] == y]
            except Exception:
                filtered = self._all_results
        self._populate_detail_tree(filtered)

    def _export_filtered(self):
        sel = self.year_var.get()
        if sel == 'All':
            filtered = self._all_results
        elif sel == 'Unknown':
            filtered = [r for r in self._all_results if r['year'] == 'Unknown']
        else:
            try:
                y = int(sel)
                filtered = [r for r in self._all_results if r['year'] == y]
            except Exception:
                filtered = self._all_results
        if not filtered:
            messagebox.showinfo('No data', 'No usernames to export for the selected year.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files', '*.txt')])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                for r in filtered:
                    f.write(r['username'] + '\n')
            messagebox.showinfo('Saved', f'Exported {len(filtered)} usernames to {path}')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to save file: {e}')

    def _sort_detail_tree(self, col, reverse):
        data = [(self.detail_tree.set(k, col), k) for k in self.detail_tree.get_children('')]
        data.sort(reverse=reverse)
        for index, (_, k) in enumerate(data):
            self.detail_tree.move(k, '', index)
        self.detail_tree.heading(col, command=lambda: self._sort_detail_tree(col, not reverse))

    def _on_double_click_user(self, event):
        sel = self.detail_tree.selection()
        if not sel:
            return
        item = sel[0]
        username = self.detail_tree.item(item, 'values')[0]
        if username:
            webbrowser.open(f'https://reddit.com/user/{username}')


if __name__ == '__main__':
    root = tk.Tk()
    app = GUIApp(root)
    root.mainloop()