"""Creation Year Distribution Tab."""

import os
import threading
import datetime
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import PAGE_SIZE, MAX_WORKERS, STATUS_LABELS, STATUS_CODES
from cache import CACHE, CACHE_LOCK
from skip_list import DEFAULT_SKIPS
from reddit_api import get_account_info


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

        mid = ttk.Frame(self)
        mid.pack(fill='both', expand=True)

        left = ttk.Frame(mid)
        left.pack(side='left', fill='both', expand=True)
        ttk.Label(left, text='Year Distribution (current page only)').pack(anchor='w')
        self.dist_tree = ttk.Treeview(left, columns=('Year', 'Count'), show='headings', height=14)
        for c in ('Year', 'Count'):
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
                        'date': entry.get('birth_date', 'Unknown'),
                        'year': int(entry['birth_date'].split('-')[0]) if entry.get('birth_date') and entry['birth_date'] != 'Unknown' else 'Unknown',
                        'status': STATUS_LABELS.get(entry.get('status_code', STATUS_CODES['active']), 'active'),
                        'source': entry.get('source', 'Unknown')
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
            y = r.get('year', 'Unknown')
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
            date_val = r.get('date', 'Unknown')
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

