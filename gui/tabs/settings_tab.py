"""Settings Tab."""

import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

import reddit_auth
from config import SKIP_LIST_FILE, CREDENTIALS_FILE
from skip_list import load_skip_list

REDDIT_APPS_URL = 'https://www.reddit.com/prefs/apps'


class SettingsTab(ttk.Frame):
    """Tab for managing application settings."""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.skip_list_path = SKIP_LIST_FILE
        self.client_id_var = tk.StringVar()
        self.client_secret_var = tk.StringVar()
        self.reddit_username_var = tk.StringVar()
        self._build_ui()
        self._load_credentials()
        self._load_skip_list()

    def _build_ui(self):
        self._build_reddit_api_view()

        ttk.Label(self, text='Customize Skip List (usernames to ignore):').pack(anchor='w', pady=(0, 8))
        self.textbox = tk.Text(self, height=10, width=60, wrap='word')
        self.textbox.pack(fill='both', expand=True)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', pady=8)
        ttk.Button(btn_frame, text='Save Changes', command=self._save_skip_list).pack(side='left', padx=6)
        ttk.Button(btn_frame, text='Reload', command=self._load_skip_list).pack(side='left', padx=6)
        self.status_label = ttk.Label(self, text='')
        self.status_label.pack(anchor='w', pady=(4, 0))

    def _build_reddit_api_view(self):
        frame = ttk.LabelFrame(self, text='Reddit API login (optional)', padding=8)
        frame.pack(fill='x', pady=(0, 12))

        ttk.Label(frame, wraplength=700, justify='left', text=(
            'Reddit refuses most anonymous lookups, so without a login creation dates are only the first '
            'known activity and account status is unknown. To get real dates and status, create a "script" '
            'app on Reddit and enter its client ID and secret here.'
        )).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 6))
        link = ttk.Label(frame, text=REDDIT_APPS_URL, foreground='blue', cursor='hand2')
        link.grid(row=1, column=0, columnspan=3, sticky='w', pady=(0, 6))
        link.bind('<Button-1>', lambda e: webbrowser.open(REDDIT_APPS_URL))

        fields = (
            ('Client ID:', self.client_id_var, None),
            ('Client secret:', self.client_secret_var, '*'),
            ('Your Reddit username:', self.reddit_username_var, None),
        )
        for i, (label, var, show) in enumerate(fields, start=2):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky='w', padx=(0, 6), pady=2)
            ttk.Entry(frame, textvariable=var, width=40, show=show or '').grid(row=i, column=1, sticky='w', pady=2)
        ttk.Label(frame, text='Leave the secret empty for an "installed app". The username goes in the '
                              'User-Agent, as Reddit\'s API rules ask.',
                  foreground='gray').grid(row=5, column=0, columnspan=3, sticky='w', pady=(2, 6))

        btns = ttk.Frame(frame)
        btns.grid(row=6, column=0, columnspan=3, sticky='w')
        self.test_btn = ttk.Button(btns, text='Save && Test', command=self._save_and_test_credentials)
        self.test_btn.pack(side='left', padx=(0, 6))
        ttk.Button(btns, text='Remove Login', command=self._remove_credentials).pack(side='left')
        self.api_status_label = ttk.Label(frame, text='', wraplength=700, justify='left')
        self.api_status_label.grid(row=7, column=0, columnspan=3, sticky='w', pady=(6, 0))

    def _load_credentials(self):
        creds = reddit_auth.load_credentials()
        self.client_id_var.set(creds['client_id'])
        self.client_secret_var.set(creds['client_secret'])
        self.reddit_username_var.set(creds['username'])
        if creds['client_id']:
            self.api_status_label.config(text='Login saved. Use "Save & Test" to check it.')
        else:
            self.api_status_label.config(text='Not logged in: creation dates are estimates from first activity.')

    def _save_and_test_credentials(self):
        username = self.reddit_username_var.get().strip()
        if username.lower().startswith('u/'):
            username = username[2:]
        creds = {
            'client_id': self.client_id_var.get().strip(),
            'client_secret': self.client_secret_var.get().strip(),
            'username': username,
        }
        if not creds['client_id']:
            messagebox.showerror('Missing client ID', 'Enter the client ID of your Reddit app.')
            return
        try:
            reddit_auth.save_credentials(creds)
        except Exception as e:
            messagebox.showerror('Error', f'Failed to save the login: {e}')
            return
        self.test_btn.config(state='disabled')
        self.api_status_label.config(text=f'Saved to {CREDENTIALS_FILE}. Testing...')

        def worker():
            ok, message = reddit_auth.check_connection()
            self.after(0, lambda: self._on_test_done(ok, message))
        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ok, message):
        self.test_btn.config(state='normal')
        self.api_status_label.config(text=('✓ ' if ok else '✗ ') + message,
                                     foreground='dark green' if ok else 'red')

    def _remove_credentials(self):
        if not messagebox.askyesno('Remove login', 'Remove the saved Reddit API login?'):
            return
        try:
            reddit_auth.save_credentials({'client_id': '', 'client_secret': '', 'username': ''})
        except Exception as e:
            messagebox.showerror('Error', f'Failed to remove the login: {e}')
            return
        self._load_credentials()
        self.api_status_label.config(foreground='')

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
