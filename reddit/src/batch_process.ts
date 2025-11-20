import { readdirSync, readFileSync, existsSync, statSync, writeFileSync } from "fs";
import { join } from "path";
import { DAG } from "./dag";
import type { RedditNode } from "./types";

// --- CONFIGURATION ---
const MAX_CHARS = 400000; // ~100k tokens
const MIN_CHARS_PER_THREAD = 500; // Skip empty stubs

// --- HELPER FUNCTIONS ---

function calculateNodeImportance(node: RedditNode): number {
  const score = node.scoreHistory[node.scoreHistory.length - 1]?.value ?? 0;
  const text = node.textHistory[node.textHistory.length - 1]?.value ?? "";
  const edits = Math.max(0, node.textHistory.length - 1);
  
  // Simple Velocity: Score change / time
  let vel = 0;
  if (node.scoreHistory.length >= 2) {
      const first = node.scoreHistory[0];
      const last = node.scoreHistory[node.scoreHistory.length - 1];
      const minutes = (new Date(last.timestamp).getTime() - new Date(first.timestamp).getTime()) / 60000;
      if (minutes > 10) vel = (last.value - first.value) / minutes;
  }

  return 0.5 * score + 0.2 * vel + 0.1 * edits;
}

function calculateThreadVelocity(dag: DAG): number {
    // Sum of absolute score deltas across all nodes
    let totalDelta = 0;
    let totalTime = 0;
    
    for (const node of dag.getNodes().values()) {
        if (node.scoreHistory.length >= 2) {
            const first = node.scoreHistory[0];
            const last = node.scoreHistory[node.scoreHistory.length - 1];
            totalDelta += Math.abs(last.value - first.value);
            const minutes = (new Date(last.timestamp).getTime() - new Date(first.timestamp).getTime()) / 60000;
            totalTime = Math.max(totalTime, minutes);
        }
    }
    return totalTime > 0 ? totalDelta / totalTime : 0;
}

function calculateThreadEffort(dag: DAG): number {
    // Avg length of comments (ignoring deleted)
    let totalLen = 0;
    let count = 0;
    for (const node of dag.getNodes().values()) {
        const text = node.textHistory[node.textHistory.length - 1]?.value || "";
        if (text !== "[deleted]" && text !== "[removed]") {
            totalLen += text.length;
            count++;
        }
    }
    return count > 0 ? totalLen / count : 0;
}

function parseSnapshot(snapshot: any): RedditNode[] {
  const nodes: RedditNode[] = [];
  const timestamp = snapshot.metadata?.scraped_at || new Date().toISOString();
  
  const processItem = (item: any, type: "post" | "comment") => {
      if (!item) return;
      // Normalize fields
      const id = item.id;
      const body = item.body || item.selftext || item.url || "";
      const score = item.score ?? 0;
      
      nodes.push({
          id: id,
          parentId: item.parent_id || null,
          author: item.author || "[deleted]",
          createdUtc: item.created_utc,
          permalink: item.permalink,
          depth: item.depth || 0,
          scoreHistory: [{ value: score, timestamp }],
          textHistory: [{ value: body, timestamp }],
          isDeleted: item.deleted || body === "[deleted]",
          deletedAt: item.deleted_at || null,
          extra: { ...item },
          subreddit: item.subreddit,
          title: item.title
      });
  };

  if (snapshot.post) processItem(snapshot.post, "post");
  (snapshot.comments || []).forEach((c: any) => processItem(c, "comment"));
  
  return nodes;
}

// --- GLOBAL KEYWORD TRACKER ---
const globalKeywords: Map<string, number> = new Map();
const STOP_WORDS = new Set(["the", "and", "to", "of", "a", "in", "is", "that", "for", "it", "on", "with", "as", "was", "at", "by", "an", "be", "this", "which", "or", "from", "but", "not", "are", "your", "have", "can", "you", "if", "we", "my", "me", "about", "so", "they", "what", "like", "just", "do", "no", "one", "all", "will", "there", "their", "has", "more", "who", "when", "out", "up", "would", "get", "some", "time", "actually", "deleted", "removed"]);

function trackKeywords(text: string) {
    if (!text) return;
    // Basic tokenization: split by non-alphanumeric
    const tokens = text.toLowerCase().split(/[^a-z0-9']+/);
    for (const t of tokens) {
        if (t.length > 3 && !STOP_WORDS.has(t)) {
            globalKeywords.set(t, (globalKeywords.get(t) || 0) + 1);
        }
    }
}

// --- MAIN ---

async function main() {
  const rootDir = join(process.cwd(), "reddit/reddit-adaptive-sampler/temporal_test");
  
  // 1. Scan Directories
  const posts = readdirSync(rootDir).filter(f => {
      const full = join(rootDir, f);
      return statSync(full).isDirectory() && existsSync(join(full, "raw_scrapes"));
  });

  console.log(`Scanning ${posts.length} threads...`);

  const threads: { 
      id: string; 
      imp: number; 
      vel: number; 
      effort: number;
      dag: DAG;
      root?: RedditNode;
  }[] = [];

  // 2. Process All Threads (Lightweight)
  let processed = 0;
  for (const postId of posts) {
      const scrapeDir = join(rootDir, postId, "raw_scrapes");
      const files = readdirSync(scrapeDir).filter(f => f.endsWith(".json"));
      if (files.length < 1) continue;

      // Optimization: Only load the LAST file for the 'Current State' view
      // But load FIRST file to calc velocity if needed?
      // Actually, for batch processing 2000 files, reading ONLY the last one is safer for memory/time.
      // We lose fine-grained velocity this way but gain speed.
      // Wait, our 'aggregator' loads ALL. That's too slow for 2000 threads in this script.
      // COMPROMISE: Load LAST file. Assume 'imp' based on current score is enough.
      
      files.sort();
      const lastFile = files[files.length - 1];
      
      try {
          const raw = readFileSync(join(scrapeDir, lastFile), "utf-8");
          const json = JSON.parse(raw);
          const nodes = parseSnapshot(json);
          
          const dag = new DAG();
          dag.merge(nodes, new Date().toISOString()); // Single snapshot merge
          
          // Calc metrics
          let imp = 0;
          let nodeCount = 0;
          let root: RedditNode | undefined;
          
          for (const node of dag.getNodes().values()) {
              imp += calculateNodeImportance(node);
              nodeCount++;
              if (node.parentId === null) root = node;
              
              // Track Keywords
              const text = node.textHistory[0].value;
              trackKeywords(text);
          }
          
          // Effort
          const effort = calculateThreadEffort(dag);
          
          threads.push({ id: postId, imp, vel: 0, effort, dag, root });
          
      } catch (e) {}
      
      processed++;
      if (processed % 100 === 0) process.stdout.write(".");
  }
  console.log("\nScan complete.");

  // 3. Stratified Selection
  const selectedIds = new Set<string>();
  const finalSelection: typeof threads = [];

  const select = (pool: typeof threads, count: number, sortFn: (a: any, b: any) => number, reason: string) => {
      pool.sort(sortFn);
      let added = 0;
      for (const t of pool) {
          if (added >= count) break;
          if (!selectedIds.has(t.id)) {
              selectedIds.add(t.id);
              (t as any).selectionReason = reason;
              finalSelection.push(t);
              added++;
          }
      }
  };

  // A. Giants (High Importance) - Top 40
  select(threads, 40, (a, b) => b.imp - a.imp, "High Importance");

  // B. Effort (High Avg Text Length) - Top 30 (Niche discussions)
  select(threads, 30, (a, b) => b.effort - a.effort, "High Effort/Depth");

  // C. Fill remaining budget with next best Importance
  // (We assume velocity is correlated with importance in this single-snapshot view)
  select(threads, 1000, (a, b) => b.imp - a.imp, "General Coverage"); // Add as many as fit

  console.log(`Selection pool size: ${finalSelection.length}`);

  // 4. Generate Output (with Token Budget)
  let output = `DATASET REPORT (7-Hour Window)\n`;
  output += `Scanned: ${posts.length} | Selected: ~${finalSelection.length}\n`;
  
  // Global Keywords
  const sortedKeywords = Array.from(globalKeywords.entries()).sort((a, b) => b[1] - a[1]).slice(0, 50);
  output += `\n=== GLOBAL KEYWORDS (Frequency) ===\n`;
  output += sortedKeywords.map(k => `${k[0]}: ${k[1]}`).join(", ") + "\n\n";

  let currentChars = output.length;
  let threadsIncluded = 0;

  // Sort selection by importance again for display order
  finalSelection.sort((a, b) => b.imp - a.imp);

  for (const t of finalSelection) {
      if (currentChars >= MAX_CHARS) break;

      const title = t.root?.title || "Unknown";
      const sub = t.root?.subreddit || "Unknown";
      
      let threadBlock = `--- THREAD [${(t as any).selectionReason}]: ${title} (r/${sub}) ---\n`;
      threadBlock += `ID: ${t.id} | Imp: ${t.imp.toFixed(0)} | Effort: ${t.effort.toFixed(0)}\n`;
      if (t.root?.textHistory[0]?.value) {
          threadBlock += `POST: ${t.root.textHistory[0].value.substring(0, 500)}\n`;
      }
      threadBlock += `COMMENTS:\n`;

      // Get comments
      const comments = Array.from(t.dag.getNodes().values())
          .filter(n => n.parentId !== null)
          .sort((a, b) => calculateNodeImportance(b) - calculateNodeImportance(a));
      
      // Add comments until thread is "full" or we run out
      // We allow up to 50 comments per thread to maximize context utility
      let commentCount = 0;
      for (const c of comments) {
          if (commentCount >= 50) break;
          const body = c.textHistory[0].value.replace(/\n/g, " ");
          const score = c.scoreHistory[0].value;
          threadBlock += `[${c.author}] (${score}): ${body.substring(0, 400)}\n`;
          commentCount++;
      }
      threadBlock += "\n";

      // Check global budget
      if (currentChars + threadBlock.length < MAX_CHARS) {
          output += threadBlock;
          currentChars += threadBlock.length;
          threadsIncluded++;
      } else {
          break;
      }
  }

  output += `\n[Truncated due to size limit: ${MAX_CHARS} chars]\n`;

  const outPath = join(process.cwd(), "reddit/batch_context.txt");
  writeFileSync(outPath, output);
  
  console.log(`\n✅ Generated Context:`);
  console.log(`   File: ${outPath}`);
  console.log(`   Threads Included: ${threadsIncluded}`);
  console.log(`   Size: ${(currentChars / 1024).toFixed(1)} KB`);
}

main();

