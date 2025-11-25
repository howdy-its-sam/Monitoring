import { RedditAPI } from "./api";
import { StorageDriver } from "./storage";
import { DAG } from "./dag";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

// --- Configuration ---
const RATE_LIMIT_BUFFER = 0.05; // Leave 5% of capacity unused
const TARGET_RPS = 0.9; // Conservative start (approx 1 request/sec)
const LOOKBACK_HOURS = 72; // How far back to sweep

// --- Types ---
interface BackfillState {
  processedIds: Set<string>;
  failedSubreddits: Set<string>; // 403/404 blacklist
}

// --- Helpers ---
function loadPriorities(): string[] {
  const path = join(process.cwd(), "reddit/reddit-adaptive-sampler/subreddit_priorities.txt");
  if (!existsSync(path)) return ["LocalLLaMA"];
  return readFileSync(path, "utf-8")
    .split("\n")
    .map(l => l.trim().replace(/^r\//, ""))
    .filter(l => l && !l.startsWith("#"));
}

class Backfiller {
  private api: RedditAPI;
  private storage: StorageDriver;
  private state: BackfillState = {
    processedIds: new Set(),
    failedSubreddits: new Set()
  };
  private subreddits: string[];

  constructor() {
    this.api = new RedditAPI();
    this.storage = new StorageDriver();
    this.subreddits = loadPriorities();
  }

  private log(msg: string, type: "info" | "success" | "warning" | "error" = "info") {
     const ts = new Date().toISOString();
     const prefix = `[${ts}] [BACKFILL]`;
     if (type === "error") console.error(`${prefix} ❌ ${msg}`);
     else if (type === "warning") console.warn(`${prefix} ⚠️ ${msg}`);
     else if (type === "success") console.log(`${prefix} ✅ ${msg}`);
     else console.log(`${prefix} ${msg}`);
  }

  public async start() {
    this.log(`Starting backfill for ${this.subreddits.length} subreddits.`);
    this.log(`Lookback Window: ${LOOKBACK_HOURS} hours.`);
    
    const cutoffTime = Date.now() - (LOOKBACK_HOURS * 3600 * 1000);

    for (const sub of this.subreddits) {
      if (this.state.failedSubreddits.has(sub)) {
        this.log(`Skipping blacklisted sub: r/${sub}`, "warning");
        continue;
      }

      this.log(`Scanning r/${sub}...`);
      
      try {
        // 1. Fetch Listing (Top + New to get coverage)
        // We'll try 'new' first as it's most consistent for timeline
        // In a real robust backfill, we might paging through listing.
        // For MVP, we'll fetch 100 items.
        const listing = await this.fetchListingWithBackoff(sub, "new", 100);
        
        let added = 0;
        let skipped = 0;

        for (const post of listing) {
            // Stop if we hit posts older than cutoff (approximate check)
            // Note: Listing usually has 'created_utc' but our minimal type might need checking
            // For now we assume the fetch returns them sorted.
            
            if (this.state.processedIds.has(post.id)) {
                skipped++;
                continue;
            }

            // Check if we already have it on disk (from Live Scraper)
            const exists = await this.storage.load(`threads/${post.id}.json`);
            if (exists) {
                this.state.processedIds.add(post.id);
                skipped++;
                continue;
            }

            // 2. Fetch Thread Details
            await this.processThread(post.id);
            added++;
            
            // Rate Limit Sleep
            // Simple linear spacing
            await new Promise(r => setTimeout(r, 1000 / TARGET_RPS));
        }
        
        this.log(`r/${sub}: +${added} scraped, ${skipped} skipped.`);

      } catch (e: any) {
          this.handleSubredditError(sub, e);
      }
    }
    
    this.log("Backfill Complete.");
  }

  private async fetchListingWithBackoff(sub: string, sort: string, batchSize: number): Promise<any[]> {
      let allPosts: any[] = [];
      let afterCursor: string | undefined = undefined;
      const cutoffTime = Date.now() / 1000 - (LOOKBACK_HOURS * 3600); // Reddit uses seconds

      this.log(`Fetching listing for r/${sub} (until ${new Date(cutoffTime * 1000).toISOString()})...`);

      while (true) {
          try {
              const batch = await this.api.getListing(sub, sort, batchSize, afterCursor);
              
              if (batch.length === 0) break;

              // Filter by date
              const validPosts = batch.filter(p => p.created_utc >= cutoffTime);
              allPosts.push(...validPosts);
              
              // If we found posts older than cutoff, we are done
              if (validPosts.length < batch.length) {
                  this.log(`Reached cutoff time in listing.`);
                  break; 
              }
              
              // Update cursor for next page
              afterCursor = batch[batch.length - 1].name;
              
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

  private async processThread(id: string) {
    try {
        const nodes = await this.api.fetchThread(id);
        
        // Create standard DAG structure (Initial Snapshot)
        const dag = new DAG();
        const stats = dag.merge(nodes, new Date().toISOString());
        
        // Save
        await this.storage.save(`threads/${id}.json`, JSON.stringify(dag.toJSON(), null, 2));
        this.state.processedIds.add(id);
        this.log(`Saved thread ${id} (${stats.newNodes} comments)`, "success");

    } catch (e: any) {
        if (e.message.includes("429")) {
            this.log("Hit 429 (Rate Limit). Sleeping 30s...", "warning");
            await new Promise(r => setTimeout(r, 30000));
            // Retry once? Or skip.
        } else {
            this.log(`Failed to fetch thread ${id}: ${e.message}`, "error");
        }
    }
  }

  private handleSubredditError(sub: string, e: any) {
    if (e.message?.includes("404") || e.message?.includes("403")) {
        this.log(`Blacklisting r/${sub} due to access error: ${e.message}`, "warning");
        this.state.failedSubreddits.add(sub);
    } else {
        this.log(`Error listing r/${sub}: ${e.message}`, "error");
    }
  }
}

// Run
new Backfiller().start().catch(console.error);
