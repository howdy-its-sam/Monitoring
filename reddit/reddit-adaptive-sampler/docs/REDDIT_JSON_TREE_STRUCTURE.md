# Reddit Comment Tree JSON Structure Guide

## Overview

Reddit scraped data is stored as a **nested tree structure** where each comment can contain child replies, forming a recursive hierarchy.

## Basic Structure

```json
{
  "post_id": "1o9example",
  "title": "Post Title",
  "comments": [
    {
      "id": "comment1",
      "author": "user1",
      "body": "Top-level comment text",
      "score": 42,
      "created_utc": 1697500000,
      "depth": 1,
      "replies": [
        {
          "id": "comment1a",
          "author": "user2",
          "body": "Reply to comment1",
          "score": 15,
          "created_utc": 1697500100,
          "depth": 2,
          "replies": [
            {
              "id": "comment1a1",
              "author": "user3",
              "body": "Reply to comment1a",
              "score": 3,
              "created_utc": 1697500200,
              "depth": 3,
              "replies": []
            }
          ]
        }
      ]
    },
    {
      "id": "comment2",
      "author": "user4",
      "body": "Another top-level comment",
      "score": 8,
      "created_utc": 1697500050,
      "depth": 1,
      "replies": []
    }
  ]
}
```

## Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique Reddit comment ID |
| `author` | string | Username of commenter |
| `body` | string | Comment text content |
| `score` | int | Net upvotes (upvotes - downvotes) |
| `created_utc` | int | Unix timestamp of creation |
| `depth` | int | How deep in the tree (1 = top-level) |
| `replies` | array | List of child comments (recursive structure) |

## Tree Traversal Patterns

### Pattern 1: Depth-First Search (Process entire branches)

```python
def traverse_dfs(comment, depth=0):
    """
    Visit current comment, then all its descendants.
    
    Args:
        comment: Comment dict with 'id', 'score', 'replies', etc.
        depth: Current depth in tree (starts at 0)
    """
    # Process current comment
    print(f"{'  ' * depth}Comment {comment['id']}: score={comment['score']}")
    
    # Recurse into all replies
    for reply in comment.get('replies', []):
        traverse_dfs(reply, depth + 1)

# Usage:
for top_comment in data['comments']:
    traverse_dfs(top_comment, depth=1)
```

### Pattern 2: Breadth-First Search (Process level by level)

```python
from collections import deque

def traverse_bfs(comments):
    """
    Process comments level by level (all depth-1, then all depth-2, etc.)
    """
    queue = deque(comments)  # Start with top-level comments
    
    while queue:
        comment = queue.popleft()
        
        # Process current comment
        print(f"Depth {comment.get('depth', 1)}: {comment['id']}")
        
        # Add all children to queue
        queue.extend(comment.get('replies', []))

# Usage:
traverse_bfs(data['comments'])
```

### Pattern 3: Conditional Pruning (Stop when criteria met)

```python
def traverse_with_pruning(comment, parent_score=None, depth=0):
    """
    Traverse tree but skip subtrees that meet pruning criteria.
    
    Example: Stop when 2 consecutive comments have score=1
    """
    score = comment.get('score', 1)
    
    # Process current comment
    process_comment(comment)
    
    # Check pruning condition
    should_prune = (depth >= 4 and parent_score == 1 and score == 1)
    
    if should_prune:
        print(f"Pruning subtree at depth {depth}")
        return  # Don't process children
    
    # Continue to children
    for reply in comment.get('replies', []):
        traverse_with_pruning(reply, parent_score=score, depth=depth + 1)

# Usage:
for top_comment in data['comments']:
    traverse_with_pruning(top_comment, depth=1)
```

### Pattern 4: Aggregate Statistics (Count/Sum across tree)

```python
def count_subtree(comment):
    """
    Count total comments in a subtree (including root).
    
    Returns: int (total comment count)
    """
    # Count this comment
    count = 1
    
    # Add counts from all children
    for reply in comment.get('replies', []):
        count += count_subtree(reply)
    
    return count

# Usage:
total = sum(count_subtree(c) for c in data['comments'])
print(f"Total comments: {total}")
```

### Pattern 5: Track Path/Lineage (Remember ancestors)

```python
def traverse_with_path(comment, path=[]):
    """
    Track the path from root to current comment.
    
    Args:
        comment: Current comment dict
        path: List of ancestor comment IDs
    """
    current_path = path + [comment['id']]
    
    # Process with full lineage
    print(f"Path: {' → '.join(current_path)}")
    print(f"Score chain: {[get_score(id) for id in current_path]}")
    
    # Recurse
    for reply in comment.get('replies', []):
        traverse_with_path(reply, current_path)

# Usage:
for top_comment in data['comments']:
    traverse_with_path(top_comment, path=[])
```

## Common Analysis Tasks

### Task: Find All Comments with Score > Threshold

```python
def find_high_score_comments(comment, threshold=10, results=None):
    """Collect all comments with score > threshold."""
    if results is None:
        results = []
    
    if comment.get('score', 0) > threshold:
        results.append(comment)
    
    for reply in comment.get('replies', []):
        find_high_score_comments(reply, threshold, results)
    
    return results
```

### Task: Calculate Average Depth

```python
def calculate_depths(comment, current_depth=1, depths=None):
    """Collect all comment depths."""
    if depths is None:
        depths = []
    
    depths.append(current_depth)
    
    for reply in comment.get('replies', []):
        calculate_depths(reply, current_depth + 1, depths)
    
    return depths

# Usage:
all_depths = []
for comment in data['comments']:
    all_depths.extend(calculate_depths(comment))

avg_depth = sum(all_depths) / len(all_depths)
max_depth = max(all_depths)
```

### Task: Detect "Dead" Conversation Threads

```python
def is_dead_thread(comment, parent_score=None, depth=0):
    """
    Detect if a thread has become inactive (low engagement).
    
    Criteria: 2+ consecutive score=1 comments at depth >= 4
    """
    score = comment.get('score', 1)
    
    if depth >= 4 and parent_score == 1 and score == 1:
        return True  # Dead thread detected
    
    # Check children
    for reply in comment.get('replies', []):
        if is_dead_thread(reply, parent_score=score, depth=depth + 1):
            return True
    
    return False
```

## Important Notes for AI Processing

### 1. Handle Missing Fields

Comments may be deleted or removed:

```python
def safe_get_score(comment):
    """Safely get score, handle deleted comments."""
    if comment.get('author') == '[deleted]':
        return 0
    return comment.get('score', 1)  # Default to 1 if missing
```

### 2. Depth Can Be Computed or Stored

Some scrapes include `depth` field, others don't:

```python
def traverse(comment, depth=1):
    """Always pass depth as parameter, don't rely on field."""
    stored_depth = comment.get('depth', depth)
    actual_depth = max(depth, stored_depth)  # Use whichever is available
    
    for reply in comment.get('replies', []):
        traverse(reply, actual_depth + 1)
```

### 3. Replies Can Be Empty List or Missing

Always use `.get()` with default:

```python
replies = comment.get('replies', [])  # Safe: returns [] if missing
```

### 4. Large Trees Can Cause Stack Overflow

For very deep threads (depth > 100), use iterative approach:

```python
def traverse_iterative(root_comments):
    """Iterative traversal to avoid stack overflow."""
    stack = [(comment, 0) for comment in root_comments]
    
    while stack:
        comment, depth = stack.pop()
        
        # Process comment
        process(comment, depth)
        
        # Add children to stack
        for reply in comment.get('replies', []):
            stack.append((reply, depth + 1))
```

## Example: Complete Pruning Analysis

```python
def analyze_for_pruning(comment, parent_score=None, depth=0):
    """
    Analyze comment tree and return statistics about pruning.
    
    Returns dict with:
    - total_comments: Total in subtree
    - prunable_comments: Comments that would be pruned
    - requests_saved: Estimated API savings
    """
    score = comment.get('score', 1)
    
    stats = {
        'total_comments': 1,
        'prunable_comments': 0,
        'requests_saved': 0
    }
    
    # Check if this subtree would be pruned
    would_prune = (depth >= 4 and parent_score == 1 and score == 1)
    
    if would_prune:
        # Count entire subtree
        subtree_size = count_subtree_size(comment)
        stats['prunable_comments'] = subtree_size
        stats['requests_saved'] = estimate_requests(subtree_size, depth)
        # Don't recurse into pruned subtree
        return stats
    
    # Recurse into children
    for reply in comment.get('replies', []):
        child_stats = analyze_for_pruning(reply, parent_score=score, depth=depth + 1)
        stats['total_comments'] += child_stats['total_comments']
        stats['prunable_comments'] += child_stats['prunable_comments']
        stats['requests_saved'] += child_stats['requests_saved']
    
    return stats
```

## Quick Reference

| Operation | Approach | Complexity |
|-----------|----------|------------|
| Count all comments | DFS or BFS | O(n) |
| Find max depth | DFS with tracking | O(n) |
| Find comment by ID | DFS with early exit | O(n) worst case |
| Prune subtrees | DFS with conditional skip | O(n) |
| Level-order processing | BFS with queue | O(n) |
| Path-dependent analysis | DFS with path tracking | O(n × d) |

Where:
- n = total number of comments
- d = maximum depth of tree

## Visual Tree Example

```
Post
├─ Comment A (depth=1, score=50)
│  ├─ Reply A1 (depth=2, score=10)
│  │  └─ Reply A1a (depth=3, score=2)
│  │     └─ Reply A1a1 (depth=4, score=1)  ← Low engagement
│  │        └─ Reply A1a1a (depth=5, score=1)  ← PRUNE HERE (2 consecutive score=1)
│  │           └─ [entire subtree skipped]
│  └─ Reply A2 (depth=2, score=25)
└─ Comment B (depth=1, score=100)
   └─ Reply B1 (depth=2, score=40)
      └─ Reply B1a (depth=3, score=8)
```

In JSON:
```json
{
  "comments": [
    {
      "id": "A",
      "score": 50,
      "depth": 1,
      "replies": [
        {
          "id": "A1",
          "score": 10,
          "depth": 2,
          "replies": [
            {
              "id": "A1a",
              "score": 2,
              "depth": 3,
              "replies": [
                {
                  "id": "A1a1",
                  "score": 1,
                  "depth": 4,
                  "replies": [
                    {
                      "id": "A1a1a",
                      "score": 1,
                      "depth": 5,
                      "replies": []
                    }
                  ]
                }
              ]
            }
          ]
        },
        {
          "id": "A2",
          "score": 25,
          "depth": 2,
          "replies": []
        }
      ]
    },
    {
      "id": "B",
      "score": 100,
      "depth": 1,
      "replies": [
        {
          "id": "B1",
          "score": 40,
          "depth": 2,
          "replies": [
            {
              "id": "B1a",
              "score": 8,
              "depth": 3,
              "replies": []
            }
          ]
        }
      ]
    }
  ]
}
```

## Key Takeaways for AI

1. **Always check for `replies` field** - use `.get('replies', [])`
2. **Track depth manually** - pass as parameter, don't rely on stored field
3. **Handle deleted comments** - check for `[deleted]` or missing fields
4. **Use recursion for trees** - natural fit for tree structures
5. **Prune early** - if subtree doesn't matter, skip it entirely
6. **Return aggregates bottom-up** - compute subtree stats, bubble up to parent

This structure makes Reddit comment trees **efficient to traverse, analyze, and prune** programmatically.

