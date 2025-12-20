#!/usr/bin/env python3
"""
Reddit Scraper using Reddit API - Much faster than browser automation
Gets all comments with minimal requests by using Reddit's JSON API endpoints
"""

import requests
import json
import time
import sys
import os
from datetime import datetime
import re
from contextlib import contextmanager

# Global API request counter for rate control
api_request_counter = 0


def increment_request_count():
    """Increment global API request counter."""
    global api_request_counter
    api_request_counter += 1


def get_request_count():
    """Get current API request count."""
    global api_request_counter
    return api_request_counter


def reset_request_count():
    """Reset API request counter (useful for testing)."""
    global api_request_counter
    api_request_counter = 0


@contextmanager
def track_request():
    """Context manager to track API requests."""
    increment_request_count()
    yield

def extract_post_id_from_url(url):
    """Extract Reddit post ID from URL"""
    # Pattern: /comments/{post_id}/title/
    match = re.search(r'/comments/([^/]+)/', url)
    if match:
        return match.group(1)
    return None

def get_reddit_data_recursive(post_id, max_requests=200, session=None, sort='confidence', rate_limiter=None):
    """
    Fetch Reddit post and comments data using recursive API calls
    Gets ALL comments including those hidden in 'more' objects

    Args:
        post_id: Reddit post ID
        max_requests: Maximum number of API requests to make
        session: Optional authenticated requests.Session for OAuth (10x rate limit)
        sort: Sort order for comments ('confidence', 'top', 'new', 'controversial', 'old', 'qa')
        rate_limiter: Optional RateLimiter instance for adaptive limit learning
    """
    link_id = f't3_{post_id}'
    
    # Use oauth.reddit.com for authenticated requests
    if session:
        base_url = f'https://oauth.reddit.com/comments/{post_id}.json'
    else:
        base_url = f'https://www.reddit.com/comments/{post_id}.json'
    
    # Headers for unauthenticated requests only
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    } if not session else {}
    
    all_comments = {}
    more_objects_queue = []
    requests_made = 0
    
    def process_comment(comment_obj):
        """Extract comment data and find nested more objects"""
        if comment_obj.get('kind') == 't1':
            data = comment_obj['data']
            comment_id = data['id']
            
            # Store full comment data
            all_comments[comment_id] = {
                'id': comment_id,
                'parent_id': data.get('parent_id'),
                'author': data.get('author'),
                'body': data.get('body', ''),
                'score': data.get('score'),
                'created_utc': data.get('created_utc'),
                'depth': data.get('depth'),
                'permalink': data.get('permalink'),
                'is_submitter': data.get('is_submitter'),
                'controversiality': data.get('controversiality'),
                'gilded': data.get('gilded'),
                'edited': data.get('edited'),
                'replies': []
            }
            
            # Check for nested replies
            replies = data.get('replies')
            if replies and isinstance(replies, dict):
                if 'data' in replies and 'children' in replies['data']:
                    for child in replies['data']['children']:
                        process_comment(child)
        
        elif comment_obj.get('kind') == 'more':
            data = comment_obj['data']
            children = data.get('children', [])
            if children:
                more_objects_queue.append({
                    'children': children,
                    'parent_id': data.get('parent_id'),
                    'depth': data.get('depth', 0)
                })
    
    try:
        print(f"🌐 Fetching Reddit data recursively for post: {post_id}")

        # Step 1: Initial request with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            if attempt > 0:
                wait_time = 30 * (2 ** attempt)  # Exponential backoff: 30s, 60s, 120s
                print(f"⏳ Waiting {wait_time} seconds before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)

            # Wait for rate limit budget before making request
            if rate_limiter and hasattr(rate_limiter, 'wait_for_budget'):
                rate_limiter.wait_for_budget(1)

            # Use session if provided (OAuth), otherwise use requests directly
            with track_request():
                params = {'limit': 100, 'sort': sort}
                if session:
                    response = session.get(base_url, params=params, timeout=30)
                else:
                    response = requests.get(base_url, headers=headers, params=params, timeout=30)
            requests_made += 1

            # Consume budget and update rate limiter from response headers
            if rate_limiter:
                if hasattr(rate_limiter, 'consume'):
                    rate_limiter.consume(1)
                if hasattr(rate_limiter, 'update_from_headers'):
                    rate_limiter.update_from_headers(response.headers)

            if response.status_code == 200:
                break
            elif response.status_code == 429:
                print(f"⚠️  Rate limited (429) on initial request - attempt {attempt + 1}/{max_retries}")
                if attempt == max_retries - 1:
                    print(f"❌ Initial API request failed after {max_retries} attempts")
                    return None
            else:
                print(f"❌ Initial API request failed with status: {response.status_code}")
                return None
        
        data = response.json()
        post_data = data[0]['data']['children'][0]['data']
        
        # Process initial comments
        comment_data = data[1]['data']
        for item in comment_data['children']:
            process_comment(item)
        
        print(f"📊 Initial: {len(all_comments)} comments, {len(more_objects_queue)} more objects to expand")
        
        # Step 2: Expand all more objects recursively with global adaptive backoff
        iteration = 0
        global_backoff = 2.0  # Start at 2 seconds, can decrease to 0 or increase to max
        max_backoff = 256.0  # Cap at ~4 minutes
        initial_backoff = 2.0  # Reset value when recovering from 0
        
        while more_objects_queue and (max_requests is None or requests_made < max_requests):
            iteration += 1
            more_obj = more_objects_queue.pop(0)
            children_ids = more_obj['children']
            
            # Batch IDs (max 100 per request)
            batch_size = 100
            batch_success = True
            
            for i in range(0, len(children_ids), batch_size):
                if max_requests is not None and requests_made >= max_requests:
                    print(f"⚠️  Reached max request limit ({max_requests})")
                    break
                    
                batch = children_ids[i:i+batch_size]
                
                # Try /api/morechildren endpoint with retry logic
                morechildren_url = 'https://www.reddit.com/api/morechildren.json'
                params = {
                    'link_id': link_id,
                    'children': ','.join(batch),
                    'api_type': 'json',
                    'limit_children': False
                }
                
                # Infinite retry logic with rate-limiter-based pacing
                while True:  # Infinite retry until success
                    try:
                        # Wait for rate limit budget before making request (replaces hardcoded sleep)
                        if rate_limiter and hasattr(rate_limiter, 'wait_for_budget'):
                            rate_limiter.wait_for_budget(1)
                        else:
                            # Fallback to global backoff if no rate limiter
                            if global_backoff > 0.01:
                                time.sleep(global_backoff)

                        # Use session if provided (OAuth), otherwise use requests directly
                        with track_request():
                            if session:
                                # OAuth uses oauth.reddit.com
                                oauth_morechildren_url = 'https://oauth.reddit.com/api/morechildren'
                                response = session.get(oauth_morechildren_url, params=params, timeout=10)
                            else:
                                response = requests.get(morechildren_url, headers=headers, params=params, timeout=10)
                        requests_made += 1

                        # Consume budget and update rate limiter from response headers
                        if rate_limiter:
                            if hasattr(rate_limiter, 'consume'):
                                rate_limiter.consume(1)
                            if hasattr(rate_limiter, 'update_from_headers'):
                                rate_limiter.update_from_headers(response.headers)

                        if response.status_code == 200:
                            result = response.json()
                            if 'json' in result and 'data' in result['json']:
                                things = result['json']['data'].get('things', [])
                                for thing in things:
                                    process_comment(thing)
                            
                            # SUCCESS: Halve the backoff (can go to 0)
                            global_backoff = global_backoff / 2.0
                            if global_backoff > 4.0:  # Only show significant decreases
                                print(f"⬇️  Backoff reduced to {global_backoff:.1f}s")
                            break  # Success, exit retry loop
                            
                        elif response.status_code == 429:
                            # RATE LIMITED: Double the backoff (or reset from 0)
                            if global_backoff < 0.1:
                                global_backoff = initial_backoff  # Jump back to 2s from near-0
                            else:
                                global_backoff = min(global_backoff * 2.0, max_backoff)
                            print(f"⚠️  Rate limited (429) - backoff increased to {global_backoff:.1f}s...")
                            time.sleep(global_backoff)
                            
                        else:
                            print(f"❌ MoreChildren API failed with status: {response.status_code}")
                            break  # Non-429 error, don't retry
                            
                    except Exception as e:
                        print(f"❌ Error in morechildren request: {e}")
                        time.sleep(5)
            
            # If the entire more_obj was processed successfully, don't put it back
            if batch_success:
                if iteration % 10 == 0:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{timestamp}] 📊 Progress: {len(all_comments)} comments collected, {len(more_objects_queue)} more objects remaining")
                    print(f"[{timestamp}] 📈 Requests: {requests_made}, Backoff: {global_backoff:.2f}s")
                    if requests_made > 0:
                        comments_per_request = len(all_comments) / requests_made
                        print(f"[{timestamp}] ⚡ Efficiency: {comments_per_request:.1f} comments/request")
                    print()  # Blank line for spacing
        
        final_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if max_requests is not None and requests_made >= max_requests:
            print(f"[{final_timestamp}] ⚠️  Stopping due to max request limit ({max_requests})")
        elif not more_objects_queue:
            print(f"[{final_timestamp}] ✅ All more objects processed successfully")
        
        print(f"[{final_timestamp}] ✅ Recursive fetch complete: {len(all_comments)} comments after {requests_made} requests")
        
        # Build comment forest
        comment_forest = []
        for comment_id, comment in all_comments.items():
            parent_id = comment['parent_id']
            if parent_id == link_id or parent_id.startswith('t3_'):
                comment_forest.append(comment)
        
        # Attach children to parents
        for comment_id, comment in all_comments.items():
            parent_id = comment['parent_id']
            if parent_id.startswith('t1_'):
                parent_comment_id = parent_id.replace('t1_', '')
                if parent_comment_id in all_comments:
                    all_comments[parent_comment_id]['replies'].append(comment)
        
        # Calculate coverage percentage (handle posts with 0 expected comments)
        expected = post_data.get('num_comments', 0)
        if expected > 0:
            coverage = round(len(all_comments) / expected * 100, 2)
        else:
            coverage = 100.0 if len(all_comments) == 0 else 0.0  # 100% if both are 0, else undefined
        
        return {
            'post_data': post_data,
            'comment_forest': comment_forest,
            'metadata': {
                'total_comments': len(all_comments),
                'top_level_comments': len(comment_forest),
                'api_requests': requests_made,
                'expected_comments': expected,
                'coverage_percent': coverage
            }
        }
        
    except Exception as e:
        print(f"❌ Error in recursive fetch: {e}")
        return None

def create_temporal_comment(comment_data, current_time):
    """Create a comment with temporal tracking structure"""
    return {
        'id': comment_data.get('id'),
        'parent_id': comment_data.get('parent_id'),
        'author': comment_data.get('author'),
        'text_history': [[comment_data.get('body', ''), current_time]] if comment_data.get('body') else [],
        'score_history': [[comment_data.get('score', 0), current_time]],
        'created_utc': comment_data.get('created_utc'),
        'depth': comment_data.get('depth'),
        'permalink': comment_data.get('permalink'),
        'is_submitter': comment_data.get('is_submitter'),
        'controversiality': comment_data.get('controversiality'),
        'gilded': comment_data.get('gilded'),
        'edited': comment_data.get('edited'),
        'deleted': False,
        'deleted_at': None,
        'replies': []
    }

def merge_comment_trees(existing_comments, new_comments, current_time):
    """Merge new comment tree with existing comment tree, tracking changes"""
    # Create lookup for existing comments
    existing_lookup = {}
    def build_lookup(comments):
        for comment in comments:
            existing_lookup[comment['id']] = comment
            if comment.get('replies'):
                build_lookup(comment['replies'])
    
    build_lookup(existing_comments)
    
    def merge_comment(new_comment, parent_replies=None):
        comment_id = new_comment['id']
        
        if comment_id in existing_lookup:
            # Comment exists - check if it's already deleted
            existing = existing_lookup[comment_id]
            
            if existing.get('deleted', False):
                # Comment is already deleted, don't update it
                return existing
            
            # Get current values from new comment
            current_score = new_comment.get('score', 0)
            current_text = new_comment.get('body', '')
            
            # Get previous values from existing comment
            old_score = existing['score_history'][-1][0] if existing.get('score_history') else 0
            old_text = existing['text_history'][-1][0] if existing.get('text_history') else ''
            
            # Always add new score entry
            if 'score_history' not in existing:
                existing['score_history'] = []
            existing['score_history'].append([old_score, existing['score_history'][-1][1] if existing['score_history'] else current_time])
            existing['score_history'].append([current_score, current_time])
            
            # Only add text entry if text actually changed
            if current_text != old_text:
                if 'text_history' not in existing:
                    existing['text_history'] = []
                if old_text:  # Only add to history if there was previous text
                    existing['text_history'].append([old_text, existing['text_history'][-1][1] if existing['text_history'] else current_time])
                existing['text_history'].append([current_text, current_time])
            
            # Mark as not deleted (in case it was previously marked)
            existing['deleted'] = False
            existing['deleted_at'] = None
            
            # Ensure no old fields exist
            existing.pop('current_score', None)
            existing.pop('current_text', None)
            existing.pop('first_seen', None)
            existing.pop('last_seen', None)
            existing.pop('score', None)
            existing.pop('body', None)
            
            # Merge replies
            if new_comment.get('replies'):
                if 'replies' not in existing:
                    existing['replies'] = []
                for reply in new_comment['replies']:
                    merge_comment(reply, existing['replies'])
            
            return existing
        else:
            # New comment - create with temporal structure
            temporal_comment = create_temporal_comment(new_comment, current_time)
            
            # Process replies
            if new_comment.get('replies'):
                for reply in new_comment['replies']:
                    merge_comment(reply, temporal_comment['replies'])
            
            if parent_replies is not None:
                parent_replies.append(temporal_comment)
            
            return temporal_comment
    
    # Merge all new comments
    merged_comments = []
    for new_comment in new_comments:
        merged_comment = merge_comment(new_comment, merged_comments)
        if merged_comment not in merged_comments:
            merged_comments.append(merged_comment)
    
    # Create complete lookup of all new comment IDs (including nested ones)
    new_comment_ids = set()
    def collect_new_ids(comments):
        for comment in comments:
            new_comment_ids.add(comment['id'])
            if comment.get('replies'):
                collect_new_ids(comment['replies'])
    
    collect_new_ids(new_comments)
    
    # Mark missing comments as deleted
    for comment_id, existing_comment in existing_lookup.items():
        if comment_id not in new_comment_ids:
            if not existing_comment.get('deleted', False):
                # Add final score entry if available
                if existing_comment.get('score_history'):
                    last_score = existing_comment['score_history'][-1][0]
                    existing_comment['score_history'].append([last_score, current_time])
                
                existing_comment['deleted'] = True
                existing_comment['deleted_at'] = current_time
    
    return merged_comments

def convert_existing_to_temporal(comment, current_time):
    """Convert existing comment to temporal structure - remove all old fields"""
    # Always remove old fields regardless of format
    old_score = comment.get('current_score', comment.get('score', 0))
    old_text = comment.get('current_text', comment.get('body', ''))
    old_timestamp = comment.get('last_seen', comment.get('first_seen', current_time))
    
    # Set up history arrays
    if 'score_history' not in comment or not comment.get('score_history'):
        comment['score_history'] = [[old_score, old_timestamp]]
    if 'text_history' not in comment or not comment.get('text_history'):
        comment['text_history'] = [[old_text, old_timestamp]] if old_text else []
    
    comment['deleted'] = comment.get('deleted', False)
    comment['deleted_at'] = comment.get('deleted_at', None)
    
    # Remove ALL old fields
    comment.pop('current_score', None)
    comment.pop('current_text', None)
    comment.pop('first_seen', None)
    comment.pop('last_seen', None)
    comment.pop('score', None)
    comment.pop('body', None)
    
    # Convert replies recursively
    if comment.get('replies'):
        for reply in comment['replies']:
            convert_existing_to_temporal(reply, current_time)
    
    return comment

# ============================================================================
# NEW FLATTEN-MERGE-REBUILD APPROACH
# ============================================================================

def flatten_tree(comments):
    """
    Convert nested comment tree to flat list
    Depth-first traversal that visits all comments at all depths
    """
    flat_list = []
    
    def traverse(comment_list):
        for comment in comment_list:
            flat_list.append(comment)
            if comment.get('replies'):
                traverse(comment['replies'])
    
    traverse(comments)
    return flat_list


def create_id_lookup(flat_comments):
    """
    Create hash map for O(1) comment lookup by ID
    """
    lookup = {}
    for comment in flat_comments:
        comment_id = comment.get('id')
        if comment_id:
            lookup[comment_id] = comment
    return lookup


def merge_flat_comments(old_flat, new_flat, current_time):
    """
    Main merge logic - operates on flat lists
    Returns flat merged list (will be rebuilt into tree later)
    """
    # Create lookup structures
    new_lookup = create_id_lookup(new_flat)
    visited_ids = set()
    merged_flat = []
    
    # PASS 1: Process all old comments
    for old_comment in old_flat:
        comment_id = old_comment.get('id')
        if not comment_id:
            continue
            
        new_comment = new_lookup.get(comment_id)  # O(1) lookup
        
        if new_comment:
            # Comment still exists - update temporal data
            visited_ids.add(comment_id)
            
            # Reset absence counter since we found it
            old_comment['absence_count'] = 0
            
            # Update score history (always append)
            new_score = new_comment.get('score', 0)
            if 'score_history' not in old_comment:
                old_comment['score_history'] = []
            old_comment['score_history'].append([new_score, current_time])
            
            # Update text history (only if changed)
            new_text = new_comment.get('body', '')
            if 'text_history' not in old_comment:
                old_comment['text_history'] = []
            
            if old_comment['text_history']:
                latest_text = old_comment['text_history'][-1][0]
                if new_text != latest_text:
                    old_comment['text_history'].append([new_text, current_time])
            else:
                # First entry
                old_comment['text_history'].append([new_text, current_time])
            
            # Keep the old comment structure (with updated data)
            # Note: We'll rebuild replies in Phase 3
            merged_flat.append(old_comment)
            
        else:
            # Comment not in this scrape - track absence
            old_comment.setdefault('absence_count', 0)
            old_comment.setdefault('first_seen', current_time)
            
            # Grace period: don't count absences for newly discovered comments
            # (skip first 2 scrapes after discovery to handle Reddit reshuffling)
            if 'score_history' in old_comment and len(old_comment['score_history']) >= 2:
                old_comment['absence_count'] += 1
            
            # Mark deleted only after 3 consecutive absences (and only once)
            if old_comment['absence_count'] >= 3 and not old_comment.get('deleted', False):
                old_comment['deleted'] = True
                old_comment['deleted_at'] = current_time
                
                # Add audit marker to score_history for temporal plots
                if 'score_history' in old_comment:
                    old_comment['score_history'].append([None, current_time])
            
            merged_flat.append(old_comment)
    
    # PASS 2: Add new comments that weren't in old_json
    for new_comment in new_flat:
        comment_id = new_comment.get('id')
        if not comment_id:
            continue
            
        if comment_id not in visited_ids:
            # Brand new comment - convert to temporal format
            temporal_comment = {
                'id': comment_id,
                'author': new_comment.get('author'),
                'parent_id': new_comment.get('parent_id'),
                'score_history': [[new_comment.get('score', 0), current_time]],
                'text_history': [[new_comment.get('body', ''), current_time]],
                'created_utc': new_comment.get('created_utc'),
                'depth': new_comment.get('depth'),
                'permalink': new_comment.get('permalink'),
                'is_submitter': new_comment.get('is_submitter'),
                'controversiality': new_comment.get('controversiality'),
                'gilded': new_comment.get('gilded'),
                'edited': new_comment.get('edited'),
                'deleted': False,
                'deleted_at': None,
                'absence_count': 0,
                'first_seen': current_time,
                # Don't set replies yet - will be built in Phase 3
            }
            
            merged_flat.append(temporal_comment)
    
    return merged_flat


def rebuild_tree(flat_comments):
    """
    Reconstruct nested tree structure from flat list using parent_id
    Returns: (root_comments, orphan_warnings)
    """
    # Create lookup for O(1) access
    comment_lookup = create_id_lookup(flat_comments)
    
    # Initialize all comments with empty replies array
    for comment in flat_comments:
        comment['replies'] = []
    
    # Build parent-child relationships
    root_comments = []
    orphaned_comments = []  # Track comments that couldn't find their parent
    
    for comment in flat_comments:
        parent_id = comment.get('parent_id', '')
        
        # Extract just the comment ID (remove t1_ or t3_ prefix if present)
        if parent_id.startswith('t1_'):
            parent_id = parent_id[3:]  # Remove "t1_" prefix
        elif parent_id.startswith('t3_'):
            # This is a top-level comment (parent is the post)
            root_comments.append(comment)
            continue
        
        # Find parent and append this comment as a reply
        parent = comment_lookup.get(parent_id)
        if parent:
            parent['replies'].append(comment)
        else:
            # Parent doesn't exist (orphaned comment)
            # Treat as root-level comment but track it
            root_comments.append(comment)
            
            text_preview = 'N/A'
            if comment.get('text_history'):
                text_preview = comment['text_history'][-1][0][:50]
            
            orphaned_comments.append({
                'comment_id': comment.get('id'),
                'missing_parent_id': parent_id,
                'author': comment.get('author'),
                'text_preview': text_preview
            })
    
    return root_comments, orphaned_comments


def merge_with_existing_data(new_data, output_file, current_time):
    """
    Merge new scraped data with existing data using flatten-merge-rebuild approach
    """
    if not os.path.exists(output_file):
        print("📄 No existing file found, creating new temporal structure")
        return new_data
    
    print("📄 Loading existing data for temporal merge...")
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    except Exception as e:
        print(f"⚠️  Error loading existing file: {e}")
        print("📄 Creating new temporal structure")
        return new_data
    
    # ========================================================================
    # PHASE 1: FLATTEN TREES
    # ========================================================================
    print("🔄 Phase 1: Flattening comment trees...")
    
    old_comments = existing_data.get('comments', [])
    new_comments = new_data.get('comments', [])
    
    old_flat = flatten_tree(old_comments)
    new_flat = flatten_tree(new_comments)
    
    print(f"   Old: {len(old_flat)} comments (flat)")
    print(f"   New: {len(new_flat)} comments (flat)")
    
    # ========================================================================
    # PHASE 2: MERGE DATA
    # ========================================================================
    print("🔄 Phase 2: Merging comment data...")
    
    merged_flat = merge_flat_comments(old_flat, new_flat, current_time)
    
    print(f"   Merged: {len(merged_flat)} comments (flat)")
    
    # ========================================================================
    # PHASE 3: REBUILD TREE
    # ========================================================================
    print("🔄 Phase 3: Rebuilding comment tree...")
    
    merged_tree, orphans = rebuild_tree(merged_flat)
    
    print(f"   Tree rebuilt: {len(merged_tree)} top-level comments")
    
    # Warn about orphaned comments
    if orphans:
        print(f"\n⚠️  WARNING: {len(orphans)} orphaned comments detected!")
        print("   These comments couldn't find their parent and were placed at root level:")
        for orphan in orphans[:5]:  # Show first 5
            print(f"   - Comment {orphan['comment_id']} by {orphan['author']}")
            print(f"     Missing parent: {orphan['missing_parent_id']}")
            print(f"     Text: {orphan['text_preview']}...")
        if len(orphans) > 5:
            print(f"   ... and {len(orphans) - 5} more orphaned comments")
        print()
    
    # ========================================================================
    # MERGE POST DATA
    # ========================================================================
    existing_post = existing_data.get('post', {})
    new_post = new_data.get('post', {})
    
    # Merge post score history
    merged_post = existing_post.copy()
    merged_post.update(new_post)
    
    # Get new score from new_post
    new_score = new_post.get('score_history', [[0, current_time]])[0][0]
    
    # Append to existing score history
    if 'score_history' not in merged_post:
        merged_post['score_history'] = []
    merged_post['score_history'].append([new_score, current_time])
    
    # ========================================================================
    # CREATE FINAL MERGED DATA
    # ========================================================================
    merged_data = {
        'post': merged_post,
        'comments': merged_tree,
        'metadata': {
            **new_data.get('metadata', {}),
            'temporal_merge': True,
            'merge_timestamp': current_time,
            'old_comment_count': len(old_flat),
            'new_comment_count': len(new_flat),
            'merged_comment_count': len(merged_flat),
            'top_level_count': len(merged_tree),
            'orphaned_count': len(orphans)
        }
    }
    
    print(f"✅ Temporal merge complete: {len(merged_flat)} total comments, {len(merged_tree)} top-level")
    return merged_data

def extract_comments_from_api_data(data):
    """
    Extract comments from Reddit API response
    API returns [post_data, comments_data] structure
    """
    if not data or len(data) < 2:
        print("❌ Invalid API response structure")
        return [], {}
    
    post_data = data[0]['data']['children'][0]['data']
    comments_data = data[1]['data']['children']
    
    print(f"📊 Found {len(comments_data)} top-level comments in API response")
    
    # Extract post information
    post_info = {
        'id': post_data.get('id'),
        'title': post_data.get('title'),
        'author': post_data.get('author'),
        'score': post_data.get('score'),
        'created_utc': post_data.get('created_utc'),
        'num_comments': post_data.get('num_comments'),
        'subreddit': post_data.get('subreddit'),
        'url': post_data.get('url'),
        'selftext': post_data.get('selftext'),
        'permalink': post_data.get('permalink')
    }
    
    # Extract all comments (including nested ones)
    all_comments = []
    comment_count = 0
    
    def process_comment(comment_data, depth=0, parent_id=None):
        nonlocal comment_count
        
        if comment_data.get('kind') != 't1':  # t1 = comment, t3 = post
            return
        
        comment = comment_data['data']
        comment_count += 1
        
        comment_info = {
            'id': comment.get('id'),
            'parent_id': parent_id,
            'author': comment.get('author'),
            'body': comment.get('body'),
            'score': comment.get('score'),
            'created_utc': comment.get('created_utc'),
            'depth': depth,
            'permalink': comment.get('permalink'),
            'is_submitter': comment.get('is_submitter'),
            'controversiality': comment.get('controversiality'),
            'gilded': comment.get('gilded'),
            'edited': comment.get('edited')
        }
        
        all_comments.append(comment_info)
        
        # Process replies recursively
        replies = comment.get('replies', {})
        if replies and replies.get('data') and replies['data'].get('children'):
            for reply in replies['data']['children']:
                process_comment(reply, depth + 1, comment.get('id'))
    
    # Process all top-level comments
    for comment in comments_data:
        process_comment(comment)
    
    print(f"📊 Total comments extracted: {comment_count}")
    return all_comments, post_info

def scrape_reddit_post_api(url, output_file=None, session=None, max_requests=200, sort='confidence', rate_limiter=None):
    """
    Main function to scrape Reddit post using recursive API approach with temporal tracking
    Gets ALL comments including those hidden in 'more' objects and merges with existing data

    Args:
        url: Reddit post URL
        output_file: Optional output file path
        session: Optional authenticated requests.Session for OAuth (10x rate limit)
        max_requests: Maximum number of API requests (None for unlimited)
        sort: Sort order for comments ('confidence', 'top', 'new', 'controversial', 'old', 'qa')
        rate_limiter: Optional RateLimiter instance for adaptive limit learning
    """
    print(f"🚀 Starting recursive API-based Reddit scraping for: {url}")
    
    # Extract post ID from URL
    post_id = extract_post_id_from_url(url)
    if not post_id:
        print(f"❌ Could not extract post ID from URL: {url}")
        return None
    
    print(f"📋 Post ID: {post_id}")
    print(f"📊 Sort order: {sort}")
    if max_requests is None:
        print(f"♾️  Unlimited requests mode - will retrieve ALL comments")
    else:
        print(f"📊 Max requests: {max_requests}")
    
    # Fetch data via recursive API calls (pass session for OAuth and rate_limiter for adaptive learning)
    recursive_data = get_reddit_data_recursive(post_id, max_requests=max_requests, session=session, sort=sort, rate_limiter=rate_limiter)
    if not recursive_data:
        return None
    
    # Extract post info with temporal structure
    post_data = recursive_data['post_data']
    current_time = datetime.now().isoformat()
    
    post_info = {
        'id': post_data.get('id'),
        'title': post_data.get('title'),
        'author': post_data.get('author'),
        'score_history': [[post_data.get('score', 0), current_time]],
        'created_utc': post_data.get('created_utc'),
        'num_comments': post_data.get('num_comments'),
        'subreddit': post_data.get('subreddit'),
        'url': post_data.get('url'),
        'selftext': post_data.get('selftext'),
        'permalink': post_data.get('permalink')
    }
    
    # Convert comment forest to temporal structure
    def convert_to_temporal_comments(comments, current_time):
        temporal_comments = []
        for comment in comments:
            temporal_comment = create_temporal_comment(comment, current_time)
            if comment.get('replies'):
                temporal_comment['replies'] = convert_to_temporal_comments(comment['replies'], current_time)
            temporal_comments.append(temporal_comment)
        return temporal_comments
    
    temporal_comments = convert_to_temporal_comments(recursive_data['comment_forest'], current_time)
    
    # Create new data structure
    new_data = {
        'post': post_info,
        'comments': temporal_comments,
        'metadata': {
            'scraped_at': current_time,
            'scraper_version': 'api_recursive_temporal_v1',
            'source_url': url,
            **recursive_data['metadata']
        }
    }
    
    # Save raw data first (for debugging/comparison)
    if output_file:
        # Generate timestamped filenames
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Extract directory and filename from the path
        output_dir = os.path.dirname(output_file)
        filename = os.path.basename(output_file).replace('.json', '')
        raw_file = f"{output_dir}/{filename}_raw_{timestamp}.json"
        merged_file = f"{output_dir}/{filename}_merged_{timestamp}.json"
        
        # Save raw scraped data
        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Raw data saved to: {raw_file}")
        
        # Check if original file exists for merging
        if os.path.exists(output_file):
            print(f"📄 Original file exists: {output_file}")
            merged_data = merge_with_existing_data(new_data, output_file, current_time)
            
            # Save merged data to timestamped file
            with open(merged_file, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, indent=2, ensure_ascii=False)
            print(f"✅ Merged data saved to: {merged_file}")
            print(f"📄 Original file preserved: {output_file}")
            
            return merged_data
        else:
            print(f"📄 No existing file to merge with, raw data is the first version")
            # Copy raw to output_file as the initial version
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)
            print(f"✅ Initial version saved to: {output_file}")
            
            return new_data
    else:
        return new_data

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reddit_scraper_api.py <reddit_url> [output_file]")
        sys.exit(1)
    
    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = scrape_reddit_post_api(url, output_file)
    if result:
        print(f"✅ Scraping completed successfully!")
        print(f"📊 Found {result['metadata']['total_comments']} comments")
    else:
        print("❌ Scraping failed")
