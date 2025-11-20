# 🧪 Unified Scraper Validation Test Plan — Steady Adaptive Equilibrium

**Runtime:** 4 hours  
**Objective:** Validate end-to-end adaptive behavior and steady-state utilization of the unified scraper system.

---

## 🎯 Primary Goal
Collect a single continuous dataset that verifies:
- Throughput regulation and gain control
- Proper coverage fractions across subreddit ranks
- Continuous discovery (no idle collapse)
- Stable RPS and utilization
- Realistic selection effects (ΔInfo/post)
- Balanced subreddit allocation

---

## ⚙️ Configuration Summary

| Parameter | Value | Purpose |
|------------|--------|----------|
| **Runtime** | 4 hours | Steady-state test |
| **Target RPS** | 10 | Push controller near designed limit |
| **Discovery Poll K** | 5 | Top 5 subreddits per idle burst |
| **Max Concurrent Scrapes** | 3 | Apply concurrency pressure |
| **Telemetry Interval** | 60s | Fine-grained monitoring |
| **Coverage Metrics Interval** | 300s | Drift & realization tracking |
| **Coverage EMA** | 0.6 * budget + 0.4 * observed | Smooth fluctuations |
| **Selection Policy** | `balanced_tiered` | Full + hot + sampled tiers |

**Command Example:**
```bash
python3 unified_scraper.py 10 10.0   --dir=adaptive_equilibrium_v1   --strategy balanced_tiered   --telemetry-interval 60   --coverage-log-interval 300   --target-rps 10   --duration 4h
```

---

## 🧠 Selection Policy (`selection_policy.json`)

```json
{
  "strategy": "balanced_tiered",
  "rules": [
    { "ranks": [0, 5], "method": "all" },
    { "ranks": [6, 20], "method": "hot_only", "min_comments": 5, "min_score": 25 },
    { "ranks": [21, 999], "method": "sample", "sample_rate": 0.25 }
  ]
}
```

**Purpose:**  
Ensures all allocation mechanisms are active simultaneously:
- Tier A → tests load saturation & gain loop
- Tier B → tests conditional inclusion logic
- Tier C → tests random sampling and discovery decoupling

---

## 🧾 Data to Collect

| File | Interval | Purpose |
|------|-----------|----------|
| `telemetry_snapshots.jsonl` | every 60s | Core controller + allocator health |
| `coverage_metrics.jsonl` | every 5–10 min | Target vs realized coverage |
| `discovery_history.jsonl` | on every discovery | Discovery cadence by subreddit |
| `request_trace.jsonl` | per request | Verify actual RPS counting |
| `controller_state.jsonl` | every 10 min | Long-term gain & RPS trend |

---

## 📊 Expected Signal Ranges (Healthy Behavior)

| Metric | Healthy Range | Interpretation |
|:--|:--|:--|
| **Global Gain (g)** | 0.8–1.2 | Controller stable, not pinned |
| **Rate EMA (RPS)** | 8–10 | Steady throughput |
| **Idle Discovery Rate** | ≥3 bursts/min | Idle time fully utilized |
| **Coverage Drift (|Fₜ–Fᵣ|)** | <0.1 | Allocator correctly balanced |
| **Top-10 Share** | 50–70% | Rank weighting honored |
| **Deep Work Share** | ≤25% | Depth advisor effective |
| **Waste Rate** | <20% | Efficient scrapes |
| **Utilization** | ≥70% sustained | Scheduler not stalling |

---

## ✅ Example Outputs — Model Validation

### 1. **Healthy Controller Loop**
```json
{
  "timestamp": "2025-10-16T14:02:00Z",
  "rate_ema": 9.7,
  "gain": 1.05,
  "idle_discovery_rate": 4.2,
  "coverage_skew_avg": 0.07,
  "top_10_share": 0.63
}
```
**Interpretation:** PI controller converged; allocator tracking desired rates; discovery system responsive.

---

### 2. **Balanced Coverage Metrics**
```json
{
  "timestamp": "2025-10-16T14:05:00Z",
  "subreddit": "WallStreetBets",
  "F_target": 0.95,
  "F_realized": 0.90,
  "coverage_drift": -0.05,
  "requests": 228
}
```
**Interpretation:** Allocator maintaining ~1.0 target; small negative drift acceptable.

---

### 3. **Expected Discovery Activity**
```json
{
  "timestamp": "2025-10-16T14:10:15Z",
  "subreddit": "cryptocurrency",
  "post_id": "1o7ai0g",
  "score": 124,
  "num_comments": 22
}
```
**Interpretation:** Continuous discovery, mid-tier post meeting "hot_only" threshold.

---

### 4. **Throughput Stability Snapshot**
```json
{
  "timestamp": "2025-10-16T14:30:00Z",
  "rps_instant": 9.8,
  "rate_ema": 9.4,
  "gain": 1.02,
  "utilization": 0.84
}
```
**Interpretation:** RPS oscillates slightly below target; controller behaving nominally.

---

### 5. **Potential Failure Example**
```json
{
  "timestamp": "2025-10-16T14:30:00Z",
  "rate_ema": 1.8,
  "gain": 0.5,
  "idle_discovery_rate": 0.0,
  "coverage_skew_avg": 0.43,
  "top_10_share": 0.91
}
```
**Interpretation:** Controller pinned at min gain → coverage collapse → discovery stalled.  
🚨 Indicates regressions in Fix #1 (budget normalization) or Fix #4 (opportunistic discovery).

---

## 📈 Post-Run Analysis Checklist

### Step 1. Compute Coverage Drift
```bash
jq -s 'map(.coverage_drift) | add / length' coverage_metrics.jsonl
```
✅ Pass if result < 0.1

### Step 2. Check Idle Discovery Rate
```bash
jq -r '.idle_discovery_rate' telemetry_snapshots.jsonl | awk '{sum+=$1; n++} END{print sum/n}'
```
✅ Pass if ≥ 3.0 bursts/min

### Step 3. Gain Stability
Plot `gain` vs `rate_ema`  
✅ Pass if tightly coupled, not pinned.

### Step 4. Subreddit Coverage Distribution
```bash
grep '"subreddit":' coverage_metrics.jsonl | jq -r '.subreddit' | sort | uniq -c | sort -nr | head
```
✅ Expect top-tier dominance but mid- and low-tiers present.

### Step 5. Deep Work & Waste
Check `deep_work_share` ≤ 25% and `waste_rate` ≤ 20%.

---

## 🧮 Summary of Success Criteria

| Category | Metric | Target |
|:--|:--|:--|
| Controller | Global Gain | 0.8–1.2 |
| Controller | RPS EMA | 8–10 |
| Discovery | Idle Discovery Rate | ≥3/min |
| Allocator | Coverage Drift | <0.1 |
| Allocator | Top-10 Share | 50–70% |
| Depth Advisor | Deep Work Share | ≤25% |
| Scheduler | Utilization | ≥70% |
| Efficiency | Waste Rate | <20% |

---

## 🧾 Outcome Interpretation

| Outcome | Meaning |
|:--|:--|
| All metrics within range | ✅ System stable — adaptive equilibrium achieved |
| Drift > 0.1 | ⚠️ Allocator imbalance; check post-rate weighting |
| Idle Discovery < 2/min | ⚠️ Idle detection threshold too high |
| Gain pinned (0.5 or 2.0) | ❌ Controller feedback mis-scaling |
| Top-10 share > 80% | ⚠️ Over-prioritization of top subs |
| Deep-work > 30% | ⚠️ Depth advisor tuning required |

---

**Deliverable Dataset Folder:** `adaptive_equilibrium_v1/`  
Contains:  
- `telemetry_snapshots.jsonl`  
- `coverage_metrics.jsonl`  
- `discovery_history.jsonl`  
- `request_trace.jsonl`  
- `controller_state.jsonl`  

This dataset can later be reused for model calibration, trend forecasting, and controller retuning.
