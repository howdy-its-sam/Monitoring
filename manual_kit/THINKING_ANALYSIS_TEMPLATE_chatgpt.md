# ChatGPT Thinking Process Analysis Template

Use this template to capture and analyze ChatGPT's reasoning during the analysis pipeline.

## Run Metadata
- **Date:** [YYYY-MM-DD]
- **Model:** ChatGPT Pro / Research Mode
- **Dataset Version:** [e.g., v1.1]
- **Total Processing Time:** [minutes]

---

## Step 1: Reddit Analysis

### Observed Thinking Patterns
```
[Copy/paste relevant excerpts from ChatGPT's thinking here]
```

### Confusion Points
- [ ] **Issue:** [What was unclear?]
  - **Evidence:** [Quote from thinking]
  - **Impact:** [Did it slow down? Make errors?]
  - **Fix:** [How could the prompt be improved?]

### Efficient Patterns
- **Pattern:** [What went smoothly?]
  - **Why it worked:** [Analysis]
  - **Keep doing:** [Recommendation]

---

## Step 2: Blog Analysis

### Observed Thinking Patterns
```
[Copy/paste relevant excerpts]
```

### Confusion Points
- [ ] **Issue:**
  - **Evidence:**
  - **Impact:**
  - **Fix:**

### Efficient Patterns
- **Pattern:**
  - **Why it worked:**
  - **Keep doing:**

---

## Step 3: ArXiv Analysis

### Observed Thinking Patterns
```
[Copy/paste relevant excerpts]
```

### Confusion Points
- [ ] **Issue:**
  - **Evidence:**
  - **Impact:**
  - **Fix:**

### Efficient Patterns
- **Pattern:**
  - **Why it worked:**
  - **Keep doing:**

---

## Step 4: Master Synthesis

### Observed Thinking Patterns
```
[Copy/paste relevant excerpts]
```

### Confusion Points
- [ ] **Issue:**
  - **Evidence:**
  - **Impact:**
  - **Fix:**

### Efficient Patterns
- **Pattern:**
  - **Why it worked:**
  - **Keep doing:**

---

## Cross-Cutting Issues

### Data Format Confusion
- [ ] **JSON parsing issues:** [Details]
- [ ] **Missing fields:** [Which fields? Which domain?]
- [ ] **Format inconsistencies:** [Between what?]

### Instruction Ambiguity
- [ ] **Unclear directive:** [Which instruction?]
  - **Interpretation:** [How did the model interpret it?]
  - **Intended meaning:** [What did we want?]
  - **Proposed rewrite:** [New version]

### Context Window / Memory
- [ ] **Forgot earlier context:** [What was forgotten?]
- [ ] **Had to re-read:** [What needed re-reading?]
- [ ] **Summary loss:** [What detail was lost in summarization?]

---

## Quantitative Metrics

### Time Breakdown (if visible)
- Step 1 (Reddit): [X minutes]
- Step 2 (Blogs): [X minutes]
- Step 3 (ArXiv): [X minutes]
- Step 4 (Synthesis): [X minutes]
- **Bottleneck:** [Which step took longest?]

### Re-processing
- **Steps repeated:** [Which steps? Why?]
- **Backtracking:** [When did the model go back?]

---

## Priority Improvements

Rank these by impact:

1. **HIGH PRIORITY:**
   - [ ] [Issue + Proposed fix]

2. **MEDIUM PRIORITY:**
   - [ ] [Issue + Proposed fix]

3. **LOW PRIORITY / POLISH:**
   - [ ] [Issue + Proposed fix]

---

## Prompt Refinements for Next Run

### INSTRUCTIONS_FOR_LLM.md Changes
```markdown
[Proposed additions or modifications]
```

### Analyst Prompt Changes

**prompt_reddit_analyst.md:**
```markdown
[Proposed changes]
```

**prompt_blog_analyst.md:**
```markdown
[Proposed changes]
```

**prompt_arxiv_analyst.md:**
```markdown
[Proposed changes]
```

**prompt_master_synthesis.md:**
```markdown
[Proposed changes]
```

---

## Things That Worked Well

- ✅ [What worked?]
- ✅ [What worked?]
- ✅ [What worked?]

---

## Notes for Future Analysis Runs

- [Any other observations]
- [Patterns to watch for]
- [Questions to investigate]

---

## Comparative Notes (vs Gemini)

Use this section after analyzing both runs to compare:

### Reasoning Approach Differences
- **ChatGPT:** [How did ChatGPT approach the task?]
- **Gemini:** [How did Gemini approach the task?]
- **Key Difference:** [What stands out?]

### Efficiency Comparison
- **Faster on:** [Which steps?]
- **Slower on:** [Which steps?]
- **Reason:** [Why?]

### Quality Differences
- **Better at:** [What did ChatGPT do better?]
- **Worse at:** [What did Gemini do better?]

### Follow Instructions
- **ChatGPT adherence:** [How well did it follow prompts?]
- **Gemini adherence:** [How well did it follow prompts?]
- **Deviation patterns:** [Where did each deviate?]
