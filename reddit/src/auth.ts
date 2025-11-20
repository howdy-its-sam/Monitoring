import { join } from "path";
import { readFileSync, existsSync } from "fs";

interface Credentials {
  clientId: string;
  clientSecret: string;
  username: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  scope: string;
}

let cachedToken: string | null = null;
let tokenExpiry = 0;

function parseCredentialsTxt(): Credentials | null {
  // Try to find the legacy credentials file
  // We assume we are running from project root, so it's in reddit/reddit-adaptive-sampler
  // Or if running from inside reddit/, it's in reddit-adaptive-sampler
  
  let legacyPath = join(process.cwd(), "reddit/reddit-adaptive-sampler/reddit_credentials.txt");
  if (!existsSync(legacyPath)) {
     // Fallback: maybe we are running inside reddit/ already
     legacyPath = join(process.cwd(), "reddit-adaptive-sampler/reddit_credentials.txt");
  }
  
  if (!existsSync(legacyPath)) return null;

  const content = readFileSync(legacyPath, "utf-8");
  const lines = content.split("\n");
  const creds: Record<string, string> = {};

  for (const line of lines) {
    const [key, value] = line.split("=");
    if (key && value) {
      creds[key.trim()] = value.trim();
    }
  }

  return {
    clientId: creds["CLIENT_ID"],
    clientSecret: creds["CLIENT_SECRET"],
    username: creds["USERNAME"],
    password: creds["PASSWORD"],
  } as Credentials;
}

export async function getAccessToken(): Promise<string> {
  // Return cached token if valid (minus buffer)
  if (cachedToken && Date.now() < tokenExpiry - 60000) {
    return cachedToken;
  }

  // 1. Try Environment Variables (Standard)
  let creds: Credentials | null = {
    clientId: process.env.REDDIT_CLIENT_ID!,
    clientSecret: process.env.REDDIT_CLIENT_SECRET!,
    username: process.env.REDDIT_USERNAME!,
    password: process.env.REDDIT_PASSWORD!
  };

  // 2. Fallback to Legacy File
  if (!creds.clientId) {
    creds = parseCredentialsTxt();
  }

  if (!creds || !creds.clientId) {
    throw new Error("Reddit Credentials not found. Please set env vars or ensure reddit_credentials.txt exists.");
  }

  // 3. Authenticate
  const authString = Buffer.from(`${creds.clientId}:${creds.clientSecret}`).toString("base64");
  
  const response = await fetch("https://www.reddit.com/api/v1/access_token", {
    method: "POST",
    headers: {
      "Authorization": `Basic ${authString}`,
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": `RedditScraper/1.0 (by /u/${creds.username})`
    },
    body: new URLSearchParams({
      "grant_type": "password",
      "username": creds.username,
      "password": creds.password
    })
  });

  if (!response.ok) {
    throw new Error(`Auth Failed: ${response.status} ${response.statusText}`);
  }

  const data = await response.json() as TokenResponse;
  
  cachedToken = data.access_token;
  tokenExpiry = Date.now() + (data.expires_in * 1000);
  
  console.log(`✅ Authenticated as ${creds.username}`);
  return cachedToken;
}
