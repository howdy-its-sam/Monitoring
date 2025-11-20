import type { RedditNode, TemporalValue } from "./types";

export interface MergeStats {
  newNodes: number;
  updatedNodes: number;
  scoreDelta: number;
  textDeltaChars: number;
  newAtDepth0: number;
  newAtDepth1: number;
  newAtDepth2Plus: number;
}

export class DAG {
  private nodes: Map<string, RedditNode>;
  private dirty: boolean;

  constructor(initialData?: Record<string, RedditNode>) {
    this.nodes = new Map(Object.entries(initialData || {}));
    this.dirty = false;
  }

  public getNodes(): Map<string, RedditNode> {
    return this.nodes;
  }

  /**
   * Merges a fresh snapshot of data into the DAG.
   * @param incomingNodes List of nodes fetched right now.
   * @param timestamp ISO timestamp of this fetch.
   */
  public merge(incomingNodes: RedditNode[], timestamp: string): MergeStats {
    const stats: MergeStats = {
        newNodes: 0, updatedNodes: 0, scoreDelta: 0, textDeltaChars: 0,
        newAtDepth0: 0, newAtDepth1: 0, newAtDepth2Plus: 0
    };

    const incomingIds = new Set<string>();

    for (const newNode of incomingNodes) {
      incomingIds.add(newNode.id);
      const existing = this.nodes.get(newNode.id);

      if (existing) {
        // UPDATE Existing
        if (this.updateNode(existing, newNode, timestamp, stats)) {
            stats.updatedNodes++;
        }
      } else {
        // CREATE New
        this.nodes.set(newNode.id, newNode);
        this.dirty = true;
        stats.newNodes++;
        
        // Depth stats
        if (newNode.depth === 0) stats.newAtDepth0++;
        else if (newNode.depth === 1) stats.newAtDepth1++;
        else stats.newAtDepth2Plus++;
        
        // For new nodes, the entire text/score is "Delta"
        stats.textDeltaChars += newNode.textHistory[0].value.length;
        stats.scoreDelta += Math.abs(newNode.scoreHistory[0].value);
      }
    }

    // CHECK FOR DELETIONS (Absence)
    for (const [id, node] of this.nodes) {
      if (!incomingIds.has(id) && !node.isDeleted) {
        // It's missing! Mark deleted.
        node.isDeleted = true;
        node.deletedAt = timestamp;
        this.dirty = true;
        stats.updatedNodes++;
      }
    }
    
    return stats;
  }

  private updateNode(existing: RedditNode, incoming: RedditNode, timestamp: string, stats: MergeStats): boolean {
    let changed = false;

    // 1. Score History
    const lastScore = existing.scoreHistory[existing.scoreHistory.length - 1]?.value;
    const newScore = incoming.scoreHistory[0].value; 

    if (lastScore !== newScore) {
        existing.scoreHistory.push({ value: newScore, timestamp });
        stats.scoreDelta += Math.abs(newScore - lastScore);
        this.dirty = true;
        changed = true;
    }

    // 2. Text History
    const lastText = existing.textHistory[existing.textHistory.length - 1]?.value;
    const newText = incoming.textHistory[0].value;

    if (lastText !== newText) {
        existing.textHistory.push({ value: newText, timestamp });
        stats.textDeltaChars += Math.abs(newText.length - lastText.length);
        this.dirty = true;
        changed = true;
    }
    
    // 3. Undelete if it reappeared
    if (existing.isDeleted) {
        existing.isDeleted = false;
        existing.deletedAt = null;
        this.dirty = true;
        changed = true;
    }
    
    return changed;
  }

  public toJSON(): Record<string, RedditNode> {
    return Object.fromEntries(this.nodes);
  }
}