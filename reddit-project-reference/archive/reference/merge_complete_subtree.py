#!/usr/bin/env python3
"""
Merge scraped subtree with directly-fetched missing branch to create complete subtree.
Simplified approach: just add the fetched branch as a new top-level tree.
"""

import json
import sys
import os
from datetime import datetime
from experiment_post_data import clean_comment_tree, prune_inactive_branches


def convert_branch_to_tree_structure(branch_data: dict) -> dict:
    """
    Convert flat branch data into a single tree structure.
    The branch data has all comments with their parent_id, so we can build a tree.
    """
    # Find the root comment (one with parent_id starting with t3_ or not in branch_data)
    root_id = None
    
    for comment_id, comment_data in branch_data.items():
        parent_id = comment_data.get('parent_id', '')
        if parent_id.startswith('t3_') or not parent_id:
            # This is a top-level comment
            root_id = comment_id
            break
    
    # If no top-level found, find the one with lowest depth or oldest parent
    if not root_id:
        # Find comment whose parent is not in branch_data
        for comment_id, comment_data in branch_data.items():
            parent_id = comment_data.get('parent_id', '')
            if parent_id.startswith('t1_'):
                parent_comment_id = parent_id[3:]
                if parent_comment_id not in branch_data:
                    # This parent is outside the branch, so this is effectively a root
                    root_id = comment_id
                    break
    
    # If still no root, just pick the first one
    if not root_id:
        root_id = list(branch_data.keys())[0]
    
    # Build parent->children map
    children_map = {}
    for comment_id, comment_data in branch_data.items():
        parent_id = comment_data.get('parent_id', '')
        if parent_id.startswith('t1_'):
            parent_comment_id = parent_id[3:]
            if parent_comment_id in branch_data:  # Only if parent is in branch
                if parent_comment_id not in children_map:
                    children_map[parent_comment_id] = []
                children_map[parent_comment_id].append(comment_id)
    
    # Build tree recursively
    def build_node(comment_id: str, visited: set) -> dict:
        if comment_id in visited:
            return None  # Circular reference protection
        visited.add(comment_id)
        
        comment_data = branch_data[comment_id]
        
        # Convert to our format
        node = {
            'id': comment_id,
            'parent_id': comment_data.get('parent_id', ''),
            'author': comment_data.get('author', ''),
            'depth': comment_data.get('depth', 0),
            'text_history': [[comment_data.get('body', ''), datetime.now().isoformat()]],
            'score_history': [[comment_data.get('score', 0), datetime.now().isoformat()]],
            'replies': []
        }
        
        # Add children
        if comment_id in children_map:
            for child_id in children_map[comment_id]:
                child_node = build_node(child_id, visited)
                if child_node:
                    node['replies'].append(child_node)
        
        return node
    
    visited = set()
    root_tree = build_node(root_id, visited)
    
    # If there are unprocessed comments, they might be separate trees
    # For now, just return the main tree
    return root_tree if root_tree else None


def find_connection_point(scraped_subtree: list, branch_parent_id: str) -> dict:
    """
    Find where the branch connects to the scraped subtree.
    Returns the node that should have the branch as a child.
    """
    def search_tree(node, target_id):
        if node.get('id') == target_id:
            return node
        if 'replies' in node:
            for reply in node['replies']:
                result = search_tree(reply, target_id)
                if result:
                    return result
        return None
    
    # Extract parent comment ID from t1_ prefix
    if branch_parent_id.startswith('t1_'):
        parent_comment_id = branch_parent_id[3:]
    else:
        return None
    
    # Search in scraped subtree
    for tree in scraped_subtree:
        result = search_tree(tree, parent_comment_id)
        if result:
            return result
    
    return None


def main():
    # Load files
    subtree_file = "data/extracted_subtrees/subtree_1dt5y8x_mineurownbiz_20251105_155242.json"
    branch_file = "data/raw/single_post_test/branch_lb84fge.json"
    
    print("=" * 80)
    print("Merging Complete Subtree")
    print("=" * 80)
    
    # Load existing subtree
    print(f"\n📂 Loading existing subtree: {subtree_file}")
    with open(subtree_file, 'r') as f:
        subtree_data = json.load(f)
    
    existing_subtree = subtree_data.get('comments', [])
    print(f"   Found {len(existing_subtree)} top-level trees")
    
    # Load fetched branch
    print(f"\n📂 Loading fetched branch: {branch_file}")
    with open(branch_file, 'r') as f:
        branch_data = json.load(f)
    print(f"   Found {len(branch_data)} comments in branch")
    
    # Convert branch to tree structure
    print(f"\n🔄 Converting branch to tree structure...")
    branch_tree = convert_branch_to_tree_structure(branch_data)
    
    if not branch_tree:
        print("❌ Failed to build branch tree")
        return
    
    print(f"   Root comment: {branch_tree['id']}")
    print(f"   Root parent: {branch_tree.get('parent_id', 'N/A')}")
    
    # Find where branch connects to scraped subtree
    # The branch tree starts at a root (lb7d0ks), but we need to find where it should attach
    # Check if the root of branch tree is already in scraped subtree
    branch_root_id = branch_tree.get('id')
    
    def find_node_in_tree(comments, target_id):
        for c in comments:
            if c.get('id') == target_id:
                return c
            if 'replies' in c:
                result = find_node_in_tree(c['replies'], target_id)
                if result:
                    return result
        return None
    
    existing_root = find_node_in_tree(existing_subtree, branch_root_id)
    
    if existing_root:
        print(f"\n🔗 Found existing root in scraped subtree: {branch_root_id}")
        print(f"   Merging branch replies into existing root...")
        # Merge the branch tree's replies into the existing root
        if 'replies' not in existing_root:
            existing_root['replies'] = []
        # Add all replies from branch tree to existing root
        existing_root['replies'].extend(branch_tree.get('replies', []))
        complete_subtree = existing_subtree
    else:
        # Try to find connection point by parent
        branch_parent_id = branch_tree.get('parent_id', '')
        connection_point = find_connection_point(existing_subtree, branch_parent_id)
        
        if connection_point:
            print(f"\n🔗 Found connection point: {connection_point['id']}")
            print(f"   Attaching branch as reply...")
            if 'replies' not in connection_point:
                connection_point['replies'] = []
            connection_point['replies'].append(branch_tree)
            complete_subtree = existing_subtree
        else:
            print(f"\n⚠️  No connection point found in scraped subtree")
            print(f"   Adding branch as separate top-level tree...")
            complete_subtree = existing_subtree + [branch_tree]
    
    # Count total comments
    def count_comments(comments):
        total = len(comments)
        for c in comments:
            if 'replies' in c:
                total += count_comments(c['replies'])
        return total
    
    total_comments = count_comments(complete_subtree)
    print(f"\n📊 Total comments in merged tree: {total_comments}")
    
    # Clean the subtree (flatten histories, remove unnecessary fields)
    print(f"\n🧹 Cleaning subtree...")
    cleaned_subtree = clean_comment_tree(complete_subtree)
    
    # Prune inactive branches (no user activity, dead ends)
    print(f"\n✂️  Pruning inactive branches...")
    target_user = subtree_data.get("target_user", "")
    pruned_subtree = prune_inactive_branches(cleaned_subtree, target_user, min_active_comments=2)
    
    def count_comments_pruned(comments):
        total = len(comments)
        for c in comments:
            if 'replies' in c:
                total += count_comments_pruned(c['replies'])
        return total
    
    pruned_count = count_comments_pruned(pruned_subtree)
    print(f"   Comments after pruning: {pruned_count} (was {total_comments})")
    print(f"   Removed: {total_comments - pruned_count} comments")
    
    # Save complete subtree
    output_dir = "data/extracted_subtrees"
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{output_dir}/subtree_1dt5y8x_mineurownbiz_complete_{timestamp}.json"
    
    complete_data = {
        "post_id": subtree_data.get("post_id"),
        "post_title": subtree_data.get("post_title"),
        "target_user": subtree_data.get("target_user"),
        "extraction_timestamp": datetime.now().isoformat(),
        "merged_with_fetched_branch": True,
        "statistics": {
            "top_level_trees": len(complete_subtree),
            "total_comments": total_comments,
            "comments_by_user": subtree_data.get("statistics", {}).get("comments_by_user", 0),
            "comments_from_scraped": count_comments(existing_subtree),
            "comments_from_branch": len(branch_data),
            "comments_after_pruning": pruned_count
        },
        "comments": pruned_subtree
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(complete_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Complete subtree saved to: {output_file}")
    print(f"   Total comments: {total_comments}")
    
    # Verify lb84fge is now included
    def find_comment(comments, target_id):
        for c in comments:
            if c.get('id') == target_id:
                return True
            if 'replies' in c:
                if find_comment(c['replies'], target_id):
                    return True
        return False
    
    has_lb84fge = find_comment(pruned_subtree, 'lb84fge')
    print(f"   ✅ Contains lb84fge: {has_lb84fge}")


if __name__ == '__main__':
    main()
