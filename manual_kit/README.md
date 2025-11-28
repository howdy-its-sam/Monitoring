# Manual Kit for ChatGPT Analysis

This directory contains everything needed to run a comprehensive AI/ML intelligence analysis using ChatGPT Pro.

## Contents

- `INSTRUCTIONS_FOR_LLM.md` - Orchestration instructions for ChatGPT
- `DATASET_SUMMARY.md` - Detailed breakdown of data coverage
- `data/` - Raw data from 3 domains (Reddit, Blogs, ArXiv)
- `prompts/` - 4 analysis prompts (updated with latest improvements)

## Quick Start

1. **Zip this directory:**
   ```bash
   cd /Users/swilliamson/Monitoring
   zip -r manual_kit_$(date +%Y%m%d).zip manual_kit/
   ```

2. **Upload to ChatGPT Pro** (with research mode enabled)

3. **Paste this into ChatGPT:**
   ```
   I've uploaded a zip file containing intelligence data from Reddit, tech blogs, and ArXiv papers covering the last 14 days (Nov 11-25, 2025).

   Please:
   1. Extract the zip file
   2. Read INSTRUCTIONS_FOR_LLM.md
   3. Follow the 4-step pipeline to generate a Master Daily Brief

   Use research mode with extended thinking for best results.
   ```

4. **Wait for analysis** (~10-15 minutes for research mode to process 56 MB)

5. **Receive:**
   - Reddit Situation Report
   - Blog/Industry Analysis
   - ArXiv Research Report
   - Master Daily Brief (synthesizing all 3 domains)

## Dataset Overview

**14-Day Window:** Nov 11-25, 2025
**Total Size:** 58.9 MB (~17-19M tokens)

- **Reddit:** 3,655 threads (3.2 MB)
- **Blogs:** 3,316 posts (50 MB)
- **ArXiv:** 3,163 papers (5.8 MB)

See `DATASET_SUMMARY.md` for detailed breakdown.

## Prompt Features

All 4 prompts have been updated with:
- ✅ Temporal analysis (BREAKING/EMERGING/SUSTAINED/RESURGENT tags)
- ✅ Ultra-dense signal dumps for cross-domain entity matching
- ✅ Hybrid confidence scoring (overall + key claims)
- ✅ Exponential temporal weighting (0-24h=1.0x, 24-48h=0.6x, etc.)
- ✅ Discourse divergence analysis
- ✅ Flexible length (expand for historic days, contract for boring days)
- ✅ Signal convergence matrix showing cross-domain alignment

## Expected Output

**Master Daily Brief** (~1,500-2,500 words) including:
1. THE HEADLINE (one sentence if user only reads one thing)
2. SIGNAL CONVERGENCE MATRIX (where domains align)
3. CROSS-DOMAIN CONNECTIONS (the "aha!" insights)
4. THE NARRATIVE ARC (how today fits into trends)
5. DISCOURSE DIVERGENCE (how each domain approaches same topics)
6. DIVERGENCE & CONFLICT (where domains disagree)
7. COMBINED WATCHLIST (top 5 items to monitor)
8. DOMAIN SUMMARIES (3 bullets each)

Plus individual domain reports with confidence scores and signal dumps.

---

**Last Updated:** 2025-11-25
**Version:** 1.1 (14-day aggressive sample with full Reddit collection)
