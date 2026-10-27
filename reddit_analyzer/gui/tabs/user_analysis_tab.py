"""User Analysis Tab."""

import os
import collections
import tkinter as tk
from tkinter import messagebox, ttk

from reddit_analyzer.gui.widgets.activity_views import ActivityViewsMixin, extract_subreddit, iter_jsonl


class UserAnalysisTab(ActivityViewsMixin, ttk.Frame):
    """Tab for analyzing user activity from JSONL files."""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.file1_path = tk.StringVar()
        self.file2_path = tk.StringVar()
        self.subreddit_counts = collections.defaultdict(int)
        self.activity_by_date = collections.defaultdict(int)
        self.raw_timestamps = []
        self.total_posts = 0
        self.total_comments = 0
        self.username = None
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

        # Left column - Subreddits (takes 40% width)
        left_frame = ttk.Frame(dashboard_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        self._build_subreddit_view(left_frame)

        # Right column - Activity visualizations (takes 60% width)
        right_frame = ttk.Frame(dashboard_frame)
        right_frame.pack(side='right', fill='both', expand=True, padx=(5, 0))

        # Top right - Activity Tracker
        activity_frame = ttk.LabelFrame(right_frame, text='Activity Tracker', padding=5)
        activity_frame.pack(fill='both', expand=True, pady=(0, 5))
        self.activity_year_var = tk.StringVar(value='All')
        self._build_activity_tracker_view(activity_frame)

        # Bottom right - Day by Day Posting Hours Heatmap
        hour_frame = ttk.LabelFrame(right_frame, text='Day by Day Posting Hours Heatmap', padding=5)
        hour_frame.pack(fill='both', expand=True, pady=(5, 0))
        self._build_hour_heatmap_view(hour_frame)

    def _build_stats_view(self, parent):
        """Build the exploratory stats display."""
        self.stats_text = tk.Text(parent, width=40, height=8, wrap='word', state='disabled', font=('Arial', 9))
        self.stats_text.pack(fill='both', expand=True)

    def _build_subreddit_view(self, parent):
        # Label frame for subreddits
        subreddit_frame = ttk.LabelFrame(parent, text='Subreddits (sorted by frequency)', padding=5)
        subreddit_frame.pack(fill='both', expand=True)
        
        # Treeview for subreddits
        self.subreddit_tree = ttk.Treeview(subreddit_frame, columns=('Subreddit', 'Count'), show='headings')
        self.subreddit_tree.heading('Subreddit', text='Subreddit', command=lambda: self._sort_subreddit_tree('Subreddit', False))
        self.subreddit_tree.heading('Count', text='Count', command=lambda: self._sort_subreddit_tree('Count', False))
        self.subreddit_tree.column('Subreddit', anchor='w', width=200)
        self.subreddit_tree.column('Count', anchor='center', width=80)
        
        scrollbar = ttk.Scrollbar(subreddit_frame, orient='vertical', command=self.subreddit_tree.yview)
        self.subreddit_tree.configure(yscrollcommand=scrollbar.set)
        
        self.subreddit_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def _validate_jsonl_structure(self, filepath, expected_type):
        """Validate that JSONL file has the expected structure and extract author.
        
        Args:
            filepath: Path to JSONL file
            expected_type: 'post' or 'comment'
        
        Returns:
            (is_valid, error_message, author_name) tuple
        """
        if not os.path.isfile(filepath):
            return False, f'File not found: {filepath}', None
        
        try:
            sample_count = 0
            author_name = None
            for obj in iter_jsonl(filepath):
                sample_count += 1

                # Extract author name
                author = obj.get('author')
                if author and author.lower() not in ('[deleted]', 'automoderator'):
                    if author_name is None:
                        author_name = author
                    elif author_name.lower() != author.lower():
                        return False, f'File is not a valid user JSONL file', None
                
                if sample_count > 10:  # Check first 10 valid lines
                    break
                
                # Check required fields
                if not obj.get('author'):
                    # Author can be missing for deleted posts, but should exist in structure
                    pass
                
                if not obj.get('created_utc') and not obj.get('created'):
                    return False, f'Missing timestamp field in {filepath}', None
                
                # Check for subreddit field (should exist)
                if not obj.get('subreddit') and not obj.get('subreddit_name_prefixed'):
                    return False, f'Missing subreddit field in {filepath}', None
                
                # Check type-specific fields
                if expected_type == 'post':
                    # Posts should have 'title' or 'is_self'
                    if 'title' not in obj and 'is_self' not in obj:
                        return False, f'File {filepath} does not appear to be a posts file (missing post-specific fields)', None
                
                elif expected_type == 'comment':
                    # Comments should have 'body' and 'link_id'
                    if 'body' not in obj or 'link_id' not in obj:
                        return False, f'File {filepath} does not appear to be a comments file (missing comment-specific fields)', None
        
            if sample_count == 0:
                return False, f'No valid JSON lines found in {filepath}', None
            
            if author_name is None:
                return False, f'Could not determine author from {filepath}. File may contain only deleted posts/comments.', None
            
            return True, None, author_name
        except Exception as e:
            return False, f'Error reading {filepath}: {e}', None

    def _load_jsonl_files(self):
        """Load and parse JSONL files with structure validation."""
        self.subreddit_counts = collections.defaultdict(int)
        self.activity_by_date = collections.defaultdict(int)
        self.raw_timestamps = []  # Store raw datetime objects for timezone conversion
        self.total_posts = 0
        self.total_comments = 0
        self.username = None
        self.date_range = None

        file1 = self.file1_path.get()
        file2 = self.file2_path.get()

        if not file1 or not file2:
            return False

        # Validate file structures and extract authors
        author1 = None
        author2 = None

        if file1:
            is_valid, error_msg, author = self._validate_jsonl_structure(file1, 'post')
            if not is_valid:
                messagebox.showerror('Validation Error', f'File A (Posts) validation failed:\n{error_msg}')
                return False
            author1 = author

        if file2:
            is_valid, error_msg, author = self._validate_jsonl_structure(file2, 'comment')
            if not is_valid:
                messagebox.showerror('Validation Error', f'File B (Comments) validation failed:\n{error_msg}')
                return False
            author2 = author

        # Validate that both files are from the same user
        if file1 and file2 and author1 and author2:
            if author1.lower() != author2.lower():
                messagebox.showerror('Validation Error', 
                    f'User mismatch:\n'
                    f'File A is from user: u/{author1}\n'
                    f'File B is from user: u/{author2}\n\n'
                    f'Both files must be from the same Reddit user.')
                return False
            self.username = author1  # Store username

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
                    # Count posts vs comments
                    if file_type == 'post':
                        self.total_posts += 1
                    elif file_type == 'comment':
                        self.total_comments += 1

                    subreddit = extract_subreddit(obj)
                    if subreddit:
                        self.subreddit_counts[subreddit] += 1

                    self._record_timestamp(obj)
            except Exception as e:
                messagebox.showerror('Error', f'Failed to read {filepath}: {e}')
                return False

        if self.activity_by_date:
            self.date_range = (min(self.activity_by_date), max(self.activity_by_date))

        return (self.total_posts + self.total_comments) > 0

    def _analyze(self):
        p1 = self.file1_path.get()
        p2 = self.file2_path.get()
        
        if not p1 or not p2:
            messagebox.showerror('Error', 'Both JSONL files are required.\nFile A (Posts) and File B (Comments) must be provided.')
            return

        if not self._load_jsonl_files():
            messagebox.showerror('Error', 'Failed to parse JSONL files or no valid data found.')
            return

        # Update all views
        self._update_stats()
        self._update_subreddit_view()
        
        # Update activity tracker (populate year dropdown first)
        self._populate_year_dropdown()
        self._update_activity_tracker()
        
        # Update hour heatmap view (will use current timezone selection)
        self._update_hour_heatmap()

        total_activity = self.total_posts + self.total_comments
        messagebox.showinfo('Analysis Complete', f'Analyzed {total_activity} posts/comments successfully.')

    def _update_stats(self):
        """Calculate and display exploratory statistics."""
        self.stats_text.config(state='normal')
        self.stats_text.delete('1.0', tk.END)
        
        total_activity = self.total_posts + self.total_comments
        if total_activity == 0:
            self.stats_text.insert('1.0', 'No data available')
            self.stats_text.config(state='disabled')
            return
        
        # Format stats with line breaks
        stats_lines = []
        
        # Basic stats
        if self.username:
            stats_lines.append(f'Username:\nu/{self.username}\n')
        stats_lines.append(f'Total Posts:\n{self.total_posts:,}\n')
        stats_lines.append(f'Total Comments:\n{self.total_comments:,}\n')
        stats_lines.append(f'Total Activity:\n{total_activity:,}\n')
        stats_lines.append(f'Unique Subreddits:\n{len(self.subreddit_counts):,}\n')
        
        # Posts per day (PPD)
        if self.date_range:
            days_span = (self.date_range[1] - self.date_range[0]).days + 1
            ppd = total_activity / days_span if days_span > 0 else 0
            stats_lines.append(f'Posts per Day (PPD):\n{ppd:.2f}\n')
            stats_lines.append(f'Date Range:\n{self.date_range[0]} to {self.date_range[1]}\n')
        
        # Posts per hour (PPH)
        if self.date_range:
            days_span = (self.date_range[1] - self.date_range[0]).days + 1
            hours_span = days_span * 24 if days_span > 0 else 1
            pph = total_activity / hours_span if hours_span > 0 else 0
            stats_lines.append(f'Posts per Hour (PPH):\n{pph:.2f}\n')
        
        # Average activity per subreddit
        if len(self.subreddit_counts) > 0:
            avg_per_sub = total_activity / len(self.subreddit_counts)
            stats_lines.append(f'Avg Activity per Sub:\n{avg_per_sub:.2f}\n')
        
        # Posts vs Comments ratio
        if self.total_comments > 0:
            post_ratio = (self.total_posts / total_activity) * 100
            comment_ratio = (self.total_comments / total_activity) * 100
            stats_lines.append(f'Posts: {post_ratio:.1f}%\nComments: {comment_ratio:.1f}%\n')
                
        self.stats_text.insert('1.0', '\n'.join(stats_lines))
        self.stats_text.config(state='disabled')

    def _update_subreddit_view(self):
        # Clear existing items
        for item in self.subreddit_tree.get_children():
            self.subreddit_tree.delete(item)

        # Sort by count (descending)
        sorted_subs = sorted(self.subreddit_counts.items(), key=lambda x: x[1], reverse=True)
        
        for subreddit, count in sorted_subs:
            self.subreddit_tree.insert('', 'end', values=(subreddit, count))

    def _sort_subreddit_tree(self, col, reverse):
        data = [(self.subreddit_tree.set(k, col), k) for k in self.subreddit_tree.get_children('')]
        if col == 'Count':
            data.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0, reverse=reverse)
        else:
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        for index, (_, k) in enumerate(data):
            self.subreddit_tree.move(k, '', index)
        self.subreddit_tree.heading(col, command=lambda: self._sort_subreddit_tree(col, not reverse))

