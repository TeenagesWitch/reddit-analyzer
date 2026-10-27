"""Activity tracker and posting-hours heatmap shared by the JSONL analysis tabs."""

import json
import datetime
import collections
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pytz

from timestamps import parse_timestamp_utc

TIMEZONES = [
    ('UTC', 'UTC'),
    ('US Eastern', 'America/New_York'),
    ('US Central', 'America/Chicago'),
    ('US Mountain', 'America/Denver'),
    ('US Pacific', 'America/Los_Angeles'),
    ('UK', 'Europe/London'),
    ('Central Europe', 'Europe/Berlin'),
    ('Japan', 'Asia/Tokyo'),
    ('Australia Eastern', 'Australia/Sydney'),
]

# GitHub-style intensity scale, lightest to darkest
COLORS = ['#ebedf0', '#c6e48b', '#7bc96f', '#239a3b', '#196127']
LEGEND_LABELS = ['No activity', 'Low', 'Medium', 'High', 'Very High']


def intensity_color(count, max_count):
    """Map a count to one of the five intensity colors."""
    if count == 0 or max_count <= 0:
        return COLORS[0]
    intensity = count / max_count
    if intensity < 0.25:
        return COLORS[1]
    if intensity < 0.5:
        return COLORS[2]
    if intensity < 0.75:
        return COLORS[3]
    return COLORS[4]


def iter_jsonl(filepath):
    """Yield each parseable JSON object in a JSONL file, skipping blank and invalid lines."""
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def extract_subreddit(obj):
    """Return the subreddit name from a post/comment object, or '' if absent."""
    subreddit = obj.get('subreddit')
    if subreddit:
        return subreddit
    subreddit_prefixed = obj.get('subreddit_name_prefixed', '')
    if subreddit_prefixed.startswith('r/'):
        return subreddit_prefixed[2:]
    return subreddit_prefixed


class ActivityViewsMixin:
    """Activity tracker and hour heatmap for tabs that load JSONL activity.

    The tab must set ``self.activity_by_date`` ({date: count}) and
    ``self.raw_timestamps`` (list of aware UTC datetimes) before drawing.
    """

    def _browse(self, var):
        path = filedialog.askopenfilename(filetypes=[('JSONL files', '*.jsonl')])
        if path:
            var.set(path)

    def _record_timestamp(self, obj):
        """Parse an object's timestamp and add it to the activity data. Returns its UTC date or None."""
        ts = obj.get('created_utc') or obj.get('created') or obj.get('timestamp')
        dt_utc = parse_timestamp_utc(ts)
        if dt_utc is None:
            return None
        self.raw_timestamps.append(dt_utc)
        date_key = dt_utc.date()
        self.activity_by_date[date_key] += 1
        return date_key

    def _build_activity_tracker_view(self, parent):
        # Year filter
        filter_frame = ttk.Frame(parent)
        filter_frame.pack(fill='x', pady=(0, 5))
        ttk.Label(filter_frame, text='Filter by Year:').pack(side='left', padx=(0, 5))
        self.activity_year_dropdown = ttk.Combobox(filter_frame, values=['All'], textvariable=self.activity_year_var,
                                                   state='readonly', width=12)
        self.activity_year_dropdown.pack(side='left', padx=(0, 5))
        self.activity_year_var.trace('w', lambda *args: self._update_activity_tracker())

        # Canvas for activity grid (horizontal scroll)
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill='both', expand=True)

        self.activity_canvas = tk.Canvas(canvas_frame, bg='white', height=175)
        scrollbar_activity_h = ttk.Scrollbar(canvas_frame, orient='horizontal', command=self.activity_canvas.xview)
        scrollbar_activity_v = ttk.Scrollbar(canvas_frame, orient='vertical', command=self.activity_canvas.yview)
        self.activity_canvas.configure(xscrollcommand=scrollbar_activity_h.set, yscrollcommand=scrollbar_activity_v.set)

        self.activity_canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar_activity_v.grid(row=0, column=1, sticky='ns')
        scrollbar_activity_h.grid(row=1, column=0, sticky='ew')
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

    def _build_hour_heatmap_view(self, parent):
        # Timezone selection
        tz_frame = ttk.Frame(parent)
        tz_frame.pack(fill='x', pady=(0, 5))
        ttk.Label(tz_frame, text='Timezone:').pack(side='left', padx=(0, 5))

        self.timezone_var = tk.StringVar(value='UTC')
        self.timezone_dropdown = ttk.Combobox(tz_frame, values=[tz[0] for tz in TIMEZONES],
                                              textvariable=self.timezone_var, state='readonly', width=20)
        self.timezone_dropdown.pack(side='left', padx=(0, 5))
        self.timezone_map = dict(TIMEZONES)
        self.selected_timezone = pytz.UTC
        self.timezone_var.trace('w', lambda *args: self._on_timezone_changed())

        # Canvas for hour heatmap
        self.hour_canvas = tk.Canvas(parent, bg='white', height=250)
        self.hour_canvas.pack(fill='both', expand=True)

    def _update_activity_tracker(self):
        """Update activity tracker (GitHub-style calendar)."""
        self.activity_canvas.delete('all')

        if not self.activity_by_date:
            self.activity_canvas.create_text(400, 100, text='No activity data available', fill='gray')
            return

        # "All" shows the most recent year; otherwise the selected year
        selected_year = self.activity_year_var.get()
        if selected_year == 'All':
            display_year = max(date.year for date in self.activity_by_date)
        else:
            try:
                display_year = int(selected_year)
            except (ValueError, TypeError):
                self.activity_canvas.create_text(400, 100, text='Invalid year selection', fill='gray')
                return

        year_filtered = {date: count for date, count in self.activity_by_date.items() if date.year == display_year}
        if not year_filtered:
            self.activity_canvas.create_text(400, 100, text=f'No activity data for year {selected_year}', fill='gray')
            return
        max_activity = max(year_filtered.values())

        year_start = datetime.date(display_year, 1, 1)
        days_in_year = (datetime.date(display_year + 1, 1, 1) - year_start).days
        dates_list = [year_start + datetime.timedelta(days=i) for i in range(days_in_year)]

        # Rows are weekdays (0=Mon, 6=Sun); the first column starts on the
        # Monday on or before Jan 1, so Jan 1 sits in its real weekday row.
        offset = year_start.weekday()
        num_cols = (offset + days_in_year + 6) // 7

        square_size = 12
        spacing = 2
        start_x = 50
        start_y = 30
        row_height = square_size + spacing
        col_width = square_size + spacing

        # Day labels on the left - only Mon, Wed, Fri like GitHub
        day_labels = ['Mon', '', 'Wed', '', 'Fri', '', 'Sun']
        for day_idx in range(7):
            if day_labels[day_idx]:
                self.activity_canvas.create_text(start_x - 25, start_y + day_idx * row_height + square_size // 2,
                                                 text=day_labels[day_idx], anchor='e', font=('Arial', 8))

        def draw_month_label(month, first_col, end_col):
            x_pos = start_x + first_col * col_width + ((end_col - first_col) * col_width) // 2
            month_label = datetime.date(display_year, month, 1).strftime('%b')
            self.activity_canvas.create_text(x_pos, start_y - 15, text=month_label, anchor='n', font=('Arial', 8))

        current_month = None
        month_start_col = 0

        for day_idx, date in enumerate(dates_list):
            slot = offset + day_idx
            row = slot % 7
            col = slot // 7

            if date.month != current_month:
                if current_month is not None:
                    draw_month_label(current_month, month_start_col, col)
                current_month = date.month
                month_start_col = col

            activity = year_filtered.get(date, 0)
            x = start_x + col * col_width
            y = start_y + row * row_height
            rect_id = self.activity_canvas.create_rectangle(
                x, y, x + square_size, y + square_size,
                fill=intensity_color(activity, max_activity), outline='#ffffff', width=1
            )

            if activity > 0:
                def make_callback(d, a):
                    return lambda e: self._show_date_info(d, a)
                self.activity_canvas.tag_bind(rect_id, '<Button-1>', make_callback(date, activity))

        if current_month is not None:
            draw_month_label(current_month, month_start_col, num_cols)

        total_width = num_cols * col_width + start_x + 20
        total_height = 7 * row_height + start_y + 20
        self.activity_canvas.configure(scrollregion=(0, 0, total_width, total_height))

        # Legend
        legend_y = start_y + 7 * row_height + 10
        self.activity_canvas.create_text(start_x, legend_y, text='Less', anchor='w', font=('Arial', 8))
        for i, (color, label) in enumerate(zip(COLORS, LEGEND_LABELS)):
            x = start_x + 100 + i * 80
            self.activity_canvas.create_rectangle(x, legend_y - 5, x + 12, legend_y + 7, fill=color, outline='white')
            self.activity_canvas.create_text(x + 18, legend_y + 1, text=label, anchor='w', font=('Arial', 7))

    def _on_timezone_changed(self):
        """Handle timezone change - recalculate heatmap."""
        tz_name = self.timezone_var.get()
        if tz_name in self.timezone_map:
            try:
                self.selected_timezone = pytz.timezone(self.timezone_map[tz_name])
                self._update_hour_heatmap()
            except Exception:
                pass

    def _update_hour_heatmap(self):
        self.hour_canvas.delete('all')

        if not self.raw_timestamps:
            self.hour_canvas.create_text(400, 125, text='No activity data available', fill='gray')
            return

        # Recalculate hour/day data with current timezone
        hour_day_data = collections.defaultdict(lambda: collections.defaultdict(int))
        for dt_utc in self.raw_timestamps:
            dt_local = dt_utc.astimezone(self.selected_timezone)
            hour_day_data[dt_local.weekday()][dt_local.hour] += 1

        max_count = max((max(day_data.values()) for day_data in hour_day_data.values() if day_data), default=0)
        if max_count == 0:
            self.hour_canvas.create_text(400, 125, text='No activity data available', fill='gray')
            return

        cell_size = 18
        spacing = 2
        start_x = 60
        start_y = 30
        num_hours = 24
        num_days = 7

        day_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

        for day_idx in range(num_days):
            y_pos = start_y + day_idx * (cell_size + spacing) + cell_size // 2
            self.hour_canvas.create_text(start_x - 5, y_pos, text=day_labels[day_idx], anchor='e', font=('Arial', 9))

        for hour in range(0, num_hours, 2):
            x_pos = start_x + hour * (cell_size + spacing) + cell_size // 2
            self.hour_canvas.create_text(x_pos, start_y - 15, text=str(hour), anchor='n', font=('Arial', 8))

        for day_idx in range(num_days):
            day_data = hour_day_data.get(day_idx, {})
            for hour in range(num_hours):
                count = day_data.get(hour, 0)
                x = start_x + hour * (cell_size + spacing)
                y = start_y + day_idx * (cell_size + spacing)
                rect_id = self.hour_canvas.create_rectangle(
                    x, y, x + cell_size, y + cell_size,
                    fill=intensity_color(count, max_count), outline='#ffffff', width=1
                )

                if count > 0:
                    def make_callback(d, h, c):
                        return lambda e: self._show_hour_day_info(d, h, c)
                    self.hour_canvas.tag_bind(rect_id, '<Button-1>', make_callback(day_labels[day_idx], hour, count))

        # Legend
        legend_y = start_y + num_days * (cell_size + spacing) + 15
        self.hour_canvas.create_text(start_x, legend_y, text='Less', anchor='w', font=('Arial', 8))
        for i, (color, label) in enumerate(zip(COLORS, LEGEND_LABELS)):
            x = start_x + 50 + i * 70
            self.hour_canvas.create_rectangle(x, legend_y - 5, x + 12, legend_y + 7, fill=color, outline='white')
            self.hour_canvas.create_text(x + 18, legend_y + 1, text=label, anchor='w', font=('Arial', 7))

        self.hour_canvas.create_text(start_x + (num_hours * (cell_size + spacing)) // 2, legend_y + 20,
                                     text='Hour of Day (0-23)', anchor='n', font=('Arial', 9))

    def _populate_year_dropdown(self):
        """Populate the year dropdown and default it to the most recent year."""
        if not self.activity_by_date:
            return
        years = sorted(set(date.year for date in self.activity_by_date), reverse=True)
        self.activity_year_dropdown.config(values=['All'] + [str(y) for y in years])
        self.activity_year_var.set(str(years[0]))

    def _show_date_info(self, date, activity):
        messagebox.showinfo('Activity Info', f'Date: {date.strftime("%Y-%m-%d")}\nActivity: {activity} posts/comments')

    def _show_hour_day_info(self, day_name, hour, count):
        messagebox.showinfo('Activity Info', f'Day: {day_name}\nHour: {hour:02d}:00\nActivity: {count} posts/comments')
