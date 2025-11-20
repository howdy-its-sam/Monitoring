import Parser from 'rss-parser';
import type { BlogPost } from '../types';

const parser = new Parser();

export async function fetchRssFeed(sourceId: string, feedUrl: string): Promise<BlogPost[]> {
    try {
        const feed = await parser.parseURL(feedUrl);

        return feed.items.map(item => ({
            id: item.guid || item.link || '',
            url: item.link || '',
            title: item.title || 'Untitled',
            content: item.content || item.contentSnippet || '',
            publishedAt: item.isoDate || item.pubDate || new Date().toISOString(),
            author: item.creator || item.author,
            sourceId: sourceId,
            metadata: {
                categories: item.categories,
                raw: item
            }
        }));
    } catch (error) {
        console.error(`Error fetching RSS feed for ${sourceId}:`, error);
        return [];
    }
}
