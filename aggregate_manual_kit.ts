#!/usr/bin/env bun
/**
 * Aggregate 14-day dataset for manual_kit with deduplication
 * Target: Nov 11-25, 2025 (14 days)
 */

import { readFileSync, writeFileSync, readdirSync, statSync, existsSync } from "fs";
import { join } from "path";

const CUTOFF_DATE = new Date("2025-11-11T00:00:00Z");
const TARGET_DIR = "/Users/swilliamson/Monitoring/manual_kit/data";

// ============================================================================
// REDDIT AGGREGATION
// ============================================================================
async function aggregateReddit() {
  console.log("📊 Aggregating Reddit data (14-day window)...");

  const redditThreadsDir = "/Users/swilliamson/Monitoring/reddit/data/threads";
  const outputFile = join(TARGET_DIR, "reddit", "reddit_data.txt");

  if (!existsSync(redditThreadsDir)) {
    console.error(`❌ Reddit threads directory not found: ${redditThreadsDir}`);
    return;
  }

  const threadFiles = readdirSync(redditThreadsDir)
    .filter(f => f.endsWith(".json"))
    .map(f => join(redditThreadsDir, f));

  console.log(`  Found ${threadFiles.length} Reddit thread files`);

  // Filter to last 14 days by file modification time
  const recentThreadFiles = threadFiles.filter(f => {
    const stat = statSync(f);
    return stat.mtime >= CUTOFF_DATE;
  });

  console.log(`  Filtered to ${recentThreadFiles.length} threads from last 14 days`);

  // Read all thread files and extract data
  const allThreads: any[] = [];
  const seenIds = new Set<string>();

  for (const threadFile of recentThreadFiles) {
    try {
      const content = readFileSync(threadFile, "utf-8");
      const thread = JSON.parse(content);

      // Get thread ID from the data or filename
      const threadId = Object.keys(thread)[0]; // First key is usually the post ID
      if (!threadId || seenIds.has(threadId)) continue;

      seenIds.add(threadId);
      allThreads.push({
        id: threadId,
        data: thread,
        file: threadFile,
      });
    } catch (e: any) {
      console.warn(`  ⚠️  Failed to parse ${threadFile}: ${e.message}`);
    }
  }

  console.log(`  Deduplicated to ${allThreads.length} unique threads`);

  // Format output similar to existing reddit_data.txt
  const outputLines: string[] = [];
  outputLines.push(`DATASET REPORT (14-Day Window: Nov 11-25, 2025)`);
  outputLines.push(`Scanned: ${allThreads.length} threads from 3,655 total collection`);
  outputLines.push("");

  // Add thread summaries
  for (const thread of allThreads) {
    const nodes = thread.data;
    const nodeIds = Object.keys(nodes);

    // Find the post node (depth 0)
    const postId = nodeIds.find(id => nodes[id].depth === 0);
    if (!postId) continue;

    const post = nodes[postId];
    const commentCount = nodeIds.filter(id => nodes[id].depth > 0).length;

    const title = post.title || post.textHistory?.[0]?.value?.substring(0, 80) || "[No title]";
    const subreddit = post.subreddit || "unknown";
    const text = post.textHistory?.[0]?.value || post.url || "[No content]";

    outputLines.push(`--- THREAD: ${title} ---`);
    outputLines.push(`ID: ${thread.id} | Subreddit: ${subreddit} | Comments: ${commentCount}`);
    outputLines.push(`POST: ${text}`);
    outputLines.push(`COMMENTS: ${commentCount} total`);
    outputLines.push("");
  }

  writeFileSync(outputFile, outputLines.join("\n"));
  console.log(`  ✅ Wrote ${allThreads.length} threads to ${outputFile}`);

  return {
    threads: allThreads.length,
    size: statSync(outputFile).size,
  };
}

// ============================================================================
// ARXIV AGGREGATION
// ============================================================================
async function aggregateArxiv() {
  console.log("📊 Aggregating ArXiv data (14-day window)...");

  const arxivDataDir = "/Users/swilliamson/Monitoring/preprints/arxiv/data";
  const outputFile = join(TARGET_DIR, "arxiv", "all_arxiv.txt");

  const arxivFiles = readdirSync(arxivDataDir)
    .filter(f => f.endsWith(".json") && f !== "state.json")
    .map(f => join(arxivDataDir, f))
    .filter(f => {
      const stat = statSync(f);
      return stat.mtime >= CUTOFF_DATE;
    });

  console.log(`  Found ${arxivFiles.length} ArXiv files from last 14 days`);

  const allEntries: any[] = [];
  const seenIds = new Set<string>();

  for (const arxivFile of arxivFiles) {
    try {
      const content = readFileSync(arxivFile, "utf-8");
      const data = JSON.parse(content);

      if (data.entries && Array.isArray(data.entries)) {
        for (const entry of data.entries) {
          const id = entry.id || entry.title;
          if (!id || seenIds.has(id)) continue;

          seenIds.add(id);
          allEntries.push({
            ...entry,
            sourceCategory: data.category,
            fetchedAt: data.fetchedAt,
          });
        }
      }
    } catch (e: any) {
      console.warn(`  ⚠️  Failed to parse ${arxivFile}: ${e.message}`);
    }
  }

  console.log(`  Deduplicated to ${allEntries.length} unique papers`);

  // Write as JSON Lines format
  const outputLines = allEntries.map(entry => JSON.stringify(entry));
  writeFileSync(outputFile, outputLines.join("\n"));

  console.log(`  ✅ Wrote ${allEntries.length} papers to ${outputFile}`);

  return {
    papers: allEntries.length,
    size: statSync(outputFile).size,
  };
}

// ============================================================================
// BLOG AGGREGATION
// ============================================================================
async function aggregateBlogs() {
  console.log("📊 Aggregating Blog data (14-day window)...");

  const blogDataDir = "/Users/swilliamson/Monitoring/blogs/data";
  const outputFile = join(TARGET_DIR, "blogs", "all_blogs.txt");

  // Find all blog JSON files from last 14 days (by file modification time)
  const blogDirs = readdirSync(blogDataDir).filter(f =>
    statSync(join(blogDataDir, f)).isDirectory()
  );

  console.log(`  Found ${blogDirs.length} blog source directories`);

  const allPosts: any[] = [];
  const seenIds = new Set<string>();

  for (const sourceDir of blogDirs) {
    const sourcePath = join(blogDataDir, sourceDir);
    const jsonFiles = readdirSync(sourcePath)
      .filter(f => f.endsWith(".json"))
      .map(f => join(sourcePath, f))
      .filter(f => {
        const stat = statSync(f);
        return stat.mtime >= CUTOFF_DATE;
      });

    for (const jsonFile of jsonFiles) {
      try {
        const content = readFileSync(jsonFile, "utf-8");
        const posts = JSON.parse(content);

        // Handle both single object and array
        const postsArray = Array.isArray(posts) ? posts : [posts];

        for (const post of postsArray) {
          const id = post.id || post.url;
          if (!id || seenIds.has(id)) continue;

          seenIds.add(id);
          allPosts.push(post);
        }
      } catch (e: any) {
        console.warn(`  ⚠️  Failed to parse ${jsonFile}: ${e.message}`);
      }
    }
  }

  console.log(`  Deduplicated to ${allPosts.length} unique posts`);

  // Write as JSON Lines format
  const outputLines = allPosts.map(post => JSON.stringify(post));
  writeFileSync(outputFile, outputLines.join("\n"));

  console.log(`  ✅ Wrote ${allPosts.length} posts to ${outputFile}`);

  return {
    posts: allPosts.length,
    size: statSync(outputFile).size,
  };
}

// ============================================================================
// MAIN
// ============================================================================
async function main() {
  console.log("🚀 Starting 14-day dataset aggregation for manual_kit");
  console.log(`   Cutoff: ${CUTOFF_DATE.toISOString()}`);
  console.log("");

  const results: any = {};

  // Aggregate all domains
  results.reddit = await aggregateReddit();
  results.arxiv = await aggregateArxiv();
  results.blogs = await aggregateBlogs();

  console.log("");
  console.log("=" .repeat(60));
  console.log("✅ AGGREGATION COMPLETE");
  console.log("=" .repeat(60));
  console.log("");
  console.log("Reddit:");
  console.log(`  Threads: ${results.reddit?.threads || 0}`);
  console.log(`  Size: ${((results.reddit?.size || 0) / 1024 / 1024).toFixed(2)} MB`);
  console.log("");
  console.log("ArXiv:");
  console.log(`  Papers: ${results.arxiv?.papers || 0}`);
  console.log(`  Size: ${((results.arxiv?.size || 0) / 1024 / 1024).toFixed(2)} MB`);
  console.log("");
  console.log("Blogs:");
  console.log(`  Posts: ${results.blogs?.posts || 0}`);
  console.log(`  Size: ${((results.blogs?.size || 0) / 1024 / 1024).toFixed(2)} MB`);
  console.log("");
  console.log("Total:");
  console.log(`  Size: ${(((results.reddit?.size || 0) + (results.arxiv?.size || 0) + (results.blogs?.size || 0)) / 1024 / 1024).toFixed(2)} MB`);
}

main().catch(console.error);
