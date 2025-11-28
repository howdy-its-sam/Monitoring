# Manual Analysis Orchestration

I am going to upload several files to you. They represent raw data from three different domains (Reddit, Tech Blogs, and ArXiv Papers) and the analysis prompts to process them.

Your goal is to act as the **Chief Intelligence Officer** and generate a Master Daily Brief. To do this, you must execute the following pipeline sequentially.

## The Files
You should see the following files uploaded:
1.  `reddit_data.txt`
2.  `all_blogs.txt`
3.  `all_arxiv.txt`
4.  `prompt_reddit_analyst.md`
5.  `prompt_blog_analyst.md`
6.  `prompt_arxiv_analyst.md`
7.  `prompt_master_synthesis.md`

## The Pipeline

### Step 1: Reddit Analysis
- **Read:** `prompt_reddit_analyst.md`
- **Apply to:** `reddit_data.txt`
- **Action:** Generate the Reddit Situation Report based on the instructions in the prompt.
- **Output:** Save or hold this output in your context as `[REDDIT_REPORT]`.

### Step 2: Blog Analysis
- **Read:** `prompt_blog_analyst.md`
- **Apply to:** `all_blogs.txt`
- **Action:** Generate the Industry/Blog Report. Note that the data file is a concatenation of many JSON objects; handle it gracefully even if the JSON structure is fragmented.
- **Output:** Save or hold this output in your context as `[BLOG_REPORT]`.

### Step 3: ArXiv Analysis
- **Read:** `prompt_arxiv_analyst.md`
- **Apply to:** `all_arxiv.txt`
- **Action:** Generate the Research/ArXiv Report.
- **Output:** Save or hold this output in your context as `[ARXIV_REPORT]`.

### Step 4: Master Synthesis
- **Read:** `prompt_master_synthesis.md`
- **Inputs:** Use the three reports you just generated (`[REDDIT_REPORT]`, `[BLOG_REPORT]`, `[ARXIV_REPORT]`).
- **Action:** Synthesize the final "Daily Brief" according to the master prompt instructions.
- **Final Output:** Display the **Master Daily Brief**.

## Output Format

**CRITICAL:** Present your final output as a **complete, standalone markdown document** that can be saved directly to disk.

Structure the document as follows:
```markdown
# AI/ML Intelligence Brief
*[Date Range]*

---

## Reddit Situation Report
[Full Reddit analysis here]

---

## Industry & Blog Analysis
[Full blog analysis here]

---

## Academic Research Report
[Full ArXiv analysis here]

---

## Master Daily Brief
[Full synthesis here]
```

Ensure all four reports are included in a single, continuous markdown file with proper formatting, headers, and section breaks. The output should be production-ready for immediate export.

Please acknowledge you have the files and begin with **Step 1**.
