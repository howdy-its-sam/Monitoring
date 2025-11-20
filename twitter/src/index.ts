import { mkdir, readdir, stat, unlink } from "node:fs/promises";
import { exit } from "node:process";

import {
  fetchTweetsForHandle,
  RateLimitInfo,
  TwitterHttpError,
  TwitterTweet,
} from "./twitterApi";

type TwitterCredentials = {
  apiKey: string;
  apiSecret: string;
  bearerToken: string;
};

const DEFAULT_CREDENTIALS_TARGET =
  Bun.env.TWITTER_CREDENTIALS_PATH ?? new URL("../twitter_credentials.env", import.meta.url);

const DEFAULT_HANDLES = ["OpenAI", "GoogleDeepMind"];
const parsedMaxResults = Number.parseInt(Bun.env.TWITTER_MAX_RESULTS ?? "", 10);
const DEFAULT_MAX_RESULTS = Number.isNaN(parsedMaxResults) ? 100 : parsedMaxResults;
const DATA_DIRECTORY = Bun.env.TWITTER_DATA_DIR ?? "data";
const RATE_LIMIT_STATE_FILE = `${DATA_DIRECTORY}/rate-limit.json`;
const MAX_ATTEMPTS_PER_HANDLE = 3;
const MIN_FETCH_INTERVAL_MS = 24 * 60 * 60 * 1000;

export async function loadTwitterCredentials(
  target: string | URL = DEFAULT_CREDENTIALS_TARGET
): Promise<TwitterCredentials> {
  const file = Bun.file(target);

  if (!(await file.exists())) {
    throw new Error(
      `Twitter credentials file not found. Set TWITTER_CREDENTIALS_PATH or create twitter_credentials.env.`
    );
  }

  const contents = await file.text();
  const entries = parseEnvFile(contents);

  const apiKey = entries.get("TWITTER_API_KEY");
  const apiSecret = entries.get("TWITTER_API_SECRET");
  const bearerToken = entries.get("TWITTER_BEARER_TOKEN");

  if (!apiKey || !apiSecret || !bearerToken) {
    throw new Error(
      `Twitter credentials file is missing one or more of TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_BEARER_TOKEN.`
    );
  }

  return {
    apiKey,
    apiSecret,
    bearerToken,
  };
}

function parseEnvFile(source: string): Map<string, string> {
  const lines = source.split(/\r?\n/);
  const entries = new Map<string, string>();

  for (const line of lines) {
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
      entries.set(key, value);
    }
  }

  return entries;
}

async function main() {
  try {
    const credentials = await loadTwitterCredentials();
    await mkdir(DATA_DIRECTORY, { recursive: true });

    let nextAvailableAt = (await loadRateLimitState(RATE_LIMIT_STATE_FILE)) ?? 0;
    const lastFetchedAt = await loadHandleRecency(DEFAULT_HANDLES);
    const handles = sortHandlesByRecency(DEFAULT_HANDLES, lastFetchedAt);
    const summary: Array<{ handle: string; savedTo?: string; count?: number; error?: string }> = [];

    for (const handle of handles) {
      const initialLastFetched = lastFetchedAt.get(handle);
      const eligible = isHandleEligibleForFetch({
        handle,
        lastFetchedAt: initialLastFetched,
        now: Date.now(),
      });

      if (!eligible) {
        const lastFetchedMessage =
          initialLastFetched !== undefined
            ? `last fetched at ${new Date(initialLastFetched).toISOString()}`
            : "no previous fetch timestamp";
        console.log(`Skipping @${handle}: ${lastFetchedMessage} (within cooldown window).`);
        continue;
      }

      let attempts = 0;
      let success = false;
      let lastError: string | undefined;

      while (attempts < MAX_ATTEMPTS_PER_HANDLE && !success) {
        const now = Date.now();

        if (now < nextAvailableAt) {
          const waitMs = nextAvailableAt - now;
          console.log(
            `Waiting ${formatDuration(waitMs)} for Twitter rate limit reset before requesting @${handle}.`
          );
          await delay(waitMs);
          continue;
        }

        attempts += 1;

        try {
          const { tweets, rateLimit } = await fetchTweetsForHandle(handle, credentials.bearerToken, {
            maxResults: DEFAULT_MAX_RESULTS,
          });

          const scheduled = computeNextAvailable(rateLimit);
          if (scheduled !== null) {
            nextAvailableAt = Math.max(nextAvailableAt, scheduled);
            await saveRateLimitState(RATE_LIMIT_STATE_FILE, nextAvailableAt);
          }

          const savedTo = await persistTweets(handle, tweets);
          lastFetchedAt.set(handle, Date.now());

          summary.push({ handle, savedTo, count: tweets.length });
          console.log(`Fetched ${tweets.length} tweets for @${handle} -> ${savedTo}`);
          success = true;
        } catch (handleError) {
          if (handleError instanceof TwitterHttpError) {
            lastError = handleError.message;

            const scheduled = computeNextAvailable(handleError.rateLimit, { force: true });
            if (scheduled !== null) {
              nextAvailableAt = Math.max(nextAvailableAt, scheduled);
              await saveRateLimitState(RATE_LIMIT_STATE_FILE, nextAvailableAt);

              const waitMs = Math.max(0, scheduled - Date.now());
              console.warn(
                `Rate limit reached fetching @${handle}. Waiting ${formatDuration(waitMs)} before retrying.`
              );
              await delay(waitMs);
              continue;
            }
          }

          const message = handleError instanceof Error ? handleError.message : String(handleError);
          lastError = message;
          console.error(`Failed to fetch tweets for @${handle}: ${message}`);
          break;
        }
      }

      if (!success) {
        summary.push({ handle, error: lastError ?? "Unknown error" });
      }
    }

    if (nextAvailableAt <= Date.now()) {
      await saveRateLimitState(RATE_LIMIT_STATE_FILE, null);
    } else {
      await saveRateLimitState(RATE_LIMIT_STATE_FILE, nextAvailableAt);
    }

    if (summary.length === 0) {
      console.log("No eligible handles to fetch at this time.");
    }

    const hasSuccess = summary.some((item) => item.savedTo && !item.error);
    const hasFailure = summary.some((item) => item.error);

    if (!hasSuccess && hasFailure) {
      exit(1);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(message);
    exit(1);
  }
}

async function persistTweets(handle: string, tweets: TwitterTweet[]): Promise<string> {
  const timestamp = new Date().toISOString().replace(/[:]/g, "-");
  const filename = `${handle}-${timestamp}.json`;
  const filePath = `${DATA_DIRECTORY}/${filename}`;

  const snapshot = {
    handle,
    fetchedAt: new Date().toISOString(),
    tweets,
  };

  await Bun.write(filePath, JSON.stringify(snapshot, null, 2));
  return filePath;
}

async function loadHandleRecency(handles: string[]): Promise<Map<string, number>> {
  const handleSet = new Set(handles);
  const latest = new Map<string, number>();

  try {
    const entries = await readdir(DATA_DIRECTORY);

    await Promise.all(
      entries
        .filter((entry) => entry.endsWith(".json"))
        .map(async (entry) => {
          const dashIndex = entry.indexOf("-");

          if (dashIndex === -1) {
            return;
          }

          const handle = entry.slice(0, dashIndex);

          if (!handleSet.has(handle)) {
            return;
          }

          try {
            const info = await stat(`${DATA_DIRECTORY}/${entry}`);
            const current = latest.get(handle) ?? -Infinity;

            if (info.mtimeMs > current) {
              latest.set(handle, info.mtimeMs);
            }
          } catch {
            // Ignore missing or unreadable snapshot files.
          }
        })
    );
  } catch (error) {
    const maybeErrno = error as NodeJS.ErrnoException | undefined;

    if (maybeErrno?.code !== "ENOENT") {
      const message = error instanceof Error ? error.message : String(error);
      console.warn(`Unable to determine fetch order: ${message}`);
    }
  }

  return latest;
}

function sortHandlesByRecency(handles: string[], latest: Map<string, number>): string[] {
  return [...handles].sort((a, b) => {
    const aTime = latest.get(a) ?? -Infinity;
    const bTime = latest.get(b) ?? -Infinity;

    if (aTime === bTime) {
      return a.localeCompare(b);
    }

    return aTime - bTime;
  });
}

if (import.meta.main) {
  main();
}

function computeNextAvailable(
  rateLimit: RateLimitInfo | undefined,
  options: { force?: boolean } = {}
): number | null {
  if (!rateLimit) {
    return null;
  }

  const { force = false } = options;
  const { remaining, resetMs } = rateLimit;

  if (resetMs === null) {
    return null;
  }

  if (!force && remaining !== null && remaining > 0) {
    return null;
  }

  return resetMs;
}

async function delay(ms: number): Promise<void> {
  if (!Number.isFinite(ms) || ms <= 0) {
    return;
  }

  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function loadRateLimitState(stateFile: string): Promise<number | null> {
  const file = Bun.file(stateFile);

  if (!(await file.exists())) {
    return null;
  }

  try {
    const contents = await file.text();
    const parsed = JSON.parse(contents);
    const value = typeof parsed.nextAvailableAt === "number" ? parsed.nextAvailableAt : null;
    return value;
  } catch {
    return null;
  }
}

async function saveRateLimitState(stateFile: string, nextAvailableAt: number | null): Promise<void> {
  if (nextAvailableAt === null || nextAvailableAt <= Date.now()) {
    try {
      await unlink(stateFile);
    } catch (error) {
      const maybeErrno = error as NodeJS.ErrnoException | undefined;

      if (maybeErrno?.code !== "ENOENT") {
        const message = error instanceof Error ? error.message : String(error);
        console.warn(`Unable to clear rate limit state: ${message}`);
      }
    }
    return;
  }

  const payload = JSON.stringify({ nextAvailableAt }, null, 2);
  await Bun.write(stateFile, payload);
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) {
    return "0 seconds";
  }

  const seconds = Math.ceil(ms / 1000);

  if (seconds < 60) {
    return seconds === 1 ? "1 second" : `${seconds} seconds`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  if (remainingSeconds === 0) {
    return minutes === 1 ? "1 minute" : `${minutes} minutes`;
  }

  return `${minutes}m ${remainingSeconds}s`;
}

function isHandleEligibleForFetch(args: {
  handle: string;
  lastFetchedAt: number | undefined;
  now: number;
}): boolean {
  const { lastFetchedAt, now } = args;

  if (lastFetchedAt === undefined) {
    return true;
  }

  return now - lastFetchedAt >= MIN_FETCH_INTERVAL_MS;
}

