# Reddit Temporal Scraping System — ARCHITECTURE.md

## 1. Overview

This document defines the architecture of an **adaptive Reddit temporal scraping system**. The objective is to maximize **information gain per API call** while respecting rate limits (~600 requests/minute) and maintaining visibility across multiple subreddits with differing activity profiles.

### Goals
- Harvest comment forests with full historical context.
- Detect dormancy and allocate scraping effort adaptively.
- Maintain smooth coverage degradation when bandwidth constrained.
- Operate continuously and self-correct through feedback control.

### Data Flow (conceptual)
```
[DiscoveryPoller] → [PostHarvester] → [Merger] → [DeltaComputer]
        ↓                  ↓               ↓            ↓
  [SubredditPriors]   [DepthAdvisor]   [TemperatureScorer]
                ↓             ↓           ↓
             [RateController] ← [ContinuousScheduler]
```

---

## 2. Core Components

### 2.1 DiscoveryPoller
- **Role:** Periodically polls `/r/<sub>/new` for fresh posts.
- **Output:** Queue of new post IDs tagged with subreddit, discovery timestamp.
- **Cadence:** Adaptive based on subreddit coverage fraction `F_i` (see §6).

### 2.2 PostHarvester
- **Role:** Fully expands a post into its comment tree.
- **Modes:** `shallow`, `medium`, `deep` — depth chosen by DepthAdvisor.
- **Output:** `raw_scrape.json` with full comment and score snapshot.

### 2.3 Merger
- **Role:** Combines sequential scrapes into `final_merged.json`.
- **Behavior:**
  - Timestamp triple fallback (metadata → filename → mtime → UTC).
  - Sparse histories: only update when data changes.
  - Deletion threshold: mark deleted after ≥3 consecutive absences.
  - Append audit marker `[null, timestamp]` when marking deleted.

### 2.4 DeltaComputer
- **Role:** Quantifies information change between scrapes.
- **Computation:**
  ```python
  ΔInfo_t = w_new * n_new_comments + w_edit * n_text_edits \
          + w_score * n_score_changes + w_del * n_deletions
  ```
  Default weights: `w_new=1.0`, `w_edit=0.5`, `w_score=0.2`, `w_del=0.1`

### 2.5 TemperatureScorer
- **Role:** Converts recent ΔInfo trends into a continuous temperature metric T∈[0,1].
- **Equation:**
  ```python
  T_i = α*rate_norm + β*exp(-λ_i * hours_since_activity) + γ*volatility_norm
  ```
  Defaults: α=0.6, β=0.3, γ=0.1

### 2.6 SubredditPriors
- **Role:** Maintains rolling estimates of λ (activity decay constant) and average cost/post for each subreddit.
- **Usage:** Seeds initial Δt scheduling and coverage fractions.

### 2.7 PriorityCoverageAllocator
- **Role:** Allocates API budget B (requests/hour) across ranked subreddits.
- **Equation:**
  ```python
  f(r) = 1 / (1 + exp(alpha_p * (r - R_c)))
  F_i = scale * f(r_i) * g
  ```
  where `F_i` = coverage fraction (probability of scraping a post),
  `g` = global gain, `scale = min(1, B / Σ f(r)*c_i*p_i)`

### 2.8 ContinuousScheduler
- **Role:** Determines when each post should next be scraped.
- **Core logic:**
  ```python
  Δt_i = clamp(k / (T_i + ε), 0.5h, 24h) * g
  due_i = last_scrape + Δt_i
  φ_i   = max(0, (now - due_i) / Δt_i)
  S_i   = T_i / (1 + λ_i * φ_i * Δt_i)
  ```
  Posts with lowest due time and highest S_i are scraped first.

### 2.9 RateController
- **Role:** Adjusts global gain `g` based on actual API request rate.
- **EMA update:**
  ```python
  rate_ema = α * rps + (1-α)*rate_ema
  e_r = (rate_ema / target_rps) - 1
  g = clamp(g * exp(η * e_r + η_l * (lateness - L*)), g_min, g_max)
  ```
  Defaults: target_rps=10, α=0.03, η=0.05, η_l=0.02, L*=0.15

### 2.10 DepthAdvisor
- **Role:** Chooses harvest depth per post.
- **Policy:** Escalate when marginal ΔInfo/request ≥ θ; de-escalate otherwise.
- **Cap:** Max concurrent deep harvests = 5.

### 2.11 DormancyRetirement
- **Dormancy:** Mark after 3 consecutive ΔInfo=0.
- **Backoff:** Exponential (1h→2h→4h→8h→…→24h).
- **Retire:** After prolonged dormancy or age > 72h.
- **Reactivation:** Any nonzero ΔInfo cancels dormancy.

### 2.12 Telemetry
- Records metrics: ΔInfo_t, T, Δt, φ, g, λ, coverage, API utilization.
- Emits alerts when waste>70%, g pinned, or coverage<50% for top subs.

---

## 3. Data Contracts

### 3.1 Merged Post Schema
```json
{
  "post": { "id": "t3_xyz", "score_history": [[20152, "2025-10-15T14:35:14Z"]] },
  "comments": [ { "id": "t1_abc", "score_history": [[42, "…Z"], [null, "…Z"]] } ]
}
```
- Sparse histories (no scrape → no entry).
- `[null, timestamp]` marks deletion.
- All timestamps UTC ISO-8601.

### 3.2 Validation Assertions
- `len(score_history) == number_of_scrapes`
- Timestamps strictly increasing.
- `[null, ts]` ⇒ `deleted == true`.

---

## 4. Information Gain Analytics

### 4.1 Metrics
- **ΔInfo_t:** weighted sum of new/edit/score/del events.
- **Half-life:** time to reach 50% cumulative ΔInfo.
- **Dormancy time:** first 3×0 ΔInfo window.
- **Waste rate:** scrapes returning no new info / total scrapes.

### 4.2 Example Calculation
```python
for scrape in scrapes:
    delta = w_new*new_comments + w_edit*edits + w_score*score_changes + w_del*deletions
    post.delta_history.append((scrape.time, delta))
```

---

## 5. Adaptive Scheduling Logic

### 5.1 Temperature & Interval
- Temperature reflects recent volatility and recency.
- Next interval inversely proportional to temperature.
- Global gain `g` scales all intervals globally.

### 5.2 Priority & Lateness Handling
- Late posts (φ>0) penalized softly: `S_i = T_i / (1 + λ_i * φ_i * Δt_i)`.
- Ensures freshness for hot posts, fairness for overdue ones.

### 5.3 Example Control Loop
```python
def control_tick(now):
    g = rate_controller.update(rps, lateness_avg)
    for post in active_posts:
        T = compute_temperature(post)
        Dt = clamp(k / (T + eps), 0.5h, 24h) * g
        due = post.last_scrape + Dt
        phi = max(0, (now - due)/Dt)
        S = T / (1 + post.lambda_hat * phi * Dt)
        scheduler.queue(post, due, S)
```

---

## 6. Bandwidth Allocation & Flex Zones

### 6.1 Smooth Coverage Allocation
Coverage fraction per subreddit:
```python
f(r) = 1 / (1 + exp(alpha_p * (r - R_c)))
F_i = scale * f(r_i) * g
```
- `r_i`: priority rank.
- `R_c`: center index where F≈0.5.
- `alpha_p`: steepness (controls flex width).
- `scale`: normalization factor to stay within budget.

### 6.2 Probabilistic Sampling (drop posts, not scrapes)
When scraping a subreddit:
```python
if random.random() < F_i:
    scrape_post(post_id)
else:
    skip_post(post_id)
```
Ensures smooth degradation without blind spots.

---

## 7. Depth & Cost Adaptation

### 7.1 Rules
- Start `shallow` for new posts.
- Escalate if `ΔInfo/request` ≥ θ.
- De-escalate if below threshold.
- Maintain rolling averages for marginal ΔInfo efficiency.

### 7.2 Parameters
```yaml
promote_threshold: 0.03  # ΔInfo/request
 demote_threshold: 0.01
 max_concurrent_deep: 5
```

---

## 8. Dormancy & Retirement

### 8.1 Logic
```python
if last_3_deltas == [0,0,0]:
    post.state = 'dormant'
    post.backoff_hours = min(post.backoff_hours * 2, 24)
if post.age > 72 and post.state == 'dormant':
    retire(post)
```
### 8.2 Reactivation
Any nonzero ΔInfo resets backoff and reactivates the post.

---

## 9. Telemetry & Observability

| Metric | Level | Description |
|--------|--------|-------------|
| `instantaneous_rps` | global | Requests per second (actual API calls) |
| `rate_ema`, `g` | global | EMA smoothed rate and gain |
| `avg_lateness` | global | Mean lateness fraction |
| `ΔInfo_t` | post | Information delta per scrape |
| `T`, `Δt`, `φ`, `λ` | post | Scheduling variables |
| `coverage_target`, `coverage_realized` | subreddit | Sampling adherence |

**Alerts:**
- `waste_rate > 0.7`
- `coverage_realized < 0.5` for top-ranked subs
- `g` at bound >5min

---

## 10. Configuration Schema (YAML)

```yaml
subreddits:
  - name: r/news
    rank: 0
    poll_min: 15s
    cost_estimate: { shallow: 8, medium: 25, deep: 80 }
    lambda_prior: 0.25
priority_curve:
  type: sigmoid
  alpha: 0.03
  Rc: 50
rate_controller:
  target_rps: 10
  ema_alpha: 0.03
  eta: 0.05
  eta_l: 0.02
  g_min: 0.5
  g_max: 3.0
dormancy:
  zero_delta_window: 3
  backoff_hours: [1,2,4,8,12,24]
  retire_after_hours: 72
depth_policy:
  promote_threshold: 0.03
  demote_threshold: 0.01
  max_concurrent_deep: 5
```

---

## 11. Testing & Simulation

### 11.1 Integrity Tests
- Timestamps monotonic.
- No missing score tuples.
- Deletion markers consistent.

### 11.2 Functional Tests
- Increasing T decreases Δt.
- Rate controller stabilizes around target_rps.
- Coverage scaling respects budget.

### 11.3 Simulation
- Bursty request patterns: verify EMA smoothing.
- Subreddit λ mixtures: confirm adaptive λ convergence.
- Measure info-yield vs budget trade-off.

---

## 12. Implementation Notes

- Count **actual** HTTP requests for RPS, not posts.
- Randomize sampling decisions per epoch to avoid bias.
- Clamp lateness for hot posts (φ ≤ 0.25) to prevent starvation.
- Keep discovery polling separate from deep comment harvesting.
- Record marginal ΔInfo/request for diagnostics.
- Reserve ~10–15% API budget for unexpected bursts.

---

## 13. Appendix

### 13.1 Variable Glossary
| Symbol | Meaning |
|---------|----------|
| ΔInfo | Information gain per scrape |
| T | Temperature (activity level) |
| λ | Decay constant |
| Δt | Next scrape interval |
| φ | Lateness fraction |
| g | Global gain (rate controller output) |
| F | Coverage fraction per subreddit |

### 13.2 Key Equations
```
Δt_i = k / (T_i + ε) * g
S_i = T_i / (1 + λ_i * φ_i * Δt_i)
f(r) = 1 / (1 + exp(α_p*(r-R_c)))
g_next = g * exp(η*e_r + η_l*(lateness - L*))
```

### 13.3 Reference Summary
- Sparse history merge logic ensures clean long-term datasets.
- ΔInfo measures yield efficiency.
- Temperature and λ create smooth decay-based scheduling.
- Sigmoid coverage curve enables graceful degradation.
- EMA gain controller provides stability under bursty rate limits.

---

*End of ARCHITECTURE.md*

