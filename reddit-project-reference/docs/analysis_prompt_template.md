

ROLE: reddit_dag_batch_analyzer

GOAL:
- Given many Reddit thread DAGs, find the most interesting conversations ACROSS THE BATCH, not per thread.
- “Interesting” = high engagement, high scores, strong edits, or clear disagreement/debate.

INPUT:
- You receive a JSON array: [thread, ...]
- Each thread:
  {
    "thread_id": string,
    "nodes": {
      "<node_id>": {
        "type": "post" | "comment",
        "current_text": string,
        "text_history": [[text, timestamp], ...],
        "score_history": [[score, timestamp], ...],
        "parent": node_id | null,
        "children": [node_id, ...],
        "depth": int,
        "metadata": { "author": string, "permalink": string, ... }
      }
    }
  }

CANONICAL VALUES:
- canonical_text(node)   = node.text_history[-1][0] (fallback to earliest if "[deleted]")
- canonical_score(node)  = node.score_history[-1][0]

PER-COMMENT METRICS:
For each comment node (type="comment"):
- popularity = canonical_score
- engagement = total number of descendants in its subtree
- edit_count = len(text_history) - 1

If timestamps available and ordered:
- earliest_score, earliest_ts = score_history[0]
- latest_score,   latest_ts   = score_history[-1]
- velocity = (latest_score - earliest_score) / max(1, latest_ts - earliest_ts)
Else:
- velocity = 0

IMPORTANCE SCORE (PER COMMENT):
importance = (0.5 * popularity) +
             (0.3 * engagement) +
             (0.1 * velocity) +
             (0.1 * edit_count)

INTERESTING COMMENT RULES (WITHIN A THREAD):
A comment is “interesting” if ANY:
- importance in top 5% of comments in that thread
- engagement >= 5
- edit_count >= 1
- velocity in top 10% of that thread
- canonical_text shows disagreement/debate (e.g. contains words like: "disagree", "actually", "no you", "wrong", "propaganda", insults, or obvious correction patterns)

BRANCH EXTRACTION:
- For each interesting comment, define its BRANCH as:
  - all ancestor nodes from root post down to this comment
  - this comment itself
  - its direct children (optional: plus grandchildren if you need context, but keep short)
- Do NOT include unrelated siblings.

PER-THREAD SUMMARY OBJECT:
For each thread, you may (but do not have to) create:
{
  "thread_id": string,
  "top_comments": [ { "node_id": string, "importance": number } ]   // at most 10 per thread
}
This is mainly for internal ranking; main goal is batch-level selection.

BATCH-LEVEL RANKING:
Across all threads:
- Collect all comments that were “interesting” in their thread.
- Rank them globally by importance (highest first).
- Select top N comments (recommended N ≈ 200 for thousands of threads).
- For each select
