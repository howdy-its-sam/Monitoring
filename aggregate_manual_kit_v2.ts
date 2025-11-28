#!/usr/bin/env bun
/**
 * Aggregate 14-day dataset for manual_kit with Phase 1 preprocessing
 *
 * Phase 1 Improvements:
 * 1. Metadata headers with format, size, and temporal info
 * 2. Content-based date filtering (not just file mtime)
 * 3. Standardized temporal fields across all domains
 * 4. JSON Lines format for all outputs
 * 5. Summary statistics in headers
 */

import { readFileSync, writeFileSync, readdirSync, statSync, existsSync } from "fs";
import { join } from "path";

const CUTOFF_START = new Date("2025-11-11T00:00:00Z");
const CUTOFF_END = new Date("2025-11-25T23:59:59Z");
const TARGET_DIR = "/Users/swilliamson/Monitoring/manual_kit/data";

// Helper: Calculate days ago from a timestamp
function daysAgo(timestamp: number): number {
  const now = CUTOFF_END.getTime() / 1000; // Use end of window as "now"
  const diff = now - timestamp;
  return Math.floor(diff / 86400);
}

// Helper: Get temporal tag based on age
function getTemporalTag(daysOld: number): string {
  if (daysOld < 1) return "BREAKING";
  if (daysOld < 7) return "EMERGING";
  if (daysOld < 30) return "SUSTAINED";
  return "RESURGENT";
}

// Helper: Get temporal weight based on age in hours
function getTemporalWeight(hoursOld: number): number {
  if (hoursOld < 24) return 1.0;
  if (hoursOld < 48) return 0.6;
  if (hoursOld < 72) return 0.3;
  return 0.1;
}

// Helper: Generate metadata header
function generateMetadataHeader(params: {
  format: string;
  totalItems: number;
  dateRange: string;
  temporalField: string;
  size: number;
  domainStats: any;
}): string {
  const lines = [
    "# METADATA",
    `Format: ${params.format}`,
    `Total Items: ${params.totalItems.toLocaleString()}`,
    `Date Range: ${params.dateRange}`,
    `Pre-filtered: Yes (all items within date range, verified by content timestamps)`,
    `Temporal Field: ${params.temporalField}`,
    `Size: ${(params.size / 1024 / 1024).toFixed(2)} MB`,
    `Encoding: UTF-8`,
    "",
    "# SUMMARY STATISTICS",
    ...Object.entries(params.domainStats).map(([key, value]) => `${key}: ${value}`),
    "",
    "# DATA FORMAT",
    "Each line is a JSON object with standardized temporal fields:",
    "  meta_timestamp: Unix timestamp (seconds)",
    "  meta_date_human: ISO date string (YYYY-MM-DD)",
    "  meta_days_ago: Days before end of window",
    "  meta_temporal_tag: BREAKING/EMERGING/SUSTAINED/RESURGENT",
    "  meta_temporal_weight: 1.0 (0-24h) / 0.6 (24-48h) / 0.3 (48-72h) / 0.1 (>72h)",
    "",
    "# DATA",
    "",
  ];
  return lines.join("\n");
}

// ============================================================================
// REDDIT AGGREGATION (Enhanced)
// ============================================================================
async function aggregateReddit() {
  console.log("📊 Aggregating Reddit data (14-day window)...");

  const redditThreadsDir = "/Users/swilliamson/Monitoring/reddit/data/threads";
  const outputFile = join(TARGET_DIR, "reddit", "reddit_data.jsonl");

  if (!existsSync(redditThreadsDir)) {
    console.error(`❌ Reddit threads directory not found: ${redditThreadsDir}`);
    return;
  }

  const threadFiles = readdirSync(redditThreadsDir)
    .filter(f => f.endsWith(".json"))
    .map(f => join(redditThreadsDir, f));

  console.log(`  Found ${threadFiles.length} Reddit thread files`);

  // Read all thread files and extract data with temporal filtering
  const allThreads: any[] = [];
  const seenIds = new Set<string>();
  const subredditCounts = new Map<string, number>();
  const temporalBuckets = { breaking: 0, emerging: 0, sustained: 0, resurgent: 0 };

  for (const threadFile of threadFiles) {
    try {
      const content = readFileSync(threadFile, "utf-8");
      const thread = JSON.parse(content);

      // Get thread ID from the data
      const threadId = Object.keys(thread)[0];
      if (!threadId || seenIds.has(threadId)) continue;

      const nodes = thread;
      const nodeIds = Object.keys(nodes);
      const postId = nodeIds.find(id => nodes[id].depth === 0);
      if (!postId) continue;

      const post = nodes[postId];

      // Extract timestamp - use createdUtc (Unix timestamp in seconds) or scoreHistory ISO string
      let timestamp: number;
      if (post.createdUtc) {
        timestamp = post.createdUtc;
      } else if (post.scoreHistory?.[0]?.timestamp) {
        timestamp = Math.floor(new Date(post.scoreHistory[0].timestamp).getTime() / 1000);
      } else {
        continue; // Skip if no timestamp available
      }

      // Filter by actual content date, not file mtime
      const postDate = new Date(timestamp * 1000);
      if (postDate < CUTOFF_START || postDate > CUTOFF_END) continue;

      seenIds.add(threadId);

      // Calculate temporal metadata
      const days = daysAgo(timestamp);
      const hours = days * 24;
      const tag = getTemporalTag(days);
      const weight = getTemporalWeight(hours);

      // Track stats
      const subreddit = post.subreddit || "unknown";
      subredditCounts.set(subreddit, (subredditCounts.get(subreddit) || 0) + 1);
      temporalBuckets[tag.toLowerCase() as keyof typeof temporalBuckets]++;

      // Build enriched thread object
      const commentCount = nodeIds.filter(id => nodes[id].depth > 0).length;
      const title = post.title || post.textHistory?.[0]?.value?.substring(0, 100) || "[No title]";
      const text = post.textHistory?.[0]?.value || post.url || "[No content]";

      const enrichedThread = {
        // Standardized temporal fields (Phase 1)
        meta_timestamp: timestamp,
        meta_date_human: new Date(timestamp * 1000).toISOString().split('T')[0],
        meta_days_ago: days,
        meta_temporal_tag: tag,
        meta_temporal_weight: weight,

        // Original data
        id: threadId,
        subreddit,
        title,
        text,
        commentCount,
        url: post.url,
        score: post.scoreHistory?.[0]?.score || 0,

        // Include all nodes for full thread context
        nodes: thread,
      };

      allThreads.push(enrichedThread);
    } catch (e: any) {
      console.warn(`  ⚠️  Failed to parse ${threadFile}: ${e.message}`);
    }
  }

  console.log(`  Filtered to ${allThreads.length} threads within date range (by content timestamp)`);

  // Sort by timestamp (newest first)
  allThreads.sort((a, b) => b.meta_timestamp - a.meta_timestamp);

  // Calculate summary statistics
  const topSubreddits = Array.from(subredditCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([sub, count]) => `${sub} (${count})`)
    .join(", ");

  const totalComments = allThreads.reduce((sum, t) => sum + t.commentCount, 0);
  const avgComments = (totalComments / allThreads.length).toFixed(1);

  // Generate metadata header
  const header = generateMetadataHeader({
    format: "JSON Lines (one JSON object per line)",
    totalItems: allThreads.length,
    dateRange: "2025-11-11 to 2025-11-25 (14 days)",
    temporalField: "meta_timestamp (from createdUtc)",
    size: 0, // Will be calculated after write
    domainStats: {
      "Unique subreddits": subredditCounts.size,
      "Top 5 subreddits": topSubreddits,
      "Total comments": totalComments.toLocaleString(),
      "Avg comments/thread": avgComments,
      "Temporal distribution": `BREAKING: ${temporalBuckets.breaking}, EMERGING: ${temporalBuckets.emerging}, SUSTAINED: ${temporalBuckets.sustained}, RESURGENT: ${temporalBuckets.resurgent}`,
    }
  });

  // Write as JSON Lines with metadata header
  const outputLines = [
    header,
    ...allThreads.map(thread => JSON.stringify(thread))
  ];

  writeFileSync(outputFile, outputLines.join("\n"));
  console.log(`  ✅ Wrote ${allThreads.length} threads to ${outputFile}`);

  return {
    threads: allThreads.length,
    size: statSync(outputFile).size,
    stats: {
      subreddits: subredditCounts.size,
      comments: totalComments,
      temporal: temporalBuckets,
    }
  };
}

// ============================================================================
// ARXIV AGGREGATION (Enhanced)
// ============================================================================
async function aggregateArxiv() {
  console.log("📊 Aggregating ArXiv data (14-day window)...");

  const arxivDataDir = "/Users/swilliamson/Monitoring/preprints/arxiv/data";
  const outputFile = join(TARGET_DIR, "arxiv", "all_arxiv.jsonl");

  const arxivFiles = readdirSync(arxivDataDir)
    .filter(f => f.endsWith(".json") && f !== "state.json")
    .map(f => join(arxivDataDir, f));

  console.log(`  Found ${arxivFiles.length} ArXiv files`);

  const allEntries: any[] = [];
  const seenIds = new Set<string>();
  const categoryCounts = new Map<string, number>();
  const temporalBuckets = { breaking: 0, emerging: 0, sustained: 0, resurgent: 0 };

  for (const arxivFile of arxivFiles) {
    try {
      const content = readFileSync(arxivFile, "utf-8");
      const data = JSON.parse(content);

      if (data.entries && Array.isArray(data.entries)) {
        for (const entry of data.entries) {
          const id = entry.id || entry.title;
          if (!id || seenIds.has(id)) continue;

          // Parse published date
          const published = new Date(entry.published);
          if (isNaN(published.getTime())) continue;

          // Filter by content date
          if (published < CUTOFF_START || published > CUTOFF_END) continue;

          seenIds.add(id);

          // Calculate temporal metadata
          const timestamp = Math.floor(published.getTime() / 1000);
          const days = daysAgo(timestamp);
          const hours = days * 24;
          const tag = getTemporalTag(days);
          const weight = getTemporalWeight(hours);

          // Track stats
          const category = data.category || "unknown";
          categoryCounts.set(category, (categoryCounts.get(category) || 0) + 1);
          temporalBuckets[tag.toLowerCase() as keyof typeof temporalBuckets]++;

          const enrichedEntry = {
            // Standardized temporal fields (Phase 1)
            meta_timestamp: timestamp,
            meta_date_human: published.toISOString().split('T')[0],
            meta_days_ago: days,
            meta_temporal_tag: tag,
            meta_temporal_weight: weight,

            // Original data
            ...entry,
            sourceCategory: category,
            fetchedAt: data.fetchedAt,
          };

          allEntries.push(enrichedEntry);
        }
      }
    } catch (e: any) {
      console.warn(`  ⚠️  Failed to parse ${arxivFile}: ${e.message}`);
    }
  }

  console.log(`  Filtered to ${allEntries.length} papers within date range`);

  // Sort by timestamp (newest first)
  allEntries.sort((a, b) => b.meta_timestamp - a.meta_timestamp);

  // Generate metadata header
  const topCategories = Array.from(categoryCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([cat, count]) => `${cat} (${count})`)
    .join(", ");

  const header = generateMetadataHeader({
    format: "JSON Lines (one JSON object per line)",
    totalItems: allEntries.length,
    dateRange: "2025-11-11 to 2025-11-25 (14 days)",
    temporalField: "meta_timestamp (from published date)",
    size: 0,
    domainStats: {
      "Unique categories": categoryCounts.size,
      "Top 5 categories": topCategories,
      "Temporal distribution": `BREAKING: ${temporalBuckets.breaking}, EMERGING: ${temporalBuckets.emerging}, SUSTAINED: ${temporalBuckets.sustained}, RESURGENT: ${temporalBuckets.resurgent}`,
    }
  });

  const outputLines = [
    header,
    ...allEntries.map(entry => JSON.stringify(entry))
  ];

  writeFileSync(outputFile, outputLines.join("\n"));
  console.log(`  ✅ Wrote ${allEntries.length} papers to ${outputFile}`);

  return {
    papers: allEntries.length,
    size: statSync(outputFile).size,
    stats: {
      categories: categoryCounts.size,
      temporal: temporalBuckets,
    }
  };
}

// ============================================================================
// BLOG AGGREGATION (Enhanced)
// ============================================================================
async function aggregateBlogs() {
  console.log("📊 Aggregating Blog data (14-day window)...");

  const blogDataDir = "/Users/swilliamson/Monitoring/blogs/data";
  const outputFile = join(TARGET_DIR, "blogs", "all_blogs.jsonl");

  const blogDirs = readdirSync(blogDataDir).filter(f =>
    statSync(join(blogDataDir, f)).isDirectory()
  );

  console.log(`  Found ${blogDirs.length} blog source directories`);

  const allPosts: any[] = [];
  const seenIds = new Set<string>();
  const sourceCounts = new Map<string, number>();
  const temporalBuckets = { breaking: 0, emerging: 0, sustained: 0, resurgent: 0 };

  for (const sourceDir of blogDirs) {
    const sourcePath = join(blogDataDir, sourceDir);
    const jsonFiles = readdirSync(sourcePath)
      .filter(f => f.endsWith(".json"))
      .map(f => join(sourcePath, f));

    for (const jsonFile of jsonFiles) {
      try {
        const content = readFileSync(jsonFile, "utf-8");
        const posts = JSON.parse(content);

        const postsArray = Array.isArray(posts) ? posts : [posts];

        for (const post of postsArray) {
          const id = post.id || post.url;
          if (!id || seenIds.has(id)) continue;

          // Parse published date
          const publishedAt = post.publishedAt || post.published || post.date;
          if (!publishedAt) continue;

          const published = new Date(publishedAt);
          if (isNaN(published.getTime())) continue;

          // Filter by content date
          if (published < CUTOFF_START || published > CUTOFF_END) continue;

          seenIds.add(id);

          // Calculate temporal metadata
          const timestamp = Math.floor(published.getTime() / 1000);
          const days = daysAgo(timestamp);
          const hours = days * 24;
          const tag = getTemporalTag(days);
          const weight = getTemporalWeight(hours);

          // Track stats
          const source = post.source || sourceDir;
          sourceCounts.set(source, (sourceCounts.get(source) || 0) + 1);
          temporalBuckets[tag.toLowerCase() as keyof typeof temporalBuckets]++;

          const enrichedPost = {
            // Standardized temporal fields (Phase 1)
            meta_timestamp: timestamp,
            meta_date_human: published.toISOString().split('T')[0],
            meta_days_ago: days,
            meta_temporal_tag: tag,
            meta_temporal_weight: weight,

            // Original data
            ...post,
            meta_source_directory: sourceDir,
          };

          allPosts.push(enrichedPost);
        }
      } catch (e: any) {
        console.warn(`  ⚠️  Failed to parse ${jsonFile}: ${e.message}`);
      }
    }
  }

  console.log(`  Filtered to ${allPosts.length} posts within date range`);

  // Sort by timestamp (newest first)
  allPosts.sort((a, b) => b.meta_timestamp - a.meta_timestamp);

  // Generate metadata header
  const topSources = Array.from(sourceCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([src, count]) => `${src} (${count})`)
    .join(", ");

  const header = generateMetadataHeader({
    format: "JSON Lines (one JSON object per line)",
    totalItems: allPosts.length,
    dateRange: "2025-11-11 to 2025-11-25 (14 days)",
    temporalField: "meta_timestamp (from publishedAt/published/date)",
    size: 0,
    domainStats: {
      "Unique sources": sourceCounts.size,
      "Top 5 sources": topSources,
      "Temporal distribution": `BREAKING: ${temporalBuckets.breaking}, EMERGING: ${temporalBuckets.emerging}, SUSTAINED: ${temporalBuckets.sustained}, RESURGENT: ${temporalBuckets.resurgent}`,
    }
  });

  const outputLines = [
    header,
    ...allPosts.map(post => JSON.stringify(post))
  ];

  writeFileSync(outputFile, outputLines.join("\n"));
  console.log(`  ✅ Wrote ${allPosts.length} posts to ${outputFile}`);

  return {
    posts: allPosts.length,
    size: statSync(outputFile).size,
    stats: {
      sources: sourceCounts.size,
      temporal: temporalBuckets,
    }
  };
}

// ============================================================================
// MAIN
// ============================================================================
async function main() {
  console.log("🚀 Starting Phase 1 Enhanced Aggregation");
  console.log(`   Date Range: ${CUTOFF_START.toISOString()} to ${CUTOFF_END.toISOString()}`);
  console.log(`   Improvements: Metadata headers, content-based filtering, standardized temporal fields`);
  console.log("");

  const results: any = {};

  results.reddit = await aggregateReddit();
  results.arxiv = await aggregateArxiv();
  results.blogs = await aggregateBlogs();

  console.log("");
  console.log("=".repeat(80));
  console.log("✅ PHASE 1 AGGREGATION COMPLETE");
  console.log("=".repeat(80));
  console.log("");
  console.log("Reddit:");
  console.log(`  Threads: ${results.reddit?.threads || 0}`);
  console.log(`  Subreddits: ${results.reddit?.stats?.subreddits || 0}`);
  console.log(`  Comments: ${results.reddit?.stats?.comments || 0}`);
  console.log(`  Size: ${((results.reddit?.size || 0) / 1024 / 1024).toFixed(2)} MB`);
  console.log("");
  console.log("ArXiv:");
  console.log(`  Papers: ${results.arxiv?.papers || 0}`);
  console.log(`  Categories: ${results.arxiv?.stats?.categories || 0}`);
  console.log(`  Size: ${((results.arxiv?.size || 0) / 1024 / 1024).toFixed(2)} MB`);
  console.log("");
  console.log("Blogs:");
  console.log(`  Posts: ${results.blogs?.posts || 0}`);
  console.log(`  Sources: ${results.blogs?.stats?.sources || 0}`);
  console.log(`  Size: ${((results.blogs?.size || 0) / 1024 / 1024).toFixed(2)} MB`);
  console.log("");
  console.log("Total:");
  console.log(`  Items: ${(results.reddit?.threads || 0) + (results.arxiv?.papers || 0) + (results.blogs?.posts || 0)}`);
  console.log(`  Size: ${(((results.reddit?.size || 0) + (results.arxiv?.size || 0) + (results.blogs?.size || 0)) / 1024 / 1024).toFixed(2)} MB`);
  console.log("");
  console.log("📝 All files now include:");
  console.log("   • Metadata headers with format and scope info");
  console.log("   • Content-based date filtering (not file mtime)");
  console.log("   • Standardized temporal fields (meta_timestamp, meta_date_human, etc.)");
  console.log("   • Pre-calculated temporal tags and weights");
  console.log("   • Summary statistics for quick overview");
}

main().catch(console.error);
