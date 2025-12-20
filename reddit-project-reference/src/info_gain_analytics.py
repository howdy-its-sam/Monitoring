#!/usr/bin/env python3
"""
Information Gain Analytics & Visualization
Computes ΔInfo per scrape, half-life, dormancy metrics, and λ estimation.
Based on reference_books/info_gain_analytics_visualization.ipynb
"""

import os
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd

# Keep analytics aligned with runtime dormancy criteria
DORMANCY_ZERO_WINDOW = int(os.getenv("SCRAPER_DORMANCY_ZERO_STREAK", "2"))


def parse_iso_utc(s: str) -> Optional[datetime]:
    """Robust timestamp parsing"""
    if not s:
        return None
    s = s.replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        m = re.search(r"(\d{8})[T_]?(\d{6})", s)
        if m:
            return datetime.strptime(
                m.group(1) + m.group(2), 
                "%Y%m%d%H%M%S"
            ).replace(tzinfo=timezone.utc)
        return None


def collect_nodes(data: Dict) -> List[Tuple[str, Dict]]:
    """
    Traverse merged JSON and collect all nodes (post + comments).
    Returns list of (type, node) tuples.
    """
    nodes = []
    nodes.append(("post", data.get("post", {})))
    
    queue = list(data.get("comments", []) or [])
    while queue:
        c = queue.pop(0)
        nodes.append(("comment", c))
        for ch in c.get("replies", []) or []:
            if isinstance(ch, dict):
                queue.append(ch)
    
    return nodes


def compute_delta_info(merged: Dict, 
                       w_new: float = 1.0,
                       w_edit: float = 0.5, 
                       w_score: float = 0.2,
                       w_delete: float = 0.1) -> Tuple[Dict, List[datetime]]:
    """
    Compute ΔInfo timeline from merged data.
    
    ΔInfo_t = w_new * new_comments 
            + w_edit * edited_comments
            + w_score * score_changed
            + w_delete * deleted_comments
    
    Returns:
    - per_ts: dict mapping timestamp → {new_comments, edited_comments, score_changed, deleted_comments, delta_info}
    - timeline: sorted list of timestamps
    """
    nodes = collect_nodes(merged)
    
    # Build timeline from post.score_history
    root_scores = nodes[0][1].get("score_history", [])
    timeline = sorted(set([
        parse_iso_utc(ts) 
        for _, ts in root_scores 
        if parse_iso_utc(ts)
    ]))
    
    # Initialize counters
    per_ts = {
        t: {
            "new_comments": 0,
            "edited_comments": 0, 
            "score_changed": 0,
            "deleted_comments": 0
        } 
        for t in timeline
    }
    
    # Process each node
    for idx, (kind, n) in enumerate(nodes):
        # Track new comments (first appearance)
        sh = n.get("score_history", [])
        if sh and idx != 0:  # Skip post root
            seq = [(val, parse_iso_utc(ts)) for val, ts in sh if parse_iso_utc(ts)]
            seq.sort(key=lambda x: x[1])
            if seq:
                first_ts = seq[0][1]
                if first_ts in per_ts:
                    per_ts[first_ts]["new_comments"] += 1
        
        # Track score changes
        if sh:
            seq = [(val, parse_iso_utc(ts)) for val, ts in sh if parse_iso_utc(ts)]
            seq.sort(key=lambda x: x[1])
            prev = None
            for val, ts in seq:
                if ts in per_ts and prev is not None and val is not None and prev is not None:
                    if val != prev:
                        per_ts[ts]["score_changed"] += 1
                prev = val
        
        # Track text edits
        th = n.get("text_history", [])
        for _, ts in th or []:
            t = parse_iso_utc(ts)
            if t in per_ts:
                per_ts[t]["edited_comments"] += 1
        
        # Track deletions
        if n.get("deleted") and n.get("deleted_at"):
            t = parse_iso_utc(n["deleted_at"])
            if t in per_ts:
                per_ts[t]["deleted_comments"] += 1
    
    # Compute weighted ΔInfo
    for t in timeline:
        d = per_ts[t]
        d["delta_info"] = (
            w_new * d["new_comments"] +
            w_edit * d["edited_comments"] +
            w_score * d["score_changed"] +
            w_delete * d["deleted_comments"]
        )
    
    return per_ts, timeline


def half_life_hours(timeline: List[datetime], deltas: List[float]) -> Optional[float]:
    """
    Compute half-life: time to reach 50% of cumulative ΔInfo.
    """
    if not deltas or sum(deltas) == 0:
        return None
    
    cum = np.cumsum(deltas)
    target = cum[-1] / 2.0
    idx = int(np.argmax(cum >= target))
    
    return (timeline[idx] - timeline[0]).total_seconds() / 3600.0


def time_to_dormancy_hours(timeline: List[datetime], deltas: List[float], window: int = DORMANCY_ZERO_WINDOW) -> Optional[float]:
    """
    Time until first occurrence of 'window' consecutive zero-Δ scrapes.
    """
    window = max(1, window)
    for i in range(0, len(deltas) - window + 1):
        if all(v == 0 for v in deltas[i:i+window]):
            return (timeline[i] - timeline[0]).total_seconds() / 3600.0
    return None


def waste_rate(deltas: List[float]) -> Optional[float]:
    """
    Fraction of zero-Δ scrapes (wasted API calls).
    """
    if not deltas:
        return None
    useful = sum(1 for x in deltas if x > 0)
    return 1 - useful / len(deltas)


def estimate_lambda_from_curve(timeline: List[datetime], deltas: List[float], eps: float = 1e-6) -> Optional[float]:
    """
    Fit exponential decay: ΔInfo ~ A * exp(-λ * t)
    Returns estimated λ (decay rate in 1/hour).
    """
    if len(timeline) < 3 or sum(deltas) <= 0:
        return None
    
    t_hours = np.array([
        (t - timeline[0]).total_seconds() / 3600.0 
        for t in timeline
    ])
    y = np.array(deltas, dtype=float)
    y = y / (y.max() + eps)
    y = np.clip(y, eps, 1.0)  # Avoid log(0)
    
    try:
        coeffs = np.polyfit(t_hours, np.log(y), 1)
        lam = -coeffs[0]
        return max(lam, 0.0)
    except:
        return None


def analyze_post(merged_file: str) -> Optional[Dict]:
    """
    Analyze a single merged post file.
    Returns metrics dict or None.
    """
    if not os.path.exists(merged_file):
        return None
    
    with open(merged_file, 'r') as f:
        data = json.load(f)
    
    post_id = data.get("post", {}).get("id", os.path.basename(os.path.dirname(merged_file)))
    
    per_ts, timeline = compute_delta_info(data)
    deltas = [per_ts[t]["delta_info"] for t in timeline]
    
    if not timeline:
        return None
    
    return {
        "post_id": post_id,
        "scrapes": len(timeline),
        "total_delta_info": sum(deltas),
        "half_life_h": half_life_hours(timeline, deltas),
        "dormancy_h": time_to_dormancy_hours(timeline, deltas),
        "waste_rate": waste_rate(deltas),
        "lambda_hat": estimate_lambda_from_curve(timeline, deltas),
        "duration_h": (timeline[-1] - timeline[0]).total_seconds() / 3600.0,
        "first_ts": timeline[0].isoformat(),
        "last_ts": timeline[-1].isoformat(),
    }


def analyze_dataset(root_dir: str) -> pd.DataFrame:
    """
    Analyze all posts in temporal_test/.
    Returns DataFrame with metrics per post.
    """
    rows = []
    
    for pid in sorted(os.listdir(root_dir)):
        pdir = os.path.join(root_dir, pid)
        if not os.path.isdir(pdir):
            continue
        
        merged_file = os.path.join(pdir, "final_merged.json")
        result = analyze_post(merged_file)
        
        if result:
            rows.append(result)
    
    return pd.DataFrame(rows)


if __name__ == '__main__':
    print("="*80)
    print("📈 INFORMATION GAIN ANALYTICS")
    print("="*80)
    print()
    
    root = 'temporal_test'
    if not os.path.exists(root):
        print(f"❌ Directory not found: {root}")
        exit(1)
    
    print(f"🔍 Analyzing {root}/")
    print()
    
    df = analyze_dataset(root)
    
    if df.empty:
        print("No posts found.")
        exit(0)
    
    # Sort by total ΔInfo descending
    df = df.sort_values('total_delta_info', ascending=False)
    
    print("="*80)
    print("📊 POST-LEVEL METRICS")
    print("="*80)
    print()
    
    # Display subset of columns
    display_cols = ['post_id', 'scrapes', 'total_delta_info', 'half_life_h', 
                    'dormancy_h', 'waste_rate', 'lambda_hat', 'duration_h']
    print(df[display_cols].to_string(index=False))
    print()
    
    # Summary statistics
    print("="*80)
    print("📈 SUMMARY STATISTICS")
    print("="*80)
    print()
    
    print(f"Total posts analyzed: {len(df)}")
    print(f"Total scrapes: {df['scrapes'].sum()}")
    print(f"Total ΔInfo collected: {df['total_delta_info'].sum():.1f}")
    print()
    
    print(f"Average metrics:")
    print(f"  ├─ Scrapes per post: {df['scrapes'].mean():.1f}")
    print(f"  ├─ ΔInfo per post: {df['total_delta_info'].mean():.1f}")
    print(f"  ├─ ΔInfo per scrape: {(df['total_delta_info'].sum() / df['scrapes'].sum()):.2f}")
    print(f"  ├─ Half-life: {df['half_life_h'].mean():.1f} hours")
    print(f"  ├─ Time to dormancy: {df['dormancy_h'].mean():.1f} hours")
    print(f"  ├─ Waste rate: {df['waste_rate'].mean()*100:.1f}%")
    print(f"  └─ Lambda (decay): {df['lambda_hat'].mean():.3f} per hour")
    print()
    
    # Distribution
    print("="*80)
    print("📊 DISTRIBUTION")
    print("="*80)
    print()
    
    print("Lambda (λ) distribution:")
    print(f"  ├─ Min: {df['lambda_hat'].min():.3f}")
    print(f"  ├─ 25th percentile: {df['lambda_hat'].quantile(0.25):.3f}")
    print(f"  ├─ Median: {df['lambda_hat'].median():.3f}")
    print(f"  ├─ 75th percentile: {df['lambda_hat'].quantile(0.75):.3f}")
    print(f"  └─ Max: {df['lambda_hat'].max():.3f}")
    print()
    
    print("Waste rate distribution:")
    print(f"  ├─ <10% waste: {len(df[df['waste_rate'] < 0.1])} posts")
    print(f"  ├─ 10-30% waste: {len(df[(df['waste_rate'] >= 0.1) & (df['waste_rate'] < 0.3)])} posts")
    print(f"  ├─ 30-70% waste: {len(df[(df['waste_rate'] >= 0.3) & (df['waste_rate'] < 0.7)])} posts")
    print(f"  └─ >70% waste: {len(df[df['waste_rate'] >= 0.7])} posts")
    print()
    
    print("="*80)

