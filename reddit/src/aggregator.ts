import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { join } from "path";
import { DAG } from "./dag";
import type { RedditNode } from "./types";

// Helper to convert Python's snapshot format to our RedditNode[]
function parseSnapshot(snapshot: any): RedditNode[] {
  const nodes: RedditNode[] = [];
  const timestamp = snapshot.metadata?.scraped_at || new Date().toISOString();

  // 1. Post
  const p = snapshot.post;
  if (p) {
    // Note: Python output might have different field names than raw API
    // Python 'post' dict keys: id, title, author, score, created_utc...
    nodes.push({
      id: p.id,
      parentId: null,
      author: p.author,
      createdUtc: p.created_utc,
      permalink: p.permalink,
      depth: 0,
      scoreHistory: [{ value: p.score, timestamp }],
      textHistory: [{ value: p.selftext || p.url || "", timestamp }],
      isDeleted: false, // We assume top-level post exists if we scraped it
      deletedAt: null,
      subreddit: p.subreddit,
      title: p.title,
      url: p.url,
      extra: { ...p } // Capture everything else
    });
  }

  // 2. Comments
  // Python snapshot usually has 'comments' as a list (if flattened) or tree
  // The 'unified_scraper' output seems to be a list of comment objects with 'depth'
  const comments = snapshot.comments || [];
  
  // Flatten if necessary (though Python scrape_single_post usually output flat list?)
  // Wait, scrape_reddit_post_api returns 'comments' as a list of temporal objects?
  // Let's handle flat list for now.
  
  for (const c of comments) {
    // Python legacy format:
    // { id, parent_id, author, body, score, created_utc... }
    const body = c.body || c.text_history?.[0]?.[0] || "[deleted]";
    const score = c.score ?? c.score_history?.[0]?.[0] ?? 0;

    nodes.push({
      id: c.id,
      parentId: c.parent_id,
      author: c.author,
      createdUtc: c.created_utc,
      permalink: c.permalink,
      depth: c.depth,
      scoreHistory: [{ value: score, timestamp }],
      textHistory: [{ value: body, timestamp }],
      isDeleted: c.deleted || body === "[deleted]",
      deletedAt: c.deleted_at || null,
      extra: { ...c }
    });
  }

  return nodes;
}

function aggregatePost(postId: string) {
  const baseDir = join(process.cwd(), "reddit/reddit-adaptive-sampler/temporal_test", postId, "raw_scrapes");
  
  if (!existsSync(baseDir)) {
    console.error(`No data found for post ${postId} at ${baseDir}`);
    return;
  }

  // 1. Find all scrape files
  const files = readdirSync(baseDir)
    .filter(f => f.endsWith(".json") && f.startsWith("scrape_"))
    .sort(); // Lexicographical sort works for scrape_001, scrape_002...

  if (files.length === 0) {
    console.log(`No scrape files found for ${postId}`);
    return;
  }

  console.log(`Aggregating ${files.length} snapshots for ${postId}...`);

  // 2. Merge loop
  const dag = new DAG();
  
  for (const file of files) {
    const path = join(baseDir, file);
    const raw = readFileSync(path, "utf-8");
    const json = JSON.parse(raw);
    
    // The timestamp is in the filename usually, or metadata
    // scrape_001_20251119_211426.json
    const tsMatch = file.match(/(\d{8}_\d{6})/);
    let timestamp = new Date().toISOString();
    if (tsMatch) {
        // Format: YYYYMMDD_HHMMSS
        // Need to convert to ISO
        const t = tsMatch[1];
        const str = `${t.substring(0,4)}-${t.substring(4,6)}-${t.substring(6,8)}T${t.substring(9,11)}:${t.substring(11,13)}:${t.substring(13,15)}Z`;
        timestamp = str;
    }

    const nodes = parseSnapshot(json);
    dag.merge(nodes, timestamp);
  }

  // 3. Output
  const outDir = join(process.cwd(), "reddit/data");
  if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
  
  const outPath = join(outDir, `merged_${postId}.json`);
  const result = dag.toJSON();
  
  writeFileSync(outPath, JSON.stringify(result, null, 2));
  console.log(`✅ Saved merged DAG to ${outPath} (${Object.keys(result).length} nodes)`);
}

// Main
const targetId = process.argv[2];
if (!targetId) {
  console.error("Usage: bun run src/aggregator.ts <post_id>");
  process.exit(1);
}

aggregatePost(targetId);
