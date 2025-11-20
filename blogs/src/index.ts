import { sources } from './sources';
import { mkdir, writeFile } from 'fs/promises';
import { join } from 'path';

async function main() {
    console.log('Starting blog ingestion...');

    const historyPath = join(process.cwd(), 'history.json');
    let history: Set<string> = new Set();

    try {
        const historyData = await import(historyPath);
        history = new Set(historyData.default);
        console.log(`Loaded ${history.size} URLs from history.`);
    } catch (e) {
        console.log('No history found, starting fresh.');
    }

    // Create new_posts directory
    const newPostsDir = join(process.cwd(), 'new_posts');
    await mkdir(newPostsDir, { recursive: true });

    const newOnly = process.argv.includes('--new-only');

    const sourcesToProcess = newOnly
        ? sources.filter(s => !s.verified)
        : sources;

    console.log(`Processing ${sourcesToProcess.length} sources (Mode: ${newOnly ? 'New Only' : 'All'})...`);

    let totalNewPosts = 0;

    for (const source of sourcesToProcess) {
        console.log(`Fetching ${source.name} (${source.id})...`);

        try {
            const posts = await source.fetcher();

            // Filter for new posts
            const newPosts = posts.filter(post => !history.has(post.url));

            console.log(`Found ${posts.length} posts (${newPosts.length} new) for ${source.id}`);

            if (newPosts.length > 0) {
                const sourceDir = join(newPostsDir, source.id);
                await mkdir(sourceDir, { recursive: true });

                const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                const filename = `${timestamp}.json`;
                const filePath = join(sourceDir, filename);

                await writeFile(filePath, JSON.stringify(newPosts, null, 2));
                console.log(`Saved ${newPosts.length} new posts to ${filePath}`);

                // Update history in memory
                newPosts.forEach(post => history.add(post.url));
                totalNewPosts += newPosts.length;
            }
        } catch (error) {
            console.error(`Failed to ingest ${source.id}:`, error);
        }
    }

    // Save updated history
    await writeFile(historyPath, JSON.stringify(Array.from(history), null, 2));
    console.log(`Ingestion complete. Total new posts: ${totalNewPosts}. History updated.`);
}

main().catch(console.error);
