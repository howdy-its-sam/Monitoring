import { readdir, readFile, writeFile } from 'fs/promises';
import { join } from 'path';
import type { BlogPost } from './types';

async function buildHistory() {
    const dataDir = join(process.cwd(), 'data');
    const historyPath = join(process.cwd(), 'history.json');
    const seenUrls = new Set<string>();

    try {
        const sources = await readdir(dataDir, { withFileTypes: true });

        for (const source of sources) {
            if (!source.isDirectory()) continue;

            const sourceDir = join(dataDir, source.name);
            const files = await readdir(sourceDir);

            for (const file of files) {
                if (!file.endsWith('.json')) continue;

                const filePath = join(sourceDir, file);
                const content = await readFile(filePath, 'utf-8');
                try {
                    const posts: BlogPost[] = JSON.parse(content);
                    for (const post of posts) {
                        if (post.url) {
                            seenUrls.add(post.url);
                        }
                    }
                } catch (e) {
                    console.error(`Error parsing ${filePath}:`, e);
                }
            }
        }

        const history = Array.from(seenUrls);
        await writeFile(historyPath, JSON.stringify(history, null, 2));
        console.log(`History built with ${history.length} unique URLs.`);

    } catch (error) {
        console.error('Failed to build history:', error);
    }
}

buildHistory();
