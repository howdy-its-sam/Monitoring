import { readFileSync } from 'fs';
import { join } from 'path';
import type { BlogSource } from '../types';
import { fetchDeepMindBlog } from '../fetchers/custom/deepmind';
import { fetchRssFeed } from '../fetchers/rss';
import { fetchOpenAIBlog } from '../fetchers/custom/openai';

// Define the shape of the JSON config
interface RssConfig {
    id: string;
    name: string;
    url: string;
    verified?: boolean;
}

function loadRssSources(): BlogSource[] {
    try {
        const configPath = join(process.cwd(), 'sources.json');
        const rawData = readFileSync(configPath, 'utf-8');
        const configs: RssConfig[] = JSON.parse(rawData);

        return configs.map(config => ({
            id: config.id,
            name: config.name,
            type: 'rss',
            url: config.url,
            fetcher: () => fetchRssFeed(config.id, config.url),
            verified: config.verified
        }));
    } catch (error) {
        console.error('Failed to load sources.json:', error);
        return [];
    }
}

export const sources: BlogSource[] = [
    // Custom Scrapers
    {
        id: 'deepmind',
        name: 'Google DeepMind',
        type: 'custom',
        url: 'https://deepmind.google/blog/',
        fetcher: fetchDeepMindBlog,
        verified: true
    },
    {
        id: 'openai',
        name: 'OpenAI',
        type: 'custom',
        url: 'https://openai.com/news/',
        fetcher: fetchOpenAIBlog,
        verified: true
    },
    // Dynamic RSS Sources
    ...loadRssSources()
];
