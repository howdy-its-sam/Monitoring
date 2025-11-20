#!/usr/bin/env python3
"""
Simple script to scrape a single Reddit post
"""

import sys
import os
import json
import time
from datetime import datetime
from reddit_scraper_api import scrape_reddit_post_api, extract_post_id_from_url
from reddit_auth import get_authenticated_session

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scrape_single_post.py <reddit_url> [log_file]")
        print("  If log_file is provided, output will be written there (for background runs)")
        sys.exit(1)
    
    url = sys.argv[1]
    log_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    post_id = extract_post_id_from_url(url)
    
    if not post_id:
        error_msg = f"❌ Could not extract post ID from URL: {url}"
        print(error_msg)
        if log_file:
            with open(log_file, 'a') as f:
                f.write(f"[{datetime.now()}] {error_msg}\n")
        sys.exit(1)
    
    start_time = time.time()
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    start_msg = f"📋 Starting scrape for post ID: {post_id}\n🔗 URL: {url}\n⏰ Started at: {timestamp_str}"
    print(start_msg)
    
    # Create output directory
    output_dir = "data/raw/single_post_test"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{output_dir}/post_{post_id}_{timestamp}.json"
    
    # Get authenticated session for better rate limits
    session = get_authenticated_session()
    
    # Scrape the post with unlimited requests (None = no limit)
    # Will backoff automatically on rate limits until all comments are retrieved
    # Check for sort parameter
    sort = 'confidence'  # default
    for arg in sys.argv:
        if arg.startswith('--sort='):
            sort = arg.split('=')[1]
    
    result = scrape_reddit_post_api(url, output_file=output_file, session=session, max_requests=None, sort=sort)
    
    elapsed_time = time.time() - start_time
    elapsed_minutes = elapsed_time / 60
    
    if result:
        final_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        comment_count = len(result.get('comments', []))
        
        summary = f"""
✅ Scrape complete!
📁 Saved to: {output_file}
📊 Post title: {result.get('post', {}).get('title', 'N/A')}
💬 Comments found: {comment_count}
⏱️  Total time: {elapsed_minutes:.1f} minutes ({elapsed_time:.0f} seconds)
🕐 Completed at: {final_timestamp}
"""
        print(summary)
        
        if log_file:
            with open(log_file, 'a') as f:
                f.write(f"\n{summary}\n")
    else:
        error_msg = f"\n❌ Scrape failed after {elapsed_minutes:.1f} minutes"
        print(error_msg)
        if log_file:
            with open(log_file, 'a') as f:
                f.write(f"{error_msg}\n")
        sys.exit(1)

if __name__ == '__main__':
    main()

