export interface TemporalValue<T> {
  value: T;
  timestamp: string; // ISO 8601
}

export interface RedditNode {
  id: string;
  parentId: string | null; // null for the Thread itself (the Post)
  author: string;
  createdUtc: number;
  permalink: string;
  depth: number;
  
  // Temporal Fields (History)
  textHistory: TemporalValue<string>[];
  scoreHistory: TemporalValue<number>[];
  
  // Status
  isDeleted: boolean;
  deletedAt: string | null;
  
  // Metadata
  subreddit?: string; // Usually only needed on the root
  title?: string;     // Only on root
  url?: string;       // Only on root
  
  // The Bag: Capture all other fields here
  extra: Record<string, any>;

  // Graph Properties (Implicit)
  // No 'children' array here! The graph is defined by 'parentId'.
}

export interface ThreadState {
  id: string;
  scrapedAt: string;
  nodes: Record<string, RedditNode>; // O(1) Access: ID -> Node
}
