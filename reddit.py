#!/usr/bin/env python3
"""
Author Tools GUI - Integrated
- Tab 1: Unique Username Extractor (union across two JSONL files; each line = username)
- Tab 2: Creation Year Distribution (paged, 1000 per page, persistent cache)

Run: requires Python 3.8+ and `requests` installed.
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

# --- Configuration ---
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'AuthorTools/0.1'})
REQUEST_TIMEOUT = 6
MAX_WORKERS = 12
PAGE_SIZE = 1000
CACHE_FILE = 'creation_cache.json'
SKIP_LIST_FILE = 'skip_list.txt'

# --- Persistent cache helpers ---

def load_persistent_cache(path=CACHE_FILE):
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
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
    except Exception:
        pass

CACHE = load_persistent_cache()
CACHE_LOCK = threading.Lock()

# --- Skip list ---

def load_skip_list(path=SKIP_LIST_FILE):
    if not os.path.isfile(path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write("[deleted]\nautomoderator\n")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return set(line.strip().lower() for line in f if line.strip())
    except Exception:
        return set()

DEFAULT_SKIPS = load_skip_list()

STATUS_CODES = {'deleted': 0, 'active': 1, 'suspended': 2}
STATUS_LABELS = {v: k for k, v in STATUS_CODES.items()}

# --- Network helpers ---

def _try_parse_timestamp_to_date(ts) -> datetime.date | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(ts).date()
        except Exception:
            return None
    if isinstance(ts, str):
        try:
            return datetime.datetime.fromisoformat(ts.rstrip('Z')).date()
        except Exception:
            return None
    return None


def _fetch_about_json(author: str):
    try:
        resp = SESSION.get(f'https://www.reddit.com/user/{author}/about.json', timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json().get('data', {}), 200
        return None, resp.status_code
    except requests.RequestException:
        return None, None


def _fetch_photon_earliest(author: str):
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
        return min(timestamps)
    return None


def get_account_info(author: str):
    """Return (status_code:int, birth_date_str, last_activity_str, source)
    source: 'True' if created_utc used, 'Estimated' if fallback used, 'Unknown' otherwise.
    Persistent global CACHE used.
    """
    lower = author.lower()
    with CACHE_LOCK:
        if lower in CACHE:
            e = CACHE[lower]
            return e.get('status_code', STATUS_CODES['active']), e.get('birth_date','Unknown'), e.get('last_activity','Unknown'), e.get('source','Unknown')

    birth_date = 'Unknown'
    last_activity = 'Unknown'
    source = 'Unknown'

    data, status_code_raw = _fetch_about_json(author)
    if status_code_raw == 200 and isinstance(data, dict):
        status_code = STATUS_CODES['suspended'] if data.get('is_suspended') else STATUS_CODES['active']
    elif status_code_raw == 404:
        status_code = STATUS_CODES['deleted']
    else:
        status_code = STATUS_CODES['active']

    if status_code_raw == 200 and isinstance(data, dict):
        ts = data.get('created_utc')
        dt = _try_parse_timestamp_to_date(ts)
        if dt:
            birth_date = dt.strftime('%Y-%m-%d')
            source = 'True'

    if birth_date == 'Unknown':
        earliest = _fetch_photon_earliest(author)
        if earliest:
            birth_date = earliest.strftime('%Y-%m-%d')
            source = 'Estimated'

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

    with CACHE_LOCK:
        CACHE[lower] = {'status_code': status_code, 'birth_date': birth_date, 'last_activity': last_activity, 'source': source}
        try:
            save_persistent_cache(CACHE)
        except Exception:
            pass

    return status_code, birth_date, last_activity, source

# ---------------------
# Unique Username Extractor Tab (placed first as requested)
# ---------------------
class UniqueUsernameExtractorTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.file1_path = tk.StringVar()
        self.file2_path = tk.StringVar()
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text='JSONL File A:').grid(row=0, column=0, sticky='w')
        ttk.Entry(self, textvariable=self.file1_path, width=50).grid(row=0, column=1)
        ttk.Button(self, text='Browse...', command=lambda: self._browse(self.file1_path)).grid(row=0, column=2)

        ttk.Label(self, text='JSONL File B:').grid(row=1, column=0, sticky='w')
        ttk.Entry(self, textvariable=self.file2_path, width=50).grid(row=1, column=1)
        ttk.Button(self, text='Browse...', command=lambda: self._browse(self.file2_path)).grid(row=1, column=2)

        ttk.Button(self, text='Analyze', command=self._analyze).grid(row=2, column=0, pady=10)

        # Results table (single column)
        self.tree = ttk.Treeview(self, columns=('Username',), show='headings')
        self.tree.heading('Username', text='Username', command=lambda: self._sort_tree())
        self.tree.column('Username', anchor='w')
        self.tree.grid(row=3, column=0, columnspan=3, sticky='nsew')
        self.rowconfigure(3, weight=1)

        ttk.Button(self, text='Export', command=self._export).grid(row=4, column=0, pady=6)

    def _browse(self, var):
        path = filedialog.askopenfilename(filetypes=[('JSONL files', '*.jsonl')])
        if path:
            var.set(path)

    def _extract_usernames(self, path):
        usernames = set()
        try:
            import json
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    author = obj.get('author')
                    if not author or author.lower() in ('[deleted]', 'automoderator'):
                        continue
                    usernames.add(author)
        except Exception:
            return None
        return usernames

    def _analyze(self):
        p1 = self.file1_path.get()
        p2 = self.file2_path.get()
        if not os.path.isfile(p1) or not os.path.isfile(p2):
            messagebox.showerror('Invalid files', 'Select valid JSONL files for both A and B.')
            return
        usersA = self._extract_usernames(p1)
        usersB = self._extract_usernames(p2)
        if usersA is None or usersB is None:
            messagebox.showerror('Error', 'Failed to read JSONL files.')
            return
        combined = sorted(usersA.union(usersB))
        # populate tree
        for row in self.tree.get_children():
            self.tree.delete(row)
        for u in combined:
            self.tree.insert('', 'end', values=(u,))

    def _sort_tree(self):
        data = [(self.tree.set(k, 'Username'), k) for k in self.tree.get_children('')]
        data.sort()
        for index, (_, k) in enumerate(data):
            self.tree.move(k, '', index)

    def _export(self):
        if not self.tree.get_children():
            messagebox.showerror('Error', 'No data to export.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files','*.txt')])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                for r in self.tree.get_children():
                    f.write(self.tree.set(r, 'Username') + '\n')
            messagebox.showinfo('Exported', f'Exported {len(self.tree.get_children())} usernames to {path}')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to export: {e}')

# ---------------------
# Creation Year Distribution Tab (paged)
# ---------------------
class CreationYearTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self.creation_txt_path = tk.StringVar()
        self.skip_bots_var = tk.BooleanVar(value=True)

        self._page_index = 0
        self._page_size = PAGE_SIZE
        self._user_pages = []
        self._current_usernames = []
        self._all_results = []

        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', pady=(0,8))
        ttk.Label(top, text='Usernames TXT file (one username per line):').pack(side='left')
        ttk.Entry(top, textvariable=self.creation_txt_path, width=60).pack(side='left', padx=8)
        ttk.Button(top, text='Browse...', command=self._browse_creation_txt).pack(side='left')

        ctrl = ttk.Frame(self)
        ctrl.pack(fill='x', pady=(6,8))
        self.analyze_btn = ttk.Button(ctrl, text='Analyze', command=self._start_analyze)
        self.analyze_btn.pack(side='left')
        self.prev_btn = ttk.Button(ctrl, text='Prev', state='disabled', command=self._prev_page)
        self.prev_btn.pack(side='left', padx=4)
        self.next_btn = ttk.Button(ctrl, text='Next', state='disabled', command=self._next_page)
        self.next_btn.pack(side='left', padx=4)

        self.progress = ttk.Progressbar(ctrl, mode='determinate', length=260)
        self.progress.pack(side='left', padx=8)
        self.cache_hits_label = ttk.Label(ctrl, text='Cache hits: 0')
        self.cache_hits_label.pack(side='left', padx=8)
        ttk.Checkbutton(ctrl, text='Skip usernames ending with "bot"', variable=self.skip_bots_var).pack(side='left', padx=8)

        mid = ttk.Frame(self)
        mid.pack(fill='both', expand=True)

        left = ttk.Frame(mid)
        left.pack(side='left', fill='both', expand=True)
        ttk.Label(left, text='Year Distribution (current page only)').pack(anchor='w')
        self.dist_tree = ttk.Treeview(left, columns=('Year', 'Count'), show='headings', height=14)
        for c in ('Year','Count'):
            self.dist_tree.heading(c, text=c)
            self.dist_tree.column(c, anchor='w')
        self.dist_tree.pack(fill='both', expand=True, padx=(0,8))

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
        self.detail_tree = ttk.Treeview(right, columns=detail_cols, show='headings', height=14)
        for c in detail_cols:
            self.detail_tree.heading(c, text=c, command=lambda col=c: self._sort_detail_tree(col, False))
            self.detail_tree.column(c, anchor='w')
        self.detail_tree.pack(fill='both', expand=True)
        self.detail_tree.bind('<Double-1>', self._on_double_click_user)

        self.page_label = ttk.Label(self, text='Page: 0 / 0')
        self.page_label.pack(anchor='e')

    def _browse_creation_txt(self):
        path = filedialog.askopenfilename(filetypes=[('Text files', '*.txt')])
        if path:
            self.creation_txt_path.set(path)

    def _init_pages_from_file(self, path: str):
        pages = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
        except Exception as e:
            messagebox.showerror('Error', f'Failed to read file: {e}')
            return []
        skip_set = set(DEFAULT_SKIPS)
        filtered = []
        for u in lines:
            if self.skip_bots_var.get() and u.lower().endswith('bot'):
                continue
            if u.lower() in skip_set:
                continue
            filtered.append(u)
        for i in range(0, len(filtered), self._page_size):
            pages.append(filtered[i:i + self._page_size])
        return pages

    def _start_analyze(self):
        path = self.creation_txt_path.get()
        if not path or not os.path.isfile(path):
            messagebox.showerror('Missing file', 'Select a valid .txt file containing usernames.')
            return
        self._user_pages = self._init_pages_from_file(path)
        self._page_index = 0
        if not self._user_pages:
            messagebox.showinfo('No users', 'No usernames found after applying skip rules.')
            return
        self._update_nav_buttons()
        self._load_page(self._page_index)

    def _update_nav_buttons(self):
        total = len(self._user_pages)
        self.page_label.config(text=f'Page: {self._page_index + 1} / {total}')
        self.prev_btn.config(state='normal' if self._page_index > 0 else 'disabled')
        self.next_btn.config(state='normal' if (self._page_index + 1) < total else 'disabled')

    def _prev_page(self):
        if self._page_index > 0:
            self._page_index -= 1
            self._update_nav_buttons()
            self._load_page(self._page_index)

    def _next_page(self):
        if (self._page_index + 1) < len(self._user_pages):
            self._page_index += 1
            self._update_nav_buttons()
            self._load_page(self._page_index)

    def _load_page(self, page_index: int):
        self._current_usernames = list(self._user_pages[page_index])
        self.analyze_btn.config(state='disabled')
        self.progress.config(maximum=len(self._current_usernames), value=0)
        self.cache_hits_label.config(text='Cache hits: 0')
        self._all_results.clear()
        threading.Thread(target=self._fetch_page_thread, args=(self._current_usernames,), daemon=True).start()

    def _fetch_page_thread(self, usernames):
        results = []
        cache_hits = 0
        users_to_fetch = []
        with CACHE_LOCK:
            for u in usernames:
                lower = u.lower()
                if lower in CACHE:
                    entry = CACHE[lower]
                    results.append({
                        'username': u,
                        'date': entry.get('birth_date','Unknown'),
                        'year': int(entry['birth_date'].split('-')[0]) if entry.get('birth_date') and entry['birth_date'] != 'Unknown' else 'Unknown',
                        'status': STATUS_LABELS.get(entry.get('status_code', STATUS_CODES['active']), 'active'),
                        'source': entry.get('source','Unknown')
                    })
                    cache_hits += 1
                else:
                    users_to_fetch.append(u)
        self.after(0, lambda: self.cache_hits_label.config(text=f'Cache hits: {cache_hits}'))
        if users_to_fetch:
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, max(1, len(users_to_fetch)))) as ex:
                fut_map = {ex.submit(self._fetch_single_user_record, u): u for u in users_to_fetch}
                completed = 0
                for fut in as_completed(fut_map):
                    u = fut_map[fut]
                    try:
                        rec = fut.result()
                    except Exception:
                        rec = {'username': u, 'date': 'Unknown', 'year': 'Unknown', 'status': 'active', 'source': 'Unknown'}
                    results.append(rec)
                    completed += 1
                    self.after(0, lambda c=completed + cache_hits: self.progress.config(value=c))
        normalized = []
        for r in results:
            y = r.get('year','Unknown')
            if isinstance(y, int):
                normalized.append(r)
            else:
                try:
                    normalized.append({**r, 'year': int(str(y))})
                except Exception:
                    normalized.append({**r, 'year': 'Unknown'})
        normalized.sort(key=lambda rr: (rr['year'] if isinstance(rr['year'], int) else 9999, rr['username'].lower()))
        self._all_results = normalized
        self.after(0, self._on_page_results_ready)

    def _fetch_single_user_record(self, username: str) -> dict:
        status_code, birth, last, source = get_account_info(username)
        status_label = STATUS_LABELS.get(status_code, 'active')
        year = 'Unknown'
        if birth and birth != 'Unknown':
            try:
                year = int(birth.split('-')[0])
            except Exception:
                year = 'Unknown'
        return {'username': username, 'date': birth, 'year': year, 'status': status_label, 'source': source}

    def _on_page_results_ready(self):
        self.analyze_btn.config(state='normal')
        self.progress.config(value=0)
        dist = {}
        for r in self._all_results:
            y = r['year']
            if isinstance(y, int):
                dist[y] = dist.get(y, 0) + 1
            else:
                dist['Unknown'] = dist.get('Unknown', 0) + 1
        self.dist_tree.delete(*self.dist_tree.get_children())
        years_sorted = sorted([k for k in dist.keys() if k != 'Unknown'])
        for y in years_sorted:
            self.dist_tree.insert('', 'end', values=(y, dist[y]))
        if 'Unknown' in dist:
            self.dist_tree.insert('', 'end', values=('Unknown', dist['Unknown']))
        dropdown_values = ['All'] + [str(y) for y in years_sorted]
        if 'Unknown' in dist:
            dropdown_values.append('Unknown')
        self.year_dropdown.config(values=dropdown_values)
        self.year_dropdown.set('All')
        self._populate_detail_tree(self._all_results)

    def _populate_detail_tree(self, rows):
        self.detail_tree.delete(*self.detail_tree.get_children())
        for r in rows:
            date_val = r.get('date','Unknown')
            if date_val and date_val != 'Unknown' and r.get('source') != 'True':
                date_display = f"{date_val} (estimated)"
            else:
                date_display = date_val
            self.detail_tree.insert('', 'end', values=(r['username'], date_display, r['status']))

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
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files','*.txt')])
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
        items = self.detail_tree.get_children('')
        data_list = []
        for it in items:
            val = self.detail_tree.set(it, col)
            if col == 'Creation Date':
                v = val.split(' ')[0] if val else ''
                try:
                    key = datetime.datetime.strptime(v, '%Y-%m-%d') if v and v != 'Unknown' else datetime.datetime.min
                except Exception:
                    key = datetime.datetime.min
            else:
                key = val.lower() if isinstance(val, str) else val
            data_list.append((key, it))
        data_list.sort(reverse=reverse, key=lambda t: t[0])
        for index, (_, it) in enumerate(data_list):
            self.detail_tree.move(it, '', index)
        self.detail_tree.heading(col, command=lambda: self._sort_detail_tree(col, not reverse))

    def _on_double_click_user(self, event):
        sel = self.detail_tree.selection()
        if not sel:
            return
        item = sel[0]
        username = self.detail_tree.item(item, 'values')[0]
        if username:
            webbrowser.open(f'https://reddit.com/user/{username}')

# ---------------------
# Overlapping Users Tab
# ---------------------
class OverlappingUsersTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.file_paths = [tk.StringVar() for _ in range(5)]
        self.year_var = tk.StringVar(value='All')
        self.results = []
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text='Select 2 to 5 TXT files containing Reddit usernames:').grid(row=0, column=0, columnspan=3, sticky='w', pady=(0,8))
        for i in range(5):
            ttk.Label(self, text=f'File {i+1}:').grid(row=i+1, column=0, sticky='w')
            ttk.Entry(self, textvariable=self.file_paths[i], width=50).grid(row=i+1, column=1)
            ttk.Button(self, text='Browse...', command=lambda v=self.file_paths[i]: self._browse(v)).grid(row=i+1, column=2)

        ttk.Button(self, text='Find Overlapping Users', command=self._start_analyze).grid(row=6, column=0, pady=10)

        # Progress bar and status
        progress_frame = ttk.Frame(self)
        progress_frame.grid(row=7, column=0, columnspan=3, sticky='w', pady=(4,4))
        ttk.Label(progress_frame, text='Progress:').pack(side='left', padx=(0,6))
        self.progress = ttk.Progressbar(progress_frame, mode='determinate', length=300)
        self.progress.pack(side='left', padx=(0,8))
        self.status_label = ttk.Label(progress_frame, text='Idle')
        self.status_label.pack(side='left')

        filter_frame = ttk.Frame(self)
        filter_frame.grid(row=8, column=0, columnspan=3, sticky='w', pady=(4,4))
        ttk.Label(filter_frame, text='Filter by Year:').pack(side='left')
        self.year_dropdown = ttk.Combobox(filter_frame, values=['All'], textvariable=self.year_var, state='readonly', width=12)
        self.year_dropdown.pack(side='left', padx=6)
        ttk.Button(filter_frame, text='Apply Filter', command=self._apply_year_filter).pack(side='left', padx=6)
        ttk.Button(filter_frame, text='Export Filtered', command=self._export_filtered).pack(side='left', padx=6)

        columns = ('Username', 'Count', 'Creation Date', 'Year', 'Status')
        self.tree = ttk.Treeview(self, columns=columns, show='headings')
        for c in columns:
            self.tree.heading(c, text=c, command=lambda col=c: self._sort_tree(col, False))
            self.tree.column(c, anchor='w', width=150)
        self.tree.grid(row=9, column=0, columnspan=3, sticky='nsew')
        self.tree.bind('<Double-1>', self._on_double_click_user)

        self.rowconfigure(9, weight=1)
        self.columnconfigure(1, weight=1)

    def _browse(self, var):
        path = filedialog.askopenfilename(filetypes=[('Text files', '*.txt')])
        if path:
            var.set(path)

    def _extract_usernames(self, path):
        usernames = set()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    u = line.strip()
                    if u and u.lower() not in ('[deleted]', 'automoderator'):
                        usernames.add(u)
        except Exception:
            return set()
        return usernames

    def _start_analyze(self):
        valid_paths = [v.get() for v in self.file_paths if os.path.isfile(v.get())]
        if len(valid_paths) < 2:
            messagebox.showerror('Error', 'Select at least two valid TXT files.')
            return

        datasets = [self._extract_usernames(p) for p in valid_paths]
        if not all(datasets):
            messagebox.showerror('Error', 'Failed to read one or more TXT files.')
            return

        overlap_counts = {}
        for dataset in datasets:
            for user in dataset:
                overlap_counts[user] = overlap_counts.get(user, 0) + 1

        overlapping = [u for u, c in overlap_counts.items() if c > 1]
        if not overlapping:
            messagebox.showinfo('No Overlap', 'No overlapping usernames found.')
            return

        self.progress.config(maximum=len(overlapping), value=0)
        self.status_label.config(text='Fetching creation dates...')
        threading.Thread(target=self._fetch_creation_dates, args=(overlapping, overlap_counts), daemon=True).start()

    def _fetch_creation_dates(self, usernames, overlap_counts):
        results = []
        total = len(usernames)
        completed = 0

        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(usernames))) as ex:
            futures = {ex.submit(get_account_info, u): u for u in usernames}
            for fut in as_completed(futures):
                u = futures[fut]
                try:
                    status_code, birth, _, _ = fut.result()
                    year = 'Unknown'
                    if birth and birth != 'Unknown':
                        try:
                            year = int(birth.split('-')[0])
                        except Exception:
                            pass
                    status_label = STATUS_LABELS.get(status_code, 'active')
                    results.append({'username': u, 'count': overlap_counts[u], 'date': birth, 'year': year, 'status': status_label})
                except Exception:
                    results.append({'username': u, 'count': overlap_counts[u], 'date': 'Unknown', 'year': 'Unknown', 'status': 'active'})

                completed += 1
                self.after(0, lambda c=completed: self._update_progress(c, total))

        results.sort(key=lambda x: (x['year'] if isinstance(x['year'], int) else 9999, x['username'].lower()))
        self.results = results
        self.after(0, self._populate_table)

    def _update_progress(self, completed, total):
        self.progress.config(value=completed)
        self.status_label.config(text=f'{completed}/{total} processed')
        if completed >= total:
            self.status_label.config(text='Completed')

    def _populate_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        years = set()
        for r in self.results:
            years.add(str(r['year']))
            self.tree.insert('', 'end', values=(r['username'], r['count'], r['date'], r['year'], r['status']))

        dropdown_values = ['All'] + sorted([y for y in years if y != 'Unknown'])
        if 'Unknown' in years:
            dropdown_values.append('Unknown')
        self.year_dropdown.config(values=dropdown_values)
        self.year_dropdown.set('All')

    def _apply_year_filter(self):
        sel = self.year_var.get()
        for row in self.tree.get_children():
            self.tree.delete(row)
        if sel == 'All':
            data = self.results
        else:
            data = [r for r in self.results if str(r['year']) == sel]
        for r in data:
            self.tree.insert('', 'end', values=(r['username'], r['count'], r['date'], r['year'], r['status']))

    def _export_filtered(self):
        sel = self.year_var.get()
        if sel == 'All':
            data = self.results
        else:
            data = [r for r in self.results if str(r['year']) == sel]
        if not data:
            messagebox.showinfo('No data', 'No usernames to export for the selected year.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files','*.txt')])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                for r in data:
                    f.write(f"{r['username']}\t{r['count']}\t{r['date']}\t{r['year']}\t{r['status']}\n")
            messagebox.showinfo('Saved', f'Exported {len(data)} usernames to {path}')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to save file: {e}')

    def _on_double_click_user(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        username = self.tree.item(item, 'values')[0]
        if username:
            webbrowser.open(f'https://www.reddit.com/user/{username}')

    def _sort_tree(self, col, reverse):
        data = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        if col == 'Count':
            data.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0, reverse=reverse)
        elif col == 'Year':
            data.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 9999, reverse=reverse)
        else:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for index, (_, k) in enumerate(data):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self._sort_tree(col, not reverse))
                
# ---------------------
# Main App
# ---------------------
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Author Tools GUI - Integrated')
        self.geometry('1100x700')
        self._build_ui()

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True)

        # Tab 1: Unique Extractor (leftmost as requested)
        extractor_tab = UniqueUsernameExtractorTab(notebook)
        notebook.add(extractor_tab, text='Unique Username Extractor')

        # Tab 2: Creation Year Distribution
        creation_tab = CreationYearTab(notebook)
        notebook.add(creation_tab, text='Creation Year Distribution')

        # Tab 3: Overlapping Users
        overlap_tab = OverlappingUsersTab(notebook)
        notebook.add(overlap_tab, text='Overlapping Users')

        # Additional tabs from earlier app can be added here if needed

if __name__ == '__main__':
    app = MainApp()
    app.mainloop()