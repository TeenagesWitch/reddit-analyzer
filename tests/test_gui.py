"""GUI tests. Skipped when Tk can't open a display."""

import collections
import datetime
import json
import tkinter as tk

import pytest

from reddit_analyzer.core.timestamps import parse_timestamp_utc


@pytest.fixture(scope='module')
def app():
    try:
        from reddit_analyzer.gui.main_app import MainApp
        root = MainApp()
    except tk.TclError as e:
        pytest.skip(f'no display for Tk: {e}')
    root.withdraw()
    nb = root.winfo_children()[0]
    tabs = {type(root.nametowidget(t)).__name__: root.nametowidget(t) for t in nb.tabs()}
    yield tabs
    root.destroy()


def write_jsonl(path, rows):
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')


def filled_calendar_rows(canvas):
    """Weekday row index (0=Mon) -> number of filled squares on the activity calendar."""
    rows = collections.Counter()
    for item in canvas.find_all():
        if canvas.type(item) == 'rectangle' and canvas.itemcget(item, 'fill') != '#ebedf0':
            _x0, y0, _x1, _y1 = canvas.coords(item)
            if y0 < 30 + 7 * 14:          # skip the legend below the grid
                rows[int((y0 - 30) // 14)] += 1
    return dict(rows)


@pytest.mark.parametrize('tab_name', ['SubredditAnalysisTab', 'UserAnalysisTab'])
def test_calendar_rows_match_weekdays(app, tab_name, tmp_path, monkeypatch):
    tab = app[tab_name]
    from reddit_analyzer.gui.tabs import subreddit_analysis_tab, user_analysis_tab
    for module in (subreddit_analysis_tab, user_analysis_tab):
        monkeypatch.setattr(module.messagebox, 'showinfo', lambda *a, **k: None)
        monkeypatch.setattr(module.messagebox, 'showerror', lambda *a, **k: None)
    posts, comments = tmp_path / 'p.jsonl', tmp_path / 'c.jsonl'
    # 2025-01-01 is a Wednesday; the string epoch checks numeric-string parsing
    write_jsonl(posts, [
        {'subreddit': 'test', 'author': 'Alice', 'created_utc': '1735689600', 'title': 't'},
        {'subreddit': 'test', 'author': 'Alice', 'created_utc': 1735776000, 'title': 't'},
    ])
    write_jsonl(comments, [{'subreddit': 'test', 'author': 'Alice', 'created_utc': 1736035200,
                            'body': 'b', 'link_id': 'x'}])
    tab.file1_path.set(str(posts))
    tab.file2_path.set(str(comments))
    tab._analyze()
    assert tab.date_range == (datetime.date(2025, 1, 1), datetime.date(2025, 1, 5))
    # Wed Jan 1, Thu Jan 2, Sun Jan 5
    assert sorted(filled_calendar_rows(tab.activity_canvas)) == [2, 3, 6]


def test_heatmap_timezone_switch(app):
    tab = app['UserAnalysisTab']
    tab.raw_timestamps = [parse_timestamp_utc(1735689600)]
    tab.timezone_var.set('Japan')
    tab.timezone_var.set('UTC')


def test_creation_year_labels_and_confirmed_column(app):
    tab = app['CreationYearTab']
    tab._all_results = [tab._make_record('Real', (1, '2015-01-01', 'x', 'True')),
                        tab._make_record('Est', (3, '2019-03-11', 'x', 'Estimated')),
                        tab._make_record('None', (3, 'Unknown', 'x', 'Unknown'))]
    tab._on_page_results_ready()
    tab._stop_prefetch()
    dist = [tab.dist_tree.item(i, 'values') for i in tab.dist_tree.get_children()]
    rows = [tab.detail_tree.item(i, 'values') for i in tab.detail_tree.get_children()]
    assert ('2015', '1', '1') in dist and ('2019', '1', '0') in dist and ('Unknown', '1', '0') in dist
    assert ('Est', '≤ 2019-03-11 (first activity)', 'unknown') in rows


def test_overlap_usernames_are_case_insensitive(app, tmp_path):
    tab = app['OverlappingUsersTab']
    first, second = tmp_path / 'a.txt', tmp_path / 'b.txt'
    first.write_text('SomeUser\nOther\n')
    second.write_text('someuser\n')
    a, b = tab._extract_usernames(str(first)), tab._extract_usernames(str(second))
    assert set(a) & b.keys() == {'someuser'} and a['someuser'] == 'SomeUser'
