"""Overlapping Users Tab."""

import os
import re
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import STATUS_LABELS
from cache import flush_cache
from skip_list import DEFAULT_SKIPS
from reddit_api import lookup_accounts, describe_creation_date


class OverlappingUsersTab(ttk.Frame):
    """Tab for finding overlapping users across multiple files."""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.file_paths = [tk.StringVar() for _ in range(5)]
        self.year_var = tk.StringVar(value='All')
        self.results = []
        self._build_ui()

    def _build_ui(self):
        ttk.Label(self, text='Select 2 to 5 TXT files containing Reddit usernames:').grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 8))
        for i in range(5):
            ttk.Label(self, text=f'File {i+1}:').grid(row=i+1, column=0, sticky='w')
            ttk.Entry(self, textvariable=self.file_paths[i], width=50).grid(row=i+1, column=1)
            ttk.Button(self, text='Browse...', command=lambda v=self.file_paths[i]: self._browse(v)).grid(row=i+1, column=2)

        ttk.Button(self, text='Find Overlapping Users', command=self._start_analyze).grid(row=6, column=0, pady=10)

        progress_frame = ttk.Frame(self)
        progress_frame.grid(row=7, column=0, columnspan=3, sticky='w', pady=(4, 4))
        ttk.Label(progress_frame, text='Progress:').pack(side='left', padx=(0, 6))
        self.progress = ttk.Progressbar(progress_frame, mode='determinate', length=300)
        self.progress.pack(side='left', padx=(0, 8))
        self.status_label = ttk.Label(progress_frame, text='Idle')
        self.status_label.pack(side='left')

        filter_frame = ttk.Frame(self)
        filter_frame.grid(row=8, column=0, columnspan=3, sticky='w', pady=(4, 4))
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
        """Return {lowercased username: username as written}; Reddit usernames are case-insensitive."""
        skip_set = set(DEFAULT_SKIPS)
        usernames = {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    u = line.strip()
                    if u and u.lower() not in skip_set and not u.lower().endswith('bot'):
                        usernames.setdefault(u.lower(), u)
        except Exception:
            return {}
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

        num_files = len(datasets)
        
        # Find users that appear in ALL files, comparing lowercased names
        # Start with users from the first file
        overlapping_keys = set(datasets[0])

        # Intersect with each subsequent file to find common users
        for dataset in datasets[1:]:
            overlapping_keys &= dataset.keys()

        if not overlapping_keys:
            messagebox.showinfo('No Overlap', f'No usernames found in all {num_files} files.')
            return

        # Display each user as written in the first file
        overlapping = [datasets[0][k] for k in overlapping_keys]

        # Create overlap_counts dict with all users having count = num_files
        overlap_counts = {u: num_files for u in overlapping}

        self.progress.config(maximum=len(overlapping), value=0)
        self.status_label.config(text=f'Fetching creation dates for {len(overlapping)} users in all {num_files} files...')
        threading.Thread(target=self._fetch_creation_dates, args=(overlapping, overlap_counts), daemon=True).start()

    def _fetch_creation_dates(self, usernames, overlap_counts):
        results = []
        total = len(usernames)
        lock = threading.Lock()

        def on_result(u, info):
            status_code, birth, _, source = info
            year = 'Unknown'
            if birth and birth != 'Unknown':
                try:
                    year = int(birth.split('-')[0])
                except ValueError:
                    pass
            with lock:
                results.append({'username': u, 'count': overlap_counts[u], 'date': birth, 'source': source,
                                'year': year, 'status': STATUS_LABELS.get(status_code, 'unknown')})
                completed = len(results)
            self.after(0, lambda: self._update_progress(completed, total))

        lookup_accounts(usernames, on_result)
        flush_cache()
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
            self.tree.insert('', 'end', values=self._row_values(r))

        dropdown_values = ['All'] + sorted([y for y in years if y != 'Unknown'])
        if 'Unknown' in years:
            dropdown_values.append('Unknown')
        self.year_dropdown.config(values=dropdown_values)
        self.year_dropdown.set('All')

    @staticmethod
    def _row_values(r):
        return (r['username'], r['count'], describe_creation_date(r['date'], r.get('source')), r['year'], r['status'])

    def _apply_year_filter(self):
        sel = self.year_var.get()
        for row in self.tree.get_children():
            self.tree.delete(row)
        if sel == 'All':
            data = self.results
        else:
            data = [r for r in self.results if str(r['year']) == sel]
        for r in data:
            self.tree.insert('', 'end', values=self._row_values(r))

    def _export_filtered(self):
        sel = self.year_var.get()
        if sel == 'All':
            data = self.results
        else:
            data = [r for r in self.results if str(r['year']) == sel]
        if not data:
            messagebox.showinfo('No data', 'No usernames to export for the selected year.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files', '*.txt')])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                for r in data:
                    # Last column says where the date came from: Reddit, or the first known activity
                    date_source = {'True': 'reddit', 'Estimated': 'first_activity'}.get(r.get('source'), 'unknown')
                    f.write(f"{r['username']}\t{r['count']}\t{r['date']}\t{r['year']}\t{r['status']}\t{date_source}\n")
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
        elif col == 'Creation Date':
            # Sort on the date itself, ignoring the '(first activity)' wording around estimates
            def date_key(x):
                m = re.search(r'\d{4}-\d{2}-\d{2}', x[0])
                return m.group(0) if m else '9999'
            data.sort(key=date_key, reverse=reverse)
        else:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for index, (_, k) in enumerate(data):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self._sort_tree(col, not reverse))

