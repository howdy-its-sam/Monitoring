#!/usr/bin/env python3
"""
Thread-Scoped Author Interestingness Scoring

Calculates author value based ONLY on their activity within a single thread.
No external API calls required - uses data already collected during scraping.
"""

from typing import Dict


def calculate_author_interestingness(thread_data: Dict) -> Dict[str, float]:
    """
    Score authors based on their activity in this thread only.

    Scoring formula (tunable weights):
        interestingness = (
            total_score * 1.0 +              # Raw engagement
            comment_count * 0.5 +            # Participation
            (total_length / 100) * 0.3 +     # Effort (per 100 chars)
            spawned_replies * 2.0 +          # Discussion catalyst
            max_depth_reached * 0.2          # Deep engagement
        )

    Args:
        thread_data: Dictionary of {node_id: node_data} from Reddit scrape

    Returns:
        Dictionary of {username: interestingness_score}
    """
    author_metrics = {}

    # Pass 1: Collect per-author metrics
    for node_id, node in thread_data.items():
        author = node.get('author')
        if not author or author in ['[deleted]', 'AutoModerator']:
            continue

        if author not in author_metrics:
            author_metrics[author] = {
                'total_score': 0,
                'comment_count': 0,
                'total_length': 0,
                'spawned_replies': 0,
                'max_depth_reached': 0
            }

        # Current node's contribution
        score_history = node.get('scoreHistory', [])
        score = score_history[-1]['value'] if score_history else 0

        text_history = node.get('textHistory', [])
        text = text_history[-1]['value'] if text_history else ""

        depth = node.get('depth', 0)

        author_metrics[author]['total_score'] += score
        author_metrics[author]['comment_count'] += 1
        author_metrics[author]['total_length'] += len(text)
        author_metrics[author]['max_depth_reached'] = max(
            author_metrics[author]['max_depth_reached'],
            depth
        )

        # Count replies spawned (children of this node)
        node_id_full = node.get('id', node_id)
        children = [n for n in thread_data.values() if n.get('parentId') == f"t1_{node_id_full}"]
        author_metrics[author]['spawned_replies'] += len(children)

    # Pass 2: Calculate final interestingness scores
    results = {}
    for author, metrics in author_metrics.items():
        interestingness = (
            metrics['total_score'] * 1.0 +
            metrics['comment_count'] * 0.5 +
            (metrics['total_length'] / 100) * 0.3 +
            metrics['spawned_replies'] * 2.0 +
            metrics['max_depth_reached'] * 0.2
        )
        results[author] = interestingness

    return results


def get_top_authors(thread_data: Dict, limit: int = 10) -> list[tuple[str, float]]:
    """
    Get top N authors by interestingness in this thread.

    Args:
        thread_data: Dictionary of {node_id: node_data}
        limit: Number of top authors to return

    Returns:
        List of (username, score) tuples, sorted by score descending
    """
    scores = calculate_author_interestingness(thread_data)
    sorted_authors = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_authors[:limit]
