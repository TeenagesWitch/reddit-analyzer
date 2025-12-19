"""Overlapping Users Tab."""

import os
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import MAX_WORKERS, STATUS_LABELS
from skip_list import DEFAULT_SKIPS
from reddit_api import get_account_info


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
        skip_set = set(DEFAULT_SKIPS)
        usernames = set()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    u = line.strip()
                    if u and u.lower() not in skip_set and not u.lower().endswith('bot'):
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
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files', '*.txt')])
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

