# 24-Hour Test Data Interpretation Guide

## Overview

This guide explains how to interpret all the data collected during the 24-hour endurance test, including the temporal scraping structure, merged datasets, and metadata.

---

## 📁 Directory Structure

```
fix16cdf_24h_endurance/
├── 1hnzdk8/                          # Post ID directory
│   ├── raw_scrapes/                  # Individual scrape snapshots
│   │   ├── scrape_001_*.json        # First scrape
│   │   ├── scrape_002_*.json        # Second scrape
│   │   └── scrape_N_*.json          # Nth scrape
│   └── scheduler_state.json          # Post scheduling metadata
├── 1hopm1d/                          # Another post
│   └── ...
└── [692 more post directories]
```

**Key Points:**
- Each post gets its own directory named by Reddit post ID
- `raw_scrapes/` contains **temporal snapshots** - each scrape is a complete snapshot of the comment tree at that moment
- `scheduler_state.json` tracks when the post should be scraped next and its lifecycle state

---

## 📊 Data File Types

### 1. Raw Scrape Files (`scrape_NNN_TIMESTAMP.json`)

**Format:** `scrape_001_20251019_110658.json`
- `001` = Sequential scrape number (1st, 2nd, 3rd...)
- `20251019` = Date (YYYYMMDD)
- `110658` = Time (HHMMSS)

**Contents:** Complete comment tree snapshot at that moment in time.

**Structure:**
```json
{
  "comments": [
    {
      "id": "abc123",
      "author": "user1",
      "body": "Comment text",
      "score": 42,
      "score_history": [[42, "2025-10-19T11:06:58"]],
      "created_utc": 1729332418,
      "depth": 1,
      "replies": [
        {
          "id": "def456",
          "author": "user2",
          "body": "Reply text",
          "score": 15,
          "score_history": [[15, "2025-10-19T11:06:58"]],
          "depth": 2,
          "replies": []
        }
      ]
    }
  ],
  "metadata": {
    "post_id": "1hnzdk8",
    "subreddit": "wallstreetbets",
    "post_title": "Market discussion thread",
    "post_score": 1523,
    "post_created_utc": 1729330000,
    "scrape_timestamp": "2025-10-19T11:06:58",
    "total_comments": 247,
    "new_comments_this_scrape": 247,
    "api_requests_used": 5
  }
}
```

### 2. Scheduler State Files (`scheduler_state.json`)

**Purpose:** Track when and how to scrape this post.

**Structure:**
```json
{
  "post_id": "1hnzdk8",
  "subreddit": "wallstreetbets",
  "title": "Market discussion thread",
  "created_utc": 1729330000,
  "discovered_at": 1729332000,
  "last_scraped": 1729341710,
  "next_scrape": 1729343510,
  "scrape_count": 6,
  "lifecycle_state": "active",
  "total_comments": 289,
  "priority_score": 8.5,
  "dormancy_indicators": {
    "consecutive_zero_growth": 0,
    "hours_since_post_creation": 3.2,
    "last_growth_rate": 1.2
  }
}
```

**Key Fields:**
- `lifecycle_state`: One of `"discovered"`, `"active"`, `"monitoring"`, `"dormant"`, or `"retired"`
- `next_scrape`: Unix timestamp of when this post should be scraped next
- `scrape_count`: How many times we've scraped this post
- `dormancy_indicators`: Signals used to determine if post should be retired

---

## 🔍 Understanding Temporal Data

### What is "Temporal Scraping"?

Instead of maintaining ONE merged file that we constantly update, we save **complete snapshots** each time we scrape. This allows us to:

1. **Track changes over time** - See exactly when comments appeared and how scores evolved
2. **Recover from errors** - Never lose data from a bad merge
3. **Analyze growth patterns** - Calculate comment velocity, engagement curves
4. **Detect dormancy** - Identify when posts stop receiving new comments

### How to "Merge" Temporal Scrapes

To get the **latest complete state** of a post:

**Option A: Just use the latest scrape**
```bash
# The highest numbered scrape has everything
ls fix16cdf_24h_endurance/1hnzdk8/raw_scrapes/ | sort | tail -1
# → scrape_006_20251019_112210.json
```

**Option B: Build a true temporal merge with score history**

Each comment has a `score_history` field that tracks how its score changed:
```json
{
  "id": "abc123",
  "score": 42,
  "score_history": [
    [15, "2025-10-19T11:06:58"],  // First seen: score=15
    [28, "2025-10-19T11:12:03"],  // Second scrape: score=28
    [42, "2025-10-19T11:22:10"]   // Latest: score=42
  ]
}
```

**To merge multiple scrapes:**
1. Start with the latest scrape (it has all comments)
2. For each comment, the `score_history` field already contains the full temporal data
3. If you need to rebuild it manually, iterate through all scrapes in chronological order and append `[score, timestamp]` entries

---

## 📈 Key Metrics Explained

### 1. Efficiency (ΔInfo/req)

**What it means:** Average new comments discovered per API request.

**Formula:** `new_comments / api_requests_used`

**Examples:**
- `Δ9.6/req` = Excellent! Found 9.6 new comments per API call
- `Δ0.1/req` = Poor - mostly re-scraping known comments
- `Δ0.0/req` = Waste - found nothing new

**Why it matters:** API budget is our limiting factor. Higher efficiency = more data collected.

### 2. Depth Distribution

**Categories:**
- **Shallow (1-3):** Top-level comments and first replies
- **Medium (4-6):** Deep conversations
- **Deep (7+):** Very deep nested threads

**What it tells us:**
- High `shallow %` = Scraping many posts with surface-level engagement
- High `deep %` = Focusing on long conversation chains (higher API cost)

### 3. Dormancy Indicators

**Purpose:** Detect when a post is no longer receiving new comments.

**Signals:**
- `consecutive_zero_growth`: How many scrapes in a row found 0 new comments
- `hours_since_post_creation`: Age of the original post
- `last_growth_rate`: ΔComments from the last scrape

**Retirement Rule (current):**
- If `consecutive_zero_growth >= 3` AND `hours_since_post_creation > 24`, mark as `dormant`
- Dormant posts are removed from the active queue to save API budget

---

## 🧮 Analysis Workflows

### Workflow 1: Calculate Total Comments Collected

```python
import json
from pathlib import Path

data_dir = Path('fix16cdf_24h_endurance')
total_comments = 0

for post_dir in data_dir.iterdir():
    if not post_dir.is_dir():
        continue
    
    # Get latest scrape
    raw_scrapes = post_dir / 'raw_scrapes'
    if not raw_scrapes.exists():
        continue
    
    scrapes = sorted(raw_scrapes.glob('scrape_*.json'))
    if not scrapes:
        continue
    
    latest = scrapes[-1]
    with open(latest) as f:
        data = json.load(f)
        total_comments += data['metadata']['total_comments']

print(f"Total comments: {total_comments:,}")
```

### Workflow 2: Find Most Active Posts

```python
import json
from pathlib import Path

data_dir = Path('fix16cdf_24h_endurance')
posts = []

for post_dir in data_dir.iterdir():
    if not post_dir.is_dir():
        continue
    
    state_file = post_dir / 'scheduler_state.json'
    if not state_file.exists():
        continue
    
    with open(state_file) as f:
        state = json.load(f)
        posts.append({
            'post_id': state['post_id'],
            'subreddit': state['subreddit'],
            'title': state['title'],
            'comments': state['total_comments'],
            'scrape_count': state['scrape_count']
        })

# Sort by comment count
posts.sort(key=lambda x: x['comments'], reverse=True)

print("Top 10 most active posts:")
for i, post in enumerate(posts[:10], 1):
    print(f"{i}. r/{post['subreddit']} - {post['comments']} comments ({post['scrape_count']} scrapes)")
    print(f"   {post['title'][:60]}...")
```

### Workflow 3: Analyze Comment Growth Over Time

```python
import json
from pathlib import Path

post_id = '1hnzdk8'  # Example post
post_dir = Path(f'fix16cdf_24h_endurance/{post_id}')
raw_scrapes = post_dir / 'raw_scrapes'

scrapes = sorted(raw_scrapes.glob('scrape_*.json'))

print(f"Comment growth for post {post_id}:")
print("-" * 60)

for scrape_file in scrapes:
    with open(scrape_file) as f:
        data = json.load(f)
        meta = data['metadata']
        
        timestamp = meta['scrape_timestamp']
        total = meta['total_comments']
        new = meta['new_comments_this_scrape']
        requests = meta['api_requests_used']
        
        print(f"{timestamp}: {total} total (+{new} new, {requests} API reqs)")
```

### Workflow 4: Calculate API Request Efficiency

```python
import json
from pathlib import Path

data_dir = Path('fix16cdf_24h_endurance')
total_requests = 0
total_new_comments = 0

for post_dir in data_dir.iterdir():
    if not post_dir.is_dir():
        continue
    
    raw_scrapes = post_dir / 'raw_scrapes'
    if not raw_scrapes.exists():
        continue
    
    for scrape_file in raw_scrapes.glob('scrape_*.json'):
        with open(scrape_file) as f:
            data = json.load(f)
            meta = data['metadata']
            total_requests += meta['api_requests_used']
            total_new_comments += meta['new_comments_this_scrape']

efficiency = total_new_comments / total_requests if total_requests > 0 else 0
print(f"Overall efficiency: {efficiency:.2f} new comments per API request")
print(f"Total API requests: {total_requests:,}")
print(f"Total new comments: {total_new_comments:,}")
```

---

## 🎯 Key Questions This Data Answers

### 1. **Did the scraper run stably for 24 hours?**

**Check:**
- Log file timestamps (start vs end)
- Budget never hit zero
- No long gaps in scraping

**Tools:**
```bash
# Check test duration
grep "🚀 Starting at" test_1440min_20251018_112237.log
grep "✅ UNIFIED SCRAPER COMPLETE" test_1440min_20251018_112237.log

# Check for budget problems
grep "Budget: 0.0" test_1440min_20251018_112237.log | wc -l
```

### 2. **How much data did we collect?**

**Check:**
- Total posts discovered
- Total comments scraped
- Data file sizes

**Tools:**
```bash
# Count posts
ls -d fix16cdf_24h_endurance/*/ | wc -l

# Count scrape files
find fix16cdf_24h_endurance -name "scrape_*.json" | wc -l

# Total data size
du -sh fix16cdf_24h_endurance
```

### 3. **Is the dormancy system working?**

**Check:**
- How many posts were retired?
- Are we wasting API requests on dead posts?

**Tools:**
```bash
# Count retirement events
grep "🗑️  Retired" test_1440min_20251018_112237.log

# Check for dormant posts
grep '"lifecycle_state": "dormant"' fix16cdf_24h_endurance/*/scheduler_state.json | wc -l
```

### 4. **What's the depth vs efficiency tradeoff?**

**Check:**
- Depth distribution percentages
- Efficiency by depth category

**Tools:** Run `analyze_24h_results.py` (see below)

---

## 🛠️ Automated Analysis Tools

### Run Complete Analysis

```bash
cd 24h_final_report
python3 analyze_24h_results.py test_1440min_20251018_112237.log ../fix16cdf_24h_endurance
```

This will:
- Parse the entire log file
- Calculate all key metrics
- Generate a comprehensive report
- Save results to `analysis_results.json`

### Output Includes:
- ✅ Overall performance stats
- 💰 Budget management analysis
- 🔍 Discovery effectiveness
- 😴 Dormancy/retirement behavior
- 📏 Depth distribution patterns
- 📂 Data file statistics

---

## 📝 Data Format Reference

### Comment Object Schema

```typescript
interface Comment {
  id: string;                    // Reddit comment ID
  author: string;                // Username (or "[deleted]")
  body: string;                  // Comment text content
  score: number;                 // Current score (upvotes - downvotes)
  score_history: [number, string][]; // [[score, timestamp], ...]
  created_utc: number;           // Unix timestamp of comment creation
  depth: number;                 // Nesting level (1 = top-level)
  replies: Comment[];            // Array of child comments
  permalink?: string;            // URL to this comment
  is_submitter?: boolean;        // True if author = OP
  edited?: number | boolean;     // Edit timestamp or false
  distinguished?: string;        // "moderator", "admin", or null
}
```

### Metadata Object Schema

```typescript
interface ScrapeMetadata {
  post_id: string;               // Reddit post ID
  subreddit: string;             // Subreddit name (without "r/")
  post_title: string;            // Post title
  post_score: number;            // Post score at scrape time
  post_created_utc: number;      // Unix timestamp of post creation
  scrape_timestamp: string;      // ISO timestamp of this scrape
  total_comments: number;        // Total comments in tree
  new_comments_this_scrape: number; // New comments found this scrape
  api_requests_used: number;     // API calls used for this scrape
}
```

### Scheduler State Schema

```typescript
interface SchedulerState {
  post_id: string;
  subreddit: string;
  title: string;
  created_utc: number;           // When post was created
  discovered_at: number;         // When we first discovered it
  last_scraped: number;          // Last scrape timestamp
  next_scrape: number;           // Scheduled next scrape
  scrape_count: number;          // How many times scraped
  lifecycle_state: "discovered" | "active" | "monitoring" | "dormant" | "retired";
  total_comments: number;        // Known comment count
  priority_score: number;        // 0-10 priority ranking
  dormancy_indicators: {
    consecutive_zero_growth: number;
    hours_since_post_creation: number;
    last_growth_rate: number;
  };
}
```

---

## 💡 Tips for Data Analysis

### 1. **Always Use the Latest Scrape**
The most recent `scrape_NNN_*.json` file contains the complete current state. Earlier scrapes are useful for temporal analysis but not needed for current stats.

### 2. **Check Scheduler State for Lifecycle Info**
The `scheduler_state.json` tells you if a post is still active or has been retired. Don't assume all posts in the directory are still being scraped.

### 3. **Score History is Already Merged**
You don't need to manually merge scrapes to get score evolution. The `score_history` field in the latest scrape already contains the full temporal data.

### 4. **API Requests ≠ Comments**
One API request can fetch multiple comments. The `api_requests_used` field tells you how many actual API calls were needed, which is what counts against your rate limit.

### 5. **Depth is Relative to Post, Not Parent**
A `depth: 5` comment is 5 levels deep from the post (not 5 levels from its immediate parent). The `replies` nesting shows the tree structure.

---

## 🔬 Advanced: Reconstructing Full Temporal History

If you need to reconstruct exactly when each comment appeared and how scores changed:

```python
import json
from pathlib import Path
from collections import defaultdict

def build_temporal_history(post_id):
    """Build complete temporal history for a post"""
    post_dir = Path(f'fix16cdf_24h_endurance/{post_id}')
    raw_scrapes = post_dir / 'raw_scrapes'
    
    # Track each comment's history
    comment_history = defaultdict(list)
    
    # Process scrapes in chronological order
    scrapes = sorted(raw_scrapes.glob('scrape_*.json'))
    
    for scrape_file in scrapes:
        with open(scrape_file) as f:
            data = json.load(f)
            timestamp = data['metadata']['scrape_timestamp']
            
            # Recursively process comment tree
            def process_comments(comments):
                for comment in comments:
                    comment_history[comment['id']].append({
                        'timestamp': timestamp,
                        'score': comment['score'],
                        'body': comment['body']
                    })
                    if comment['replies']:
                        process_comments(comment['replies'])
            
            process_comments(data['comments'])
    
    return comment_history

# Example usage
history = build_temporal_history('1hnzdk8')
print(f"Tracked {len(history)} unique comments")

# Show score evolution for a specific comment
comment_id = 'abc123'
if comment_id in history:
    print(f"\nScore evolution for comment {comment_id}:")
    for entry in history[comment_id]:
        print(f"  {entry['timestamp']}: score={entry['score']}")
```

---

## 🎓 Summary

**The 24-hour test data provides:**
1. ✅ Complete temporal history of all scraped posts and comments
2. ✅ Scheduler metadata showing lifecycle transitions
3. ✅ Detailed metrics on efficiency, budget, and discovery
4. ✅ Evidence of dormancy system performance

**To analyze it:**
1. Use `analyze_24h_results.py` for automated analysis
2. Use the latest scrape file for current state
3. Use `score_history` for temporal patterns
4. Check `scheduler_state.json` for lifecycle info

**Key insight:**
We use **temporal snapshots** instead of a single merged file because it preserves the complete history without risk of data loss from failed merges. The latest scrape is always the "merged" version you need.

