import type { RedditNode } from "./types";

// The exact fields output by the Python script's 'process_comment'
export interface LegacyComment {
  id: string;
  parent_id: string | null;
  author: string;
  body: string;
  score: number;
  created_utc: number;
  depth: number;
  permalink: string;
  is_submitter: boolean;
  controversiality: number;
  gilded: number;
  edited: boolean | number;
}

/**
 * Maps a modern RedditNode (with temporal history and extra bag) 
 * back to the flat, lossy format used by the legacy Python scraper.
 * Used for verification/parity testing.
 */
export function toLegacyFormat(node: RedditNode): LegacyComment {
  // 1. Extract current value from history (always the latest for comparison)
  const currentScore = node.scoreHistory[node.scoreHistory.length - 1].value;
  const currentBody = node.textHistory[node.textHistory.length - 1].value;

  // 2. Extract fields from 'extra' bag if they aren't top-level
  // Note: In api.ts we destructured these into 'extra' if they weren't in our core set
  // But wait, 'is_submitter', 'controversiality', 'gilded', 'edited' ARE in 'extra' now.
  
  return {
    id: node.id,
    parent_id: node.parentId,
    author: node.author,
    body: currentBody,
    score: currentScore,
    created_utc: node.createdUtc,
    depth: node.depth,
    permalink: node.permalink,
    
    // Fields that live in the 'extra' bag in the new system
    is_submitter: node.extra.is_submitter ?? false,
    controversiality: node.extra.controversiality ?? 0,
    gilded: node.extra.gilded ?? 0,
    edited: node.extra.edited ?? false
  };
}
