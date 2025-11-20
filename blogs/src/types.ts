export interface BlogPost {
    id: string;           // Unique ID (URL or GUID)
    url: string;          // Canonical Link
    title: string;
    content?: string;     // Full text or summary
    publishedAt: string;  // ISO8601
    author?: string;
    sourceId: string;     // e.g., "openai", "deepmind"
    metadata: Record<string, any>; // Raw source data
}

export interface BlogSource {
    id: string;
    name: string;
    type: 'rss' | 'custom';
    url: string; // RSS feed URL or Main Blog URL
    fetcher: () => Promise<BlogPost[]>;
    verified?: boolean;
}
