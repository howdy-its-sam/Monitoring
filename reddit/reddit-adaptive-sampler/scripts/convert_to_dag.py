#!/usr/bin/env python3
"""
Convert a raw Reddit post JSON (as collected by the scraper) into a DAG-friendly
representation. The output schema is designed for downstream LLM consumption.

Usage:
    python scripts/convert_to_dag.py path/to/input.json
        (saves to dag_samples/<input_stem>_dag.json by default)
    python scripts/convert_to_dag.py path/to/input.json --output custom.json
    python scripts/convert_to_dag.py path/to/input.json --stdout
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def ensure_prefixed(node_id: Optional[str], prefix: str) -> Optional[str]:
    if node_id is None:
        return None
    if node_id.startswith("t"):
        return node_id
    return f"{prefix}{node_id}"


def latest_text(text_history: Optional[List[List[Any]]]) -> Optional[str]:
    if not text_history:
        return None
    entry = text_history[-1]
    return entry[0] if entry else None


def normalize_comment(
    comment: Dict[str, Any],
    post_id: str,
    nodes: Dict[str, Dict[str, Any]],
    edges: List[List[str]],
) -> None:
    raw_comment_id = comment.get("id")
    node_id = ensure_prefixed(raw_comment_id, "t1_")
    if node_id is None:
        return

    parent_id = comment.get("parent_id")
    if parent_id is None:
        parent_id = f"t3_{post_id}"

    text_history = comment.get("text_history") or []
    score_history = comment.get("score_history") or []

    nodes[node_id] = {
        "type": "comment",
        "author": comment.get("author"),
        "created_utc": comment.get("created_utc"),
        "current_text": latest_text(text_history),
        "text_history": text_history,
        "score_history": score_history,
        "metadata": {
            "depth": comment.get("depth"),
            "permalink": comment.get("permalink"),
            "is_submitter": comment.get("is_submitter"),
            "controversiality": comment.get("controversiality"),
            "gilded": comment.get("gilded"),
            "edited": comment.get("edited"),
            "deleted": comment.get("deleted"),
            "deleted_at": comment.get("deleted_at"),
            "children": [
                ensure_prefixed(child.get("id"), "t1_")
                for child in (comment.get("replies") or [])
                if child.get("id")
            ],
        },
    }

    edges.append([parent_id, node_id])

    for child in comment.get("replies") or []:
        normalize_comment(child, post_id, nodes, edges)


def convert_to_dag(data: Dict[str, Any]) -> Dict[str, Any]:
    post = data.get("post") or {}
    post_id = post.get("id") or data.get("metadata", {}).get("post_id")
    if not post_id:
        raise ValueError("Unable to determine post ID from input data.")

    root_id = ensure_prefixed(post_id, "t3_")
    if root_id is None:
        raise ValueError("Post ID is missing or malformed.")

    nodes: Dict[str, Dict[str, Any]] = {
        root_id: {
            "type": "post",
            "title": post.get("title"),
            "author": post.get("author"),
            "created_utc": post.get("created_utc"),
            "selftext": post.get("selftext"),
            "url": post.get("url"),
            "score_history": post.get("score_history") or [],
            "metadata": {
                "subreddit": post.get("subreddit"),
                "permalink": post.get("permalink"),
                "num_comments": post.get("num_comments"),
            },
        }
    }
    edges: List[List[str]] = []

    for comment in data.get("comments") or []:
        normalize_comment(comment, post_id, nodes, edges)

    return {
        "thread_id": root_id,
        "nodes": nodes,
        "edges": edges,
        "source_metadata": data.get("metadata", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a Reddit raw JSON export into a DAG representation."
    )
    parser.add_argument("input", type=Path, help="Path to the input JSON file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path to write the DAG JSON. Defaults to dag_samples/<input_stem>_dag.json.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write DAG JSON to stdout instead of creating a file.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        parser.error(f"Input file does not exist: {args.input}")

    try:
        with args.input.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        parser.error(f"Failed to parse JSON: {exc}")

    dag = convert_to_dag(data)
    
    if args.stdout and args.output:
        parser.error("Cannot use --stdout and --output together.")

    output_path = args.output
    if output_path is None:
        default_dir = Path("dag_samples")
        output_path = default_dir / f"{args.input.stem}_dag.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(dag, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

