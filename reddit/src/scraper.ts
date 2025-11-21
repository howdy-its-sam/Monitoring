import { RedditAPI } from "./api";
import { DAG } from "./dag";
import { Discovery } from "./discovery";
import { RateLimiter } from "./rate_limiter";
import { Telemetry } from "./telemetry";
import { StorageDriver } from "./storage";

interface ThreadConfig {
  id: string;
  interval: number; // seconds
  nextRun: number;  // timestamp
  lastScrape: number; // timestamp
}

export class Scraper {
  private api: RedditAPI;
  private discovery: Discovery;
  private rateLimiter: RateLimiter;
  private telemetry: Telemetry;
  private storage: StorageDriver;
  private threads: Map<string, DAG>; // In-memory state
  private schedule: Map<string, ThreadConfig>;
  private subreddits: string[] = [];
  private isRunning: boolean = false;
  private lastDiscoveryTime: number = 0;

  constructor(subreddits: string[] = []) {
    this.api = new RedditAPI();
    this.discovery = new Discovery();
    this.rateLimiter = new RateLimiter(60, 1); // Conservative: 1 RPS (60/min)
    this.telemetry = new Telemetry();
    this.storage = new StorageDriver();
    this.threads = new Map();
    this.schedule = new Map();
    this.subreddits = subreddits;
  }

  public addThread(id: string, initialInterval = 60) {
    if (!this.schedule.has(id)) {
      this.schedule.set(id, {
        id,
        interval: initialInterval,
        nextRun: Date.now(),
        lastScrape: 0
      });
      // Try to load existing state
      this.loadState(id);
    }
  }

  public async start() {
    this.isRunning = true;
    console.log("🚀 TypeScript Scraper Started");

    while (this.isRunning) {
      const now = Date.now();
      
      // 0. Discovery Tick (Every 5 minutes)
      if (now - this.lastDiscoveryTime > 300000) {
          await this.runDiscovery();
          this.lastDiscoveryTime = now;
      }

      // 1. Find due threads
      let nextTask: ThreadConfig | null = null;
      
      for (const config of this.schedule.values()) {
        if (config.nextRun <= now) {
          nextTask = config;
          break; 
        }
      }

      if (nextTask) {
        await this.processThread(nextTask);
      } else {
        // Nothing to do, sleep briefly
        await new Promise(r => setTimeout(r, 1000));
      }
    }
    
    console.log("🛑 Scraper loop stopped.");
  }

  private async runDiscovery() {
      // Discovery also costs tokens!
      for (const sub of this.subreddits) {
          await this.rateLimiter.wait(1);
          const newIds = await this.discovery.scanSubreddit(sub);
          for (const id of newIds) {
              this.addThread(id);
          }
      }
  }

  private async processThread(config: ThreadConfig) {
    // Rate Limit Check
    await this.rateLimiter.wait(1);

    console.log(`🎯 Scraping ${config.id}...`);
    const start = Date.now();
    
    try {
      // 1. Fetch
      const nodes = await this.api.fetchThread(config.id);
      
      // 2. Get or Create DAG
      let dag = this.threads.get(config.id);
      if (!dag) {
        dag = new DAG();
        this.threads.set(config.id, dag);
      }

      // 3. Merge (Capture Stats)
      const stats = dag.merge(nodes, new Date().toISOString());
      
      // 4. Log Telemetry
      this.telemetry.log({
          timestamp: new Date().toISOString(),
          threadId: config.id,
          timeSinceLastScrape: config.lastScrape ? (start - config.lastScrape) / 1000 : 0,
          newNodes: stats.newNodes,
          updatedNodes: stats.updatedNodes,
          scoreDelta: stats.scoreDelta,
          textDeltaChars: stats.textDeltaChars,
          newAtDepth0: stats.newAtDepth0,
          newAtDepth1: stats.newAtDepth1,
          newAtDepth2Plus: stats.newAtDepth2Plus,
          tokensUsed: 1,
          durationMs: Date.now() - start
      });

      // 5. Save Checkpoint
      await this.saveState(config.id);

      // 6. Update Schedule (Adaptive Backoff)
      // Logic: Hot -> Faster, Cold -> Slower
      let newInterval = config.interval;

      if (stats.newNodes > 0) {
          // HOT: Found new content. Speed up!
          // Decay back down to 60s
          newInterval = Math.max(60, Math.floor(newInterval / 2));
      } else if (stats.scoreDelta > 0 || stats.updatedNodes > 0) {
          // WARM: Score changing, but no new comments. Maintain pace.
          // Maybe slight backoff if it was super fast
          if (newInterval < 300) newInterval = 300; // Floor at 5m for score-only updates
      } else {
          // COLD: No changes at all. Backoff exponentially.
          newInterval = Math.min(21600, newInterval * 2); // Cap at 6 hours
      }

      config.interval = newInterval;
      config.lastScrape = start;
      config.nextRun = Date.now() + (config.interval * 1000);
      
      console.log(`   ✅ Merged ${nodes.length} nodes (+${stats.newNodes} new). Interval: ${config.interval}s -> ${newInterval}s`);

    } catch (e) {
      console.error(`   ❌ Error: ${e}`);
      // Backoff on error
      config.nextRun = Date.now() + 60000; 
    }
  }

  private async saveState(id: string) {
    const dag = this.threads.get(id);
    if (!dag) return;
    await this.storage.save(`merged_${id}.json`, JSON.stringify(dag.toJSON(), null, 2));
  }

  private async loadState(id: string) {
    const raw = await this.storage.load(`merged_${id}.json`);
    if (raw) {
      const json = JSON.parse(raw);
      const dag = new DAG(json); // Hydrate
      this.threads.set(id, dag);
      console.log(`   📄 Loaded state for ${id}`);
    }
  }

  public async shutdown() {
    console.log("\n⚠️  Shutting down... Saving all state.");
    this.isRunning = false;
    
    let count = 0;
    for (const id of this.threads.keys()) {
        await this.saveState(id);
        count++;
    }
    console.log(`✅ Saved ${count} threads. Bye.`);
  }
}