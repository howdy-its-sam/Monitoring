---
description: Load Reddit scraper design context and current status
---

Please refresh your context on this project by reviewing the following:

1. **Design Philosophy:** Read DESIGN.md - pay attention to core principles, anti-patterns, and provisional nature of metrics

2. **Recent Decisions:** Read the top 3 entries from DECISIONS.md - understand recent architectural changes

3. **Current Status:** Run ./scraper_report.sh and extract:
   - Current waste % (target: <10%)
   - Average buffer tokens (target: 5-15)
   - Scrape patterns (compare to provisional targets in DESIGN.md)

4. **Check for Violations:** Look for anti-patterns:
   - Any `time.sleep()` calls with fixed durations in unified_scraper.py or rate_limiter.py
   - Time-based filtering in scheduler (get_ready_posts should return all posts)
   - Multiple temporal control layers

After loading context, provide a brief summary:

```
## Project Status

**Core Principle:** [restate from DESIGN.md]

**Current Metrics:**
- Waste: X% (target <10%)
- Buffer: Y tokens (target 5-15)

**Recent Changes:**
- [List top 2-3 from DECISIONS.md]

**Compliance Check:**
✅ or ❌ for each anti-pattern

**Next Focus:**
[Based on which target metric is furthest from goal]
```

This ensures I have full context before we continue work.
