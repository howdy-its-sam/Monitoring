# Manual Kit Dataset Summary
## 14-Day Aggressive Sample (Nov 11-25, 2025)

**Generated:** 2025-11-25
**Coverage:** 14 days (Nov 11-25, 2025)
**Total Size:** 58.87 MB

---

## Data Breakdown

### Reddit (Discourse Analysis)
- **Threads:** 3,655 unique threads
- **Size:** 3.21 MB
- **Lines:** ~73,000+
- **Source:** Main collection from backfill (/reddit/data/threads/)
- **Subreddits:** 98 AI/ML/tech communities
- **Format:** Structured text with thread summaries (single-snapshot, no temporal confusion)

**Coverage:**
- Thread titles, authors, subreddits
- Post content and URLs
- Comment counts per thread
- Metadata (created timestamps, scores)

### ArXiv (Academic Research)
- **Papers:** 3,163 unique papers
- **Size:** 5.78 MB
- **Lines:** 3,162 (JSON Lines format)
- **Source:** Metadata from 83 category fetches (Nov 12-25)
- **Categories:** cs.AI, cs.LG, cs.CL, cs.CV, cs.RO, stat.ML, and 15+ others
- **Format:** JSON Lines (one paper per line)

**Coverage:**
- Titles, authors, abstracts
- ArXiv IDs and URLs
- Primary and secondary categories
- Published and updated dates
- PDF links
- Comments/notes (when available)

### Blogs (Industry & News)
- **Posts:** 3,316 unique posts
- **Size:** 49.88 MB
- **Lines:** 3,315 (JSON Lines format)
- **Source:** 54 blog sources from data directory
- **Sources:** Stability AI, Neo4j, LangChain, Google Research, Anthropic, OpenAI, and 48+ others
- **Format:** JSON Lines (one post per line)

**Coverage:**
- Titles, URLs, publication dates
- Full content (HTML)
- Content snippets (plain text)
- Source IDs
- Metadata (authors, categories, GUIDs)

---

## Token Estimates

**Conservative estimate:** ~17-19 million tokens
- Reddit: ~1M tokens (3,655 threads with comments)
- ArXiv: ~1.5-2M tokens (abstracts + metadata)
- Blogs: ~14-16M tokens (full content included)

**Note:** Blog data dominates token count due to full HTML content inclusion.

---

## ChatGPT Pro Research Mode Compatibility

✅ **Feasible** for ChatGPT Pro with highest-tier plan
- Research mode uses multi-stage processing
- Can handle 30-60MB inputs via chunking
- Will process each domain separately, then synthesize

**Recommended approach:**
1. Upload all files to ChatGPT Pro
2. Use INSTRUCTIONS_FOR_LLM.md to orchestrate
3. Research mode will chunk and process progressively
4. Expect 10-15 minute processing time

---

## Data Quality Notes

### Deduplication
- ✅ Reddit: Deduplicated by thread ID
- ✅ ArXiv: Deduplicated by paper ID
- ✅ Blogs: Deduplicated by URL/ID

### Temporal Coverage
- Reddit: Mixed (some old threads with recent activity)
- ArXiv: Strong (Nov 12-25, fresh submissions)
- Blogs: Strong (Nov 11-25, based on file modification time)

### Known Issues
- Blog `publishedAt` dates may not be accurate (some show Feb 2025)
- Relying on file modification timestamps for blog temporal filtering
- Reddit DAG structure includes historical threads with recent comments

---

## Files Included

```
manual_kit/
├── INSTRUCTIONS_FOR_LLM.md
├── DATASET_SUMMARY.md (this file)
├── data/
│   ├── reddit/
│   │   └── reddit_data.txt (774 KB)
│   ├── blogs/
│   │   └── all_blogs.txt (50 MB)
│   └── arxiv/
│       └── all_arxiv.txt (5.8 MB)
└── prompts/
    ├── prompt_reddit_analyst.md
    ├── prompt_blog_analyst.md
    ├── prompt_arxiv_analyst.md
    └── prompt_master_synthesis.md
```

---

## Next Steps

1. **Zip the manual_kit directory**
   ```bash
   cd /Users/swilliamson/Monitoring
   zip -r manual_kit_14day_$(date +%Y%m%d).zip manual_kit/
   ```

2. **Upload to ChatGPT Pro**
   - Extract zip in ChatGPT interface
   - Point ChatGPT to INSTRUCTIONS_FOR_LLM.md
   - Use research mode with extended thinking

3. **Expect Output:**
   - Reddit Analysis Report (~1,200-1,600 words)
   - Blog Analysis Report (~1,200-1,600 words)
   - ArXiv Analysis Report (~1,200-1,600 words)
   - Master Daily Brief (~1,500-2,500 words, expandable for historic days)

---

## Comparison to Original Manual Kit

| Metric | Original (7h-10d) | This Version (14d) | Increase |
|--------|-------------------|-------------------|----------|
| Reddit | 7,129 lines (394 KB) | ~73,000 lines (3.2 MB) | +924% / +713% |
| Blogs | 3,002 lines (1.1 MB) | 3,315 lines (50 MB) | +10% / +4,445% |
| ArXiv | 160,365 lines (10.1 MB) | 3,162 lines (5.8 MB) | -98% / -43% |
| **Total** | **~11.7 MB** | **~58.9 MB** | **+403%** |

**Key differences:**
- ArXiv: Switched from verbose format to compact JSON Lines (more papers, less size)
- Blogs: Massive increase due to full content inclusion from 54 sources
- Reddit: **Massive increase** from 759 to 3,655 threads (+381%) using full backfill collection

---

## Revision History

- **v1.1** (2025-11-25): Updated with full Reddit collection
  - **3,655 Reddit threads** (was 759)
  - 3,163 ArXiv papers
  - 3,316 blog posts
  - Total: 58.87 MB

- **v1.0** (2025-11-25): Initial 14-day aggressive sample
  - 759 Reddit threads
  - 3,163 ArXiv papers
  - 3,316 blog posts
  - Total: 56.41 MB
