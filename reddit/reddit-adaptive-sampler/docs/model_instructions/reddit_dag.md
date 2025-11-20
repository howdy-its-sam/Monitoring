# Reddit Conversation DAG Schema & Interpretation Guide

## Schema Overview

Each DAG JSON produced by `scripts/convert_to_dag.py` has the following shape:

```
{
  "thread_id": "t3_<post_id>",
  "nodes": {
    "<node_id>": {
      "type": "post" | "comment",
      "title": "...",          # post only
      "current_text": "...",   # latest text for comments
      "text_history": [ [text, timestamp], ... ],
      "score_history": [ [score, timestamp], ... ],
      "created_utc": "...",
      "author": "...",
      "metadata": {
        "subreddit": "...",    # post only
        "permalink": "...",
        "num_comments": ...,
        "depth": 0,
        "is_submitter": false,
        "edited": true | false,
        "deleted": true | false,
        "deleted_at": null,
        "controversiality": 0,
        "gilded": 0,
        "children": ["t1_childA", ...]  # convenience list of direct replies
      }
    },
    ...
  },
  "edges": [
    ["t3_<post>", "t1_<child>"],
    ["t1_<parent>", "t1_<child>"],
    ...
  ],
  "source_metadata": {
    "scraped_at": "...",
    "total_comments": ...,
    "coverage_percent": ...
  }
}
```

- Node IDs follow Reddit’s `t3_` (submission) and `t1_` (comment) prefixes.
- `text_history` records textual edits only when content changes; the last entry is the current text (`current_text`).
- `score_history` logs every scrape timestamp (even if the score is unchanged), so the latest entry is both the current score and most recent observation time.
- `metadata.children` mirrors the outbound edges for convenience.
- `source_metadata.merged_snapshot_count` and `source_metadata.merged_snapshot_files` indicate how many incremental scrapes were merged to form this snapshot.

## Suggested Interpretation Steps for LLMs

1. **Reconstruct conversation paths**  
   - Start at the root `thread_id` (`type = post`).  
   - Follow `edges` (or `metadata.children`) to gather full chains from root to any comment.
   - Use the ordered chain to analyse tone, argument flow, or sentiment shifts.

2. **Use scores as weights**  
   - Latest score = last entry in `score_history`.  
   - High-score comments or branches indicate community endorsement; low/negative scores may signal controversy or poor reception.

3. **Detect edits & evolution**  
   - `text_history` length > 1 means the text changed between scrapes; a single entry alongside a longer `score_history` implies the text stayed constant.
   - Use `score_history` timestamps to spot delayed engagement or surges in popularity.

4. **Account for structural context**  
   - `metadata.depth` gives nesting depth (root post `=0`).  
   - Sibling comparisons help measure diverging viewpoints after a common ancestor.

5. **Filter noise**  
   - Skip comments where `metadata.deleted` is `true`.  
   - `is_submitter` highlights the original poster’s follow-ups.  
   - `controversiality > 0` may signal polarising content worthy of inspection.

6. **Cross-thread analysis**  
   - If multiple DAG files share a `content_signature` (optional external index), aggregate perspectives across subreddits before surfacing insights.

## Example Prompt Snippet

```
You are given a Reddit conversation DAG.
- Use the root post (type=post) as the conversation topic.
- Reconstruct any comment branch by following edges from parent to child.
- When evaluating a comment:
  * current_text = last entry in text_history (the only entry if the comment never changed).
  * current_score = last entry in score_history.
  * depth indicates how deep in the conversation tree the comment sits.
Highlight branches where score_weight is high or where text_history shows significant edits.
```

## Notes

- The converter does not compute embeddings or advanced metrics; callers may add them under `nodes[*].metadata`.
- DAG files are independent; batch them as JSONL for large-scale processing.
- Always cite `metadata.permalink` when surfacing extracted insights so humans can verify the context.

