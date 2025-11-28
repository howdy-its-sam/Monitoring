# Analysis Runs

Store ChatGPT and Gemini transcripts and thinking analyses here for comparative evaluation.

## Naming Convention

```
YYYY-MM-DD_vX.X_chatgpt_transcript.md    - ChatGPT conversation transcript
YYYY-MM-DD_vX.X_chatgpt_thinking.md      - ChatGPT thinking traces
YYYY-MM-DD_vX.X_chatgpt_analysis.md      - ChatGPT analysis template
YYYY-MM-DD_vX.X_chatgpt_output.md        - ChatGPT final brief

YYYY-MM-DD_vX.X_gemini_transcript.md     - Gemini conversation transcript
YYYY-MM-DD_vX.X_gemini_thinking.md       - Gemini thinking traces
YYYY-MM-DD_vX.X_gemini_analysis.md       - Gemini analysis template
YYYY-MM-DD_vX.X_gemini_output.md         - Gemini final brief

YYYY-MM-DD_vX.X_dom_capture_chatgpt.html - ChatGPT DOM capture test
YYYY-MM-DD_vX.X_dom_capture_gemini.html  - Gemini DOM capture test
YYYY-MM-DD_vX.X_comparison.md            - Side-by-side comparison
```

## Example

```
2025-11-25_v1.1_chatgpt_transcript.md
2025-11-25_v1.1_chatgpt_thinking.md
2025-11-25_v1.1_chatgpt_analysis.md
2025-11-25_v1.1_chatgpt_output.md

2025-11-25_v1.1_gemini_transcript.md
2025-11-25_v1.1_gemini_thinking.md
2025-11-25_v1.1_gemini_analysis.md
2025-11-25_v1.1_gemini_output.md

2025-11-25_v1.1_comparison.md
```

## Quick Analysis Workflow

### For Each Model (ChatGPT & Gemini)

1. **Capture DOM** using the respective HTML file to test completeness
2. **Export transcript** (use Share → Copy link or manual copy)
3. **Extract thinking** sections to `*_thinking.md`
4. **Fill out template** using respective template → save as `*_analysis.md`
5. **Save final output** to `*_output.md`

### Comparative Analysis

6. **Create comparison** file documenting differences in reasoning, speed, quality
7. **Identify strengths** of each model for different analysis steps
8. **Iterate** prompts based on combined insights from both runs

## Tracking Improvements

Create a summary file tracking key metrics for both models:

| Run | Model | Date | Time | Confusion Events | Quality | Key Changes |
|-----|-------|------|------|------------------|---------|-------------|
| v1.0 | ChatGPT | 2025-11-25 | 35 min | 6 | 7/10 | Initial run |
| v1.0 | Gemini | 2025-11-25 | 28 min | 4 | 7/10 | Initial run |
| v1.1 | ChatGPT | 2025-11-26 | 28 min | 3 | 8/10 | Added format examples |
| v1.1 | Gemini | 2025-11-26 | 22 min | 2 | 8/10 | Added format examples |
| v1.2 | ChatGPT | 2025-11-27 | 22 min | 1 | 9/10 | Clarified synthesis |
| v1.2 | Gemini | 2025-11-27 | 18 min | 1 | 9/10 | Clarified synthesis |

### Comparison Metrics to Track

- **Speed:** Which model completes each step faster?
- **Reasoning Quality:** Which shows deeper analysis?
- **Instruction Following:** Which adheres better to prompts?
- **Output Quality:** Which produces better final briefs?
- **Confusion Patterns:** Where does each model struggle?
