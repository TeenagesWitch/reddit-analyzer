"""Subreddit Analysis Tab."""

import os
import collections
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from skip_list import DEFAULT_SKIPS
from .activity_views import ActivityViewsMixin, extract_subreddit, iter_jsonl


class SubredditAnalysisTab(ActivityViewsMixin, ttk.Frame):
    """Tab for analyzing subreddits with comprehensive dashboard."""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.file1_path = tk.StringVar()
        self.file2_path = tk.StringVar()
        self.subreddit_counts = collections.defaultdict(int)
        self.usernames = set()
        self.user_contributions = collections.defaultdict(int)  # {username: count}
        self.activity_by_date = collections.defaultdict(int)
        self.raw_timestamps = []
        self.total_posts = 0
        self.date_range = None
        self._build_ui()

    def _build_ui(self):
        # Top section: File selection and Stats side by side
        top_frame = ttk.Frame(self)
        top_frame.pack(fill='x', pady=(0, 10))
        
        # Left side: File inputs
        input_frame = ttk.Frame(top_frame)
        input_frame.pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        ttk.Label(input_frame, text='JSONL File A (Posts):').grid(row=0, column=0, sticky='w', padx=(0, 5))
        ttk.Entry(input_frame, textvariable=self.file1_path, width=50).grid(row=0, column=1, padx=(0, 5))
        ttk.Button(input_frame, text='Browse...', command=lambda: self._browse(self.file1_path)).grid(row=0, column=2)

        ttk.Label(input_frame, text='JSONL File B (Comments):').grid(row=1, column=0, sticky='w', padx=(0, 5), pady=(5, 0))
        ttk.Entry(input_frame, textvariable=self.file2_path, width=50).grid(row=1, column=1, padx=(0, 5), pady=(5, 0))
        ttk.Button(input_frame, text='Browse...', command=lambda: self._browse(self.file2_path)).grid(row=1, column=2, pady=(5, 0))

        ttk.Button(input_frame, text='Analyze', command=self._analyze).grid(row=2, column=0, pady=10)

        # Right side: Stats panel
        stats_frame = ttk.LabelFrame(top_frame, text='Exploratory Stats', padding=5)
        stats_frame.pack(side='right', fill='both', expand=False)
        self._build_stats_view(stats_frame)

        # Dashboard layout - main container
        dashboard_frame = ttk.Frame(self)
        dashboard_frame.pack(fill='both', expand=True)

        # Left column - Lists
        left_frame = ttk.Frame(dashboard_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))

        # Unique usernames panel
        username_frame = ttk.LabelFrame(left_frame, text='Unique Usernames', padding=5)
        username_frame.pack(fill='both', expand=True, pady=(0, 5))
        self._build_username_view(username_frame)

        # Top contributors panel
        contributors_frame = ttk.LabelFrame(left_frame, text='Top 20 Contributors', padding=5)
        contributors_frame.pack(fill='both', expand=True)
        self._build_contributors_view(contributors_frame)

        # Right column - Visualizations
        right_frame = ttk.Frame(dashboard_frame)
        right_frame.pack(side='right', fill='both', expand=True, padx=(5, 0))

        # Activity Tracker
        activity_frame = ttk.LabelFrame(right_frame, text='Activity Tracker', padding=5)
        activity_frame.pack(fill='both', expand=True, pady=(0, 5))
        self.activity_year_var = tk.StringVar(value='All')
        self._build_activity_tracker_view(activity_frame)

        # Day by Day Posting Hours Heatmap
        hour_frame = ttk.LabelFrame(right_frame, text='Day by Day Posting Hours Heatmap', padding=5)
        hour_frame.pack(fill='both', expand=True, pady=(5, 0))
        self._build_hour_heatmap_view(hour_frame)

    def _build_stats_view(self, parent):
        # Use a text widget or multiple labels for better formatting
        self.stats_text = tk.Text(parent, height=8, width=40, wrap='word', font=('Arial', 9), state='disabled')
        self.stats_text.pack(fill='both', expand=True)
        
        # Initial message
        self.stats_text.config(state='normal')
        self.stats_text.insert('1.0', 'Click "Analyze" to see statistics')
        self.stats_text.config(state='disabled')

    def _build_username_view(self, parent):
        # Username list with export
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill='both', expand=True)
        
        self.username_tree = ttk.Treeview(list_frame, columns=('Username',), show='headings', height=8)
        self.username_tree.heading('Username', text='Username', command=lambda: self._sort_username_tree())
        self.username_tree.column('Username', anchor='w')
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.username_tree.yview)
        self.username_tree.configure(yscrollcommand=scrollbar.set)
        
        self.username_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        ttk.Button(parent, text='Export Usernames as TXT', command=self._export_usernames).pack(pady=5)

    def _build_contributors_view(self, parent):
        # Top contributors list
        self.contributors_tree = ttk.Treeview(parent, columns=('Username', 'Posts/Comments'), show='headings', height=8)
        self.contributors_tree.heading('Username', text='Username')
        self.contributors_tree.heading('Posts/Comments', text='Posts/Comments', command=lambda: self._sort_contributors_tree('Posts/Comments', False))
        self.contributors_tree.column('Username', anchor='w', width=200)
        self.contributors_tree.column('Posts/Comments', anchor='center', width=120)
        
        scrollbar = ttk.Scrollbar(parent, orient='vertical', command=self.contributors_tree.yview)
        self.contributors_tree.configure(yscrollcommand=scrollbar.set)
        
        self.contributors_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def _validate_jsonl_structure(self, filepath, expected_type):
        """Validate that JSONL file has the expected structure.
        
        Args:
            filepath: Path to JSONL file
            expected_type: 'post' or 'comment'
        
        Returns:
            (is_valid, error_message, subreddit_name) tuple
        """
        if not os.path.isfile(filepath):
            return False, f'File not found: {filepath}', None
        
        try:
            sample_count = 0
            subreddit_name = None
            for obj in iter_jsonl(filepath):
                sample_count += 1

                # Extract subreddit name
                subreddit = extract_subreddit(obj)

                if subreddit:
                    if subreddit_name is None:
                        subreddit_name = subreddit
                    elif subreddit_name.lower() != subreddit.lower():
                        return False, f'File is not a valid subreddit JSONL file', None
                
                if sample_count > 10:  # Check first 10 valid lines
                    break
                
                # Check required fields
                if not obj.get('subreddit') and not obj.get('subreddit_name_prefixed'):
                    return False, f'Missing subreddit field in {filepath}', None
                
                if not obj.get('author'):
                    # Author can be missing for deleted posts, but should exist in structure
                    pass
                
                if not obj.get('created_utc') and not obj.get('created'):
                    return False, f'Missing timestamp field in {filepath}', None
                
                # Check type-specific fields
                if expected_type == 'post':
                    # Posts should have 'title' or 'selftext' or 'is_self'
                    if 'title' not in obj and 'is_self' not in obj:
                        return False, f'File {filepath} does not appear to be a posts file (missing post-specific fields)', None
                
                elif expected_type == 'comment':
                    # Comments should have 'body' and 'link_id'
                    if 'body' not in obj or 'link_id' not in obj:
                        return False, f'File {filepath} does not appear to be a comments file (missing comment-specific fields)', None
        
            if sample_count == 0:
                return False, f'No valid JSON lines found in {filepath}', None
            
            if subreddit_name is None:
                return False, f'Could not determine subreddit from {filepath}', None
            
            return True, None, subreddit_name
        except Exception as e:
            return False, f'Error reading {filepath}: {e}', None

    def _load_jsonl_files(self):
        """Load and parse JSONL files with structure validation."""
        self.subreddit_counts = collections.defaultdict(int)
        self.usernames = set()
        self.user_contributions = collections.defaultdict(int)
        self.activity_by_date = collections.defaultdict(int)
        self.raw_timestamps = []
        self.total_posts = 0
        self.date_range = None

        file1 = self.file1_path.get()
        file2 = self.file2_path.get()
        
        if not file1 or not file2:
            return False
        
        # Validate file structures and extract subreddits
        subreddit1 = None
        subreddit2 = None
        
        if file1:
            is_valid, error_msg, subreddit = self._validate_jsonl_structure(file1, 'post')
            if not is_valid:
                messagebox.showerror('Validation Error', f'File A (Posts) validation failed:\n{error_msg}')
                return False
            subreddit1 = subreddit
        
        if file2:
            is_valid, error_msg, subreddit = self._validate_jsonl_structure(file2, 'comment')
            if not is_valid:
                messagebox.showerror('Validation Error', f'File B (Comments) validation failed:\n{error_msg}')
                return False
            subreddit2 = subreddit
        
        # Validate that both files are from the same subreddit
        if file1 and file2 and subreddit1 and subreddit2:
            if subreddit1.lower() != subreddit2.lower():
                messagebox.showerror('Validation Error', 
                    f'Subreddit mismatch:\n'
                    f'File A (Posts) is from: r/{subreddit1}\n'
                    f'File B (Comments) is from: r/{subreddit2}\n\n'
                    f'Both files must be from the same subreddit.')
                return False
        
        # Process files
        files_to_process = []
        if file1:
            files_to_process.append((file1, 'post'))
        if file2:
            files_to_process.append((file2, 'comment'))
        
        for filepath, file_type in files_to_process:
            if not os.path.isfile(filepath):
                continue
            try:
                for obj in iter_jsonl(filepath):
                    self.total_posts += 1

                    subreddit = extract_subreddit(obj)
                    if subreddit:
                        self.subreddit_counts[subreddit] += 1

                    # Extract username, honoring the Settings skip list
                    author = obj.get('author')
                    if author and author.lower() != '[deleted]' and author.lower() not in DEFAULT_SKIPS:
                        self.usernames.add(author)
                        self.user_contributions[author] += 1

                    self._record_timestamp(obj)
            except Exception as e:
                messagebox.showerror('Error', f'Failed to read {filepath}: {e}')
                return False

        if self.activity_by_date:
            self.date_range = (min(self.activity_by_date), max(self.activity_by_date))

        return True

    def _analyze(self):
        p1 = self.file1_path.get()
        p2 = self.file2_path.get()
        
        if not p1 or not p2:
            messagebox.showerror('Error', 'Both JSONL files are required.\nFile A (Posts) and File B (Comments) must be provided.')
            return
        
        if not self._load_jsonl_files():
            messagebox.showerror('Error', 'Failed to read JSONL files.')
            return
        
        # Update all views
        self._update_stats()
        self._update_username_view()
        self._update_contributors_view()
        self._populate_year_dropdown()
        self._update_activity_tracker()
        self._update_hour_heatmap()
        
        messagebox.showinfo('Analysis Complete', f'Analyzed {self.total_posts} posts/comments successfully.')

    def _update_stats(self):
        """Calculate and display exploratory statistics."""
        self.stats_text.config(state='normal')
        self.stats_text.delete('1.0', tk.END)
        
        if self.total_posts == 0:
            self.stats_text.insert('1.0', 'No data available')
            self.stats_text.config(state='disabled')
            return
        
        # Format stats with line breaks
        stats_lines = []
        
        # Basic stats
        if self.subreddit_counts:
            sub_name = next(iter(self.subreddit_counts))
            stats_lines.append(f'Subreddit:\n{sub_name}\n')
        stats_lines.append(f'Total Posts/Comments:\n{self.total_posts:,}\n')
        stats_lines.append(f'Unique Usernames:\n{len(self.usernames):,}\n')
        stats_lines.append(f'Unique Subreddits:\n{len(self.subreddit_counts):,}\n')
        
        # Posts per day (PPD)
        if self.date_range:
            days_span = (self.date_range[1] - self.date_range[0]).days + 1
            ppd = self.total_posts / days_span if days_span > 0 else 0
            stats_lines.append(f'Posts per Day (PPD):\n{ppd:.2f}\n')
            stats_lines.append(f'Date Range:\n{self.date_range[0]} to {self.date_range[1]}\n')
        
        # Posts per hour (PPH)
        if self.date_range:
            days_span = (self.date_range[1] - self.date_range[0]).days + 1
            hours_span = days_span * 24 if days_span > 0 else 1
            pph = self.total_posts / hours_span if hours_span > 0 else 0
            stats_lines.append(f'Posts per Hour (PPH):\n{pph:.2f}\n')
        
        # Average posts per user
        if len(self.usernames) > 0:
            avg_per_user = self.total_posts / len(self.usernames)
            stats_lines.append(f'Avg Posts per User:\n{avg_per_user:.2f}\n')
                
        self.stats_text.insert('1.0', '\n'.join(stats_lines))
        self.stats_text.config(state='disabled')

    def _update_username_view(self):
        """Update unique usernames list."""
        for row in self.username_tree.get_children():
            self.username_tree.delete(row)
        
        sorted_users = sorted(self.usernames)
        for u in sorted_users:
            self.username_tree.insert('', 'end', values=(u,))

    def _update_contributors_view(self):
        """Update top 20 contributors list."""
        for row in self.contributors_tree.get_children():
            self.contributors_tree.delete(row)
        
        # Sort by contribution count (descending) and take top 20
        sorted_contributors = sorted(self.user_contributions.items(), key=lambda x: x[1], reverse=True)[:20]
        
        for username, count in sorted_contributors:
            self.contributors_tree.insert('', 'end', values=(username, count))

    def _sort_username_tree(self):
        data = [(self.username_tree.set(k, 'Username'), k) for k in self.username_tree.get_children('')]
        data.sort()
        for index, (_, k) in enumerate(data):
            self.username_tree.move(k, '', index)

    def _sort_contributors_tree(self, col, reverse):
        data = [(self.contributors_tree.set(k, col), k) for k in self.contributors_tree.get_children('')]
        if col == 'Posts/Comments':
            data.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0, reverse=reverse)
        else:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for index, (_, k) in enumerate(data):
            self.contributors_tree.move(k, '', index)
        self.contributors_tree.heading(col, command=lambda: self._sort_contributors_tree(col, not reverse))

    def _export_usernames(self):
        """Export usernames to TXT file."""
        if not self.username_tree.get_children():
            messagebox.showerror('Error', 'No data to export.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files', '*.txt')])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                for r in self.username_tree.get_children():
                    f.write(self.username_tree.set(r, 'Username') + '\n')
            messagebox.showinfo('Exported', f'Exported {len(self.username_tree.get_children())} usernames to {path}')
        except Exception as e:
            messagebox.showerror('Error', f'Failed to export: {e}')
