import { XMLParser } from "fast-xml-parser";
import { appendFile, readFile } from "fs/promises";
import { join } from "path";

// --- Configuration ---
const CATEGORIES_FILE = join(import.meta.dir, "arxiv_categories.conf");
const OUTPUT_FILE = join(import.meta.dir, "data/metadata_archive.jsonl");
const BASE_URL = "http://export.arxiv.org/api/query";
const LOOKBACK_MONTHS = 24;
const BATCH_SIZE = 100;
const DELAY_MS = 3000; // Respect arXiv API rate limit

// --- Helper Types ---
interface ArxivEntry {
  id: string;
  updated: string;
  published: string;
  title: string;
  summary: string;
  author: any;
  category: any;
  link: any;
}

// --- Load Categories ---
async function loadCategories(): Promise<string[]> {
  const content = await readFile(CATEGORIES_FILE, "utf-8");
  const categories: string[] = [];
  for (const line of content.split("\n")) {
    if (line.trim().startsWith("category:")) {
      categories.push(line.split(":")[1].trim());
    }
  }
  return categories;
}

// --- Date Logic ---
function getCutoffDate(): Date {
  const d = new Date();
  d.setMonth(d.getMonth() - LOOKBACK_MONTHS);
  return d;
}

// --- API Client ---
const parser = new XMLParser({ ignoreAttributes: false });

async function fetchBatch(category: string, start: number): Promise<{ entries: ArxivEntry[], hasMore: boolean }> {
  // Construct Query
  const query = `search_query=cat:${category}&sortBy=submittedDate&sortOrder=descending&start=${start}&max_results=${BATCH_SIZE}`;
  const url = `${BASE_URL}?${query}`;

  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const xml = await response.text();
    
    const obj = parser.parse(xml);
    if (!obj.feed || !obj.feed.entry) return { entries: [], hasMore: false };

    // Normalize 'entry' to array (fast-xml-parser returns object for single entry)
    let entries = Array.isArray(obj.feed.entry) ? obj.feed.entry : [obj.feed.entry];
    
    return { entries, hasMore: entries.length === BATCH_SIZE };
  } catch (e) {
    console.error(`Error fetching ${url}:`, e);
    return { entries: [], hasMore: false }; // Fail safe
  }
}

// --- Main Loop ---
async function main() {
  const categories = await loadCategories();
  const cutoff = getCutoffDate();
  console.log(`📅 Fetching arXiv papers since: ${cutoff.toISOString().split('T')[0]} (${LOOKBACK_MONTHS} months)`);
  console.log(`📂 Categories: ${categories.join(", ")}`);
  console.log(`💾 Output: ${OUTPUT_FILE}`);

  let totalSaved = 0;

  for (const cat of categories) {
    console.log(`
--- Processing Category: ${cat} ---`);
    let start = 0;
    let active = true;

    while (active) {
      process.stdout.write(`Fetching start=${start}... `);
      const { entries, hasMore } = await fetchBatch(cat, start);
      
      if (entries.length === 0) {
        console.log("No entries found.");
        break;
      }

      // Filter & Format
      const validEntries = [];
      let oldestInBatch = new Date();

      for (const entry of entries) {
        const pubDate = new Date(entry.published);
        if (pubDate < oldestInBatch) oldestInBatch = pubDate;

        if (pubDate >= cutoff) {
            // Clean up metadata
            const cleanCat = Array.isArray(entry.category) 
                ? entry.category.map((c: any) => c['@_term']) 
                : [entry.category['@_term']];
            
            validEntries.push({
                id: typeof entry.id === 'string' ? entry.id.replace('http://arxiv.org/abs/', '') : entry.id,
                title: entry.title.trim().replace(/\s+/g, ' '),
                abstract: entry.summary.trim().replace(/\s+/g, ' '),
                published: entry.published,
                updated: entry.updated,
                categories: cleanCat,
                link: typeof entry.id === 'string' ? entry.id : ''
            });
        }
      }

      // Write to disk
      if (validEntries.length > 0) {
        const lines = validEntries.map(e => JSON.stringify(e)).join("\n") + "\n";
        await appendFile(OUTPUT_FILE, lines);
        totalSaved += validEntries.length;
        process.stdout.write(`Saved ${validEntries.length}. `);
      }

      // Check exit conditions
      process.stdout.write(`Oldest: ${oldestInBatch.toISOString().split('T')[0]}
`);
      
      if (oldestInBatch < cutoff) {
        console.log(`✅ Reached cutoff date for ${cat}. Moving to next category.`);
        active = false;
      } else if (!hasMore) {
        console.log(`✅ Reached end of stream for ${cat}.`);
        active = false;
      } else {
        // Next page
        start += BATCH_SIZE;
        await new Promise(resolve => setTimeout(resolve, DELAY_MS));
      }
    }
  }

  console.log(`
🎉 Complete! Total papers saved: ${totalSaved}`);
}

main();
