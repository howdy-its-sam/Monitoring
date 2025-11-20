import { Buffer } from "node:buffer";
import { mkdir } from "node:fs/promises";
import { exit } from "node:process";

import { XMLParser } from "fast-xml-parser";

const DEFAULT_CREDENTIAL_TARGET =
  Bun.env.ARXIV_CREDENTIALS_PATH ?? new URL("../arxiv_credentials.env", import.meta.url);
const CATEGORIES_CONFIG_FILE =
  Bun.env.ARXIV_CATEGORIES_CONFIG ?? new URL("../arxiv_categories.conf", import.meta.url);
const DATA_DIRECTORY = Bun.env.ARXIV_DATA_DIR ?? "data";
const STATE_FILE = `${DATA_DIRECTORY}/state.json`;
const MAX_RESULTS = clampMaxResults(
  Number.parseInt(Bun.env.ARXIV_MAX_RESULTS ?? "100", 10) || 100
);
const DOWNLOAD_TARBALLS = parseBooleanEnv(Bun.env.ARXIV_DOWNLOAD_TARBALLS ?? "true");
const DOWNLOAD_SAMPLE_TARBALLS = parseBooleanEnv(
  Bun.env.ARXIV_DOWNLOAD_SAMPLE_TARBALLS ?? "false"
);
const SAMPLE_TARBALL_CATEGORY = Bun.env.ARXIV_SAMPLE_TARBALL_CATEGORY ?? "cs.AI";
const SAMPLE_TARBALL_COUNT = clampSampleCount(
  Number.parseInt(Bun.env.ARXIV_SAMPLE_TARBALL_COUNT ?? "10", 10) || 10
);
const MAX_PAGES = clampPageCount(Number.parseInt(Bun.env.ARXIV_MAX_PAGES ?? "5", 10) || 5);
const TAR_OUTPUT_DIRECTORY = `${DATA_DIRECTORY}/tarballs`;
const TAR_SAMPLE_DIRECTORY = `${TAR_OUTPUT_DIRECTORY}/sample`;
const DEBUG = parseBooleanEnv(Bun.env.ARXIV_DEBUG ?? "false");
const LOOKBACK_DAYS = clampLookbackDays(
  Number.parseInt(Bun.env.ARXIV_LOOKBACK_DAYS ?? "7", 10) || 7
);
const LOOKBACK_PADDING_DAYS = clampLookbackDays(
  Number.parseInt(Bun.env.ARXIV_LOOKBACK_PADDING_DAYS ?? "2", 10) || 2
);
const LOOKAHEAD_MINUTES = clampLookaheadMinutes(
  Number.parseInt(Bun.env.ARXIV_LOOKAHEAD_MINUTES ?? "120", 10) || 120
);
const MS_PER_MINUTE = 60_000;
const MS_PER_DAY = 24 * 60 * MS_PER_MINUTE;
const MAX_PENDING_AGE_DAYS = 30;
const HISTORICAL_MAX_BATCHES = clampHistoricalMaxBatches(
  Number.parseInt(Bun.env.ARXIV_HISTORICAL_MAX_BATCHES ?? "1000", 10) || 1000
);
const MAX_RETRIES = 5;
const INITIAL_RETRY_DELAY_MS = 30000; // Start with 30 seconds
const MAX_RETRY_DELAY_MS = 240000; // Cap at 240 seconds (4 minutes)
const TARBALL_CHECKPOINT_INTERVAL = 50; // Save state every N tarballs downloaded (~4 minutes)

type ArxivCredentials = {
  userAgent: string;
  contactEmail: string;
  defaultCategories: string[];
  minRequestIntervalMs: number;
};

type CategoryState = {
  lastPublished?: string;
  lastId?: string;
  lastIdentifier?: string;
  lastBaseIdentifier?: string;
  downloadedEntries?: Record<
    string,
    {
      updated?: string;
      tarballPath: string;
    }
  >;
  pendingTarballs?: Record<
    string,
    {
      updated?: string;
      firstFailedAt?: string;
    }
  >;
  confirmedRanges?: Array<{
    startDate: string; // YYYY-MM-DD
    endDate: string; // YYYY-MM-DD
    completedAt: string; // ISO timestamp
    paperCount: number;
  }>;
  inProgressBackfill?: {
    startDate: string; // YYYY-MM-DD
    endDate: string; // YYYY-MM-DD
    fetchedCount: number; // Papers fetched so far
    fetchedIds: string[]; // IDs of papers already fetched
    lastBatchOffset: number; // Last successful batch offset
  };
};

type StateFile = Record<string, CategoryState>;

type CategoryConfig = {
  category: string;
  startDate: string; // YYYY-MM-DD format
};

type ArxivEntry = {
  id: string;
  title: string;
  summary?: string;
  published: string;
  updated?: string;
  authors: string[];
  categories: string[];
  primaryCategory?: string | null;
  links: Array<{ rel: string | null; href: string; type: string | null }>;
  comment?: string; // arXiv comment field, often contains withdrawal notices
};

type FetchResult = {
  category: string;
  newEntries: ArxivEntry[];
  totalFetched: number;
  snapshotPath?: string;
  tarballsDownloaded: number;
};

class RateLimiter {
  private nextAvailableAt = 0;

  constructor(private readonly intervalMs: number) {}

  async waitForTurn(): Promise<void> {
    const now = Date.now();
    if (now < this.nextAvailableAt) {
      await delay(this.nextAvailableAt - now);
    }
    this.nextAvailableAt = Date.now() + this.intervalMs;
  }
}

export async function loadArxivCredentials(
  target: string | URL = DEFAULT_CREDENTIAL_TARGET
): Promise<ArxivCredentials> {
  const file = Bun.file(target);

  if (!(await file.exists())) {
    throw new Error(
      `arXiv credentials file not found. Set ARXIV_CREDENTIALS_PATH or create arxiv_credentials.env.`
    );
  }

  const contents = await file.text();
  const entries = parseEnv(contents);

  const userAgent = entries.get("ARXIV_USER_AGENT");
  const contactEmail = entries.get("ARXIV_CONTACT_EMAIL");
  const categoriesRaw = entries.get("ARXIV_DEFAULT_CATEGORIES") ?? "";
  const defaultCategories = categoriesRaw
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const intervalRaw = entries.get("ARXIV_MIN_REQUEST_INTERVAL_MS");
  const minRequestIntervalMs = intervalRaw ? Number.parseInt(intervalRaw, 10) : Number.NaN;

  if (!userAgent || !contactEmail) {
    throw new Error(
      `arXiv credentials file is missing ARXIV_USER_AGENT or ARXIV_CONTACT_EMAIL. Both are required by the API.`
    );
  }

  return {
    userAgent,
    contactEmail,
    defaultCategories,
    minRequestIntervalMs: Number.isNaN(minRequestIntervalMs) ? 5000 : minRequestIntervalMs,
  };
}

async function main() {
  try {
    const credentials = await loadArxivCredentials();
    console.log(`[${new Date().toISOString()}] Starting arXiv ingestion.`);

    if (DOWNLOAD_SAMPLE_TARBALLS) {
      await downloadSampleTarballs(credentials);
      return;
    }

    // Historical backfill mode
    const historicalCategory = Bun.env.ARXIV_HISTORICAL_CATEGORY;
    const historicalMonths = Number.parseInt(
      Bun.env.ARXIV_HISTORICAL_MONTHS ?? "6",
      10
    );

    if (historicalCategory) {
      await mkdir(DATA_DIRECTORY, { recursive: true });
      const state = await loadState(STATE_FILE);
      normalizeState(state);
      const rateLimiter = new RateLimiter(credentials.minRequestIntervalMs);

      // Calculate date range from months
      const now = Date.now();
      const monthsInMs = historicalMonths * 30 * MS_PER_DAY;
      const startDate = new Date(now - monthsInMs).toISOString().split("T")[0];
      const endDate = new Date(now).toISOString().split("T")[0];

      const result = await getHistorical(
        historicalCategory,
        startDate,
        endDate,
        credentials,
        state,
        rateLimiter
      );

      await saveState(STATE_FILE, state);

      console.log(
        `Historical backfill complete for ${historicalCategory}: ${result.totalFetched} papers found, ${result.tarballsDownloaded} new tarballs downloaded.`
      );
      return;
    }

    // Load categories from config file
    const categoryConfigs = await loadCategoriesConfig(CATEGORIES_CONFIG_FILE);
    const categories = categoryConfigs.length > 0
      ? categoryConfigs.map((c) => c.category)
      : credentials.defaultCategories.length
        ? credentials.defaultCategories
        : ["cs.AI", "cs.LG", "cs.CV", "cs.CL", "stat.ML"];

    await mkdir(DATA_DIRECTORY, { recursive: true });
    const state = await loadState(STATE_FILE);
    normalizeState(state);
    const rateLimiter = new RateLimiter(credentials.minRequestIntervalMs);

    // Check for categories that need historical backfill
    if (categoryConfigs.length > 0) {
      console.log("[Config] Checking for categories that need historical backfill...");

      for (const config of categoryConfigs) {
        const categoryState = state[config.category];
        const earliestDownloaded = findEarliestDownloadedDate(categoryState);
        const now = new Date().toISOString().split("T")[0];

        // Determine if we need to backfill
        let needsBackfill = false;
        let startDate = config.startDate;
        let endDate = now;

        if (!categoryState || !earliestDownloaded) {
          // New category - backfill from start date to now
          needsBackfill = true;
          console.log(
            `[Config] New category ${config.category} detected - will backfill from ${startDate} to ${endDate}`
          );
        } else if (new Date(config.startDate) < new Date(earliestDownloaded)) {
          // Start date is earlier than earliest downloaded - extend backfill
          needsBackfill = true;
          endDate = earliestDownloaded; // Only fetch the gap
          console.log(
            `[Config] Extended date range for ${config.category} - will backfill from ${startDate} to ${endDate}`
          );
        } else {
          // Config start date is same or later than earliest downloaded
          // This means user may have narrowed the range - no backfill needed
          console.log(
            `[Config] ${config.category}: Start date ${config.startDate} is after earliest downloaded ${earliestDownloaded}, no backfill needed`
          );
        }

        if (needsBackfill) {
          const result = await getHistorical(
            config.category,
            startDate,
            endDate,
            credentials,
            state,
            rateLimiter
          );
          console.log(
            `[Config] Historical backfill for ${config.category}: ${result.totalFetched} papers found, ${result.tarballsDownloaded} new tarballs downloaded.`
          );
          await saveState(STATE_FILE, state);
        }
      }

      console.log("[Config] Historical backfill check complete.");
    }
    const results: FetchResult[] = [];

    console.log(
      `Fetching arXiv categories: ${categories.join(", ")} (max ${MAX_RESULTS} entries each, interval ${credentials.minRequestIntervalMs} ms)`
    );

    for (const category of categories) {
      try {
        const result = await fetchAndPersistCategory(
          category,
          credentials,
          state,
          rateLimiter
        );
        results.push(result);

        if (result.newEntries.length > 0) {
          console.log(
            `Fetched ${result.newEntries.length} new entries for ${category} -> ${result.snapshotPath}`
          );
        } else {
          console.log(`No new entries for ${category}.`);
        }

        if (result.tarballsDownloaded > 0) {
          console.log(
            `Downloaded ${result.tarballsDownloaded} source tarball(s) for ${category}.`
          );
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error(`Failed to fetch ${category}: ${message}`);
      }
    }

    await saveState(STATE_FILE, state);

    const totalNew = results.reduce((acc, item) => acc + item.newEntries.length, 0);
    const totalTarballs = results.reduce(
      (acc, item) => acc + item.tarballsDownloaded,
      0
    );
    console.log(`Done. Total new entries across categories: ${totalNew}.`);
    if (DOWNLOAD_TARBALLS) {
      console.log(`Total tarballs downloaded: ${totalTarballs}.`);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(message);
    exit(1);
  }
}

async function downloadSampleTarballs(credentials: ArxivCredentials): Promise<void> {
  const category = SAMPLE_TARBALL_CATEGORY;
  console.log(
    `Downloading sample tarballs for category ${category} (count ${SAMPLE_TARBALL_COUNT})`
  );

  await mkdir(TAR_SAMPLE_DIRECTORY, { recursive: true });

  const rateLimiter = new RateLimiter(credentials.minRequestIntervalMs);
  await rateLimiter.waitForTurn();
  const search = buildSearchQuery(category, undefined);
  const entries = await fetchCategoryFeed(category, search.query, credentials, {
    maxResults: SAMPLE_TARBALL_COUNT,
    start: 0,
  });

  if (!entries.length) {
    console.log("No entries returned for sample download.");
    return;
  }

  let downloaded = 0;

  for (const entry of entries) {
    if (downloaded >= SAMPLE_TARBALL_COUNT) {
      break;
    }

    const tarballLink = resolveTarballLink(entry);
    if (!tarballLink) {
      continue;
    }

    await rateLimiter.waitForTurn();

    try {
      const tarballPath = await downloadTarball(category, entry, tarballLink, {
        directory: TAR_SAMPLE_DIRECTORY,
      });
      console.log(`Downloaded sample tarball -> ${tarballPath}`);
      downloaded += 1;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error(`Failed to download sample tarball for ${entry.id}: ${message}`);
    }
  }

  console.log(`Sample tarball download finished. Total downloaded: ${downloaded}.`);
}

async function fetchAndPersistCategory(
  category: string,
  credentials: ArxivCredentials,
  state: StateFile,
  rateLimiter: RateLimiter
): Promise<FetchResult> {
  const previousState = state[category] ?? {};
  const newEntries = await gatherCategoryEntries(
    category,
    credentials,
    previousState,
    rateLimiter
  );

  let snapshotPath: string | undefined;

  if (newEntries.length > 0) {
    // Sort by most recent timestamp (updated or published)
    const sorted = [...newEntries].sort((a, b) => {
      const aTime = parseTimestamp(a.updated ?? a.published) ?? 0;
      const bTime = parseTimestamp(b.updated ?? b.published) ?? 0;
      return aTime - bTime;
    });
    const newest = sorted[sorted.length - 1];
    const newestIdentifier = extractIdentifier(newest);
    const newestBaseIdentifier = extractBaseIdentifier(newestIdentifier);
    const newestTimestamp = newest.updated ?? newest.published;

    state[category] = {
      lastPublished: newestTimestamp,
      lastId: newest.id,
      lastIdentifier: newestIdentifier ?? previousState.lastIdentifier,
      lastBaseIdentifier: newestBaseIdentifier ?? previousState.lastBaseIdentifier,
      downloadedEntries: previousState.downloadedEntries ?? {},
      pendingTarballs: previousState.pendingTarballs ?? {},
    };

    snapshotPath = await persistSnapshot(
      category,
      newEntries,
      newEntries.length,
      MAX_RESULTS
    );
  } else {
    state[category] = {
      lastPublished: previousState.lastPublished,
      lastId: previousState.lastId,
      lastIdentifier: previousState.lastIdentifier,
      lastBaseIdentifier: previousState.lastBaseIdentifier,
      downloadedEntries: previousState.downloadedEntries ?? {},
      pendingTarballs: previousState.pendingTarballs ?? {},
    };
  }

  const tarballsDownloaded = DOWNLOAD_TARBALLS
    ? await downloadTarballsForEntries(
        category,
        newEntries,
        previousState,
        state,
        credentials,
        rateLimiter
      )
    : 0;

  return {
    category,
    newEntries,
    totalFetched: newEntries.length,
    snapshotPath,
    tarballsDownloaded,
  };
}

async function gatherCategoryEntries(
  category: string,
  credentials: ArxivCredentials,
  categoryState: CategoryState,
  rateLimiter: RateLimiter
): Promise<ArxivEntry[]> {
  const newEntries: ArxivEntry[] = [];
  const seen = new Set<string>();
  let start = 0;
  const search = buildSearchQuery(category, categoryState);

  if (DEBUG) {
    console.log(
      `[${category}] query window ${search.lowerBound} -> ${search.upperBound}`
    );
  }

  for (let page = 0; page < MAX_PAGES; page += 1) {
    await rateLimiter.waitForTurn();
    const batch = await fetchCategoryFeed(category, search.query, credentials, {
      start,
      maxResults: MAX_RESULTS,
    });

    if (!batch.length) {
      if (DEBUG) {
        console.log(`[${category}] No entries returned at start=${start}.`);
      }
      break;
    }

    if (DEBUG) {
      const top = batch[0];
      console.log(
        `[${category}] Page ${page + 1} start=${start} first=${extractIdentifier(top)} published=${top.published}`
      );
    }

    for (const entry of batch) {
      if (seen.has(entry.id)) {
        continue;
      }

      const decision = evaluateEntryFreshness(entry, categoryState);

      if (decision.isNew) {
        newEntries.push(entry);
        seen.add(entry.id);
        if (DEBUG) {
          console.log(
            `[${category}] new entry ${extractIdentifier(entry)} published=${entry.published}`
          );
        }
      }

      if (decision.stop) {
        if (DEBUG) {
          console.log(
            `[${category}] stop encountered at ${extractIdentifier(entry)} (seen before).`
          );
        }
        return newEntries;
      }
    }

    if (batch.length < MAX_RESULTS) {
      if (DEBUG) {
        console.log(
          `[${category}] Reached final batch (size ${batch.length}) before hitting MAX_PAGES.`
        );
      }
      break;
    }

    start += batch.length;
  }

  return newEntries;
}

type SearchQuery = {
  query: string;
  lowerBound: string;
  upperBound: string;
};

function buildSearchQuery(category: string, categoryState: CategoryState | undefined): SearchQuery {
  const now = Date.now();
  const upperDate = new Date(now + LOOKAHEAD_MINUTES * MS_PER_MINUTE);

  const fallbackLower = new Date(now - LOOKBACK_DAYS * MS_PER_DAY);
  const lastPublishedMs = parseTimestamp(categoryState?.lastPublished);
  let lowerDate = fallbackLower;

  if (lastPublishedMs !== null) {
    const padded = new Date(lastPublishedMs - LOOKBACK_PADDING_DAYS * MS_PER_DAY);
    if (padded > lowerDate) {
      lowerDate = padded;
    }
  }

  if (lowerDate > upperDate) {
    lowerDate = new Date(upperDate.getTime() - LOOKBACK_DAYS * MS_PER_DAY);
  }

  const lowerBound = formatArxivDate(lowerDate);
  const upperBound = formatArxivDate(upperDate);
  const query = `cat:${category} AND lastUpdatedDate:[${lowerBound} TO ${upperBound}]`;

  return {
    query,
    lowerBound,
    upperBound,
  };
}

/**
 * Retry wrapper for handling transient errors with exponential backoff
 */
async function retryWithBackoff<T>(
  operation: () => Promise<T>,
  options: {
    maxRetries?: number;
    initialDelayMs?: number;
    maxDelayMs?: number;
    operationName?: string;
  } = {}
): Promise<T> {
  const {
    maxRetries = MAX_RETRIES,
    initialDelayMs = INITIAL_RETRY_DELAY_MS,
    maxDelayMs = MAX_RETRY_DELAY_MS,
    operationName = "operation",
  } = options;

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      // Check if this is a retryable error
      const errorMessage = lastError.message;
      const isRetryable =
        errorMessage.includes("(500)") ||
        errorMessage.includes("(502)") ||
        errorMessage.includes("(503)") ||
        errorMessage.includes("(504)") ||
        errorMessage.includes("ETIMEDOUT") ||
        errorMessage.includes("ECONNRESET");

      // If not retryable or we're out of retries, throw immediately
      if (!isRetryable || attempt === maxRetries) {
        throw lastError;
      }

      // Calculate delay with exponential backoff
      const delayMs = Math.min(
        initialDelayMs * Math.pow(2, attempt),
        maxDelayMs
      );

      console.warn(
        `[Retry] ${operationName} failed (attempt ${attempt + 1}/${maxRetries + 1}): ${lastError.message}`
      );
      console.warn(`[Retry] Waiting ${Math.round(delayMs / 1000)}s before retry...`);

      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }

  // This should never be reached, but TypeScript needs it
  throw lastError ?? new Error("Retry failed with unknown error");
}

async function fetchCategoryFeed(
  category: string,
  query: string,
  credentials: ArxivCredentials,
  options: { start?: number; maxResults?: number } = {}
): Promise<ArxivEntry[]> {
  const url = new URL("https://export.arxiv.org/api/query");
  const start = options.start ?? 0;
  const maxResults = clampMaxResults(options.maxResults ?? MAX_RESULTS);
  url.searchParams.set("search_query", query);
  url.searchParams.set("start", String(start));
  url.searchParams.set("max_results", String(maxResults));
  url.searchParams.set("sortBy", "lastUpdatedDate");
  url.searchParams.set("sortOrder", "descending");

  const parsed = await retryWithBackoff(
    async () => {
      const response = await fetch(url, {
        headers: {
          "User-Agent": credentials.userAgent,
          From: credentials.contactEmail,
        },
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(`arXiv request failed (${response.status}): ${message}`);
      }

      const body = await response.text();
      const parser = new XMLParser({
        ignoreAttributes: false,
        attributeNamePrefix: "@_",
        trimValues: true,
      });

      return parser.parse(body);
    },
    {
      operationName: `arXiv API request for ${category}`,
    }
  );

  if (DEBUG) {
    const totalResults = Number(parsed?.feed?.["opensearch:totalResults"] ?? NaN);
    const startIndex = Number(parsed?.feed?.["opensearch:startIndex"] ?? start);
    const itemsPerPage = Number(parsed?.feed?.["opensearch:itemsPerPage"] ?? maxResults);
    console.log(
      `[${category}] fetched start=${startIndex} size=${itemsPerPage} total=${Number.isNaN(totalResults) ? "?" : totalResults
      }`
    );
  }
  const rawEntries = parsed?.feed?.entry;

  if (!rawEntries) {
    return [];
  }

  const entriesArray = Array.isArray(rawEntries) ? rawEntries : [rawEntries];

  return entriesArray
    .map(normalizeEntry)
    .filter((entry): entry is ArxivEntry => Boolean(entry) && Boolean(entry.id));
}

async function fetchEntryById(
  id: string,
  credentials: ArxivCredentials
): Promise<ArxivEntry | null> {
  try {
    return await retryWithBackoff(
      async () => {
        const url = new URL("https://export.arxiv.org/api/query");
        url.searchParams.set("id_list", id);

        const response = await fetch(url, {
          headers: {
            "User-Agent": credentials.userAgent,
            From: credentials.contactEmail,
          },
        });

        if (!response.ok) {
          // For 4xx errors (not found, bad request), don't retry
          if (response.status >= 400 && response.status < 500) {
            return null;
          }
          const message = await response.text();
          throw new Error(`arXiv request failed (${response.status}): ${message}`);
        }

        const body = await response.text();
        const parser = new XMLParser({
          ignoreAttributes: false,
          attributeNamePrefix: "@_",
          trimValues: true,
        });

        const parsed = parser.parse(body);
        const rawEntries = parsed?.feed?.entry;

        if (!rawEntries) {
          return null;
        }

        const entry = Array.isArray(rawEntries) ? rawEntries[0] : rawEntries;
        return normalizeEntry(entry);
      },
      {
        operationName: `arXiv API request for entry ${id}`,
      }
    );
  } catch (error) {
    // If all retries failed, return null
    console.warn(`Failed to fetch entry ${id} after retries: ${error}`);
    return null;
  }
}

function normalizeEntry(entry: any): ArxivEntry | null {
  if (!entry?.id || !entry?.published) {
    return null;
  }

  const authorsRaw = entry.author ?? [];
  const authorsArray = Array.isArray(authorsRaw) ? authorsRaw : [authorsRaw];
  const authors = authorsArray
    .map((author) => author?.name ?? (typeof author === "string" ? author : null))
    .filter((name): name is string => Boolean(name));

  const categoriesRaw = entry.category ?? [];
  const categoriesArray = Array.isArray(categoriesRaw) ? categoriesRaw : [categoriesRaw];
  const categories = categoriesArray
    .map((category) => category?.["@_term"] ?? (typeof category === "string" ? category : null))
    .filter((value): value is string => Boolean(value));

  const linksRaw = entry.link ?? [];
  const linksArray = Array.isArray(linksRaw) ? linksRaw : [linksRaw];
  const links = linksArray
    .map((link) => {
      const href = link?.["@_href"] ?? (typeof link === "string" ? link : null);
      if (!href) {
        return null;
      }
      return {
        rel: link?.["@_rel"] ?? null,
        href,
        type: link?.["@_type"] ?? null,
      };
    })
    .filter((link): link is { rel: string | null; href: string; type: string | null } =>
      Boolean(link)
    );

  const primaryCategory =
    entry["arxiv:primary_category"]?.["@_term"] ?? categories[0] ?? null;

  const comment = entry["arxiv:comment"];
  const commentStr = typeof comment === "string" ? comment : undefined;

  return {
    id: entry.id,
    title: entry.title,
    summary: typeof entry.summary === "string" ? entry.summary : undefined,
    published: entry.published,
    updated: entry.updated,
    authors,
    categories,
    primaryCategory,
    links,
    comment: commentStr,
  };
}

function isWithdrawn(entry: ArxivEntry): boolean {
  // Check comment field for withdrawal indicators
  if (entry.comment) {
    const commentLower = entry.comment.toLowerCase();
    if (
      commentLower.includes("withdrawn") ||
      commentLower.includes("retracted") ||
      commentLower.includes("removed by author")
    ) {
      return true;
    }
  }

  // Check summary/abstract for withdrawal notices
  if (entry.summary) {
    const summaryLower = entry.summary.toLowerCase();
    if (
      summaryLower.includes("paper has been withdrawn") ||
      summaryLower.includes("this submission has been withdrawn")
    ) {
      return true;
    }
  }

  return false;
}

function extractIdentifier(entry: ArxivEntry): string | null {
  return extractIdentifierFromId(entry.id);
}

function extractIdentifierFromId(id?: string): string | null {
  if (!id) {
    return null;
  }

  const segments = id.split("/");
  const last = segments[segments.length - 1];
  return last ?? null;
}

function extractBaseIdentifier(identifier: string | null): string | null {
  if (!identifier) {
    return null;
  }

  // Strip version suffix (e.g., "2511.09558v1" -> "2511.09558")
  const versionIndex = identifier.lastIndexOf("v");
  if (versionIndex === -1) {
    return identifier;
  }

  // Check if everything after 'v' is a number
  const afterV = identifier.slice(versionIndex + 1);
  if (/^\d+$/.test(afterV)) {
    return identifier.slice(0, versionIndex);
  }

  return identifier;
}

function findExistingTarball(entry: ArxivEntry, state: StateFile): string | null {
  // Check if this paper's tarball was already downloaded in any category
  for (const categoryState of Object.values(state)) {
    if (!categoryState?.downloadedEntries) {
      continue;
    }

    const downloaded = categoryState.downloadedEntries[entry.id];
    if (downloaded?.tarballPath) {
      return downloaded.tarballPath;
    }
  }

  return null;
}

async function downloadTarballsForEntries(
  category: string,
  entries: ArxivEntry[],
  previousState: CategoryState,
  state: StateFile,
  credentials: ArxivCredentials,
  rateLimiter: RateLimiter
): Promise<number> {
  const currentState = state[category];
  const downloadedMap = currentState.downloadedEntries ?? {};
  const pendingMap = currentState.pendingTarballs ?? {};
  currentState.downloadedEntries = downloadedMap;
  currentState.pendingTarballs = pendingMap;

  const now = Date.now();
  const maxAge = MAX_PENDING_AGE_DAYS * MS_PER_DAY;

  const entriesById = new Map<string, ArxivEntry>();
  for (const entry of entries) {
    entriesById.set(entry.id, entry);
  }

  // Fetch pending entries, but skip those older than MAX_PENDING_AGE_DAYS
  const pendingIds = Object.keys(pendingMap);
  const expiredIds: string[] = [];

  for (const id of pendingIds) {
    if (entriesById.has(id)) {
      continue;
    }

    const pendingInfo = pendingMap[id];
    const firstFailedAt = parseTimestamp(pendingInfo.firstFailedAt);

    // Skip retrying if too old
    if (firstFailedAt !== null && now - firstFailedAt > maxAge) {
      expiredIds.push(id);
      continue;
    }

    await rateLimiter.waitForTurn();
    const fetched = await fetchEntryById(id, credentials);

    if (fetched) {
      entriesById.set(fetched.id, fetched);
    }
  }

  // Remove expired pending entries
  for (const id of expiredIds) {
    delete pendingMap[id];
  }

  const combinedEntries = Array.from(entriesById.values()).sort(
    (a, b) => (parseTimestamp(a.published) ?? 0) - (parseTimestamp(b.published) ?? 0)
  );

  let downloaded = 0;
  let attempted = 0;
  const totalToAttempt = combinedEntries.filter((entry) => {
    const mostRecentUpdated = entry.updated ?? entry.published;
    const lastDownloaded = downloadedMap[entry.id];
    const pendingInfo = pendingMap[entry.id];
    return (
      pendingInfo !== undefined ||
      !lastDownloaded ||
      isUpdatedAfter(lastDownloaded.updated, mostRecentUpdated)
    );
  }).length;

  for (const entry of combinedEntries) {
    const mostRecentUpdated = entry.updated ?? entry.published;
    const lastDownloaded = downloadedMap[entry.id];
    const pendingInfo = pendingMap[entry.id];

    const shouldAttempt =
      pendingInfo !== undefined ||
      !lastDownloaded ||
      isUpdatedAfter(lastDownloaded.updated, mostRecentUpdated);

    if (!shouldAttempt) {
      continue;
    }

    attempted += 1;

    // Check if paper is withdrawn before attempting download
    if (isWithdrawn(entry)) {
      console.warn(
        `[Tarball] Skipping ${entry.id}: marked as withdrawn in metadata`
      );
      downloadedMap[entry.id] = {
        updated: mostRecentUpdated,
        tarballPath: "(withdrawn)",
      };
      delete pendingMap[entry.id];
      continue;
    }

    const tarballLink = resolveTarballLink(entry);

    if (!tarballLink) {
      const existing = pendingMap[entry.id];
      pendingMap[entry.id] = {
        updated: mostRecentUpdated,
        firstFailedAt: existing?.firstFailedAt ?? new Date().toISOString(),
      };
      continue;
    }

    // Check if tarball already exists across all categories (cross-category dedup)
    const existingTarball = findExistingTarball(entry, state);

    if (existingTarball) {
      // Tarball already downloaded for another category, just reference it
      downloadedMap[entry.id] = {
        updated: mostRecentUpdated,
        tarballPath: existingTarball,
      };
      delete pendingMap[entry.id];
      continue;
    }

    await rateLimiter.waitForTurn();

    try {
      const tarballPath = await downloadTarball(category, entry, tarballLink);

      // Empty string means 404/withdrawn - mark as processed but without tarball
      if (tarballPath === "") {
        downloadedMap[entry.id] = {
          updated: mostRecentUpdated,
          tarballPath: "(unavailable)",
        };
        delete pendingMap[entry.id];
        // Don't count as downloaded since no file was saved
      } else {
        downloadedMap[entry.id] = {
          updated: mostRecentUpdated,
          tarballPath,
        };
        delete pendingMap[entry.id];
        downloaded += 1;

        // Show progress every 10 downloads
        if (downloaded % 10 === 0 || downloaded === totalToAttempt) {
          console.log(
            `[Tarball] Downloaded ${downloaded}/${totalToAttempt} (${attempted} attempted)`
          );
        }

        // Save state periodically to enable resume
        if (downloaded % TARBALL_CHECKPOINT_INTERVAL === 0) {
          await saveState(STATE_FILE, state);
          console.log(`[Tarball] Checkpoint: Saved progress (${downloaded}/${totalToAttempt})`);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error(`Failed to download tarball for ${entry.id}: ${message}`);
      const existing = pendingMap[entry.id];
      pendingMap[entry.id] = {
        updated: mostRecentUpdated,
        firstFailedAt: existing?.firstFailedAt ?? new Date().toISOString(),
      };
    }
  }

  return downloaded;
}

function resolveTarballLink(entry: ArxivEntry): { href: string; rel: string | null; type: string | null } | null {
  for (const link of entry.links) {
    if (
      link.rel === "related" &&
      (link.type === "application/x-eprint-tar" || link.type === "application/x-eprint") &&
      !link.href.endsWith(".pdf") &&
      !link.href.endsWith(".ps")
    ) {
      return link;
    }
  }

  for (const link of entry.links) {
    if (
      (link.rel === "related" || link.rel === "derived" || link.rel === null) &&
      link.type === "application/x-tar" &&
      !link.href.endsWith(".pdf") &&
      !link.href.endsWith(".ps")
    ) {
      return link;
    }
  }

  for (const link of entry.links) {
    if ((link.href.endsWith(".tar") || link.href.endsWith(".tar.gz")) && !link.href.endsWith(".tar.pdf")) {
      return link;
    }
  }

  const identifier = entry.id.split("/").pop();
  if (identifier) {
    return {
      rel: "derived",
      href: `https://arxiv.org/e-print/${identifier}`,
      type: "application/x-tar",
    };
  }

  return null;
}

async function downloadTarball(
  category: string,
  entry: ArxivEntry,
  link: { href: string; rel: string | null; type: string | null },
  options: { directory?: string } = {}
): Promise<string> {
  const { directory = TAR_OUTPUT_DIRECTORY } = options;
  const identifier = entry.id.split("/").pop() ?? entry.id;

  return await retryWithBackoff(
    async () => {
      const response = await fetch(link.href, {
        headers: {
          "User-Agent": Bun.env.ARXIV_USER_AGENT ?? "arxiv-downloader/0.1",
        },
      });

      if (!response.ok) {
        // 4xx errors are permanent (withdrawn papers, not found, etc.)
        // Don't retry these - just skip them
        if (response.status >= 400 && response.status < 500) {
          console.warn(
            `[Tarball] Skipping ${identifier}: HTTP ${response.status} (withdrawn or unavailable)`
          );
          // Return empty string to signal "no tarball but don't fail"
          return "";
        }
        const message = await response.text();
        throw new Error(`Tarball request failed (${response.status}): ${message}`);
      }

      const arrayBuffer = await response.arrayBuffer();
      const buffer = Buffer.from(arrayBuffer);
      await mkdir(directory, { recursive: true });

      const safeIdentifier = identifier.replace(/[^a-zA-Z0-9.-]/g, "_");
      const timestamp = new Date().toISOString().replace(/[:]/g, "-");
      const fileName = `${category.replace(/[^a-zA-Z0-9.-]/g, "_")}-${safeIdentifier}-${timestamp}.tar`;
      const filePath = `${directory}/${fileName}`;

      await Bun.write(filePath, buffer);
      return filePath;
    },
    {
      operationName: `Tarball download for ${identifier}`,
    }
  );
}

async function persistSnapshot(
  category: string,
  entries: ArxivEntry[],
  totalEntries: number,
  maxResults: number
): Promise<string> {
  const timestamp = new Date().toISOString().replace(/[:]/g, "-");
  const safeCategory = category.replace(/[^a-zA-Z0-9.-]/g, "_");
  const filePath = `${DATA_DIRECTORY}/${safeCategory}-${timestamp}.json`;

  const snapshot = {
    category,
    fetchedAt: new Date().toISOString(),
    totalEntries,
    newEntryCount: entries.length,
    request: {
      maxResults,
      sortBy: "submittedDate",
      sortOrder: "descending",
    },
    entries,
  };

  await Bun.write(filePath, JSON.stringify(snapshot, null, 2));
  return filePath;
}

async function loadState(path: string): Promise<StateFile> {
  const file = Bun.file(path);

  if (!(await file.exists())) {
    return {};
  }

  try {
    const raw = await file.text();
    const parsed = JSON.parse(raw) as StateFile;
    return parsed ?? {};
  } catch {
    console.warn(`Unable to parse state file at ${path}. Starting fresh.`);
    return {};
  }
}

async function saveState(path: string, state: StateFile): Promise<void> {
  await Bun.write(path, JSON.stringify(state, null, 2));
}

function parseEnv(source: string): Map<string, string> {
  const map = new Map<string, string>();

  for (const line of source.split(/\r?\n/)) {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separatorIndex = trimmed.indexOf("=");

    if (separatorIndex === -1) {
      continue;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    const value = trimmed.slice(separatorIndex + 1).trim();

    if (key) {
      map.set(key, value);
    }
  }

  return map;
}

function evaluateEntryFreshness(
  entry: ArxivEntry,
  categoryState: CategoryState
): { isNew: boolean; stop: boolean } {
  // Use most recent timestamp (updated or published)
  const entryTime = parseTimestamp(entry.updated ?? entry.published);
  const lastTime = parseTimestamp(categoryState.lastPublished);
  const lastId = categoryState.lastId;
  const entryIdentifier = extractIdentifier(entry);
  const entryBaseIdentifier = extractBaseIdentifier(entryIdentifier);
  const lastBaseIdentifier =
    categoryState.lastBaseIdentifier ??
    extractBaseIdentifier(categoryState.lastIdentifier) ??
    extractBaseIdentifier(extractIdentifierFromId(categoryState.lastId));

  // Use base identifier comparison (without version) to determine if we've seen this paper before
  if (lastBaseIdentifier) {
    if (!entryBaseIdentifier) {
      // Fall back to timestamp logic if identifier missing.
    } else {
      const cmp = compareBaseIdentifiers(entryBaseIdentifier, lastBaseIdentifier);

      if (cmp > 0) {
        // This is a newer paper (not just a new version)
        return { isNew: true, stop: false };
      }

      if (cmp === 0) {
        // Same paper (possibly different version) - consider it seen, stop paginating
        return { isNew: false, stop: true };
      }

      // Older paper - we've gone past what we've seen, stop
      return { isNew: false, stop: true };
    }
  }

  // Fall back to timestamp-based comparison
  if (lastTime === null) {
    return { isNew: true, stop: false };
  }

  if (entryTime === null) {
    return { isNew: true, stop: false };
  }

  if (entryTime > lastTime) {
    return { isNew: true, stop: false };
  }

  if (entryTime === lastTime) {
    if (lastId && entry.id === lastId) {
      return { isNew: false, stop: true };
    }

    return { isNew: true, stop: false };
  }

  return { isNew: false, stop: true };
}

function compareBaseIdentifiers(current: string, previous: string): number {
  if (current === previous) {
    return 0;
  }

  // Simple lexicographic comparison of base identifiers (e.g., "2511.09558" vs "2511.09559")
  return current.localeCompare(previous);
}

function compareIdentifiers(current: string, previous: string): number {
  if (current === previous) {
    return 0;
  }

  const [currentBase, currentVersionRaw] = current.split("v");
  const [previousBase, previousVersionRaw] = previous.split("v");

  if (currentBase !== previousBase) {
    return currentBase.localeCompare(previousBase);
  }

  const currentVersion = Number(currentVersionRaw ?? "1");
  const previousVersion = Number(previousVersionRaw ?? "1");

  if (Number.isNaN(currentVersion) || Number.isNaN(previousVersion)) {
    return (currentVersionRaw ?? "").localeCompare(previousVersionRaw ?? "");
  }

  return currentVersion - previousVersion;
}

function clampMaxResults(value: number): number {
  if (Number.isNaN(value)) {
    return 100;
  }
  return Math.min(Math.max(value, 1), 300);
}

async function delay(ms: number): Promise<void> {
  if (!Number.isFinite(ms) || ms <= 0) {
    return;
  }
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function parseTimestamp(value?: string): number | null {
  if (!value) {
    return null;
  }
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

function isUpdatedAfter(previous?: string, current?: string): boolean {
  const prevMs = parseTimestamp(previous);
  const currMs = parseTimestamp(current);

  if (currMs === null) {
    return false;
  }

  if (prevMs === null) {
    return true;
  }

  return currMs > prevMs;
}

function formatArxivDate(date: Date): string {
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth() + 1;
  const day = date.getUTCDate();
  const hours = date.getUTCHours();
  const minutes = date.getUTCMinutes();

  return (
    year.toString().padStart(4, "0") +
    month.toString().padStart(2, "0") +
    day.toString().padStart(2, "0") +
    hours.toString().padStart(2, "0") +
    minutes.toString().padStart(2, "0")
  );
}

function parseBooleanEnv(value: string): boolean {
  return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
}

function clampSampleCount(value: number): number {
  if (Number.isNaN(value)) {
    return 10;
  }
  return Math.min(Math.max(value, 1), 50);
}

function clampPageCount(value: number): number {
  if (Number.isNaN(value)) {
    return 5;
  }
  return Math.min(Math.max(value, 1), 10);
}

function clampLookbackDays(value: number): number {
  if (Number.isNaN(value)) {
    return 7;
  }
  return Math.min(Math.max(value, 1), 365);
}

function clampLookaheadMinutes(value: number): number {
  if (Number.isNaN(value)) {
    return 120;
  }
  return Math.min(Math.max(value, 10), 1440);
}

function clampHistoricalMaxBatches(value: number): number {
  if (Number.isNaN(value)) {
    return 1000;
  }
  return Math.min(Math.max(value, 1), 10000);
}

function normalizeState(state: StateFile): void {
  for (const categoryState of Object.values(state)) {
    if (!categoryState) {
      continue;
    }

    if (!categoryState.lastIdentifier && categoryState.lastId) {
      const identifier = extractIdentifierFromId(categoryState.lastId);
      if (identifier) {
        categoryState.lastIdentifier = identifier;
      }
    }

    if (!categoryState.lastBaseIdentifier) {
      const baseIdentifier =
        extractBaseIdentifier(categoryState.lastIdentifier) ??
        extractBaseIdentifier(extractIdentifierFromId(categoryState.lastId));
      if (baseIdentifier) {
        categoryState.lastBaseIdentifier = baseIdentifier;
      }
    }

    categoryState.downloadedEntries = categoryState.downloadedEntries ?? {};
    categoryState.pendingTarballs = categoryState.pendingTarballs ?? {};
  }
}

async function loadCategoriesConfig(configPath: string | URL): Promise<CategoryConfig[]> {
  const categories: CategoryConfig[] = [];

  try {
    const file = Bun.file(configPath);
    const content = await file.text();
    const lines = content.split("\n");

    let currentCategory: string | null = null;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      // Skip comments and empty lines
      if (!line || line.startsWith("#")) {
        continue;
      }

      // Parse "category: value" lines
      if (line.startsWith("category:")) {
        currentCategory = line.substring("category:".length).trim();
      }
      // Parse "start_date: value" lines
      else if (line.startsWith("start_date:") && currentCategory) {
        const startDate = line.substring("start_date:".length).trim();
        categories.push({ category: currentCategory, startDate });
        currentCategory = null; // Reset for next pair
      }
    }
  } catch (error) {
    console.error(`Failed to load categories config from ${configPath}:`, error);
    return [];
  }

  return categories;
}

function calculateMonthsToBackfill(startDate: string, referenceDate?: string): number {
  const start = new Date(startDate);
  const reference = referenceDate ? new Date(referenceDate) : new Date();

  const monthsDiff =
    (reference.getFullYear() - start.getFullYear()) * 12 +
    (reference.getMonth() - start.getMonth());

  // Add 1 to include the current month
  return Math.max(1, monthsDiff + 1);
}

function findEarliestDownloadedDate(categoryState: CategoryState | undefined): string | null {
  if (!categoryState?.downloadedEntries) {
    return null;
  }

  const entries = Object.values(categoryState.downloadedEntries);
  if (entries.length === 0) {
    return null;
  }

  let earliest: number | null = null;

  for (const entry of entries) {
    const timestamp = parseTimestamp(entry.updated);
    if (timestamp !== null && (earliest === null || timestamp < earliest)) {
      earliest = timestamp;
    }
  }

  return earliest ? new Date(earliest).toISOString().split("T")[0] : null;
}

function isRangeConfirmed(
  startDate: string,
  endDate: string,
  confirmedRanges: CategoryState["confirmedRanges"]
): boolean {
  if (!confirmedRanges || confirmedRanges.length === 0) {
    return false;
  }

  const start = new Date(startDate).getTime();
  const end = new Date(endDate).getTime();

  // Check if the entire requested range is covered by confirmed ranges
  for (const range of confirmedRanges) {
    const rangeStart = new Date(range.startDate).getTime();
    const rangeEnd = new Date(range.endDate).getTime();

    if (rangeStart <= start && rangeEnd >= end) {
      return true; // Entire range is confirmed
    }
  }

  return false;
}

function addConfirmedRange(
  categoryState: CategoryState,
  startDate: string,
  endDate: string,
  paperCount: number
): void {
  if (!categoryState.confirmedRanges) {
    categoryState.confirmedRanges = [];
  }

  // Add new range
  categoryState.confirmedRanges.push({
    startDate,
    endDate,
    completedAt: new Date().toISOString(),
    paperCount,
  });

  // Sort ranges by start date
  categoryState.confirmedRanges.sort(
    (a, b) => new Date(a.startDate).getTime() - new Date(b.startDate).getTime()
  );

  // Merge overlapping or adjacent ranges
  const merged: CategoryState["confirmedRanges"] = [];
  for (const range of categoryState.confirmedRanges) {
    if (merged.length === 0) {
      merged.push(range);
      continue;
    }

    const last = merged[merged.length - 1];
    const lastEnd = new Date(last.endDate).getTime();
    const currentStart = new Date(range.startDate).getTime();

    // If ranges overlap or are adjacent (within 1 day), merge them
    if (currentStart <= lastEnd + MS_PER_DAY) {
      last.endDate = range.endDate;
      last.paperCount += range.paperCount;
      last.completedAt = range.completedAt; // Use most recent completion time
    } else {
      merged.push(range);
    }
  }

  categoryState.confirmedRanges = merged;
}

async function getHistorical(
  category: string,
  startDateStr: string,
  endDateStr: string,
  credentials: ArxivCredentials,
  state: StateFile,
  rateLimiter: RateLimiter
): Promise<{ totalFetched: number; tarballsDownloaded: number }> {
  const startDate = new Date(startDateStr);
  const endDate = new Date(endDateStr);

  // Initialize category state if needed
  if (!state[category]) {
    state[category] = {
      downloadedEntries: {},
      pendingTarballs: {},
      confirmedRanges: [],
    };
  }

  const categoryState = state[category];

  // Check if this range is already confirmed
  if (isRangeConfirmed(startDateStr, endDateStr, categoryState.confirmedRanges)) {
    console.log(
      `[Historical] ${category}: Range ${startDateStr} to ${endDateStr} already confirmed, skipping`
    );
    return { totalFetched: 0, tarballsDownloaded: 0 };
  }

  const lowerBound = formatArxivDate(startDate);
  const upperBound = formatArxivDate(endDate);
  const query = `cat:${category} AND lastUpdatedDate:[${lowerBound} TO ${upperBound}]`;

  // Calculate duration in months for display and estimation
  const durationMonths = Math.ceil(
    (endDate.getTime() - startDate.getTime()) / (30 * MS_PER_DAY)
  );

  // Rough estimate: ~1500 papers per month for active categories
  const estimatedPapers = durationMonths * 1500;
  const estimatedBatches = Math.ceil(estimatedPapers / 100);
  const estimatedMinutes = Math.ceil((estimatedBatches * 5) / 60);

  console.log(
    `[Historical] ${category}: ${durationMonths} months (${startDateStr} to ${endDateStr})`
  );
  console.log(
    `[Historical] Estimated ~${estimatedMinutes} min for metadata, plus tarballs`
  );

  // Check if we have an in-progress backfill to resume
  const inProgress = categoryState.inProgressBackfill;
  const isResumingBackfill =
    inProgress &&
    inProgress.startDate === startDateStr &&
    inProgress.endDate === endDateStr;

  // Fetch all entries in batches
  const allEntries: ArxivEntry[] = [];
  const allEntryIds = new Set<string>();
  let start = 0;
  const batchSize = 100;
  const maxBatches = HISTORICAL_MAX_BATCHES;
  let hitLimit = false;
  const fetchStartTime = Date.now();

  // Resume from previous progress if available
  if (isResumingBackfill && inProgress) {
    start = inProgress.lastBatchOffset;
    // We don't need to re-add the entries since we'll skip them during dedup
    // But we track them so we know what we've seen
    for (const id of inProgress.fetchedIds) {
      allEntryIds.add(id);
    }
    console.log(
      `[Historical] Resuming from offset ${start} (${inProgress.fetchedCount} papers already fetched)`
    );
  } else if (inProgress) {
    // Clear old in-progress backfill for different range
    delete categoryState.inProgressBackfill;
  }

  for (let batch = 0; batch < maxBatches; batch += 1) {
    await rateLimiter.waitForTurn();
    const entries = await fetchCategoryFeed(category, query, credentials, {
      start,
      maxResults: batchSize,
    });

    if (!entries.length) {
      break;
    }

    allEntries.push(...entries);
    // Track all IDs we've fetched
    for (const entry of entries) {
      allEntryIds.add(entry.id);
    }

    // Show progress every 10 batches or on completion
    const isProgressMilestone = (batch + 1) % 10 === 0;
    const isComplete = entries.length < batchSize;

    if (isProgressMilestone || isComplete) {
      const elapsed = (Date.now() - fetchStartTime) / 1000;
      const rate = (batch + 1) / elapsed;
      const estimatedRemaining = estimatedBatches - (batch + 1);
      const etaSeconds = estimatedRemaining > 0 ? Math.ceil(estimatedRemaining / rate) : 0;
      const etaMinutes = Math.ceil(etaSeconds / 60);

      if (isComplete || estimatedRemaining <= 0) {
        console.log(`[Historical] Fetched ${allEntries.length} papers in ${Math.ceil(elapsed / 60)} min`);
      } else {
        console.log(
          `[Historical] ${allEntries.length} papers so far, ~${etaMinutes} min remaining`
        );
      }

      // Save progress checkpoint every 10 batches
      if (isProgressMilestone && !isComplete) {
        // Update in-progress tracker
        categoryState.inProgressBackfill = {
          startDate: startDateStr,
          endDate: endDateStr,
          fetchedCount: allEntries.length,
          fetchedIds: Array.from(allEntryIds),
          lastBatchOffset: start + entries.length,
        };
        await saveState(STATE_FILE, state);
      }
    }

    if (entries.length < batchSize) {
      break;
    }

    start += entries.length;

    // Check if we're about to hit the limit
    if (batch + 1 >= maxBatches) {
      hitLimit = true;
      break;
    }
  }

  if (hitLimit) {
    console.warn(
      `[Historical] WARNING: Reached maximum batch limit (${maxBatches} batches = ${maxBatches * batchSize} papers).`
    );
    console.warn(
      `[Historical] There may be more papers in this date range. Run again to continue, or increase ARXIV_HISTORICAL_MAX_BATCHES.`
    );
  }

  // Filter out entries already downloaded for this category
  const existingDownloads = categoryState.downloadedEntries ?? {};
  const existingIds = new Set(Object.keys(existingDownloads));

  const newEntries = allEntries.filter((entry) => !existingIds.has(entry.id));

  if (newEntries.length === 0) {
    console.log(`[Historical] All ${allEntries.length} papers already downloaded`);
    return { totalFetched: allEntries.length, tarballsDownloaded: 0 };
  }

  // Initialize category state if needed
  if (!state[category]) {
    state[category] = {
      downloadedEntries: {},
      pendingTarballs: {},
    };
  }

  // Download tarballs for new entries
  console.log(`[Historical] Downloading tarballs for ${newEntries.length} new papers...`);
  const tarballStartTime = Date.now();

  const tarballsDownloaded = await downloadTarballsForEntries(
    category,
    newEntries,
    categoryState,
    state,
    credentials,
    rateLimiter
  );

  const tarballElapsed = Math.ceil((Date.now() - tarballStartTime) / 60000);
  console.log(
    `[Historical] Downloaded ${tarballsDownloaded} tarballs in ${tarballElapsed} min`
  );

  // Update lastPublished to the most recent entry
  if (newEntries.length > 0) {
    const sorted = [...newEntries].sort((a, b) => {
      const aTime = parseTimestamp(a.updated ?? a.published) ?? 0;
      const bTime = parseTimestamp(b.updated ?? b.published) ?? 0;
      return aTime - bTime;
    });
    const newest = sorted[sorted.length - 1];
    const newestIdentifier = extractIdentifier(newest);
    const newestBaseIdentifier = extractBaseIdentifier(newestIdentifier);
    const newestTimestamp = newest.updated ?? newest.published;

    state[category].lastPublished = newestTimestamp;
    state[category].lastId = newest.id;
    state[category].lastIdentifier = newestIdentifier ?? state[category].lastIdentifier;
    state[category].lastBaseIdentifier =
      newestBaseIdentifier ?? state[category].lastBaseIdentifier;
  }

  // Mark this range as confirmed complete
  addConfirmedRange(categoryState, startDateStr, endDateStr, allEntries.length);

  // Clear in-progress tracker since we completed successfully
  if (categoryState.inProgressBackfill) {
    delete categoryState.inProgressBackfill;
  }

  console.log(`[Historical] Range ${startDateStr} to ${endDateStr} confirmed complete`);

  return { totalFetched: allEntries.length, tarballsDownloaded };
}

if (import.meta.main) {
  main();
}

