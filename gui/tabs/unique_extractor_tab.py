"""Unique Username Extractor Tab."""

import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class UniqueUsernameExtractorTab(ttk.Frame):
    """Tab for extracting unique usernames from two JSONL files."""

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
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files', '*.txt')])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                for r in self.tree.get_children():
                    f.write(self.tree.set(r, 'Username') + '\n')
            messagebox.showinfo('Exported', f'Exported {len(self.tree.get_children())} usernames to {path}')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to export: {e}')

