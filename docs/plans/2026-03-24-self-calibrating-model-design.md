# Self-Calibrating Racing Model — Design Doc

**Date:** 2026-03-24
**Status:** Approved

## Problem

The 14-factor scoring engine uses static, hand-tuned weights. It has no feedback loop — predictions are never compared against actual results, and weights never adapt to evidence.

## Solution

Add three capabilities:

1. **Results Logger** — click-to-rank UI on the dashboard to log finishing positions after each race
2. **Performance Dashboard** — accuracy tracking per confidence tier, factor correlation analysis, cumulative accuracy over time
3. **Calibration Engine** — after 50+ logged races per surface profile, proposes new factor weights based on rank correlation analysis. Human approval required before applying.

## Data Model

### results_history.json

```json
{
  "version": 1,
  "races": [
    {
      "date": "2026-03-24",
      "venue": "Wolverhampton",
      "time": "17:00",
      "race_name": "BetMGM Handicap",
      "field_size": 11,
      "going": "Standard",
      "surface": "AW",
      "race_type": "Flat",
      "profile": "aw",
      "results": [
        {
          "name": "Red Diesel",
          "finish_pos": 1,
          "predicted_score": 92,
          "predicted_confidence": "TOP PICK",
          "score_breakdown": {"form": 18, "rating": 15, ...}
        }
      ],
      "non_runners": ["Horse X"]
    }
  ],
  "calibrations": [
    {
      "date": "2026-04-25",
      "profile": "aw",
      "races_used": 67,
      "old_weights": {"form": 20, "rating": 15, ...},
      "new_weights": {"form": 23, "rating": 12, ...},
      "correlations": {"form": 0.42, "rating": 0.31, ...},
      "backtest": {"old_top3_rate": 0.58, "new_top3_rate": 0.63},
      "applied": false
    }
  ],
  "weight_profiles": {
    "aw": {"form": 20, "rating": 15, "trainer": 12, "jockey": 10, "fitness": 8, "class": 8, "going": 8, "course": 6, "distance": 6, "age": 7, "weight": 8, "draw": 5, "headgear": 3, "spotlight": 2},
    "turf_flat": {"form": 20, "rating": 15, "trainer": 12, "jockey": 10, "fitness": 8, "class": 8, "going": 8, "course": 6, "distance": 6, "age": 7, "weight": 8, "draw": 5, "headgear": 3, "spotlight": 2},
    "nh": {"form": 20, "rating": 15, "trainer": 12, "jockey": 10, "fitness": 8, "class": 8, "going": 8, "course": 6, "distance": 6, "age": 7, "weight": 8, "draw": 5, "headgear": 3, "spotlight": 2}
  }
}
```

## Surface Profiles

| Profile | Matches | Rationale |
|---------|---------|-----------|
| `aw` | surface=AW | Draw matters more, going barely relevant |
| `turf_flat` | surface=Turf AND race_type=Flat | Going critical, draw important, age peaks younger |
| `nh` | race_type in (Hurdle, Chase, NH Flat, Bumper) | Going critical, draw irrelevant, trainer/jockey higher weight |

## Results Input: Click-to-Rank UI

- "Log Results" button appears on each race card (enabled after race time passes)
- Opens a panel showing all runners as clickable tiles
- User clicks horses in finishing order: 1st, 2nd, 3rd, etc.
- NR button to mark non-runners
- Only top 3-4 positions needed (partial ranking is fine)
- Save writes to results_history.json with predicted scores captured at prediction time

## Performance Dashboard (new "Performance" tab)

### Accuracy Table
Hit rates per confidence tier, filterable by profile (All / AW / Turf Flat / NH):
- Tier, Race count, Win rate, Top 3 rate, Expected Top 3 rate, Calibration status

### Factor Correlation Chart
Bar chart of Spearman rank correlation (factor score vs finishing position) per profile. High bars = genuinely predictive factors.

### Cumulative Accuracy Line
Rolling accuracy over time to visualise model improvement or degradation.

### Race Counter
"23/50 races logged for AW" — shows progress toward calibration threshold per profile.

## Calibration Engine

### Trigger
"Run Calibration" button enabled per profile once 50+ races logged in that profile.

### Algorithm
1. For each factor, compute Spearman ρ between factor score and finish position (inverted — lower finish = better)
2. Propose new weights: `new_weight = base_weight × (1 + ρ × k)`, normalized to sum to 118
3. k = adjustment factor (0.5 initially, conservative to prevent wild swings)
4. Backtest: re-score all historical races with proposed weights, compare TOP PICK/STRONG accuracy

### Output: Calibration Report
- Current vs proposed weights side-by-side, highlighting increases/decreases
- Correlation values per factor
- Backtest results: "TOP PICK top-3 rate would be 63% vs current 58%"

### User Decision
Two buttons:
- **"Apply New Weights"** → saves to weight_profiles, future scoring uses them
- **"Keep Current"** → logs calibration attempt with applied=false, no changes

Weights are NEVER auto-applied.

## Scope Limits

- No odds or staking / ROI tracking (just prediction accuracy)
- No factor additions — calibration tunes existing 14 factor weights only
- One weight set per profile (no per-venue splits — insufficient data)
- Minimum 50 races per profile before calibration is enabled
- Maximum weight swing per calibration capped at ±40% of original to prevent instability

## Files to Create/Modify

1. `results_history.json` — new data file
2. `calibration_engine.py` — new: Spearman correlation, weight proposal, backtest
3. `fetch_daily_races.py` — modify: accept weight profile param, load weights from history
4. `daily_racing_analyzer.html` — modify: add Results Input UI, Performance tab, Calibration report
