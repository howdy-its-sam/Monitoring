#!/usr/bin/env python3
"""
Reddit Adaptive Sampler - Main Entry Point

Usage:
    python main.py <duration_minutes> <threshold> [options]

Examples:
    python main.py 60 10.0                    # Run for 60 minutes
    python main.py 120 10.0 --unauthenticated # Run without Reddit auth
    python main.py 30 5.0 --dir=my_output     # Custom output directory

Arguments:
    duration_minutes: How long to run the scraper (in minutes)
    threshold: Target requests per second

Options:
    --unauthenticated: Run without Reddit OAuth (lower rate limits)
    --dir=<path>: Custom output directory (default: temporal_test)
    --no-bootstrap: Skip bootstrapping from historical data
"""

import os
import sys

# Resolve the project root directory (where this main.py lives)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Add src/ to the Python path so imports work
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

# Change to project root so relative paths work correctly
os.chdir(PROJECT_ROOT)

# Ensure required directories exist
REQUIRED_DIRS = [
    'temporal_test',
    'data',
    'logs',
]

for dir_name in REQUIRED_DIRS:
    dir_path = os.path.join(PROJECT_ROOT, dir_name)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        print(f"📁 Created directory: {dir_name}/")

# Verify required files exist (warn if missing)
REQUIRED_FILES = {
    'subreddit_priorities.txt': 'List of subreddits to monitor (one per line with optional priority)',
    'reddit_credentials.txt': 'Reddit API credentials (see .env.example for format)',
}

for filename, description in REQUIRED_FILES.items():
    filepath = os.path.join(PROJECT_ROOT, filename)
    if not os.path.exists(filepath):
        print(f"⚠️  Missing: {filename}")
        print(f"   {description}")

# Now import and run the unified scraper
if __name__ == '__main__':
    import runpy
    runpy.run_module('unified_scraper', run_name='__main__')
