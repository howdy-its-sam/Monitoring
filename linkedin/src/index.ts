const DEFAULT_CREDENTIAL_TARGET =
  Bun.env.LINKEDIN_CREDENTIALS_PATH ?? new URL("../linkedin_credentials.env", import.meta.url);

type LinkedInCredentials = {
  clientId: string;
  clientSecret: string;
  accessToken: string;
  refreshToken: string;
  redirectUri: string;
};

export async function loadLinkedInCredentials(
  target: string | URL = DEFAULT_CREDENTIAL_TARGET
): Promise<LinkedInCredentials> {
  const file = Bun.file(target);

  if (!(await file.exists())) {
    throw new Error(
      `LinkedIn credentials file not found. Set LINKEDIN_CREDENTIALS_PATH or create linkedin_credentials.env.`
    );
  }

  const contents = await file.text();
  const entries = parseEnv(contents);

  const clientId = entries.get("LINKEDIN_CLIENT_ID");
  const clientSecret = entries.get("LINKEDIN_CLIENT_SECRET");
  const accessToken = entries.get("LINKEDIN_ACCESS_TOKEN");
  const refreshToken = entries.get("LINKEDIN_REFRESH_TOKEN");
  const redirectUri = entries.get("LINKEDIN_REDIRECT_URI");

  if (!clientId || !clientSecret || !accessToken || !refreshToken || !redirectUri) {
    throw new Error(
      `LinkedIn credentials file is missing one or more required fields (LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_ACCESS_TOKEN, LINKEDIN_REFRESH_TOKEN, LINKEDIN_REDIRECT_URI).`
    );
  }

  return {
    clientId,
    clientSecret,
    accessToken,
    refreshToken,
    redirectUri,
  };
}

function parseEnv(raw: string): Map<string, string> {
  const map = new Map<string, string>();

  for (const line of raw.split(/\r?\n/)) {
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

async function main() {
  try {
    await loadLinkedInCredentials();
    console.log("LinkedIn credentials verified. Ready to add ingestion logic.");
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(message);
    Bun.exit(1);
  }
}

if (import.meta.main) {
  main();
}

