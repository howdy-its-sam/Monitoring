# Data Preprocessing Log

## Phase 1 Improvements (2025-11-25)

### Motivation
Analyzed ChatGPT and Gemini thinking traces from first manual_kit run. Found significant confusion around:
- Data format ambiguity (is it JSON? plain text?)
- Truncation paranoia (spent enormous effort checking for "...")
- Missing temporal metadata (had to hunt for timestamp fields)
- Manual date filtering required mid-analysis
- File size anxiety

### Solution: Enhanced Aggregation Script (v2)

**Location:** `/Users/swilliamson/Monitoring/aggregate_manual_kit_v2.ts`

**Key Changes:**

1. **Metadata Headers** - Added comprehensive header to each output file:
   - Format specification (JSON Lines)
   - Total items and date range
   - Temporal field location
   - Pre-filtered confirmation
   - Summary statistics

2. **Content-Based Filtering** - Changed from file mtime to actual content timestamps:
   - Reddit: Uses `createdUtc` field
   - Blogs: Uses `publishedAt/published/date` field
   - ArXiv: Uses `published` field
   - All items verified within Nov 11-25, 2025 window

3. **Standardized Temporal Fields** - Added to every item:
   ```json
   {
     "meta_timestamp": <unix_timestamp>,
     "meta_date_human": "YYYY-MM-DD",
     "meta_days_ago": <number>,
     "meta_temporal_tag": "BREAKING/EMERGING/SUSTAINED/RESURGENT",
     "meta_temporal_weight": <0.1-1.0>
   }
   ```

4. **Pre-Calculated Weights** - Applied exponential temporal decay:
   - 0-24h old: 1.0x
   - 24-48h old: 0.6x
   - 48-72h old: 0.3x
   - >72h old: 0.1x

5. **Summary Statistics** - Added to headers:
   - Top sources/subreddits/categories
   - Total comments/posts
   - Temporal distribution by tag

### Results

**Dataset Size:**
- Reddit: 3,655 threads (141.31 MB)
- ArXiv: 2,784 papers (5.53 MB)
- Blogs: 317 posts (3.37 MB)
- **Total: 6,756 items (150.21 MB)**

**Output Format:**
- All domains: `.jsonl` (JSON Lines)
- Metadata header at top
- One JSON object per line after header

### Expected Impact

**Eliminated Confusion Points:**
- ✅ Format ambiguity (explicitly stated as JSON Lines)
- ✅ Truncation checking (clear statement of completeness)
- ✅ Timestamp hunting (standardized meta_timestamp field)
- ✅ Manual date filtering (pre-filtered with verification)
- ✅ Temporal calculations (pre-calculated weights/tags)

**Estimated Improvements:**
- 60-70% reduction in data discovery time
- 50+ fewer confusion events
- More thinking devoted to analysis vs data wrangling

---

## Phase 2 Planning (Future)

**Medium Priority:**
- [ ] Add data summaries at file start
- [ ] Pre-calculate temporal weights
- [ ] Convert all to `.jsonl` format consistency

**Low Priority:**
- [ ] Add cross-reference IDs for entity matching
- [ ] Provide sample data snippets in INSTRUCTIONS_FOR_LLM.md

---

## Technical Notes

### Reddit Data Format
- File structure: `{nodeId: {node_data}}`
- Timestamp field: `createdUtc` (Unix seconds)
- Alternative: `scoreHistory[0].timestamp` (ISO string)
- Comment structure: DAG with depth field

### Blog Data Format
- Date field: `publishedAt` or `published` or `date`
- Format: ISO string
- Structure: Varies by source

### ArXiv Data Format
- Date field: `published`
- Format: ISO string
- Nested in: `{entries: [...]}`

---

## Usage

Run enhanced aggregation:
```bash
bun aggregate_manual_kit_v2.ts
```

Output files:
- `/manual_kit/data/reddit/reddit_data.jsonl`
- `/manual_kit/data/blogs/all_blogs.jsonl`
- `/manual_kit/data/arxiv/all_arxiv.jsonl`
