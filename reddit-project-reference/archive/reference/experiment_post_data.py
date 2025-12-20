#!/usr/bin/env python3
"""
Template script to experiment with extracting data from a single Reddit post JSON file.
"""

import json
import os
from typing import Optional, Dict, Any, List, Set
from collections import deque
from datetime import datetime


def load_post_data(filepath: str) -> Dict[str, Any]:
    """Load the JSON file containing post data."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_comment_by_id(comments: list, target_id: str) -> Optional[Dict[str, Any]]:
    """
    Recursively search for a comment by ID in the comments tree.
    
    Args:
        comments: List of comment objects (may contain nested replies)
        target_id: The comment ID to find
        
    Returns:
        Comment dict if found, None otherwise
    """
    for comment in comments:
        if comment.get("id") == target_id:
            return comment
        if "replies" in comment and comment["replies"]:
            result = find_comment_by_id(comment["replies"], target_id)
            if result:
                return result
    return None


def get_first_text(comment: Dict[str, Any]) -> Optional[str]:
    """Get the first text entry from a comment's text_history."""
    if "text_history" in comment and comment["text_history"]:
        return comment["text_history"][0][0]
    return None


def build_comment_map(comments: list) -> Dict[str, Dict[str, Any]]:
    """
    Create a flat map of comment_id -> comment object for O(1) lookups.
    
    Args:
        comments: List of top-level comment objects (may contain nested replies)
        
    Returns:
        Dictionary mapping comment ID to comment object
    """
    comment_map = {}
    
    def traverse(comment_list):
        for comment in comment_list:
            comment_id = comment.get("id")
            if comment_id:
                comment_map[comment_id] = comment
            if "replies" in comment and comment["replies"]:
                traverse(comment["replies"])
    
    traverse(comments)
    return comment_map


def find_all_comments_by_user(comments: list, target_user: str) -> List[Dict[str, Any]]:
    """
    Recursively find all comments by a target user.
    
    Args:
        comments: List of comment objects (may contain nested replies)
        target_user: Username to search for
        
    Returns:
        List of comment objects authored by target_user
    """
    user_comments = []
    
    def traverse(comment_list):
        for comment in comment_list:
            if comment.get("author") == target_user:
                user_comments.append(comment)
            if "replies" in comment and comment["replies"]:
                traverse(comment["replies"])
    
    traverse(comments)
    return user_comments


def collect_descendants(comment: Dict[str, Any]) -> Set[str]:
    """
    Recursively collect all descendant comment IDs from a comment's replies subtree.
    
    Args:
        comment: Comment object to collect descendants from
        
    Returns:
        Set of comment IDs (descendants)
    """
    descendant_ids = set()
    
    def traverse(comment_obj):
        if "replies" in comment_obj and comment_obj["replies"]:
            for reply in comment_obj["replies"]:
                reply_id = reply.get("id")
                if reply_id:
                    descendant_ids.add(reply_id)
                    traverse(reply)  # Recursively collect nested replies
    
    traverse(comment)
    return descendant_ids


def collect_ancestors_to_root(comment_id: str, comment_map: Dict[str, Dict[str, Any]]) -> Set[str]:
    """
    Walk up the parent chain from a comment to the top-level comment.
    
    Args:
        comment_id: ID of comment to start from
        comment_map: Flat map of all comments for lookup
        
    Returns:
        Set of all ancestor comment IDs in the chain (including the starting comment)
    """
    ancestor_ids = set()
    current_id = comment_id
    
    while current_id:
        if current_id in ancestor_ids:  # Avoid infinite loops
            break
        ancestor_ids.add(current_id)
        
        comment = comment_map.get(current_id)
        if not comment:
            break
        
        parent_id = comment.get("parent_id", "")
        if not parent_id or parent_id.startswith("t3_"):  # Top-level comment (post)
            break
        
        # Extract comment ID from parent_id (format: "t1_<id>")
        if parent_id.startswith("t1_"):
            current_id = parent_id[3:]  # Remove "t1_" prefix
        else:
            break
    
    return ancestor_ids


def extract_user_subtree(comments: list, target_user: str) -> List[Dict[str, Any]]:
    """
    Extract a unified comment forest containing all comments by target_user,
    their ancestors up to top-level, and all descendants, with no duplicates.
    
    Args:
        comments: List of top-level comment objects
        target_user: Username to extract subtree for
        
    Returns:
        List of top-level comment trees (forest) containing the extracted subtree
    """
    # Build flat comment map for O(1) lookups
    comment_map = build_comment_map(comments)
    
    # Find all comments by target user
    user_comments = find_all_comments_by_user(comments, target_user)
    
    if not user_comments:
        return []  # No comments by this user
    
    # Collect all relevant comment IDs (breadth-first approach)
    collected_ids = set()
    queue = deque(user_comments)
    processed_user_comments = set()
    
    # Process user comments in breadth-first order
    while queue:
        user_comment = queue.popleft()
        comment_id = user_comment.get("id")
        
        if not comment_id or comment_id in processed_user_comments:
            continue
        
        processed_user_comments.add(comment_id)
        collected_ids.add(comment_id)  # Explicitly add user comment
        
        # Collect descendants (entire subtree below this comment)
        descendants = collect_descendants(user_comment)
        collected_ids.update(descendants)
        
        # Collect ancestors (linear chain up to top-level)
        ancestors = collect_ancestors_to_root(comment_id, comment_map)
        collected_ids.update(ancestors)
    
    # Identify top-level comments in the collected set
    # Top-level comments have parent_id starting with "t3_" or are directly in comments list
    top_level_ids = set()
    for cid in collected_ids:
        comment = comment_map.get(cid)
        if comment:
            parent_id = comment.get("parent_id", "")
            if parent_id.startswith("t3_") or not parent_id:
                top_level_ids.add(cid)
    
    # Also check if any top-level comment in original list contains collected comments
    for top_comment in comments:
        top_id = top_comment.get("id")
        if top_id in collected_ids:
            top_level_ids.add(top_id)
    
    # Reconstruct forest by filtering original structure to only include collected IDs
    def filter_tree(comment_list):
        """Recursively filter comments to only include those in collected_ids."""
        filtered = []
        for comment in comment_list:
            comment_id = comment.get("id")
            if comment_id and comment_id in collected_ids:
                # Create a copy of the comment
                filtered_comment = comment.copy()
                # Filter replies recursively
                if "replies" in filtered_comment and filtered_comment["replies"]:
                    filtered_comment["replies"] = filter_tree(filtered_comment["replies"])
                else:
                    filtered_comment["replies"] = []
                filtered.append(filtered_comment)
            elif "replies" in comment and comment["replies"]:
                # This comment isn't in our set, but check if any descendants are
                filtered_replies = filter_tree(comment["replies"])
                if filtered_replies:
                    # This comment is an ancestor of a collected comment
                    filtered_comment = comment.copy()
                    filtered_comment["replies"] = filtered_replies
                    filtered.append(filtered_comment)
                    collected_ids.add(comment_id)  # Add to collected set
        return filtered
    
    # Build the forest starting from top-level comments
    forest = []
    for top_comment in comments:
        top_id = top_comment.get("id")
        if top_id in top_level_ids:
            # This top-level comment is in our collected set
            filtered_tree = filter_tree([top_comment])
            if filtered_tree:
                forest.extend(filtered_tree)
        else:
            # Check if any descendants of this top-level comment are collected
            filtered_tree = filter_tree([top_comment])
            if filtered_tree:
                forest.extend(filtered_tree)
    
    return forest


def clean_comment_tree(comment_list: list) -> list:
    """
    Clean and trim comment tree by:
    - Flattening text_history[0][0] → text
    - Flattening score_history[0][0] → score
    - Removing unnecessary fields: created_utc, permalink, is_submitter, 
      controversiality, gilded, edited, deleted, deleted_at
    
    Args:
        comment_list: List of comment objects (may contain nested replies)
        
    Returns:
        List of cleaned comment objects
    """
    cleaned = []
    
    for comment in comment_list:
        # Create a new comment dict with only the fields we want
        cleaned_comment = {
            "id": comment.get("id"),
            "parent_id": comment.get("parent_id"),
            "author": comment.get("author"),
            "depth": comment.get("depth"),
        }
        
        # Flatten text_history[0][0] → text
        # Handle both formats: already cleaned (has 'text') or raw (has 'text_history')
        if "text" in comment:
            # Already cleaned, use existing text
            cleaned_comment["text"] = comment.get("text", "")
        else:
            # Not cleaned yet, extract from text_history
            text_history = comment.get("text_history", [])
            if text_history and len(text_history) > 0 and len(text_history[0]) > 0:
                cleaned_comment["text"] = text_history[0][0]
            else:
                cleaned_comment["text"] = ""
        
        # Flatten score_history[0][0] → score
        # Handle both formats: already cleaned (has 'score') or raw (has 'score_history')
        if "score" in comment:
            # Already cleaned, use existing score
            cleaned_comment["score"] = comment.get("score", 0)
        else:
            # Not cleaned yet, extract from score_history
            score_history = comment.get("score_history", [])
            if score_history and len(score_history) > 0 and len(score_history[0]) > 0:
                cleaned_comment["score"] = score_history[0][0]
            else:
                cleaned_comment["score"] = 0
        
        # Recursively clean replies
        if "replies" in comment and comment["replies"]:
            cleaned_comment["replies"] = clean_comment_tree(comment["replies"])
        else:
            cleaned_comment["replies"] = []
        
        cleaned.append(cleaned_comment)
    
    return cleaned


def prune_inactive_branches(comment_list: list, target_user: str, 
                           min_active_comments: int = 2) -> list:
    """
    Prune descendant branches that have no user activity and are inactive/dead.
    
    Keeps branches that:
    - Contain any comments by target_user
    - Have active conversation (min_active_comments with visible text)
    
    Removes branches that:
    - Have no user comments
    - Are mostly deleted/removed
    - Have minimal activity (dead ends)
    
    Args:
        comment_list: List of comment objects
        target_user: Username to check for activity
        min_active_comments: Minimum number of non-deleted comments to consider a branch "active"
        
    Returns:
        Pruned list of comments
    """
    def is_deleted_or_removed(comment: dict) -> bool:
        """Check if comment is deleted or removed."""
        text = comment.get('text', '').strip()
        author = comment.get('author', '')
        return (text in ['[deleted]', '[removed]', ''] or 
                author == '[deleted]' or 
                text.startswith('[removed]'))
    
    def has_user_activity(comment: dict) -> bool:
        """Check if comment or any descendant has user activity."""
        if comment.get('author') == target_user:
            return True
        if 'replies' in comment:
            for reply in comment['replies']:
                if has_user_activity(reply):
                    return True
        return False
    
    def count_active_comments(comment: dict) -> int:
        """Count comments with visible text (not deleted/removed)."""
        count = 0
        if not is_deleted_or_removed(comment):
            count += 1
        if 'replies' in comment:
            for reply in comment['replies']:
                count += count_active_comments(reply)
        return count
    
    def should_keep_branch(comment: dict) -> bool:
        """Determine if a branch should be kept."""
        # Always keep if user is involved
        if has_user_activity(comment):
            return True
        
        # Check if branch has active conversation
        active_count = count_active_comments(comment)
        if active_count >= min_active_comments:
            return True
        
        # If the comment itself is deleted/removed and has no active conversation below,
        # it's a dead branch
        if is_deleted_or_removed(comment):
            # Still check if descendants have activity
            if active_count > 0:
                return True
            # Dead branch - deleted comment with no active descendants
            return False
        
        # Dead branch - no user, minimal activity
        return False
    
    def prune_node(comment: dict) -> dict:
        """Recursively prune a comment node."""
        # Create a copy
        pruned = {
            'id': comment.get('id'),
            'parent_id': comment.get('parent_id'),
            'author': comment.get('author'),
            'depth': comment.get('depth'),
            'text': comment.get('text'),
            'score': comment.get('score'),
            'replies': []
        }
        
        # Process replies
        if 'replies' in comment and comment['replies']:
            for reply in comment['replies']:
                # Check if this reply branch should be kept
                if should_keep_branch(reply):
                    pruned_reply = prune_node(reply)
                    # Only add if the reply itself is worth keeping
                    # (not a deleted comment with no active descendants)
                    if not (is_deleted_or_removed(pruned_reply) and 
                            not has_user_activity(pruned_reply) and
                            count_active_comments(pruned_reply) == 0 and
                            len(pruned_reply.get('replies', [])) == 0):
                        pruned['replies'].append(pruned_reply)
                # else: drop this branch
        
        return pruned
    
    # Prune each top-level comment
    pruned = []
    for comment in comment_list:
        pruned_comment = prune_node(comment)
        pruned.append(pruned_comment)
    
    return pruned


# ============================================================================
# EXPERIMENTATION AREA
# ============================================================================

if __name__ == "__main__":
    # Load the post data
    json_file = "raw_posts/post_1dt5y8x_20251105_144833_raw_20251105_144927.json"
    data = load_post_data(json_file)
    
    # Access post data
    post = data.get("post", {})
    comments = data.get("comments", [])
    
    print(f"Post ID: {post.get('id')}")
    print(f"Post Title: {post.get('title')}")
    print(f"Total top-level comments: {len(comments)}")
    print()
    
    # Example: Find a specific comment by ID
    comment_id = "lb7m54c"
    comment = find_comment_by_id(comments, comment_id)
    
    if comment:
        print(f"Found comment: {comment_id}")
        print(f"Author: {comment.get('author')}")
        
        # Get first text entry
        first_text = get_first_text(comment)
        if first_text:
            print(f"First text: {first_text[:100]}...")  # First 100 chars
        
        # Access other fields
        print(f"Score history: {comment.get('score_history', [])}")
        print(f"Text history length: {len(comment.get('text_history', []))}")
    else:
        print(f"Comment {comment_id} not found")
    
    # Add your experiments below:
    # ============================================
    # Example: Find all comments by a specific author
    # author = "some_username"
    # matching = [c for c in comments if c.get("author") == author]
    
    # Example: Get all comment IDs
    # all_ids = []
    # def collect_ids(comments):
    #     for comment in comments:
    #         all_ids.append(comment.get("id"))
    #         if "replies" in comment:
    #             collect_ids(comment["replies"])
    # collect_ids(comments)
    
    # Example: Extract text_history[0][0] for a specific comment
    # result = find_comment_by_id(comments, "lb7m54c")
    # if result:
    #     text = result["text_history"][0][0]
    #     print(text)
    
    # Example: Extract user subtree and save to JSON
    print("=" * 60)
    print("User Subtree Extraction Example")
    print("=" * 60)
    target_user = "mineurownbiz"
    user_subtree = extract_user_subtree(comments, target_user)
    
    if user_subtree:
        print(f"\nFound {len(user_subtree)} top-level comment tree(s) containing comments by '{target_user}'")
        
        # Count total comments in subtree
        def count_comments(comment_list):
            total = len(comment_list)
            for comment in comment_list:
                if "replies" in comment and comment["replies"]:
                    total += count_comments(comment["replies"])
            return total
        
        total_comments = count_comments(user_subtree)
        print(f"Total comments in subtree: {total_comments}")
        
        # Count comments by target user
        user_comment_count = len(find_all_comments_by_user(user_subtree, target_user))
        print(f"Comments by '{target_user}': {user_comment_count}")
        
        # Clean the subtree (flatten histories, remove unnecessary fields)
        cleaned_subtree = clean_comment_tree(user_subtree)
        
        # Save subtree to JSON file
        output_dir = "data/extracted_subtrees"
        os.makedirs(output_dir, exist_ok=True)
        
        post_id = post.get("id", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{output_dir}/subtree_{post_id}_{target_user}_{timestamp}.json"
        
        subtree_data = {
            "post_id": post_id,
            "post_title": post.get("title"),
            "target_user": target_user,
            "extraction_timestamp": datetime.now().isoformat(),
            "statistics": {
                "top_level_trees": len(user_subtree),
                "total_comments": total_comments,
                "comments_by_user": user_comment_count
            },
            "comments": cleaned_subtree
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(subtree_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Subtree saved to: {output_file}")
    else:
        print(f"\nNo comments found by user '{target_user}'")

