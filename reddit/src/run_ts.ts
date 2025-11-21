import { Scraper } from "./scraper";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

function loadSubreddits(): string[] {
  // Try multiple paths to be robust
  const paths = [
      join(process.cwd(), "reddit/reddit-adaptive-sampler/subreddit_priorities.txt"), // From root
      join(process.cwd(), "reddit-adaptive-sampler/subreddit_priorities.txt")         // From reddit/
  ];

  for (const p of paths) {
      if (existsSync(p)) {
          console.log(`Loading priorities from: ${p}`);
          return readFileSync(p, "utf-8")
            .split("\n")
            .map(line => line.trim())
            .filter(line => line && !line.startsWith("#"))
            .map(line => line.replace(/^r\//, ""));
      }
  }
  
  console.warn("⚠️ Priority list not found in expected locations, using defaults.");
  return ["LocalLLaMA", "OpenAI"];
}

const SUBS = loadSubreddits();
console.log(`Loaded ${SUBS.length} subreddits from priority list.`);

async function main() {
  const scraper = new Scraper(SUBS);
  
  // Add a known seed thread to start immediately
  scraper.addThread("1p1kpmu"); 

  // Handle Graceful Shutdown
  const handleExit = () => {
      scraper.shutdown();
      process.exit(0);
  };

  process.on("SIGINT", handleExit);
  process.on("SIGTERM", handleExit);

  await scraper.start();
}

main();
