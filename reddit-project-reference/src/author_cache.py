#!/usr/bin/env python3
"""
Author Profile Cache - Local storage for Reddit user metadata

Caches author profiles to minimize API calls and enable reputation-based
depth selection decisions.
"""

import json
import os
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, Dict


@dataclass
class AuthorProfile:
    """Reddit user profile data."""
    username: str
    comment_karma: int
    link_karma: int
    created_utc: float              # Account creation timestamp
    account_age_days: int           # Calculated from created_utc
    verified: bool
    is_gold: bool
    is_mod: bool
    hide_from_robots: bool          # Search engine visibility preference
    profile_is_private: bool        # Profile page privacy (if detectable)
    last_updated: str               # ISO timestamp of last fetch

    @property
    def total_karma(self) -> int:
        """Total karma (comment + link)."""
        return self.comment_karma + self.link_karma

    @property
    def karma_per_day(self) -> float:
        """Average karma earned per day."""
        if self.account_age_days == 0:
            return 0.0
        return self.total_karma / self.account_age_days

    @property
    def comment_to_post_ratio(self) -> float:
        """Ratio of comment karma to link karma."""
        if self.link_karma == 0:
            return float('inf') if self.comment_karma > 0 else 0.0
        return self.comment_karma / self.link_karma


class AuthorCache:
    """
    Local cache for author profiles with TTL expiry.

    Cache file format: JSON with {username: {profile_data}}
    """

    def __init__(self, cache_file: str = 'author_cache.json', ttl_days: int = 7):
        """
        Initialize author cache.

        Args:
            cache_file: Path to cache file
            ttl_days: Cache time-to-live in days (default: 7)
        """
        self.cache_file = cache_file
        self.ttl_days = ttl_days
        self.cache: Dict[str, AuthorProfile] = {}
        self._load()

    def _load(self):
        """Load cache from disk."""
        if not os.path.exists(self.cache_file):
            return

        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)

            # Deserialize into AuthorProfile objects
            for username, profile_dict in data.items():
                try:
                    self.cache[username] = AuthorProfile(**profile_dict)
                except (TypeError, KeyError) as e:
                    print(f"⚠️  Failed to load profile for {username}: {e}")

            print(f"📚 Loaded {len(self.cache)} author profiles from cache")

        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️  Failed to load author cache: {e}")

    def save(self):
        """Save cache to disk."""
        try:
            # Serialize AuthorProfile objects to dicts
            data = {username: asdict(profile) for username, profile in self.cache.items()}

            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)

        except IOError as e:
            print(f"⚠️  Failed to save author cache: {e}")

    def get(self, username: str) -> Optional[AuthorProfile]:
        """
        Get author profile from cache if present and not expired.

        Args:
            username: Reddit username

        Returns:
            AuthorProfile if cached and fresh, None otherwise
        """
        if username not in self.cache:
            return None

        profile = self.cache[username]

        # Check if expired
        last_updated = datetime.fromisoformat(profile.last_updated)
        age = datetime.now() - last_updated

        if age > timedelta(days=self.ttl_days):
            # Expired, remove from cache
            del self.cache[username]
            return None

        return profile

    def set(self, profile: AuthorProfile):
        """
        Add or update author profile in cache.

        Args:
            profile: AuthorProfile to cache
        """
        self.cache[profile.username] = profile

    def get_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics
        """
        if not self.cache:
            return {
                'total_profiles': 0,
                'avg_karma': 0,
                'avg_account_age_days': 0
            }

        profiles = list(self.cache.values())

        return {
            'total_profiles': len(profiles),
            'avg_karma': sum(p.total_karma for p in profiles) / len(profiles),
            'avg_account_age_days': sum(p.account_age_days for p in profiles) / len(profiles),
            'avg_comment_karma': sum(p.comment_karma for p in profiles) / len(profiles),
            'avg_link_karma': sum(p.link_karma for p in profiles) / len(profiles)
        }
