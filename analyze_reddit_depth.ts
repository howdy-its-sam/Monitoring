#!/usr/bin/env bun
import { readdirSync, readFileSync } from 'fs';
import { join } from 'path';

const threadsDir = '/Users/swilliamson/Monitoring/reddit/data/threads';
const files = readdirSync(threadsDir).filter(f => f.endsWith('.json'));

console.log(`Analyzing ${files.length} Reddit threads...\n`);

const stats: Array<{ file: string; nodes: number; maxDepth: number; comments: number }> = [];

for (const file of files.slice(0, 50)) {  // Sample first 50
  try {
    const data = JSON.parse(readFileSync(join(threadsDir, file), 'utf-8'));
    const nodes = Object.values(data) as any[];

    const maxDepth = Math.max(...nodes.map((n: any) => n.depth ?? 0));
    const commentCount = nodes.filter((n: any) => n.depth && n.depth > 0).length;

    stats.push({
      file: file,
      nodes: nodes.length,
      maxDepth: maxDepth,
      comments: commentCount
    });
  } catch (e) {
    console.error(`Error reading ${file}: ${e}`);
  }
}

// Sort by maxDepth
stats.sort((a, b) => b.maxDepth - a.maxDepth);

console.log('Top 10 threads by maximum depth:\n');
for (const s of stats.slice(0, 10)) {
  console.log(`  ${s.file}: ${s.nodes} nodes, ${s.comments} comments, max depth = ${s.maxDepth}`);
}

console.log('\nDepth distribution across all sampled threads:');
const depthCounts: Record<number, number> = {};
for (const s of stats) {
  depthCounts[s.maxDepth] = (depthCounts[s.maxDepth] || 0) + 1;
}

for (const [depth, count] of Object.entries(depthCounts).sort((a, b) => Number(a[0]) - Number(b[0]))) {
  console.log(`  Depth ${depth}: ${count} threads`);
}

console.log(`\nAverage max depth: ${(stats.reduce((sum, s) => sum + s.maxDepth, 0) / stats.length).toFixed(2)}`);
console.log(`Average nodes per thread: ${(stats.reduce((sum, s) => sum + s.nodes, 0) / stats.length).toFixed(2)}`);
console.log(`Average comments per thread: ${(stats.reduce((sum, s) => sum + s.comments, 0) / stats.length).toFixed(2)}`);
