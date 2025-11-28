#!/usr/bin/env python3
"""
Depth Advisor - Signal-Based Depth Selection

Replaces hard depth limits with multi-signal decision logic.
Integrates with IntensityProfiles for configurable thresholds.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from collections import deque

from intensity_profiles import IntensityProfile, AGGRESSIVE
from author_cache import AuthorCache, AuthorProfile


def should_continue_exploring(
    comment: Dict,
    parent: Optional[Dict],
    profile: IntensityProfile,
    author_cache: AuthorCache,
    current_time: Optional[datetime] = None
) -> Tuple[bool, bool]:
    """
    Decide whether to explore deeper from this comment.

    Uses multiple signals instead of hard depth cutoffs:
    - Minimum guaranteed depth (always explore visible comments)
    - Recency (recent comments may not have votes yet)
    - Sibling density (active discussions worth preserving)
    - Author reputation (high-karma authors explored deeper)
    - Engagement scores (stop if both parent & child below threshold)

    Args:
        comment: Current comment node
        parent: Parent comment node (None if top-level)
        profile: IntensityProfile with threshold settings
        author_cache: Cache of author profiles
        current_time: Current time (defaults to now)

    Returns:
        Tuple of (continue_exploring, fetch_all_siblings)
        - continue_exploring: Should we go deeper from this comment?
        - fetch_all_siblings: Should we fetch ALL siblings for context?
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # Extract comment data
    depth = comment.get('depth', 0)
    created_utc = comment.get('createdUtc', 0)
    author = comment.get('author', '')

    # ALWAYS fetch min guaranteed depth (visible by default)
    if depth < profile.min_guaranteed_depth:
        return (True, True)  # Fetch everything in visible range

    # Check recency (handles "too new to have votes" problem)
    if profile.recency_window_hours is not None:
        comment_age_hours = (current_time.timestamp() - created_utc) / 3600
        if comment_age_hours < profile.recency_window_hours:
            return (True, True)  # Recent activity = fetch everything

    # Check sibling density (active discussion cluster)
    # Note: This requires access to parent's children, which we'll handle in the caller
    # For now, we'll return a signal that the caller should check

    # Check author signals (if available in cache)
    author_profile = author_cache.get(author) if author and author != '[deleted]' else None
    if author_profile:
        if (author_profile.comment_karma > profile.karma_threshold or
            author_profile.account_age_days > profile.account_age_days):
            return (True, False)  # Continue exploring, but selectively

    # Check engagement scores
    parent_score = 0
    if parent and parent.get('scoreHistory'):
        parent_score = parent['scoreHistory'][-1].get('value', 0)

    comment_score = 0
    if comment.get('scoreHistory'):
        comment_score = comment['scoreHistory'][-1].get('value', 0)

    # Both parent and child below threshold = dead branch
    if parent and parent_score <= profile.score_threshold and comment_score <= profile.score_threshold:
        return (False, False)  # Stop exploring

    # If only one is above threshold, continue selectively
    if comment_score > profile.score_threshold:
        return (True, False)  # This comment is interesting, explore deeper

    # Default: continue selectively
    return (True, False)


def check_sibling_density(comment_id: str, thread_data: Dict, threshold: int) -> bool:
    """
    Check if comment has enough siblings to be part of an active cluster.

    Args:
        comment_id: Comment ID to check
        thread_data: Full thread data dictionary
        threshold: Minimum number of siblings required

    Returns:
        True if comment has >= threshold siblings
    """
    # Find this comment's parent
    comment = thread_data.get(comment_id)
    if not comment:
        return False

    parent_id = comment.get('parentId')
    if not parent_id:
        return False  # Top-level comment

    # Count siblings (other children of same parent)
    siblings = [
        node for node in thread_data.values()
        if node.get('parentId') == parent_id and node.get('id') != comment_id
    ]

    return len(siblings) >= threshold


class DepthAdvisor:
    """
    Adaptive depth selection using signal-based thresholds.

    Maintains per-post efficiency history for dynamic profile adjustment.
    """

    def __init__(self, profile: IntensityProfile = AGGRESSIVE, history_window: int = 3):
        """
        Initialize depth advisor.

        Args:
            profile: IntensityProfile to use for decisions
            history_window: Number of recent scrapes to track for efficiency
        """
        self.profile = profile
        self.history_window = history_window

        # Track efficiency history per post
        self.efficiency_history: Dict[str, deque] = {}  # post_id → deque of (ΔInfo/request)

        # Track which posts are using which profile (for analytics)
        self.post_profiles: Dict[str, str] = {}  # post_id → profile_name

    def get_profile(self, post_id: str) -> IntensityProfile:
        """
        Get current intensity profile for a post.

        Args:
            post_id: Reddit post ID

        Returns:
            IntensityProfile (defaults to instance profile)
        """
        return self.profile

    def set_profile(self, profile: IntensityProfile):
        """
        Update the global intensity profile.

        Args:
            profile: New IntensityProfile to use
        """
        self.profile = profile

    def record_scrape(self, post_id: str, delta_info: float, api_requests: int):
        """
        Record scrape result for efficiency tracking.

        Args:
            post_id: Reddit post ID
            delta_info: Information gain from this scrape
            api_requests: Number of API requests made
        """
        # Compute marginal efficiency
        efficiency = delta_info / api_requests if api_requests > 0 else 0.0

        # Initialize history if needed
        if post_id not in self.efficiency_history:
            self.efficiency_history[post_id] = deque(maxlen=self.history_window)

        # Add to history
        self.efficiency_history[post_id].append(efficiency)

        # Track which profile was used
        self.post_profiles[post_id] = self.profile.name

    def get_avg_efficiency(self, post_id: str) -> float:
        """
        Get rolling average efficiency for a post.

        Args:
            post_id: Reddit post ID

        Returns:
            Average ΔInfo/request over history window
        """
        if post_id not in self.efficiency_history or not self.efficiency_history[post_id]:
            return 0.0

        history = self.efficiency_history[post_id]
        return sum(history) / len(history)

    def recommend_profile_for_new_post(self, subreddit: Optional[str] = None) -> IntensityProfile:
        """
        Recommend initial intensity profile for a newly discovered post.

        Default: Use instance profile (typically AGGRESSIVE)

        Future: Could use subreddit-specific priors.

        Args:
            subreddit: Optional subreddit name for prior-based recommendation

        Returns:
            IntensityProfile recommendation
        """
        # For now, use instance profile
        # Future: could have per-subreddit preferences
        return self.profile

    def get_status(self) -> Dict:
        """
        Get advisor status for monitoring.

        Returns:
            Dict with metrics
        """
        # Compute average efficiency across all posts
        all_efficiencies = []
        for history in self.efficiency_history.values():
            all_efficiencies.extend(history)

        avg_efficiency = sum(all_efficiencies) / len(all_efficiencies) if all_efficiencies else 0.0

        # Count posts by profile
        profile_counts = {}
        for profile_name in self.post_profiles.values():
            profile_counts[profile_name] = profile_counts.get(profile_name, 0) + 1

        return {
            'current_profile': self.profile.name,
            'total_posts': len(self.efficiency_history),
            'avg_efficiency': avg_efficiency,
            'profile_distribution': profile_counts
        }
