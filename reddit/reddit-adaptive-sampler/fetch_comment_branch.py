#!/usr/bin/env python3
"""
Fetch a comment and walk up the parent chain to get ancestors.
"""

import requests
import json
import sys
from reddit_auth import get_authenticated_session


def fetch_comment_by_id(comment_id: str):
    """Fetch a comment by ID."""
    session = get_authenticated_session()
    comment_full_id = f"t1_{comment_id}"
    
    url = "https://oauth.reddit.com/api/info.json"
    params = {"id": comment_full_id}
    
    try:
        response = session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and 'children' in data['data']:
                children = data['data']['children']
                if children:
                    return children[0].get('data', {})
    except Exception as e:
        print(f"Error fetching {comment_id}: {e}")
    return None


def fetch_comment_branch(root_comment_id: str):
    """
    Fetch a comment and all its ancestors up to top-level.
    """
    session = get_authenticated_session()
    collected_comments = {}
    current_id = root_comment_id
    
    print(f"🌳 Fetching comment branch starting from {root_comment_id}...")
    print()
    
    # Walk up the parent chain
    while current_id:
        if current_id in collected_comments:
            print(f"⚠️  Circular reference detected at {current_id}")
            break
        
        print(f"📥 Fetching {current_id}...")
        comment = fetch_comment_by_id(current_id)
        
        if not comment:
            print(f"❌ Could not fetch {current_id}")
            break
        
        collected_comments[current_id] = comment
        
        print(f"   Author: {comment.get('author', 'N/A')}")
        print(f"   Score: {comment.get('score', 'N/A')}")
        print(f"   Parent: {comment.get('parent_id', 'N/A')}")
        print()
        
        # Check parent
        parent_id = comment.get('parent_id', '')
        if not parent_id or parent_id.startswith('t3_'):  # Top-level (post)
            print(f"✅ Reached top-level (post)")
            break
        
        # Extract parent comment ID
        if parent_id.startswith('t1_'):
            current_id = parent_id[3:]  # Remove 't1_' prefix
        else:
            print(f"⚠️  Unexpected parent format: {parent_id}")
            break
    
    return collected_comments


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_comment_branch.py <comment_id>")
        print("Example: python3 fetch_comment_branch.py lb84fge")
        sys.exit(1)
    
    root_id = sys.argv[1]
    
    branch = fetch_comment_branch(root_id)
    
    print("=" * 80)
    print(f"✅ Collected {len(branch)} comments in branch")
    print("=" * 80)
    
    # Save to file
    output_file = f"data/raw/single_post_test/branch_{root_id}.json"
    with open(output_file, 'w') as f:
        json.dump(branch, f, indent=2)
    print(f"💾 Saved to: {output_file}")

