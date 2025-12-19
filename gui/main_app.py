"""Main application window for Reddit Analyzer."""

import tkinter as tk
from tkinter import ttk

from gui.tabs import (
    UniqueUsernameExtractorTab,
    CreationYearTab,
    OverlappingUsersTab,
    SettingsTab,
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

        # Tab 1: Unique Extractor (leftmost as requested)
        extractor_tab = UniqueUsernameExtractorTab(notebook)
        notebook.add(extractor_tab, text='Unique Username Extractor')

        # Tab 2: Creation Year Distribution
        creation_tab = CreationYearTab(notebook)
        notebook.add(creation_tab, text='Creation Year Distribution')

        # Tab 3: Overlapping Users
        overlap_tab = OverlappingUsersTab(notebook)
        notebook.add(overlap_tab, text='Overlapping Users')

        # Tab 4: Settings Tab
        settings_tab = SettingsTab(notebook)
        notebook.add(settings_tab, text='Settings')

