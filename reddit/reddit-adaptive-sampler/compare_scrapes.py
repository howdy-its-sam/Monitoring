#!/usr/bin/env python3
"""
Compare two scraped post files to identify differences in captured comments.
"""

import json
import sys
from typing import Set, Dict, List


def load_comments(filepath: str) -> Dict[str, dict]:
    """Load comments from a scraped JSON file and return a flat map."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    comment_map = {}
    
    def traverse(comments):
        for comment in comments:
            comment_id = comment.get('id')
            if comment_id:
                comment_map[comment_id] = comment
            if 'replies' in comment:
                traverse(comment['replies'])
    
    traverse(data.get('comments', []))
    return comment_map


def find_target_comments(filepath: str, target_ids: Set[str]) -> Dict[str, bool]:
    """Check if target comment IDs exist in a scraped file."""
    comment_map = load_comments(filepath)
    results = {}
    for target_id in target_ids:
        results[target_id] = target_id in comment_map
    return results


def compare_scrapes(file1: str, file2: str):
    """Compare two scraped files and show differences."""
    print("=" * 80)
    print("Comparing Scrapes")
    print("=" * 80)
    
    comments1 = load_comments(file1)
    comments2 = load_comments(file2)
    
    ids1 = set(comments1.keys())
    ids2 = set(comments2.keys())
    
    print(f"\nFile 1: {file1}")
    print(f"  Total comments: {len(ids1)}")
    print(f"\nFile 2: {file2}")
    print(f"  Total comments: {len(ids2)}")
    
    # Find differences
    only_in_1 = ids1 - ids2
    only_in_2 = ids2 - ids1
    in_both = ids1 & ids2
    
    print(f"\n📊 Comparison:")
    print(f"  Comments in both: {len(in_both)}")
    print(f"  Only in file 1: {len(only_in_1)}")
    print(f"  Only in file 2: {len(only_in_2)}")
    
    # Check for target missing comments
    target_ids = {'lb7wawa', 'lb81upl', 'lb8344j', 'lb83n5q', 'lb84fge', 
                  'lb852m3', 'lb86apw', 'lb87hgt', 'lb8e6uq'}
    
    print(f"\n🔍 Checking for target missing comments:")
    found_in_1 = {cid for cid in target_ids if cid in ids1}
    found_in_2 = {cid for cid in target_ids if cid in ids2}
    
    print(f"  Found in file 1: {found_in_1}")
    print(f"  Found in file 2: {found_in_2}")
    
    if found_in_2 - found_in_1:
        print(f"\n✅ NEW COMMENTS FOUND in file 2: {found_in_2 - found_in_1}")
    elif found_in_1 == found_in_2 and len(found_in_1) == 0:
        print(f"\n❌ Still missing all target comments in both scrapes")
    
    if only_in_1:
        print(f"\n📋 Sample comments only in file 1 (first 10):")
        for i, cid in enumerate(sorted(list(only_in_1))[:10]):
            comment = comments1[cid]
            print(f"  {i+1}. {cid} (author: {comment.get('author', 'N/A')})")
    
    if only_in_2:
        print(f"\n📋 Sample comments only in file 2 (first 10):")
        for i, cid in enumerate(sorted(list(only_in_2))[:10]):
            comment = comments2[cid]
            print(f"  {i+1}. {cid} (author: {comment.get('author', 'N/A')})")
    
    return {
        'file1_total': len(ids1),
        'file2_total': len(ids2),
        'in_both': len(in_both),
        'only_in_1': len(only_in_1),
        'only_in_2': len(only_in_2),
        'target_found_1': found_in_1,
        'target_found_2': found_in_2
    }


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 compare_scrapes.py <file1> <file2>")
        sys.exit(1)
    
    file1 = sys.argv[1]
    file2 = sys.argv[2]
    
    compare_scrapes(file1, file2)

