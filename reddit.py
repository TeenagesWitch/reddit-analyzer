#!/usr/bin/env python3
"""
Author Tools GUI - Integrated
- Tab 1: Unique Username Extractor (union across two JSONL files; each line = username)
- Tab 2: Creation Year Distribution (paged, 1000 per page, persistent cache)

Run: requires Python 3.8+ and `requests` installed.
"""

from gui.main_app import MainApp

if __name__ == '__main__':
    app = MainApp()
    app.mainloop()
