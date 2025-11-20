#!/usr/bin/env python3
"""
Fetch a specific Reddit comment by ID using the API.
"""

import requests
import json
import sys
from reddit_auth import get_authenticated_session


def fetch_comment_by_id(comment_id: str, post_id: str = None):
    """
    Fetch a specific comment by ID.
    
    Args:
        comment_id: Reddit comment ID (e.g., 'lb84fge')
        post_id: Optional post ID for context
    
    Returns:
        Comment data if found, None otherwise
    """
    session = get_authenticated_session()
    
    # Try direct API endpoint for a comment
    # Format: https://oauth.reddit.com/api/info.json?id=t1_<comment_id>
    comment_full_id = f"t1_{comment_id}"
    
    url = "https://oauth.reddit.com/api/info.json"
    params = {"id": comment_full_id}
    
    print(f"🔍 Fetching comment {comment_id}...")
    
    try:
        response = session.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'data' in data and 'children' in data['data']:
                children = data['data']['children']
                if children and len(children) > 0:
                    comment_data = children[0].get('data', {})
                    print(f"✅ Found comment {comment_id}")
                    return comment_data
                else:
                    print(f"❌ Comment {comment_id} not found in response")
            else:
                print(f"❌ Unexpected response format")
                print(f"Response: {json.dumps(data, indent=2)[:500]}")
        else:
            print(f"❌ API request failed with status: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ Error fetching comment: {e}")
    
    return None


def fetch_comment_with_context(comment_id: str, post_id: str):
    """
    Fetch a comment with context using the comments endpoint.
    Format: /r/subreddit/comments/{post_id}/comment/{comment_id}/
    """
    session = get_authenticated_session()
    
    # Try the comment permalink endpoint
    url = f"https://oauth.reddit.com/r/millenials/comments/{post_id}/comment/{comment_id}/.json"
    params = {"context": "3"}  # Get 3 levels of context
    
    print(f"🔍 Fetching comment {comment_id} with context...")
    
    try:
        response = session.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Got response for comment {comment_id}")
            return data
        else:
            print(f"❌ Request failed with status: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return None


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_specific_comment.py <comment_id> [post_id]")
        print("Example: python3 fetch_specific_comment.py lb84fge 1dt5y8x")
        sys.exit(1)
    
    comment_id = sys.argv[1]
    post_id = sys.argv[2] if len(sys.argv) > 2 else "1dt5y8x"
    
    print("=" * 80)
    print("Attempt 1: Direct API fetch")
    print("=" * 80)
    result1 = fetch_comment_by_id(comment_id, post_id)
    
    if result1:
        print(f"\nComment data:")
        print(f"  Author: {result1.get('author')}")
        print(f"  Body: {result1.get('body', '')[:200]}...")
        print(f"  Score: {result1.get('score')}")
        print(f"  Parent ID: {result1.get('parent_id')}")
    else:
        print("\n" + "=" * 80)
        print("Attempt 2: Fetch with context")
        print("=" * 80)
        result2 = fetch_comment_with_context(comment_id, post_id)
        
        if result2:
            print(f"\nGot response with context")
            # Save to file for inspection
            output_file = f"data/raw/single_post_test/comment_{comment_id}_context.json"
            with open(output_file, 'w') as f:
                json.dump(result2, f, indent=2)
            print(f"Saved to: {output_file}")

