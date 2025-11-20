import { readFileSync, writeFileSync } from "fs";
import { join } from "path";

// Configuration from Prompt Draft
const CONFIG = {
  IMP_WEIGHTS: { POP: 0.5, ENG: 0.3, VEL: 0.1, EDITS: 0.1 },
  THRESHOLDS: {
    IMP_PERCENTILE: 0.95, // Top 5%
    ENG_MIN: 5,
    EDITS_MIN: 1,
    VEL_PERCENTILE: 0.90, // Top 10%
  },
  CONFLICT_KEYWORDS: [
    "disagree", "actually", "wrong", "propaganda", "bullshit", "false", 
    "correction", "source?", "lie", "biased"
  ],
  TOP_N: 100
};

interface HistoryTuple {
  0: any; // Value
  1: string; // Timestamp ISO
}

interface CommentNode {
  id: string;
  parent_id: string;
  author: string;
  text_history: [string, string][]; // [text, timestamp]
  score_history: [number, string][]; // [score, timestamp]
  created_utc: number;
  depth: number;
  // Computed fields
  text?: string;
  score?: number;
  eng?: number;
  edits?: number;
  vel?: number;
  imp?: number;
  is_interesting?: boolean;
  children?: CommentNode[];
}

interface ThreadData {
  comments: CommentNode[];
  post?: any; // Structure of post object if available
}

function getLast<T>(history: [T, string][]): T {
  if (!history || history.length === 0) return null as any;
  return history[history.length - 1][0];
}

function calculateVelocity(scoreHistory: [number, string][]): number {
  if (scoreHistory.length < 2) return 0;
  
  const first = scoreHistory[0];
  const last = scoreHistory[scoreHistory.length - 1];
  
  const scoreDelta = last[0] - first[0];
  const timeDelta = (new Date(last[1]).getTime() - new Date(first[1]).getTime()) / 1000 / 60; // Minutes
  
  if (timeDelta <= 0) return 0;
  return scoreDelta / timeDelta; // Score per minute
}

function countDescendants(node: CommentNode, map: Map<string, CommentNode>): number {
    // This requires building the tree first or having a parent pointer.
    // For flat list, we need to construct adjacency list.
    // Simplified: we will do this after tree construction.
    return 0; // Placeholder
}

function processThread(filePath: string): string {
  console.log(`Processing ${filePath}...`);
  const raw = readFileSync(filePath, "utf-8");
  const data = JSON.parse(raw);

  // Handle both new DAG format (Map) and legacy format (Array)
  let nodes: CommentNode[] = [];
  
  if (Array.isArray(data.comments)) {
      // Legacy format
      nodes = data.comments;
  } else {
      // New DAG format (Record<string, Node>)
      // We need to map RedditNode -> CommentNode (internal interface)
      nodes = Object.values(data).map((n: any) => {
          // Get latest values
          const score = n.scoreHistory?.[n.scoreHistory.length - 1]?.value ?? 0;
          const text = n.textHistory?.[n.textHistory.length - 1]?.value ?? "";
          
          return {
              id: n.id,
              parent_id: n.parentId,
              author: n.author,
              text_history: n.textHistory.map((h: any) => [h.value, h.timestamp]),
              score_history: n.scoreHistory.map((h: any) => [h.value, h.timestamp]),
              created_utc: n.createdUtc,
              depth: n.depth,
              // Computed fields helpers
              text: text,
              score: score
          } as CommentNode;
      });
  }

  const nodeMap = new Map<string, CommentNode>();
  const childrenMap = new Map<string, string[]>();

  // 1. First Pass: Basic Metrics & Map Construction
  nodes.forEach(node => {
    // ... rest of the logic remains valid since we mapped to CommentNode ...
    // But we need to ensure 'text' and 'score' are set if they weren't already
    if (node.text === undefined) node.text = getLast(node.text_history);
    if (node.score === undefined) node.score = getLast(node.score_history);
    
    node.edits = Math.max(0, (node.text_history?.length || 1) - 1);
    node.vel = calculateVelocity(node.score_history);
    
    nodeMap.set(node.id, node);
    
    const pid = node.parent_id || "ROOT"; // Handle null parent
    if (!childrenMap.has(pid)) {
      childrenMap.set(pid, []);
    }
    childrenMap.get(pid)?.push(node.id);
  });

  // 2. Second Pass: Engagement (Descendants)
  // Recursive count with memoization (conceptually, or just recursive traversal)
  const getEngagement = (id: string): number => {
    const children = childrenMap.get(id) || [];
    let count = children.length;
    for (const childId of children) {
      count += getEngagement(childId);
    }
    return count;
  };

  nodes.forEach(node => {
    node.eng = getEngagement(node.id);
  });

  // 3. Third Pass: Importance & Interestingness
  // We need percentiles for IMP and VEL
  const allVels = nodes.map(n => n.vel || 0).sort((a, b) => a - b);
  const allImps: number[] = []; // Calculate imp first to sort

  nodes.forEach(node => {
    const pop = node.score || 0;
    const eng = node.eng || 0;
    const vel = node.vel || 0;
    const edits = node.edits || 0;

    node.imp = (
      CONFIG.IMP_WEIGHTS.POP * pop +
      CONFIG.IMP_WEIGHTS.ENG * eng +
      CONFIG.IMP_WEIGHTS.VEL * vel +
      CONFIG.IMP_WEIGHTS.EDITS * edits
    );
    allImps.push(node.imp);
  });
  
  allImps.sort((a, b) => a - b);
  
  const velThreshold = allVels[Math.floor(allVels.length * CONFIG.THRESHOLDS.VEL_PERCENTILE)] || 0;
  const impThreshold = allImps[Math.floor(allImps.length * CONFIG.THRESHOLDS.IMP_PERCENTILE)] || 0;

  const interestingNodes: CommentNode[] = [];

  nodes.forEach(node => {
    const isConflict = CONFIG.CONFLICT_KEYWORDS.some(kw => node.text?.toLowerCase().includes(kw));
    
    const isInteresting = 
      (node.imp! >= impThreshold) ||
      (node.eng! >= CONFIG.THRESHOLDS.ENG_MIN) ||
      (node.edits! >= CONFIG.THRESHOLDS.EDITS_MIN) ||
      (node.vel! >= velThreshold) ||
      isConflict;

    if (isInteresting) {
      interestingNodes.push(node);
    }
  });

  // 4. Sort by Importance and Take Top N
  interestingNodes.sort((a, b) => (b.imp || 0) - (a.imp || 0));
  const topNodes = interestingNodes.slice(0, CONFIG.TOP_N);

  // 5. Format Output
  // Format: JSON-like structure but simplified for LLM
  const output = topNodes.map(node => ({
    id: node.id,
    author: node.author,
    score: node.score,
    eng: node.eng,
    imp: node.imp?.toFixed(2),
    text: node.text,
    parent: node.parent_id
  }));

  return JSON.stringify(output, null, 2);
}

// Main Execution
const targetFile = process.argv[2];
if (!targetFile) {
  console.error("Usage: bun run src/generate_prompt.ts <path_to_json>");
  process.exit(1);
}

try {
  const result = processThread(targetFile);
  const outputPath = join(process.cwd(), "reddit/prompt_context.txt");
  writeFileSync(outputPath, result);
  console.log(`Successfully generated context at: ${outputPath}`);
} catch (e) {
  console.error("Error processing file:", e);
}
