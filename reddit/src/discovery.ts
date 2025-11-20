import { getAccessToken } from "./auth";

export class Discovery {
  private userAgent = "RedditScraper/2.0";
  private knownPosts: Set<string> = new Set();

  public async scanSubreddit(subreddit: string): Promise<string[]> {
    const token = await getAccessToken();
    const url = `https://oauth.reddit.com/r/${subreddit}/new?limit=25`;
    
    console.log(`🔍 Scanning r/${subreddit}...`);
    const response = await fetch(url, {
      headers: {
        "Authorization": `Bearer ${token}`,
        "User-Agent": this.userAgent
      }
    });

    if (!response.ok) {
      console.error(`Error scanning r/${subreddit}: ${response.status}`);
      return [];
    }

    const json = await response.json() as any;
    const newIds: string[] = [];

    for (const child of json.data.children) {
      const id = child.data.id;
      if (!this.knownPosts.has(id)) {
        this.knownPosts.add(id);
        newIds.push(id);
      }
    }

    if (newIds.length > 0) {
      console.log(`   Found ${newIds.length} new posts.`);
    }
    
    return newIds;
  }
}
