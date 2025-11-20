import { readFileSync } from "fs";
import { join } from "path";
import { RedditAPI } from "./api";
import { toLegacyFormat } from "./legacy_mapper";

// The file we just captured
const FIXTURE_PATH = join(process.cwd(), "reddit/raw_dumps/raw_1p1kpmu_20251119_210138.json");

async function main() {
  console.log(`Loading fixture: ${FIXTURE_PATH}`);
  const raw = readFileSync(FIXTURE_PATH, "utf-8");
  const json = JSON.parse(raw);

  const api = new RedditAPI();
  
  console.log("Parsing with TypeScript API...");
  const nodes = api.parseResponse(json);
  
  console.log(`Parsed ${nodes.length} nodes.`);
  
  // Verification 1: Check if Extra Bag is working
  const firstComment = nodes.find(n => n.parentId !== null);
  if (firstComment) {
    console.log("\n--- Node Inspection ---");
    console.log("ID:", firstComment.id);
    console.log("Extra Bag Keys:", Object.keys(firstComment.extra));
    console.log("Controversiality (from bag):", firstComment.extra.controversiality);
    console.log("Is Submitter (from bag):", firstComment.extra.is_submitter);
  }

  // Verification 2: Legacy Format Parity
  console.log("\n--- Legacy Format Check ---");
  if (firstComment) {
      const legacy = toLegacyFormat(firstComment);
      console.log("Legacy Output:", legacy);
  }
}

main();
