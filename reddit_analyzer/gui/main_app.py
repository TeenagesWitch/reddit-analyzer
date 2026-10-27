"""Main application window for Reddit Analyzer."""

import tkinter as tk
from tkinter import ttk

from reddit_analyzer.gui.tabs import (
    SubredditAnalysisTab,
    CreationYearTab,
    OverlappingUsersTab,
    SettingsTab,
    UserAnalysisTab,
)


class MainApp(tk.Tk):
    """Main application window with tabbed interface."""

    def __init__(self):
        super().__init__()
        self.title('Reddit Analyzer')
        self.geometry('1100x700')
        self._build_ui()

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True)

        # Tab 1: Subreddit Analysis
        subreddit_tab = SubredditAnalysisTab(notebook)
        notebook.add(subreddit_tab, text='Subreddit Analysis')

        # Tab 2: Creation Year Distribution
        creation_tab = CreationYearTab(notebook)
        notebook.add(creation_tab, text='Creation Year Distribution')

        # Tab 3: Overlapping Users
        overlap_tab = OverlappingUsersTab(notebook)
        notebook.add(overlap_tab, text='Overlapping Users')

        # Tab 4: User Analysis
        user_analysis_tab = UserAnalysisTab(notebook)
        notebook.add(user_analysis_tab, text='User Analysis')

        # Tab 5: Settings Tab
        settings_tab = SettingsTab(notebook)
        notebook.add(settings_tab, text='Settings')

