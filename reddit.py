#!/usr/bin/env python3
import threading
import json
import os
import webbrowser
import requests
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Persistent HTTP session to reduce overhead
session = requests.Session()

# Skip list file path
SKIP_LIST_FILE = 'skip_list.txt'

def load_skip_list():
    if not os.path.isfile(SKIP_LIST_FILE):
        # Create file with some defaults if missing
        with open(SKIP_LIST_FILE, 'w', encoding='utf-8') as f:
            f.write("[deleted]\nautomoderator\nthesunflowerseeds\nwaitingtobetriggered\nb0trank\n")
    with open(SKIP_LIST_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip().lower() for line in f if line.strip())

def save_skip_list(skip_list):
    with open(SKIP_LIST_FILE, 'w', encoding='utf-8') as f:
        for item in sorted(skip_list):
            f.write(item + '\n')

DEFAULT_SKIPS = load_skip_list()

# Status code mapping
STATUS_CODES = {'deleted': 0, 'active': 1, 'suspended': 2}
STATUS_LABELS = {v: k for k, v in STATUS_CODES.items()}


def get_account_status(author):
    """
    Return status_code for a given Reddit author via Reddit API only.
    """
    headers = {'User-Agent': 'AuthorTools/0.1'}
    try:
        resp = session.get(f'https://www.reddit.com/user/{author}/about.json', headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            return STATUS_CODES['suspended'] if data.get('is_suspended') else STATUS_CODES['active']
        elif resp.status_code == 404:
            return STATUS_CODES['deleted']
    except requests.RequestException:
        pass
    # default to active if uncertain
    return STATUS_CODES['active']


def extract_unique_authors(file_paths):
    unique_authors = set()
    for path in file_paths:
        if not os.path.isfile(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    author = data.get('author')
                    if author:
                        unique_authors.add(author)
                except json.JSONDecodeError:
                    continue
    return sorted(unique_authors)


def load_authors_from_txt(files, skip_list=None, skip_bots=True):
    skip_set = set(skip_list) if skip_list is not None else DEFAULT_SKIPS
    authors = set()
    for path in files:
        if not os.path.isfile(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                author = line.strip()
                if not author:
                    continue
                lower = author.lower()
                if lower in skip_set or (skip_bots and lower.endswith('bot')):
                    continue
                authors.add(author)
    return authors


def get_account_info(author):
    headers = {'User-Agent': 'AuthorTools/0.1'}
    birth_date = 'Unknown'
    last_activity = 'Unknown'
    data = {}

    # Determine status
    try:
        about = session.get(f'https://www.reddit.com/user/{author}/about.json', headers=headers, timeout=5)
        if about.status_code == 200:
            data = about.json().get('data', {})
            status_code = STATUS_CODES['suspended'] if data.get('is_suspended') else STATUS_CODES['active']
        elif about.status_code == 404:
            status_code = STATUS_CODES['deleted']
        else:
            status_code = STATUS_CODES['active']
    except requests.RequestException:
        status_code = STATUS_CODES['active']

    # Birth date
    if status_code == STATUS_CODES['active']:
        ts = data.get('created_utc')
        if isinstance(ts, (int, float)):
            birth_date = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    else:
        timestamps = []
        for endpoint in [
            f'https://arctic-shift.photon-reddit.com/api/posts/search?author={author}&sort=asc',
            f'https://arctic-shift.photon-reddit.com/api/comments/search?author={author}&sort=asc'
        ]:
            try:
                resp = session.get(endpoint, timeout=5)
                if not resp.ok:
                    continue
                payload = resp.json()
                items = payload.get('data', payload) if isinstance(payload, dict) else payload
                if isinstance(items, list) and items:
                    ts = items[0].get('created_utc') or items[0].get('created') or items[0].get('timestamp')
                    if isinstance(ts, (int, float)):
                        timestamps.append(datetime.datetime.fromtimestamp(ts))
                    elif isinstance(ts, str):
                        try:
                            timestamps.append(datetime.datetime.fromisoformat(ts.rstrip('Z')))
                        except ValueError:
                            pass
            except requests.RequestException:
                continue
        if timestamps:
            birth_date = min(timestamps).strftime('%Y-%m-%d')

    # Last activity
    last_timestamps = []
    for endpoint in [
        f'https://arctic-shift.photon-reddit.com/api/posts/search?author={author}&sort=desc',
        f'https://arctic-shift.photon-reddit.com/api/comments/search?author={author}&sort=desc'
    ]:
        try:
            resp = session.get(endpoint, timeout=5)
            if not resp.ok:
                continue
            payload = resp.json()
            items = payload.get('data', payload) if isinstance(payload, dict) else payload
            if isinstance(items, list) and items:
                ts = items[0].get('created_utc') or items[0].get('created') or items[0].get('timestamp')
                if isinstance(ts, (int, float)):
                    last_timestamps.append(datetime.datetime.fromtimestamp(ts))
                elif isinstance(ts, str):
                    try:
                        last_timestamps.append(datetime.datetime.fromisoformat(ts.rstrip('Z')))
                    except ValueError:
                        pass
        except requests.RequestException:
            continue
    if last_timestamps:
        last_activity = max(last_timestamps).strftime('%Y-%m-%d')

    return status_code, birth_date, last_activity


def get_account_creation_date(author):
    _, date, _ = get_account_info(author)
    return date


class GUIApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Author Tools GUI')

        # Extraction vars
        self.jsonl_paths = [tk.StringVar(), tk.StringVar()]
        self.unique_count = tk.StringVar(value='Total unique authors: 0')

        # Overlap vars
        self.txt_set1_paths = tk.StringVar()
        self.txt_set2_paths = tk.StringVar()
        self.txt_set1 = []
        self.txt_set2 = []
        self.overlap_count = tk.StringVar(value='Overlapping authors: 0')
        self.status_filter = tk.StringVar(value='All')  # new status filter

        # Settings
        self.skip_list = list(DEFAULT_SKIPS)
        self.skip_bots = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True)

        tab1 = ttk.Frame(notebook)
        notebook.add(tab1, text='Extract Unique Authors')
        self._build_unique_tab(tab1)

        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text='Find Overlapping Authors')
        self._build_overlap_tab(tab2)

        tab3 = ttk.Frame(notebook)
        notebook.add(tab3, text='Settings')
        self._build_settings_tab(tab3)

    def _build_unique_tab(self, parent):
        # unchanged
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Select two JSONL files:').grid(row=0, column=0, sticky='w')
        for i in range(2):
            ttk.Entry(frame, textvariable=self.jsonl_paths[i], width=50).grid(row=i+1, column=0, pady=5)
            ttk.Button(frame, text='Browse...', command=lambda idx=i: self._browse_jsonl(idx)).grid(row=i+1, column=1)
        ttk.Label(frame, textvariable=self.unique_count).grid(row=3, column=0, pady=10)
        self.extract_btn = ttk.Button(frame, text='Extract & Save', command=self._handle_unique_async)
        self.extract_btn.grid(row=4, column=0, columnspan=2, pady=5)
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.grid(row=5, column=0, columnspan=2, sticky='ew')

    def _browse_jsonl(self, idx):
        path = filedialog.askopenfilename(filetypes=[('JSONL files', '*.jsonl')])
        if path:
            self.jsonl_paths[idx].set(path)

    def _handle_unique_async(self):
        paths = [v.get() for v in self.jsonl_paths]
        if not all(os.path.isfile(p) for p in paths):
            messagebox.showerror('Error', 'Select valid JSONL files.')
            return
        save_path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text', '*.txt')])
        if not save_path:
            return
        self.extract_btn.config(state='disabled')
        self.progress.start(10)
        def task():
            authors = extract_unique_authors(paths)
            with open(save_path, 'w', encoding='utf-8') as f:
                for a in authors:
                    f.write(a + '\n')
            self.root.after(0, lambda: self._on_unique_done(len(authors), save_path))
        threading.Thread(target=task, daemon=True).start()

    def _on_unique_done(self, count, path):
        self.progress.stop()
        self.extract_btn.config(state='normal')
        self.unique_count.set(f'Total unique authors: {count}')
        messagebox.showinfo('Saved', f'Saved to {path}')

    def _build_overlap_tab(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text='TXT file paths for Set 1 (comma-separated):').grid(row=0, column=0, sticky='w')
        ttk.Entry(frame, textvariable=self.txt_set1_paths, width=40).grid(row=1, column=0, pady=5)
        ttk.Button(frame, text='Browse...', command=lambda: self._browse_txt_set(1)).grid(row=1, column=1)

        ttk.Label(frame, text='TXT file paths for Set 2 (comma-separated):').grid(row=2, column=0, sticky='w')
        ttk.Entry(frame, textvariable=self.txt_set2_paths, width=40).grid(row=3, column=0, pady=5)
        ttk.Button(frame, text='Browse...', command=lambda: self._browse_txt_set(2)).grid(row=3, column=1)

        # Status filter options
        ttk.Label(frame, text='Show statuses:').grid(row=4, column=0, sticky='w', pady=(10,0))
        status_options = ['All'] + list(STATUS_CODES.keys())
        status_cb = ttk.Combobox(frame, values=status_options, textvariable=self.status_filter, state='readonly', width=10)
        status_cb.grid(row=4, column=1, sticky='w', pady=(10,0))

        ttk.Label(frame, textvariable=self.overlap_count).grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(frame, text='Compute Overlap', command=self._handle_overlap).grid(row=6, column=0, columnspan=2)

    def _browse_txt_set(self, set_no):
        files = filedialog.askopenfilenames(filetypes=[('Text', '*.txt')])
        if not files:
            return
        if set_no == 1:
            self.txt_set1.clear(); self.txt_set1.extend(files)
            self.txt_set1_paths.set(','.join(files))
        else:
            self.txt_set2.clear(); self.txt_set2.extend(files)
            self.txt_set2_paths.set(','.join(files))

    def _handle_overlap(self):
        if not (self.txt_set1 and self.txt_set2):
            messagebox.showwarning('Missing Files', 'Please input TXT files for both sets.')
            return
        base_overlap = (
            load_authors_from_txt(self.txt_set1, self.skip_list, self.skip_bots.get())
            & load_authors_from_txt(self.txt_set2, self.skip_list, self.skip_bots.get())
        )
        # apply status filter
        filtered = []
        sel = self.status_filter.get()
        for author in sorted(base_overlap):
            code = get_account_status(author)
            label = STATUS_LABELS.get(code, 'active')
            if sel == 'All' or label == sel:
                filtered.append(author)
        count = len(filtered)
        self.overlap_count.set(f'Overlapping authors: {count}')
        if not filtered:
            messagebox.showinfo('No Overlap', 'No overlapping authors with selected status.')
            return
        self._show_overlap_popup(filtered)

    def _show_overlap_popup(self, authors):
        popup = tk.Toplevel(self.root)
        popup.title('Overlapping Authors')
        # existing popup code unchanged...
        filter_frame = ttk.Frame(popup)
        filter_frame.pack(fill='x', padx=10, pady=(10, 0))
        ttk.Label(filter_frame, text='Filter by status:').pack(side='left')
        status_options = ['All'] + list(STATUS_CODES.keys())
        filter_var = tk.StringVar(value='All')
        combobox = ttk.Combobox(filter_frame, values=status_options, textvariable=filter_var, state='readonly', width=10)
        combobox.pack(side='left', padx=(5, 0))

        frame = ttk.Frame(popup, padding=10)
        frame.pack(fill='both', expand=True)
        columns = ('Username', 'Status', 'Birth Date', 'Last Activity')
        tree = ttk.Treeview(frame, columns=columns, show='headings')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor='w')
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)

        all_rows = []
        for author in authors:
            code, birth, last = get_account_info(author)
            all_rows.append((author, STATUS_LABELS.get(code, 'active'), birth, last))

        def populate(status_filter):
            tree.delete(*tree.get_children())
            for user, stat, birth, last in all_rows:
                if status_filter == 'All' or stat == status_filter:
                    tree.insert('', 'end', values=(user, stat, birth, last))
        populate('All')
        combobox.bind('<<ComboboxSelected>>', lambda e: populate(filter_var.get()))

        # sorting and dbl-click as before
        def sort_column(tv, col, reverse=False):
            data_list = [(tv.set(child, col), child) for child in tv.get_children('')]
            if col in ['Birth Date', 'Last Activity']:
                def parse_date(val):
                    try: return datetime.datetime.strptime(val, '%Y-%m-%d')
                    except: return datetime.datetime.min
                data_list.sort(key=lambda t: parse_date(t[0]), reverse=reverse)
            else:
                data_list.sort(key=lambda t: t[0].lower(), reverse=reverse)
            for index, (_, child) in enumerate(data_list):
                tv.move(child, '', index)
            tv.heading(col, command=lambda: sort_column(tv, col, not reverse))
        for col in columns:
            tree.heading(col, text=col, command=lambda _col=col: sort_column(tree, _col, False))
        tree.bind('<Double-1>', lambda e: webbrowser.open(f'https://reddit.com/user/{tree.item(tree.selection()[0],"values")[0]}'))

    def _build_settings_tab(self, parent):
        # unchanged settings tab
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill='both', expand=True)
        ttk.Checkbutton(frame, text='Skip usernames ending with "bot"', variable=self.skip_bots).pack(anchor='w', pady=5)
        ttk.Label(frame, text='Custom Skip List:').pack(anchor='w')
        self.skip_listbox = tk.Listbox(frame, height=6)
        self.skip_listbox.pack(fill='x', pady=5)
        for item in self.skip_list:
            self.skip_listbox.insert('end', item)
        entry_frame = ttk.Frame(frame)
        entry_frame.pack(fill='x', pady=5)
        self.new_skip_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.new_skip_var).pack(side='left', fill='x', expand=True)
        ttk.Button(entry_frame, text='Add', command=self._add_skip).pack(side='left', padx=5)
        ttk.Button(entry_frame, text='Remove Selected', command=self._remove_skip).pack(side='left')

    def _add_skip(self):
        val = self.new_skip_var.get().strip()
        if val and val not in self.skip_list:
            self.skip_list.append(val)
            self.skip_listbox.insert('end', val)
            self.new_skip_var.set('')
            save_skip_list(self.skip_list)

    def _remove_skip(self):
        sel = self.skip_listbox.curselection()
        for i in reversed(sel):
            val = self.skip_listbox.get(i)
            self.skip_list.remove(val)
            self.skip_listbox.delete(i)
            save_skip_list(self.skip_list)

if __name__ == '__main__':
    root = tk.Tk()
    app = GUIApp(root)
    root.mainloop()