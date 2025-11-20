import * as cheerio from 'cheerio';
import type { BlogPost } from '../../types';

export async function fetchOpenAIBlog(): Promise<BlogPost[]> {
    const url = 'https://openai.com/news/';
    try {
        const response = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        });

        if (!response.ok) {
            console.error(`Failed to fetch OpenAI blog: ${response.status} ${response.statusText}`);
            return [];
        }

        const html = await response.text();
        const $ = cheerio.load(html);
        const posts: BlogPost[] = [];

        // Note: This selector is a best-guess and will likely need adjustment based on actual DOM
        // OpenAI's site structure changes frequently.
        // Looking for article links or list items.
        $('a[href*="/index/"], a[href*="/news/"]').each((_, element) => {
            const link = $(element);
            const href = link.attr('href');
            const title = link.text().trim();

            if (href && title && title.length > 5) { // Filter out small navigation links
                const fullUrl = href.startsWith('http') ? href : `https://openai.com${href}`;

                posts.push({
                    id: fullUrl,
                    url: fullUrl,
                    title: title,
                    publishedAt: new Date().toISOString(), // OpenAI index often doesn't show dates easily
                    sourceId: 'openai',
                    metadata: {
                        rawUrl: href
                    }
                });
            }
        });

        // Deduplicate by URL
        const uniquePosts = Array.from(new Map(posts.map(p => [p.url, p])).values());
        return uniquePosts;

    } catch (error) {
        console.error('Error scraping OpenAI blog:', error);
        return [];
    }
}
