# Project Notes & To-Dos

**Last Updated:** 2025-11-25

---

## Current Status

### Manual Kit for ChatGPT/Gemini Analysis
- ✅ Phase 1 preprocessing improvements complete
- ✅ Enhanced aggregation script (v2) tested and working
- ✅ Thinking analysis toolkit created
- 🔄 Waiting for next manual_kit run to validate improvements

**Files:**
- Analysis prompts: `/Monitoring/prompts/` (4 prompts)
- Data aggregation: `/Monitoring/aggregate_manual_kit_v2.ts`
- Manual kit: `/Monitoring/manual_kit/`
- Thinking analysis: `/Monitoring/manual_kit/runs/` (templates, HTML capture files)
- Preprocessing log: `/Monitoring/manual_kit/PREPROCESSING_LOG.md`

---

## Active To-Dos

### High Priority
- [ ] Run next manual_kit analysis with v2 data (ChatGPT + Gemini)
- [ ] Capture thinking traces using HTML DOM method
- [ ] Fill out comparative analysis templates
- [ ] Measure improvement vs previous run

### Medium Priority
- [ ] Implement Phase 2 preprocessing (if needed after validation)
- [ ] Document best practices from comparative analysis
- [ ] Create iteration workflow document

### Low Priority
- [ ] Explore automated thinking extraction
- [ ] Build metrics dashboard for tracking improvements over time

---

## Ongoing Work

### Blog Ingestion System
- Status: Some feeds failing (42% dead feeds)
- Recent changes: Removed browser-based fetching
- Location: `/Monitoring/blogs/`

### Reddit Collection
- Status: 3,655 threads collected
- Location: `/Monitoring/reddit/data/threads/`
- Format: Single-snapshot (clean)

### ArXiv Collection
- Status: Working
- Location: `/Monitoring/preprints/arxiv/data/`

---

## Key Decisions & Context

### Manual Kit Philosophy
- "Noise is signal" - Redundancy across domains shows strength
- Dynamic weighting based on confidence/recency
- Quality over arbitrary targets
- Flexible synthesis length

### Data Preprocessing Strategy
- Content-based filtering (not file mtime)
- Standardized temporal fields across domains
- Pre-calculate weights and tags
- Comprehensive metadata headers

### Analysis Approach
- Use ChatGPT Pro (Research Mode) for analysis
- Run parallel comparison with Gemini 2.0 Flash (Thinking Mode)
- Analyze thinking traces to improve prompts iteratively
- Track metrics: confusion events, processing time, quality scores

---

## Questions for Future Sessions

- [ ] Should we add entity pre-extraction for Phase 2?
- [ ] Do we need automated prompt refinement based on thinking analysis?
- [ ] Should we create a template for daily brief output formatting?

---

## Useful Commands

### Run aggregation:
```bash
bun aggregate_manual_kit_v2.ts
```

### Package manual kit:
```bash
cd /Users/swilliamson/Monitoring
zip -r manual_kit_$(date +%Y%m%d).zip manual_kit/
```

### Check background tasks:
Use `/tasks` command in Claude Code

---

## Notes Template

### [Date] - [Topic]
**Context:** [What were we working on?]
**Outcome:** [What was accomplished?]
**Next Steps:** [What's left to do?]
**Blockers:** [Any issues?]

---

## Session History

### 2025-11-25: Phase 1 Preprocessing Implementation
**Context:** Analyzed ChatGPT + Gemini thinking traces, found significant data format confusion
**Outcome:**
- Created enhanced aggregation script (v2)
- Added metadata headers, standardized temporal fields, content-based filtering
- Created thinking analysis toolkit
- Documented all improvements

**Next Steps:**
- Run next analysis with improved data
- Validate that confusion is reduced
- Track metrics

**Blockers:** None
