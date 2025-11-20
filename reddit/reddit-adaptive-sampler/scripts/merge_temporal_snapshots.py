#!/usr/bin/env python3
"""
Merge temporal Reddit snapshots into full-thread histories.

This utility walks `temporal_test/<post_id>/raw_scrapes/` (the incremental
snapshots produced by `unified_scraper.py`) and consolidates them into a single
JSON file per post under `merged_posts/`. For every comment we stitch together
`text_history` and `score_history` entries across scrapes so edits and score
changes are preserved in chronological order.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge per-scrape temporal snapshots into full post histories."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("temporal_test"),
        help="Directory containing per-post subdirectories (default: temporal_test)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("merged_posts"),
        help="Output directory for merged posts (default: merged_posts)",
    )
    parser.add_argument(
        "--post-id",
        help="Optional specific post_id to merge (defaults to all directories).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute merge stats but do not write output files.",
    )
    return parser.parse_args()


def iter_comments(comments: Optional[List[Dict[str, Any]]]) -> Iterable[Dict[str, Any]]:
    if not comments:
        return
    for comment in comments:
        yield comment
        yield from iter_comments(comment.get("replies"))


def _clone_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_clone_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _clone_value(v) for k, v in value.items()}
    return value


def _extract_text(value: Any) -> Any:
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    if isinstance(value, dict):
        # Some structures might keep the text under a known key.
        for key in ("text", "body", "value"):
            if key in value:
                return value[key]
    return value


def append_text_entry(history: List[Any], entry: Any) -> None:
    if entry is None:
        return
    normalized = _clone_value(entry)
    new_text = _extract_text(normalized)
    if history:
        prev = history[-1]
        prev_text = _extract_text(prev)
        if prev_text == new_text:
            return
    history.append(normalized)


def append_score_entry(history: List[Any], entry: Any) -> None:
    if entry is None:
        return
    normalized = _clone_value(entry)
    history.append(normalized)


def aggregate_snapshots(
    snapshots: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    comment_state: Dict[str, Dict[str, Any]] = {}
    for snap in snapshots:
        for comment in iter_comments(snap.get("comments")):
            comment_id = comment.get("id")
            if not comment_id:
                continue
            state = comment_state.setdefault(
                comment_id,
                {
                    "text_history": [],
                    "score_history": [],
                    "latest_comment": comment,
                },
            )
            for entry in comment.get("text_history") or []:
                append_text_entry(state["text_history"], entry)
            for entry in comment.get("score_history") or []:
                append_score_entry(state["score_history"], entry)
            state["latest_comment"] = comment
    return comment_state


def merge_post_snapshots(post_dir: Path) -> Optional[Dict[str, Any]]:
    raw_dir = post_dir / "raw_scrapes"
    if not raw_dir.is_dir():
        return None
    snapshot_paths = sorted(raw_dir.glob("*.json"))
    if not snapshot_paths:
        return None

    snapshots: List[Dict[str, Any]] = []
    for path in snapshot_paths:
        try:
            with path.open("r", encoding="utf-8") as fh:
                snapshots.append(json.load(fh))
        except json.JSONDecodeError as exc:
            print(f"⚠️  Skipping {path}: invalid JSON ({exc})")
        except OSError as exc:
            print(f"⚠️  Skipping {path}: {exc}")

    if not snapshots:
        return None

    latest = _clone_value(snapshots[-1])
    comment_state = aggregate_snapshots(snapshots)

    def apply_histories(node: MutableMapping[str, Any]) -> None:
        comment_id = node.get("id")
        if comment_id and comment_id in comment_state:
            state = comment_state[comment_id]
            node["text_history"] = state["text_history"]
            node["score_history"] = state["score_history"]
        for child in node.get("replies") or []:
            apply_histories(child)

    for comment in latest.get("comments") or []:
        apply_histories(comment)

    # Merge post-level histories (score, title, selftext if available)
    post_state: Dict[str, List[Any]] = {}
    for snap in snapshots:
        post = snap.get("post") or {}
        for key, value in post.items():
            if not key.endswith("_history"):
                continue
            history = post_state.setdefault(key, [])
            for entry in value or []:
                if key.startswith("score"):
                    append_score_entry(history, entry)
                else:
                    append_text_entry(history, entry)

    latest_post = latest.get("post") or {}
    for key, history in post_state.items():
        latest_post[key] = history
    latest["post"] = latest_post

    metadata = latest.setdefault("metadata", {})
    metadata["merged_snapshot_count"] = len(snapshot_paths)
    metadata["merged_snapshot_files"] = [path.name for path in snapshot_paths]

    return latest


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    dest = args.dest.resolve()

    if not source.exists():
        raise SystemExit(f"Source directory does not exist: {source}")

    post_dirs: List[Path]
    if args.post_id:
        post_dir = source / args.post_id
        if not post_dir.exists():
            raise SystemExit(f"Post directory not found: {post_dir}")
        post_dirs = [post_dir]
    else:
        post_dirs = sorted(p for p in source.iterdir() if p.is_dir())

    if not args.dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    merged = 0
    for post_dir in post_dirs:
        merged_data = merge_post_snapshots(post_dir)
        if merged_data is None:
            continue
        post_id = post_dir.name
        if not args.dry_run:
            out_path = dest / f"{post_id}.json"
            with out_path.open("w", encoding="utf-8") as fh:
                json.dump(merged_data, fh, ensure_ascii=False, indent=2)
        merged += 1

    action = "Would write" if args.dry_run else "Wrote"
    print(f"{action} merged histories for {merged} posts into {dest}")


if __name__ == "__main__":
    main()

