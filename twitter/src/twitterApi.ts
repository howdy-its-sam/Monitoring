const API_BASE_URL = "https://api.twitter.com/2";

type TwitterErrorDetail = {
  title?: string;
  detail?: string;
  type?: string;
};

type TwitterUserResponse = {
  data?: {
    id: string;
    username: string;
  };
  errors?: TwitterErrorDetail[];
};

type TwitterTweetsResponse = {
  data?: TwitterTweet[];
  meta?: {
    result_count?: number;
    newest_id?: string;
    oldest_id?: string;
  };
  errors?: TwitterErrorDetail[];
};

export type TwitterTweet = {
  id: string;
  text: string;
  created_at?: string;
};

export type RateLimitInfo = {
  remaining: number | null;
  resetMs: number | null;
};

type ApiResponse<T> = {
  body: T;
  rateLimit: RateLimitInfo;
};

export class TwitterHttpError extends Error {
  readonly status: number;
  readonly rateLimit: RateLimitInfo;

  constructor(message: string, status: number, rateLimit: RateLimitInfo) {
    super(message);
    this.name = "TwitterHttpError";
    this.status = status;
    this.rateLimit = rateLimit;
  }
}

export async function fetchTweetsForHandle(
  handle: string,
  bearerToken: string,
  options: { maxResults?: number } = {}
): Promise<{ tweets: TwitterTweet[]; rateLimit: RateLimitInfo }> {
  const sanitizedHandle = handle.trim();

  if (!sanitizedHandle) {
    throw new Error("Twitter handle must be a non-empty string.");
  }

  const user = await fetchUserByHandle(sanitizedHandle, bearerToken);
  const { tweets, rateLimit } = await fetchTweetsByUserId(
    user.id,
    bearerToken,
    options.maxResults
  );
  return { tweets, rateLimit };
}

async function fetchUserByHandle(handle: string, bearerToken: string) {
  const url = new URL(`${API_BASE_URL}/users/by/username/${handle}`);
  const { body } = await request<TwitterUserResponse>(url, bearerToken);

  if (!body.data?.id) {
    throw new Error(formatErrors("Failed to resolve user ID", body.errors));
  }

  return body.data;
}

async function fetchTweetsByUserId(
  userId: string,
  bearerToken: string,
  maxResults = 5
): Promise<{ tweets: TwitterTweet[]; rateLimit: RateLimitInfo }> {
  const url = new URL(`${API_BASE_URL}/users/${userId}/tweets`);
  const cappedResults = clamp(Math.round(maxResults), 1, 100);

  url.searchParams.set("max_results", String(cappedResults));
  url.searchParams.set("tweet.fields", "created_at,text");

  const { body, rateLimit } = await request<TwitterTweetsResponse>(url, bearerToken);

  if (!body.data) {
    throw new Error(formatErrors("No tweets returned for user", body.errors));
  }

  return { tweets: body.data, rateLimit };
}

async function request<T>(url: URL, bearerToken: string): Promise<ApiResponse<T>> {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${bearerToken}`,
    },
  });

  const rateLimit = extractRateLimit(response.headers);

  if (!response.ok) {
    const message = await response.text();
    throw new TwitterHttpError(
      `Twitter API request failed (${response.status}): ${message}`,
      response.status,
      rateLimit
    );
  }

  const body = (await response.json()) as T;

  return {
    body,
    rateLimit,
  };
}

function formatErrors(prefix: string, errors?: TwitterErrorDetail[]): string {
  if (!errors?.length) {
    return prefix;
  }

  const details = errors
    .map((error) => error.detail ?? error.title ?? error.type ?? "Unknown error")
    .join("; ");

  return `${prefix}: ${details}`;
}

function extractRateLimit(headers: Headers): RateLimitInfo {
  const remainingHeader = headers.get("x-rate-limit-remaining");
  const resetHeader = headers.get("x-rate-limit-reset");

  const parsedRemaining =
    remainingHeader !== null ? Number.parseInt(remainingHeader, 10) : Number.NaN;
  const parsedReset =
    resetHeader !== null ? Number.parseInt(resetHeader, 10) * 1000 : Number.NaN;

  const remaining = Number.isNaN(parsedRemaining) ? null : parsedRemaining;
  const resetMs = Number.isNaN(parsedReset) ? null : parsedReset;

  return {
    remaining,
    resetMs,
  };
}

function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) {
    return min;
  }

  return Math.min(Math.max(value, min), max);
}

