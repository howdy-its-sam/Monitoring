import * as cheerio from 'cheerio';
import type { BlogPost } from '../../types';

export async function fetchDeepMindBlog(): Promise<BlogPost[]> {
    const url = 'https://deepmind.google/blog/';
    try {
        const response = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        });

        if (!response.ok) {
            console.error(`Failed to fetch DeepMind blog: ${response.status} ${response.statusText}`);
            return [];
        }

        const html = await response.text();
        const $ = cheerio.load(html);
        const posts: BlogPost[] = [];

        // Based on observation: Titles are in H3, followed by links.
        // Or we can look for all links that look like blog posts.

        // Strategy: Find all 'a' tags. If they link to deepmind.google/blog/ or blog.google, and have a title nearby.
        // A safer bet given the markdown output "### Title ... [Learn more](url)"
        // is that the H3 contains the title, and the following 'a' tag contains the link.

        $('h3').each((_, element) => {
            const title = $(element).text().trim();
            // The link might be inside the H3 or immediately following it in a container
            // Let's look for the closest 'a' tag in the parent container or next sibling

            // Often these are wrapped in a card.
            // Let's try to find an 'a' tag with an href in the parent element.
            const parent = $(element).parent();
            const link = parent.find('a').attr('href') || parent.parent().find('a').attr('href');

            if (title && link) {
                const fullUrl = link.startsWith('http') ? link : `https://deepmind.google${link}`;

                // Filter out non-blog links if necessary
                if (fullUrl.includes('/blog/') || fullUrl.includes('blog.google')) {
                    posts.push({
                        id: fullUrl,
                        url: fullUrl,
                        title: title,
                        publishedAt: new Date().toISOString(), // Date is hard to extract without more specific selectors
                        sourceId: 'deepmind',
                        metadata: {
                            scraped: true
                        }
                    });
                }
            }
        });

        // Deduplicate
        const uniquePosts = Array.from(new Map(posts.map(p => [p.url, p])).values());
        return uniquePosts;

    } catch (error) {
        console.error('Error scraping DeepMind blog:', error);
        return [];
    }
}
