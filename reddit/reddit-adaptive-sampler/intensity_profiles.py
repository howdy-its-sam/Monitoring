#!/usr/bin/env python3
"""
Intensity Profiles - Configurable Depth Selection Strategy

Replaces hard-coded depth limits (SHALLOW/MEDIUM/DEEP) with signal-based
thresholds that can be adjusted via CLI or dynamically based on budget.

Philosophy: Instead of "explore to depth N", we ask "should we continue
exploring this branch?" based on multiple signals:
- Engagement scores (upvotes)
- Recency (comment age)
- Sibling density (discussion activity)
- Author reputation (karma, account age)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class IntensityProfile:
    """
    Configurable intensity profile for depth selection.

    Unlike hard depth limits, profiles define WHEN to stop exploring
    based on signal thresholds, not arbitrary depth cutoffs.
    """
    name: str

    # Depth guarantees
    min_guaranteed_depth: int        # Always fetch this deep (visible by default)

    # Stopping criteria
    score_threshold: float            # Stop if both parent & child below this
    recency_window_hours: Optional[float]  # Continue if comment within N hours (None = no limit)

    # Author signals
    karma_threshold: int              # Continue if author above this karma
    account_age_days: int             # Continue if account older than this

    # Context preservation
    sibling_density_threshold: int    # Continue if comment has N+ siblings
    preserve_sibling_context: bool    # Fetch all siblings in active clusters

    # Budget control
    max_requests_per_post: int        # Hard cap for safety
    max_more_objects: int             # Limit on "more" expansions


# Predefined profiles
AGGRESSIVE = IntensityProfile(
    name="aggressive",
    min_guaranteed_depth=4,
    score_threshold=0.0,              # Don't stop on score alone
    recency_window_hours=None,        # No time restriction
    karma_threshold=100,
    account_age_days=7,
    sibling_density_threshold=2,
    preserve_sibling_context=True,
    max_requests_per_post=100,
    max_more_objects=200
)

BALANCED = IntensityProfile(
    name="balanced",
    min_guaranteed_depth=3,
    score_threshold=2.0,
    recency_window_hours=24.0,        # Last 24 hours
    karma_threshold=1000,
    account_age_days=90,
    sibling_density_threshold=3,
    preserve_sibling_context=True,
    max_requests_per_post=25,
    max_more_objects=50
)

CONSERVATIVE = IntensityProfile(
    name="conservative",
    min_guaranteed_depth=3,
    score_threshold=5.0,              # Higher bar
    recency_window_hours=12.0,        # Last 12 hours only
    karma_threshold=10000,
    account_age_days=365,
    sibling_density_threshold=5,
    preserve_sibling_context=False,
    max_requests_per_post=10,
    max_more_objects=20
)

# Default profile
DEFAULT_PROFILE = AGGRESSIVE

# Profile registry for CLI lookup
PROFILES = {
    "aggressive": AGGRESSIVE,
    "balanced": BALANCED,
    "conservative": CONSERVATIVE
}


def get_profile(name: str) -> IntensityProfile:
    """
    Get intensity profile by name.

    Args:
        name: Profile name ("aggressive", "balanced", "conservative")

    Returns:
        IntensityProfile instance

    Raises:
        ValueError: If profile name not found
    """
    if name not in PROFILES:
        raise ValueError(f"Unknown profile '{name}'. Valid profiles: {list(PROFILES.keys())}")
    return PROFILES[name]
