"""
Reddit OAuth Authentication Module
Handles OAuth authentication for Reddit API to increase rate limits from ~60 to ~600 requests/minute.
"""

import requests
import os
from typing import Optional, Dict, Tuple


def load_credentials(filepath: str = 'reddit_credentials.txt') -> Optional[Dict[str, str]]:
    """
    Load Reddit API credentials from a text file.
    
    Expected format:
        CLIENT_ID=your_client_id
        CLIENT_SECRET=your_secret
        USERNAME=your_username
        PASSWORD=your_password
    
    Args:
        filepath: Path to credentials file
        
    Returns:
        Dictionary with credentials or None if file not found/invalid
    """
    if not os.path.exists(filepath):
        print(f"⚠️  Credentials file not found: {filepath}")
        return None
    
    try:
        credentials = {}
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    credentials[key.strip()] = value.strip()
        
        # Validate required fields
        required = ['CLIENT_ID', 'CLIENT_SECRET', 'USERNAME', 'PASSWORD']
        missing = [field for field in required if field not in credentials or credentials[field].startswith('your_')]
        
        if missing:
            print(f"⚠️  Missing or incomplete credentials: {', '.join(missing)}")
            return None
        
        return credentials
    
    except Exception as e:
        print(f"⚠️  Error loading credentials: {e}")
        return None


def get_oauth_token(credentials: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """
    Authenticate with Reddit and get an OAuth access token.
    
    Args:
        credentials: Dictionary with CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD
        
    Returns:
        Tuple of (access_token, username) or None if authentication fails
    """
    try:
        # Reddit OAuth endpoint
        auth_url = 'https://www.reddit.com/api/v1/access_token'
        
        # Basic auth with client credentials
        auth = (credentials['CLIENT_ID'], credentials['CLIENT_SECRET'])
        
        # Request body
        data = {
            'grant_type': 'password',
            'username': credentials['USERNAME'],
            'password': credentials['PASSWORD']
        }
        
        # User agent (Reddit requires a unique user agent)
        headers = {
            'User-Agent': f"RedditScraper/1.0 (by /u/{credentials['USERNAME']})"
        }
        
        # Make authentication request
        response = requests.post(auth_url, auth=auth, data=data, headers=headers, timeout=10)
        response.raise_for_status()
        
        token_data = response.json()
        access_token = token_data.get('access_token')
        
        if not access_token:
            print("⚠️  No access token in response")
            return None
        
        print(f"✅ OAuth authenticated as u/{credentials['USERNAME']}")
        return access_token, credentials['USERNAME']
    
    except requests.exceptions.RequestException as e:
        print(f"⚠️  OAuth authentication failed: {e}")
        return None
    except Exception as e:
        print(f"⚠️  Unexpected error during authentication: {e}")
        return None


def get_authenticated_session(filepath: str = 'reddit_credentials.txt') -> Optional[requests.Session]:
    """
    Create an authenticated requests.Session for Reddit API calls.
    
    This session will have:
    - OAuth bearer token in Authorization header
    - Proper User-Agent header
    - 10x higher rate limits (~600 requests/minute vs ~60)
    
    Args:
        filepath: Path to credentials file
        
    Returns:
        Authenticated requests.Session or None if authentication fails
    """
    # Load credentials
    credentials = load_credentials(filepath)
    if not credentials:
        print("⚠️  Falling back to unauthenticated mode (lower rate limits)")
        return None
    
    # Get OAuth token
    auth_result = get_oauth_token(credentials)
    if not auth_result:
        print("⚠️  Falling back to unauthenticated mode (lower rate limits)")
        return None
    
    access_token, username = auth_result
    
    # Create authenticated session
    session = requests.Session()
    session.headers.update({
        'Authorization': f'Bearer {access_token}',
        'User-Agent': f'RedditScraper/1.0 (by /u/{username})'
    })
    
    return session


if __name__ == '__main__':
    # Test authentication
    print("Testing Reddit OAuth authentication...")
    print("="*60)
    
    session = get_authenticated_session()
    
    if session:
        print("\n✅ Authentication successful!")
        print("📊 Testing API access...")
        
        # Test with a simple API call
        try:
            response = session.get('https://oauth.reddit.com/api/v1/me', timeout=10)
            response.raise_for_status()
            user_data = response.json()
            print(f"✅ API test successful! Logged in as: {user_data.get('name', 'Unknown')}")
        except Exception as e:
            print(f"⚠️  API test failed: {e}")
    else:
        print("\n❌ Authentication failed")
        print("Please check your credentials in reddit_credentials.txt")

