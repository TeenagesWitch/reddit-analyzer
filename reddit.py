#!/usr/bin/env python3
"""
Reddit Analyzer - A comprehensive Reddit analysis tool for OSINT purposes.

Features:
- Subreddit Analysis: Analyze activity and contributors within subreddits
- User Analysis: Analyze individual Reddit user activity patterns
- Creation Year Distribution: Analyze account creation year patterns
- Overlapping Users: Find users present across multiple datasets

Requires Python 3.8+ and dependencies listed in requirements.txt
"""

import sys

# Check Python version
if sys.version_info < (3, 8):
    print("Error: Python 3.8 or higher is required.")
    print(f"Current version: {sys.version}")
    sys.exit(1)

from reddit_analyzer.gui.main_app import MainApp

if __name__ == '__main__':
    app = MainApp()
    app.mainloop()
