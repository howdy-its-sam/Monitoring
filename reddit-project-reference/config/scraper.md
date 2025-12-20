---
description: Load Reddit scraper design context and current status
---

Please refresh your context on this project by reviewing the following:

1. **Design Philosophy:** Read docs/DESIGN.md - pay attention to core principles, anti-patterns, and provisional nature of metrics

2. **Recent Decisions:** Read the top 3 entries from docs/DECISIONS.md - understand recent architectural changes

3. **Current Status:** Run scripts/scraper_report.sh and extract:
   - Current waste % (target: <10%)
   - Average buffer tokens (target: 5-15)
   - Scrape patterns (compare to provisional targets in docs/DESIGN.md)

4. **Check for Violations:** Look for anti-patterns:
   - Any `time.sleep()` calls with fixed durations in src/unified_scraper.py or src/rate_limiter.py
   - Time-based filtering in scheduler (get_ready_posts should return all posts)
   - Multiple temporal control layers

5. **Archive Review:** Check .archive/ARCHIVE_LOG.md for files moved out of workflow:
   - Review archive creation date and last review date
   - Assess if any archived files were needed during recent work
   - Based on archive age, determine if deprecated files can be safely deleted:
     * After 1 month: Check if we needed anything from archive
     * After 3 months: Consider permanent deletion of deprecated/
     * After 6 months: Safe to delete deprecated/, keep reference/ indefinitely
   - Update "Last reviewed" date in ARCHIVE_LOG.md after review

After loading context, provide a brief summary:

```
## Project Status

**Core Principle:** [restate from docs/DESIGN.md]

**Current Metrics:**
- Waste: X% (target <10%)
- Buffer: Y tokens (target 5-15)

**Recent Changes:**
- [List top 2-3 from docs/DECISIONS.md]

**Compliance Check:**
✅ or ❌ for each anti-pattern

**Archive Status:**
- Created: [date from .archive/ARCHIVE_LOG.md]
- Last reviewed: [date from .archive/ARCHIVE_LOG.md]
- Age: X days (review schedule: 1mo/3mo/6mo)
- Assessment: [Have we needed any archived files? Are we ready to delete deprecated/?]

**Next Focus:**
[Based on which target metric is furthest from goal]
```

This ensures I have full context before we continue work.
