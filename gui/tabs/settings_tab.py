"""Settings Tab."""

import tkinter as tk
from tkinter import messagebox, ttk

from config import SKIP_LIST_FILE
from skip_list import load_skip_list


class SettingsTab(ttk.Frame):
    """Tab for managing application settings."""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.skip_list_path = SKIP_LIST_FILE
        self._build_ui()
        self._load_skip_list()

    def _build_ui(self):
        ttk.Label(self, text='Customize Skip List (usernames to ignore):').pack(anchor='w', pady=(0, 8))
        self.textbox = tk.Text(self, height=15, width=60, wrap='word')
        self.textbox.pack(fill='both', expand=True)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', pady=8)
        ttk.Button(btn_frame, text='Save Changes', command=self._save_skip_list).pack(side='left', padx=6)
        ttk.Button(btn_frame, text='Reload', command=self._load_skip_list).pack(side='left', padx=6)
        self.status_label = ttk.Label(self, text='')
        self.status_label.pack(anchor='w', pady=(4, 0))

    def _load_skip_list(self):
        try:
            with open(self.skip_list_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            self.textbox.delete('1.0', tk.END)
            self.textbox.insert(tk.END, content)
            self.status_label.config(text=f'Loaded skip list from {self.skip_list_path}')
        except Exception as e:
            self.status_label.config(text=f'Error loading skip list: {e}')

    def _save_skip_list(self):
        try:
            content = self.textbox.get('1.0', tk.END).strip()
            with open(self.skip_list_path, 'w', encoding='utf-8') as f:
                f.write(content + '\n')
            # Reload the skip list module's default skips
            import skip_list
            skip_list.DEFAULT_SKIPS.clear()
            skip_list.DEFAULT_SKIPS.update(load_skip_list(self.skip_list_path))
            self.status_label.config(text='Skip list saved and reloaded.')
            messagebox.showinfo('Saved', 'Skip list updated successfully.')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to save skip list: {e}')

