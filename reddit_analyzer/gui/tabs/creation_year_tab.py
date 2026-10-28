"""Creation Year Distribution Tab."""

import os
import re
import threading
import datetime
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from reddit_analyzer.config import PAGE_SIZE, STATUS_LABELS
from reddit_analyzer.core.cache import flush_cache
from reddit_analyzer.core.skip_list import DEFAULT_SKIPS
from reddit_analyzer.api.accounts import get_cached_account_info, describe_creation_date, lookup_accounts


class CreationYearTab(ttk.Frame):
    """Tab for analyzing creation year distribution with pagination."""

    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self.creation_txt_path = tk.StringVar()
        self.skip_bots_var = tk.BooleanVar(value=True)

        self._page_index = 0
        self._page_size = PAGE_SIZE
        self._user_pages = []
        self._current_usernames = []
        self._all_results = []
        # Set to stop the background prefetch of upcoming pages
        self._prefetch_cancel = None

        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', pady=(0, 8))
        ttk.Label(top, text='Usernames TXT file (one username per line):').pack(side='left')
        ttk.Entry(top, textvariable=self.creation_txt_path, width=60).pack(side='left', padx=8)
        ttk.Button(top, text='Browse...', command=self._browse_creation_txt).pack(side='left')

        ctrl = ttk.Frame(self)
        ctrl.pack(fill='x', pady=(6, 8))
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
        self.prefetch_label = ttk.Label(ctrl, text='', foreground='gray')
        self.prefetch_label.pack(side='left', padx=8)

        mid = ttk.Frame(self)
        mid.pack(fill='both', expand=True)

        left = ttk.Frame(mid)
        left.pack(side='left', fill='both', expand=True)
        ttk.Label(left, text='Year Distribution (current page only)').pack(anchor='w')
        ttk.Label(left, text='Confirmed = creation date from Reddit; the rest use the year of first activity',
                  foreground='gray').pack(anchor='w')
        dist_cols = ('Year', 'Count', 'Confirmed')
        self.dist_tree = ttk.Treeview(left, columns=dist_cols, show='headings', height=14)
        for c in dist_cols:
            self.dist_tree.heading(c, text=c)
            self.dist_tree.column(c, anchor='w')
        self.dist_tree.pack(fill='both', expand=True, padx=(0, 8))

        right = ttk.Frame(mid)
        right.pack(side='left', fill='both', expand=True)
        filter_frame = ttk.Frame(right)
        filter_frame.pack(fill='x')
        ttk.Label(filter_frame, text='Filter by year:').pack(side='left')
        self.year_var = tk.StringVar(value='All')
        self.year_dropdown = ttk.Combobox(filter_frame, values=['All'], textvariable=self.year_var, state='readonly', width=12)
        self.year_dropdown.pack(side='left', padx=6)
        self.year_var.trace('w', lambda *args: self._apply_year_filter())
        ttk.Button(filter_frame, text='Export Filtered', command=self._export_filtered).pack(side='left', padx=6)

        ttk.Label(right, text='Usernames (filtered)').pack(anchor='w', pady=(6, 0))
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
        self._stop_prefetch()
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
        # The page load takes over: anything the prefetch already cached is reused
        self._stop_prefetch()
        self._current_usernames = list(self._user_pages[page_index])
        # Only one page may load at a time, or a slower earlier fetch overwrites the newer page's results
        self.analyze_btn.config(state='disabled')
        self.prev_btn.config(state='disabled')
        self.next_btn.config(state='disabled')
        self.progress.config(maximum=len(self._current_usernames), value=0)
        self.cache_hits_label.config(text='Cache hits: 0')
        self._all_results.clear()
        threading.Thread(target=self._fetch_page_thread, args=(self._current_usernames,), daemon=True).start()

    def _fetch_page_thread(self, usernames):
        try:
            self._all_results = self._fetch_page_results(usernames)
        finally:
            # Always hand control back to the UI so the buttons are re-enabled
            self.after(0, self._on_page_results_ready)

    def _fetch_page_results(self, usernames):
        cache_hits = sum(1 for u in usernames if get_cached_account_info(u))
        self.after(0, lambda: self.cache_hits_label.config(text=f'Cache hits: {cache_hits}'))
        results = []
        lock = threading.Lock()

        def on_result(username, info):
            with lock:
                results.append(self._make_record(username, info))
                done = len(results)
            self.after(0, lambda: self.progress.config(value=done))

        lookup_accounts(usernames, on_result)
        flush_cache()
        results.sort(key=lambda rr: (rr['year'] if isinstance(rr['year'], int) else 9999, rr['username'].lower()))
        return results

    def _start_prefetch(self, page_index):
        """Look up one page in the background, so Next is quick.

        Only the next page is fetched, not every remaining one: pages you
        never open would be wasted requests to Arctic Shift and Reddit.
        """
        self._stop_prefetch()
        if page_index >= len(self._user_pages):
            return
        cancel = threading.Event()
        self._prefetch_cancel = cancel
        page = list(self._user_pages[page_index])
        label = f'page {page_index + 1} / {len(self._user_pages)}'

        def show(text):
            # Don't let a stopped prefetch overwrite the label of the one that replaced it
            self.after(0, lambda: cancel.is_set() or self.prefetch_label.config(text=text))

        def worker():
            try:
                show(f'Prefetching {label}...')
                if lookup_accounts(page, lambda u, info: None, cancel=cancel):
                    show(f'Next {label} ready')
            finally:
                flush_cache()

        threading.Thread(target=worker, daemon=True).start()

    def _stop_prefetch(self):
        if self._prefetch_cancel is not None:
            self._prefetch_cancel.set()
            self._prefetch_cancel = None
        self.prefetch_label.config(text='')

    @staticmethod
    def _make_record(username, account_info) -> dict:
        status_code, birth, _last, source = account_info
        year = 'Unknown'
        if birth and birth != 'Unknown':
            try:
                year = int(birth.split('-')[0])
            except ValueError:
                pass
        return {'username': username, 'date': birth, 'year': year,
                'status': STATUS_LABELS.get(status_code, 'unknown'), 'source': source}

    def _on_page_results_ready(self):
        self.analyze_btn.config(state='normal')
        self._update_nav_buttons()
        self.progress.config(value=0)
        self._start_prefetch(self._page_index + 1)
        dist = {}
        confirmed = {}
        for r in self._all_results:
            y = r['year'] if isinstance(r['year'], int) else 'Unknown'
            dist[y] = dist.get(y, 0) + 1
            if r.get('source') == 'True':
                confirmed[y] = confirmed.get(y, 0) + 1
        self.dist_tree.delete(*self.dist_tree.get_children())
        years_sorted = sorted([k for k in dist.keys() if k != 'Unknown'])
        for y in years_sorted:
            self.dist_tree.insert('', 'end', values=(y, dist[y], confirmed.get(y, 0)))
        if 'Unknown' in dist:
            self.dist_tree.insert('', 'end', values=('Unknown', dist['Unknown'], 0))
        dropdown_values = ['All'] + [str(y) for y in years_sorted]
        if 'Unknown' in dist:
            dropdown_values.append('Unknown')
        self.year_dropdown.config(values=dropdown_values)
        self.year_dropdown.set('All')
        self._populate_detail_tree(self._all_results)

    def _populate_detail_tree(self, rows):
        self.detail_tree.delete(*self.detail_tree.get_children())
        for r in rows:
            date_display = describe_creation_date(r.get('date', 'Unknown'), r.get('source'))
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
        items = self.detail_tree.get_children('')
        data_list = []
        for it in items:
            val = self.detail_tree.set(it, col)
            if col == 'Creation Date':
                m = re.search(r'\d{4}-\d{2}-\d{2}', val or '')
                try:
                    key = datetime.datetime.strptime(m.group(0), '%Y-%m-%d') if m else datetime.datetime.min
                except ValueError:
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

