import { getAccessToken } from "./auth";
import { RateLimiter } from "./rate_limiter";
import type { RedditNode, TemporalValue } from "./types";

interface RedditListing {
  kind: "Listing";
  data: {
    children: RedditThing[];
  };
}

interface RedditThing {
  kind: "t1" | "t3" | "more";
  data: any;
}

export class RedditAPI {
  private userAgent = "RedditScraper/2.0";
  private rateLimiter = new RateLimiter(600, 10); // Start high, let headers correct us

  /**
   * Fetches a thread and returns it as a flat list of Nodes.
   * @param postId The ID of the post (e.g. "1p1kpmu")
   */
  /**
   * Fetches a listing of posts from a subreddit.
   * @param subreddit Name of the subreddit (e.g. "LocalLLaMA")
   * @param sort Sort order ("new", "hot", "top")
   * @param limit Number of posts to fetch (max 100)
   * @param after Pagination cursor (fullname of the last post)
   */
  public async getListing(subreddit: string, sort = "new", limit = 100, after?: string): Promise<any[]> {
    // Wait for rate limit token
    await this.rateLimiter.wait();

    const token = await getAccessToken();
    const qs = new URLSearchParams({ limit: limit.toString() });
    if (after) qs.append("after", after);
    
    const url = `https://oauth.reddit.com/r/${subreddit}/${sort}?${qs.toString()}`;
    
    try {
      console.log(`Fetching listing ${url}...`);
      const response = await fetch(url, {
        headers: {
          "Authorization": `Bearer ${token}`,
          "User-Agent": this.userAgent
        }
      });

      if (!response.ok) {
        throw new Error(`Reddit API Error: ${response.status}`);
      }

      // Update rate limiter based on official Reddit headers
      const remaining = response.headers.get("x-ratelimit-remaining");
      if (remaining) {
        const val = parseFloat(remaining);
        if (!isNaN(val)) {
          this.rateLimiter.setTokens(val);
        }
      }

      const json = await response.json();
      if (!json.data || !json.data.children) {
          throw new Error("Invalid listing response structure");
      }
      
      // Map to a cleaner format immediately
      return json.data.children.map((child: any) => ({
          id: child.data.id,
          title: child.data.title,
          author: child.data.author,
          created_utc: child.data.created_utc,
          num_comments: child.data.num_comments,
          score: child.data.score,
          permalink: child.data.permalink,
          name: child.data.name // This is the 'fullname' needed for 'after' cursor
      }));
    } catch (e: any) {
      console.error(`Failed to fetch listing for r/${subreddit}: ${e.message}`);
      throw e;
    }
  }

  public async fetchThread(postId: string): Promise<RedditNode[]> {
    // Wait for rate limit token
    await this.rateLimiter.wait();

    const token = await getAccessToken();
    const url = `https://oauth.reddit.com/comments/${postId}?sort=confidence&limit=500`;
    
    console.log(`Fetching ${url}...`);
    const response = await fetch(url, {
      headers: {
        "Authorization": `Bearer ${token}`,
        "User-Agent": this.userAgent
      }
    });

    if (!response.ok) {
      throw new Error(`Reddit API Error: ${response.status}`);
    }

    // Update rate limiter based on official Reddit headers
    const remaining = response.headers.get("x-ratelimit-remaining");
    if (remaining) {
      const val = parseFloat(remaining);
      if (!isNaN(val)) {
        // Sync our local bucket with the server's truth
        this.rateLimiter.setTokens(val);
      }
    }

    const json = await response.json();
    return this.parseResponse(json);
  }

  /**
   * Parses a raw Reddit API response (Post + Comments) into a flat list of Nodes.
   * @param json The raw JSON response from the Reddit API (array of 2 listings).
   */
  public parseResponse(json: any): RedditNode[] {
    const listings = json as [RedditListing, RedditListing];
    // json[0] is the Post (t3)
    // json[1] is the Comments (t1)

    const nodes: RedditNode[] = [];
    const now = new Date().toISOString();

    // 1. Process Post
    const postThing = listings[0].data.children[0];
    if (postThing.kind === "t3") {
      nodes.push(this.parseThing(postThing, null, now));
    } else {
        console.warn("First element in response was not a t3 (Post).");
    }

    // 2. Process Comments (Recursive)
    // The listing itself isn't a thing, it HAS things.
    // Use the ID from the post we just parsed as the root parent
    const rootId = postThing.data.id;
    this.processListing(listings[1], rootId, nodes, now);

    return nodes;
  }

  private processListing(listing: RedditListing, parentId: string, nodes: RedditNode[], timestamp: string) {
    for (const child of listing.data.children) {
      if (child.kind === "t1") {
        nodes.push(this.parseThing(child, parentId, timestamp));
        
        // Recursion: Check for replies
        if (child.data.replies && child.data.replies !== "") {
           // Reddit returns empty string "" for no replies sometimes, instead of null/empty obj
           this.processListing(child.data.replies, child.data.id, nodes, timestamp);
        }
      }
      // TODO: Handle "kind: more" (Pagination)
      // For v1, we skip 'more' objects. The Python script had complex logic for this.
      // We will add that in Phase 3.
    }
  }

  private parseThing(thing: RedditThing, parentId: string | null, timestamp: string): RedditNode {
    const {
      id,
      author,
      created_utc,
      permalink,
      depth,
      score,
      body,
      selftext,
      subreddit,
      title,
      url,
      replies, // We don't store replies in the node, we traverse them
      ...rest
    } = thing.data;

    // Normalize ID (remove t1_ / t3_ prefixes if present - though usually data.id is clean)
    const nodeId = id; 

    return {
      id: nodeId,
      parentId: parentId,
      author: author || "[deleted]",
      createdUtc: created_utc,
      permalink: permalink,
      depth: depth || 0,
      
      // Initialize History
      scoreHistory: [{ value: score, timestamp }],
      textHistory: [{ value: body || selftext || "", timestamp }],
      
      isDeleted: body === "[deleted]" || body === "[removed]",
      deletedAt: null,
      
      // Metadata (mostly for root)
      subreddit: subreddit,
      title: title,
      url: url,
      
      // Capture everything else!
      extra: rest
    };
  }

}
