import { RedditAPI } from "./api";
import { StorageDriver } from "./storage";
import { DAG } from "./dag";
import { readFileSync, existsSync, writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";

// --- Configuration ---
const RATE_LIMIT_BUFFER = 0.05; // Leave 5% of capacity unused
const TARGET_RPS = 10.0; // Use full OAuth limit (600/min)
const LOOKBACK_HOURS = 72; // How far back to sweep
const STATE_FILE = "backfill_state.json";
const LOG_FILE = "backfill_run.log";

// --- Types ---
interface BackfillState {
  processedIds: string[]; // Changed from Set for JSON serialization
  failedSubreddits: string[];
  lastRun?: string;
  stats: BackfillStats;
}

interface BackfillStats {
  totalSubreddits: number;
  completedSubreddits: number;
  totalPostsScraped: number;
  totalPostsSkipped: number;
  totalCommentsScraped: number;
  subredditStats: Record<string, SubredditStats>;
  failedPosts: FailedPost[];
  startTime?: string;
  endTime?: string;
}

interface SubredditStats {
  postsScraped: number;
  postsSkipped: number;
  totalComments: number;
  avgCommentsPerPost: number;
}

interface FailedPost {
  postId: string;
  subreddit: string;
  error: string;
  timestamp: string;
  retryCount: number;
}

// --- Helpers ---

/**
 * Resolves project root directory by looking for characteristic files
 */
function findProjectRoot(): string {
  let current = process.cwd();
  const maxDepth = 5;

  for (let i = 0; i < maxDepth; i++) {
    // Check for characteristic project files
    const markers = [
      join(current, "reddit/reddit-adaptive-sampler"),
      join(current, "package.json"),
      join(current, ".git")
    ];

    if (markers.some(m => existsSync(m))) {
      return current;
    }

    const parent = dirname(current);
    if (parent === current) break; // Reached filesystem root
    current = parent;
  }

  // Fallback to cwd
  return process.cwd();
}

const PROJECT_ROOT = findProjectRoot();
const DATA_DIR = join(PROJECT_ROOT, "reddit/data");
const STATE_PATH = join(DATA_DIR, STATE_FILE);
const LOG_PATH = join(DATA_DIR, LOG_FILE);

function loadPriorities(): string[] {
  const possiblePaths = [
    join(PROJECT_ROOT, "reddit/reddit-adaptive-sampler/subreddit_priorities.txt"),
    join(PROJECT_ROOT, "reddit-adaptive-sampler/subreddit_priorities.txt"),
    join(process.cwd(), "subreddit_priorities.txt")
  ];

  for (const path of possiblePaths) {
    if (existsSync(path)) {
      return readFileSync(path, "utf-8")
        .split("\n")
        .map(l => l.trim().replace(/^r\//, ""))
        .filter(l => l && !l.startsWith("#"));
    }
  }

  console.warn("⚠️  No subreddit_priorities.txt found, using default: LocalLLaMA");
  return ["LocalLLaMA"];
}

class Backfiller {
  private api: RedditAPI;
  private storage: StorageDriver;
  private state: BackfillState;
  private subreddits: string[];
  private logStream: any; // File descriptor for logging
  private lastProgressUpdate = 0;
  private processedIdsSet: Set<string>; // For fast lookups
  private failedSubredditsSet: Set<string>;

  constructor() {
    this.api = new RedditAPI();
    this.storage = new StorageDriver();
    this.subreddits = loadPriorities();

    // Ensure data directory exists
    if (!existsSync(DATA_DIR)) {
      mkdirSync(DATA_DIR, { recursive: true });
    }

    // Ensure threads subdirectory exists
    const threadsDir = join(DATA_DIR, "threads");
    if (!existsSync(threadsDir)) {
      mkdirSync(threadsDir, { recursive: true });
    }

    // Load or initialize state
    this.state = this.loadState();
    this.processedIdsSet = new Set(this.state.processedIds);
    this.failedSubredditsSet = new Set(this.state.failedSubreddits);

    // Open log file (append mode)
    this.logStream = require('fs').createWriteStream(LOG_PATH, { flags: 'a' });

    this.log(`Backfiller initialized. Project root: ${PROJECT_ROOT}`);
    this.log(`Data directory: ${DATA_DIR}`);
    this.log(`Loaded ${this.subreddits.length} subreddits from priorities file`);
  }

  private loadState(): BackfillState {
    if (existsSync(STATE_PATH)) {
      try {
        const data = JSON.parse(readFileSync(STATE_PATH, "utf-8"));
        this.log(`Loaded state from previous run (${data.processedIds?.length || 0} processed posts)`, "success");
        return {
          processedIds: data.processedIds || [],
          failedSubreddits: data.failedSubreddits || [],
          lastRun: data.lastRun,
          stats: data.stats || this.initializeStats()
        };
      } catch (e: any) {
        this.log(`Failed to load state: ${e.message}. Starting fresh.`, "warning");
      }
    }

    this.log("No previous state found. Starting fresh backfill.", "info");
    return {
      processedIds: [],
      failedSubreddits: [],
      stats: this.initializeStats()
    };
  }

  private initializeStats(): BackfillStats {
    return {
      totalSubreddits: this.subreddits.length,
      completedSubreddits: 0,
      totalPostsScraped: 0,
      totalPostsSkipped: 0,
      totalCommentsScraped: 0,
      subredditStats: {},
      failedPosts: []
    };
  }

  private saveState() {
    try {
      // Convert Sets back to arrays for JSON
      this.state.processedIds = Array.from(this.processedIdsSet);
      this.state.failedSubreddits = Array.from(this.failedSubredditsSet);
      this.state.lastRun = new Date().toISOString();

      writeFileSync(STATE_PATH, JSON.stringify(this.state, null, 2));
    } catch (e: any) {
      this.log(`Failed to save state: ${e.message}`, "error");
    }
  }

  private log(msg: string, type: "info" | "success" | "warning" | "error" = "info") {
    const ts = new Date().toISOString();
    const prefix = `[${ts}] [BACKFILL]`;
    let fullMsg = "";

    if (type === "error") {
      fullMsg = `${prefix} ❌ ${msg}`;
      console.error(fullMsg);
    } else if (type === "warning") {
      fullMsg = `${prefix} ⚠️  ${msg}`;
      console.warn(fullMsg);
    } else if (type === "success") {
      fullMsg = `${prefix} ✅ ${msg}`;
      console.log(fullMsg);
    } else {
      fullMsg = `${prefix} ${msg}`;
      console.log(fullMsg);
    }

    // Write to log file
    if (this.logStream) {
      this.logStream.write(fullMsg + '\n');
    }
  }

  private logProgress(current: number, total: number, label: string) {
    const now = Date.now();
    // Throttle progress updates to every 2 seconds
    if (now - this.lastProgressUpdate < 2000 && current < total) {
      return;
    }
    this.lastProgressUpdate = now;

    const pct = ((current / total) * 100).toFixed(1);
    const bar = this.makeProgressBar(current, total, 30);
    this.log(`${label}: [${bar}] ${current}/${total} (${pct}%)`);
  }

  private makeProgressBar(current: number, total: number, width: number): string {
    const filled = Math.floor((current / total) * width);
    const empty = width - filled;
    return '█'.repeat(filled) + '░'.repeat(empty);
  }

  public async start() {
    this.state.stats.startTime = new Date().toISOString();
    this.log(`═══════════════════════════════════════════════════════`);
    this.log(`Starting backfill for ${this.subreddits.length} subreddits`);
    this.log(`Lookback Window: ${LOOKBACK_HOURS} hours`);
    this.log(`Target RPS: ${TARGET_RPS} (${TARGET_RPS * 60} requests/min)`);
    this.log(`Log file: ${LOG_PATH}`);
    this.log(`State file: ${STATE_PATH}`);
    this.log(`═══════════════════════════════════════════════════════`);

    const startTime = Date.now();
    let requestCount = 0;
    let lastRateCheck = Date.now();
    let requestsSinceLastCheck = 0;

    for (let i = 0; i < this.subreddits.length; i++) {
      const sub = this.subreddits[i];

      if (this.failedSubredditsSet.has(sub)) {
        this.log(`Skipping blacklisted sub: r/${sub}`, "warning");
        continue;
      }

      this.logProgress(i + 1, this.subreddits.length, "Subreddit Progress");
      this.log(`\n📂 Scanning r/${sub} (${i + 1}/${this.subreddits.length})...`);

      // Initialize subreddit stats
      if (!this.state.stats.subredditStats[sub]) {
        this.state.stats.subredditStats[sub] = {
          postsScraped: 0,
          postsSkipped: 0,
          totalComments: 0,
          avgCommentsPerPost: 0
        };
      }

      try {
        const listing = await this.fetchListingWithBackoff(sub, "new", 100);
        requestCount++;
        requestsSinceLastCheck++;

        let added = 0;
        let skipped = 0;

        for (const post of listing) {
          // Safety check: Ensure created_utc exists
          if (!post.created_utc) {
            this.log(`⚠️  Post ${post.id} missing created_utc field, skipping`, "warning");
            continue;
          }

          if (this.processedIdsSet.has(post.id)) {
            skipped++;
            continue;
          }

          // Check if we already have it on disk
          const exists = await this.storage.load(`threads/${post.id}.json`);
          if (exists) {
            this.processedIdsSet.add(post.id);
            this.state.stats.totalPostsSkipped++;
            this.state.stats.subredditStats[sub].postsSkipped++;
            skipped++;
            continue;
          }

          // Fetch thread with retry logic
          const commentCount = await this.processThreadWithRetry(post.id, sub);
          requestCount++;
          requestsSinceLastCheck++;

          if (commentCount !== null) {
            added++;
            this.state.stats.totalPostsScraped++;
            this.state.stats.totalCommentsScraped += commentCount;
            this.state.stats.subredditStats[sub].postsScraped++;
            this.state.stats.subredditStats[sub].totalComments += commentCount;
          }

          // Rate Limit Sleep
          await new Promise(r => setTimeout(r, 1000 / TARGET_RPS));
        }

        // Update avg for this subreddit
        const subStats = this.state.stats.subredditStats[sub];
        if (subStats.postsScraped > 0) {
          subStats.avgCommentsPerPost = subStats.totalComments / subStats.postsScraped;
        }

        this.log(`✓ r/${sub}: +${added} scraped, ${skipped} skipped, avg ${subStats.avgCommentsPerPost.toFixed(1)} comments/post`, "success");
        this.state.stats.completedSubreddits++;

        // Save state periodically (every 5 subreddits)
        if ((i + 1) % 5 === 0) {
          this.saveState();
          this.log(`💾 State saved (checkpoint at ${i + 1}/${this.subreddits.length})`);
        }

        // Check actual RPS every 30 seconds
        const timeSinceLastCheck = (Date.now() - lastRateCheck) / 1000;
        if (timeSinceLastCheck >= 30) {
          const actualRPS = requestsSinceLastCheck / timeSinceLastCheck;
          const utilization = (actualRPS / TARGET_RPS) * 100;

          if (utilization < 50) {
            this.log(`⚠️  LOW RATE UTILIZATION: ${actualRPS.toFixed(2)} RPS (${utilization.toFixed(1)}% of ${TARGET_RPS} target)`, "warning");
            this.log(`   You may not be using your full OAuth quota (600 req/min)`, "warning");
          } else {
            this.log(`📊 Rate: ${actualRPS.toFixed(2)} RPS (${utilization.toFixed(1)}% utilization)`);
          }

          lastRateCheck = Date.now();
          requestsSinceLastCheck = 0;
        }

      } catch (e: any) {
        this.handleSubredditError(sub, e);
      }
    }

    // Final save
    this.state.stats.endTime = new Date().toISOString();
    this.saveState();

    // Print final summary
    this.printFinalSummary(startTime, requestCount);

    // Close log stream
    if (this.logStream) {
      this.logStream.end();
    }
  }

  private async fetchListingWithBackoff(sub: string, sort: string, batchSize: number): Promise<any[]> {
    let allPosts: any[] = [];
    let afterCursor: string | undefined = undefined;
    const cutoffTime = Date.now() / 1000 - (LOOKBACK_HOURS * 3600); // Reddit uses seconds

    this.log(`Fetching listing for r/${sub} (until ${new Date(cutoffTime * 1000).toISOString()})...`);

    while (true) {
      try {
        const batch = await this.api.getListing(sub, sort, batchSize, afterCursor);

        // Safety check: empty batch
        if (!batch || batch.length === 0) {
          this.log(`Empty batch received, ending pagination`);
          break;
        }

        // Filter by date
        const validPosts = batch.filter(p => p.created_utc && p.created_utc >= cutoffTime);
        allPosts.push(...validPosts);

        // If we found posts older than cutoff, we are done
        if (validPosts.length < batch.length) {
          this.log(`Reached cutoff time in listing.`);
          break;
        }

        // Safety check: Update cursor for next page
        const lastPost = batch[batch.length - 1];
        if (!lastPost || !lastPost.name) {
          this.log(`⚠️  Last post missing 'name' field, cannot paginate further`, "warning");
          break;
        }
        afterCursor = lastPost.name;

        // Safety break for infinite loops or huge subs
        if (allPosts.length >= 1000) {
          this.log("Hit 1000 post safety limit for listing.");
          break;
        }

        // Tiny sleep between listing pages
        await new Promise(r => setTimeout(r, 1000));

      } catch (e: any) {
        this.log(`Listing fetch failed: ${e.message}`, "error");
        break;
      }
    }

    return allPosts;
  }

  private async processThread(id: string): Promise<number> {
    const nodes = await this.api.fetchThread(id);

    // Create standard DAG structure (Initial Snapshot)
    const dag = new DAG();
    const stats = dag.merge(nodes, new Date().toISOString());

    // Save
    await this.storage.save(`threads/${id}.json`, JSON.stringify(dag.toJSON(), null, 2));
    this.processedIdsSet.add(id);

    return stats.newNodes;
  }

  private async processThreadWithRetry(id: string, subreddit: string, maxRetries: number = 3): Promise<number | null> {
    let lastError: any = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const commentCount = await this.processThread(id);
        this.log(`  ✓ Thread ${id}: ${commentCount} comments`);
        return commentCount;

      } catch (e: any) {
        lastError = e;

        if (e.message.includes("429")) {
          const waitTime = Math.min(60 * attempt, 180); // Exponential backoff, max 3 min
          this.log(`  ⏳ Hit 429 (Rate Limit) on ${id}. Sleeping ${waitTime}s... (attempt ${attempt}/${maxRetries})`, "warning");
          await new Promise(r => setTimeout(r, waitTime * 1000));
          continue; // Retry
        }

        if (attempt < maxRetries) {
          this.log(`  ⚠️  Failed to fetch thread ${id}: ${e.message}. Retrying (${attempt}/${maxRetries})...`, "warning");
          await new Promise(r => setTimeout(r, 2000 * attempt)); // 2s, 4s, 6s
        }
      }
    }

    // All retries exhausted
    this.log(`  ❌ Failed to fetch thread ${id} after ${maxRetries} attempts: ${lastError.message}`, "error");

    // Track failed post
    this.state.stats.failedPosts.push({
      postId: id,
      subreddit: subreddit,
      error: lastError.message,
      timestamp: new Date().toISOString(),
      retryCount: maxRetries
    });

    return null;
  }

  private handleSubredditError(sub: string, e: any) {
    if (e.message?.includes("404") || e.message?.includes("403")) {
      this.log(`Blacklisting r/${sub} due to access error: ${e.message}`, "warning");
      this.failedSubredditsSet.add(sub);
    } else {
      this.log(`Error listing r/${sub}: ${e.message}`, "error");
    }
  }

  private printFinalSummary(startTime: number, requestCount: number) {
    const elapsed = (Date.now() - startTime) / 1000;
    const elapsedMins = (elapsed / 60).toFixed(1);
    const avgRPS = (requestCount / elapsed).toFixed(2);
    const stats = this.state.stats;

    this.log(`\n═══════════════════════════════════════════════════════`);
    this.log(`📊 BACKFILL COMPLETE`);
    this.log(`═══════════════════════════════════════════════════════`);
    this.log(``);
    this.log(`⏱️  Duration: ${elapsedMins} minutes`);
    this.log(`📡 Total API Requests: ${requestCount}`);
    this.log(`⚡ Average RPS: ${avgRPS} (target: ${TARGET_RPS})`);
    this.log(`📈 Rate Utilization: ${((parseFloat(avgRPS) / TARGET_RPS) * 100).toFixed(1)}%`);
    this.log(``);
    this.log(`📂 Subreddits:`);
    this.log(`   ├─ Total: ${stats.totalSubreddits}`);
    this.log(`   ├─ Completed: ${stats.completedSubreddits}`);
    this.log(`   └─ Blacklisted: ${this.failedSubredditsSet.size}`);
    this.log(``);
    this.log(`📝 Posts:`);
    this.log(`   ├─ Scraped: ${stats.totalPostsScraped}`);
    this.log(`   ├─ Skipped (already existed): ${stats.totalPostsSkipped}`);
    this.log(`   └─ Failed: ${stats.failedPosts.length}`);
    this.log(``);
    this.log(`💬 Comments:`);
    this.log(`   ├─ Total: ${stats.totalCommentsScraped}`);
    const avgComments = stats.totalPostsScraped > 0
      ? (stats.totalCommentsScraped / stats.totalPostsScraped).toFixed(1)
      : '0';
    this.log(`   └─ Avg per post: ${avgComments}`);
    this.log(``);

    // Top 10 subreddits by comments
    const subsByComments = Object.entries(stats.subredditStats)
      .filter(([_, s]) => s.postsScraped > 0)
      .sort((a, b) => b[1].totalComments - a[1].totalComments)
      .slice(0, 10);

    if (subsByComments.length > 0) {
      this.log(`🏆 Top 10 Subreddits by Total Comments:`);
      subsByComments.forEach(([sub, s], i) => {
        this.log(`   ${i + 1}. r/${sub}: ${s.totalComments} comments (${s.postsScraped} posts, avg ${s.avgCommentsPerPost.toFixed(1)}/post)`);
      });
      this.log(``);
    }

    // Failed posts summary
    if (stats.failedPosts.length > 0) {
      this.log(`❌ Failed Posts (${stats.failedPosts.length}):`);
      stats.failedPosts.slice(0, 5).forEach(fp => {
        this.log(`   - ${fp.postId} in r/${fp.subreddit}: ${fp.error}`);
      });
      if (stats.failedPosts.length > 5) {
        this.log(`   ... and ${stats.failedPosts.length - 5} more (see state file)`);
      }
      this.log(``);
    }

    this.log(`💾 State saved to: ${STATE_PATH}`);
    this.log(`📋 Log saved to: ${LOG_PATH}`);
    this.log(`═══════════════════════════════════════════════════════`);
  }
}

// Run
new Backfiller().start().catch(console.error);
