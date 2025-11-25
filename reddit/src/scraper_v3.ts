import { AdaptiveScheduler } from "./scheduler/adaptive";
import { DAG } from "./dag";
import { existsSync, readFileSync } from "fs";
import { join } from "path";

// Load priorities
function loadSubreddits(): string[] {
  const path = join(process.cwd(), "reddit/reddit-adaptive-sampler/subreddit_priorities.txt");
  if (!existsSync(path)) return ["LocalLLaMA"]; // Fallback
  return readFileSync(path, "utf-8")
    .split("\n")
    .map(l => l.trim().replace(/^r\//, ""))
    .filter(l => l && !l.startsWith("#"));
}

export class ScraperV3 {
  private scheduler: AdaptiveScheduler;
  private isRunning = false;
  private threads: Map<string, DAG> = new Map();

  // Rate Limiting State
  private apiCallsInTick = 0;
  private lastTickTime = Date.now();

  constructor() {
    this.scheduler = new AdaptiveScheduler();
    
    // Load priorities
    const subs = loadSubreddits();
    this.scheduler.allocator.loadPriorities(subs);
  }

  private log(msg: string, type: "info" | "success" | "warning" | "error" | "debug" = "info") {
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}]`;
    switch (type) {
      case "success":
        console.log(`${prefix} ✅ ${msg}`);
        break;
      case "warning":
        console.log(`${prefix} ⚠️ ${msg}`);
        break;
      case "error":
        console.error(`${prefix} ❌ ${msg}`);
        break;
      case "debug":
        if (this.scheduler.controller.g > 0) console.log(`${prefix} 🐛 ${msg}`); // Placeholder for debug flag
        break;
      default:
        console.log(`${prefix} ${msg}`);
    }
  }

  public async start() {
    this.log("🚀 Scraper V3 (Adaptive) Started", "info");
    this.isRunning = true;
    this.lastTickTime = Date.now(); // Initialize
    
    // Initial sleep to let the discovery poller run a bit
    await new Promise(r => setTimeout(r, 5000)); 

    while (this.isRunning) {
      const now = Date.now();
      const dt = (now - this.lastTickTime) / 1000.0; // Convert to seconds
      this.lastTickTime = now;
      this.apiCallsInTick = 0; // Reset for this tick

      // 1. Discovery (Poller)
      // The poller itself makes API calls, but its rate is generally much lower than fetching comments.
      // For now, we'll primarily control the comment fetching rate.
      const newPosts = await this.scheduler.poller.poll(now);
      for (const p of newPosts) {
          this.scheduler.registerPost(p.id, p.subreddit);
      }
      if (newPosts.length > 0) this.log(`🔍 Discovered ${newPosts.length} new posts.`, "info");

      // 2. Scheduler Tick
      this.scheduler.tick(now);
      
      // Determine batch size dynamically based on rate controller gain
      // Ensure batch size is at least 1.
      const dynamicBatchSize = Math.max(1, Math.round(5 * this.scheduler.controller.g));
      const batch = this.scheduler.getNextBatch(dynamicBatchSize, now);

      if (batch.length === 0) {
          // If no posts to process, sleep a bit before the next tick.
          // Adjust sleep based on gain to potentially recover faster if rate limit was hit.
          await new Promise(r => setTimeout(r, 1000 * (2.0 - this.scheduler.controller.g))); 
          continue;
      }

      // 3. Scrape Batch
      this.log(`⚡ Processing batch of ${batch.length} threads...`, "info");
      for (const id of batch) {
          await this.processPost(id);
      }
      
      // 4. Rate Control Feedback
      // This is the core update to the rate controller
      const measured_rps = dt > 0 ? this.apiCallsInTick / dt : 0;
      this.scheduler.controller.update(measured_rps, dt);
      this.log(`Measured RPS: ${measured_rps.toFixed(2)}, Controller Gain (g): ${this.scheduler.controller.g.toFixed(2)}`, "info");

      // Add a small delay to avoid hammering the API too hard immediately after processing a batch
      // The gain 'g' will already adjust the next batch size, but a minimum sleep is good.
      await new Promise(r => setTimeout(r, 200)); 
    }
  }

  private async processPost(id: string) {
      try {
          const nodes = await this.scheduler.api.fetchThread(id);
          this.apiCallsInTick++; // Increment API call count

          // Update DAG
          let dag = this.threads.get(id);
          if (!dag) { dag = new DAG(); this.threads.set(id, dag); }
          
          const stats = dag.merge(nodes, new Date().toISOString());
          
          if (stats.newNodes > 0 || stats.scoreDelta > 0) {
             this.log(`${id}: +${stats.newNodes} comments, ΔScore=${stats.scoreDelta}`, "success");
          }
          
          // Record Delta for Scheduler
          this.scheduler.recordScrape(id, {
              ts: Date.now(),
              new_comments: stats.newNodes,
              edited_comments: stats.updatedNodes,
              score_changed: stats.scoreDelta,
              deleted_comments: 0 // TODO: DAG doesn't count dels yet
          });
          
          // Save
          await this.scheduler.storage.save(`threads/${id}.json`, JSON.stringify(dag.toJSON(), null, 2));

      } catch (e: any) {
          if (e.message?.includes("403")) {
              this.log(`${id}: Private/Forbidden (403)`, "warning");
              // TODO: Mark as retired/dead so we don't retry
          } else if (e.message?.includes("404")) {
              this.log(`${id}: Not Found (404)`, "warning");
          } else if (e.message?.includes("429")) {
              this.log(`${id}: Reddit API Rate Limit (429) - Signaling controller to slow down.`, "warning");
              // Signal controller aggressively for rate limit.
              // Note: This 0.1 is a "measured_rps" for *this single API call* if it fails.
              // The controller will average it out.
              this.scheduler.controller.update(0.1, 1.0); 
              // Add a longer backoff after 429
              await new Promise(r => setTimeout(r, 5000));
          } else {
              this.log(`${id}: ${e.message}`, "error");
          }
      }
  }
}
