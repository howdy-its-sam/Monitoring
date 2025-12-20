#!/usr/bin/env python3
"""
Author Profile Fetcher - Reddit User API Integration

Fetches author metadata from Reddit's /user/{username}/about endpoint.
"""

import requests
from datetime import datetime
from typing import Optional
from author_cache import AuthorProfile


def fetch_author_profile(username: str, session: Optional[requests.Session] = None) -> Optional[AuthorProfile]:
    """
    Fetch author profile from Reddit API.

    Args:
        username: Reddit username (without /u/ prefix)
        session: Optional authenticated session (for OAuth rate limits)

    Returns:
        AuthorProfile if successful, None if failed
    """
    try:
        # Use OAuth endpoint if session provided
        if session:
            url = f'https://oauth.reddit.com/user/{username}/about'
            response = session.get(url, timeout=10)
        else:
            url = f'https://www.reddit.com/user/{username}/about.json'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return None

        data = response.json().get('data', {})

        # Calculate account age
        created_utc = data.get('created_utc', 0)
        account_age_days = int((datetime.now().timestamp() - created_utc) / 86400)

        # Create profile
        profile = AuthorProfile(
            username=username,
            comment_karma=data.get('comment_karma', 0),
            link_karma=data.get('link_karma', 0),
            created_utc=created_utc,
            account_age_days=account_age_days,
            verified=data.get('verified', False),
            is_gold=data.get('is_gold', False) or data.get('is_premium', False),
            is_mod=data.get('is_mod', False),
            hide_from_robots=data.get('hide_from_robots', False),
            profile_is_private=False,  # Not directly exposed, would need separate check
            last_updated=datetime.now().isoformat()
        )

        return profile

    except (requests.RequestException, KeyError, ValueError) as e:
        print(f"⚠️  Failed to fetch profile for u/{username}: {e}")
        return None


def batch_fetch_authors(usernames: list[str], session: Optional[requests.Session] = None, max_fetches: int = 10) -> dict[str, AuthorProfile]:
    """
    Fetch multiple author profiles (respects max limit).

    Note: Reddit API does not support batch user lookups, so this makes
    individual requests. Use sparingly and cache aggressively.

    Args:
        usernames: List of usernames to fetch
        session: Optional authenticated session
        max_fetches: Maximum number of profiles to fetch

    Returns:
        Dictionary of {username: AuthorProfile} for successful fetches
    """
    results = {}

    for username in usernames[:max_fetches]:
        profile = fetch_author_profile(username, session)
        if profile:
            results[username] = profile

    return results
