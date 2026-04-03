# Racing Analyzer Improvements — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 6 high-impact engines/features to the daily racing analyzer that directly improve daily betting decisions — each grounded in what data we already collect but don't exploit.

**Architecture:** All features live in the single HTML file. New engines added as functions alongside existing `computeStats`/`computeWinnerAnalysis`. New UI sections rendered inside existing tabs or as new sub-panels. All data sourced from `resultsHistory` and current-day JSON — no external APIs needed.

**Tech Stack:** Vanilla JS, localStorage, inline CSS (dark theme variables)

---

## Priority Ranking (by impact on daily bet decisions)

| # | Feature | Impact | Effort | Why |
|---|---------|--------|--------|-----|
| 1 | **Form Momentum Engine** | 🔥🔥🔥 | Medium | Detects horses on upward/downward trajectory — raw form string exists but no velocity analysis |
| 2 | **Confidence Threshold Optimizer** | 🔥🔥🔥 | Medium | Auto-calculates "only bet above X score" threshold from your data — directly answers "should I bet today?" |
| 3 | **Daily Betting Summary Card** | 🔥🔥🔥 | Low | One-glance GO/CAUTION/SKIP signal per race based on sweet spot matching — the "should I bet?" answer |
| 4 | **Race Condition Fingerprinting** | 🔥🔥 | Medium | Tags each race with a condition fingerprint (surface+fieldSize+class+gap), matches against historical accuracy |
| 5 | **Trainer/Jockey Hot Streak Tracker** | 🔥🔥 | Medium | Identifies trainers/jockeys on 3+ win streaks from logged data — momentum signal separate from combos |
| 6 | **Value Detector (Score vs Field Position)** | 🔥🔥 | Low | Flags picks where score gap is huge but confidence tier is moderate — model sees something others might not |

---

### Task 1: Daily Betting Summary Card

**Files:**
- Modify: `daily_racing_analyzer.html` — add to Races tab, above Top 10 Picks

**What it does:** For each race today, produces a GO / CAUTION / SKIP signal by matching today's race conditions against your historical sweet spots and weak spots. Shows at-a-glance which races to bet on.

**Step 1: Add `generateBetSignals()` function**

```javascript
function generateBetSignals(data) {
  // For each race, check if conditions match sweet spots (GO) or weak spots (SKIP)
  // Uses: field size bucket, surface, race type, score gap of #1 pick
  // Cross-references computeWinnerAnalysis results from Performance tab
  // Returns: [{race, venue, time, signal:'GO'|'CAUTION'|'SKIP', reasons:[], confidence}]

  const hist = window._resultsHistory;
  if (!hist || !hist.races || hist.races.length < 10) return null; // need history

  // Build accuracy lookup from historical data
  // For each dimension (fieldSize bucket, surface, raceType, gap bucket):
  //   compute placed rate from all logged races
  // Match today's races against these rates
  // GO = 2+ dimensions with >=70% placed rate, 0 weak dimensions
  // CAUTION = mixed signals
  // SKIP = 2+ dimensions with <40% placed rate
}
```

**Step 2: Render as a compact strip above Top 10 Picks**

Visual: Horizontal cards per race showing venue, time, signal badge (green GO / amber CAUTION / red SKIP), and 1-line reason ("Small field AW — 85% historical accuracy" or "Large field jumps — model struggles here").

**Step 3: Wire into `renderTopPicks()` — insert signal strip before picks grid**

**Step 4: Test with existing data, verify signals match known sweet/weak spots**

**Step 5: Commit**

---

### Task 2: Confidence Threshold Optimizer

**Files:**
- Modify: `daily_racing_analyzer.html` — add to Performance tab after Winner Prediction Analysis

**What it does:** Calculates the optimal minimum composite score to bet on — the threshold where placed rate crosses your target (80%). Shows a chart of "if you only bet on picks scoring above X, your placed rate would be Y%."

**Step 1: Add `computeThresholdAnalysis()` inside `renderPerformance()`**

```javascript
function computeThresholdAnalysis(pf) {
  // For each race, get #1 pick's composite score and whether they placed
  // Sort by composite score descending
  // Walk down: at each threshold, compute placed rate of picks above that threshold
  // Find the score where placed rate first drops below 80%
  // Also compute: races skipped %, expected profit zone

  // Returns: {
  //   optimalThreshold: 65.2,  // composite score cutoff
  //   placedRateAtThreshold: 82%,
  //   racesAbove: 47,  // how many of your picks were above
  //   racesTotal: 120,
  //   curve: [{threshold, placedRate, count}]  // for chart
  // }
}
```

**Step 2: Render threshold card + visual curve**

Show: "Optimal bet threshold: 65+ composite" with placed rate curve rendered as inline bars (no chart library needed — CSS bar chart).

**Step 3: Add "Today's picks above threshold" indicator to each Top 10 pick card**

Small badge: "✓ Above threshold" or "⚠ Below threshold" on each pick.

**Step 4: Commit**

---

### Task 3: Form Momentum Engine

**Files:**
- Modify: `daily_racing_analyzer.html` — add momentum badge to runner table + Top 10 picks

**What it does:** Analyzes the form string (e.g., "5,3,2,1") to detect trajectory. A horse going 8→5→3→1 has strong upward momentum. A horse going 1→2→4→7 is declining. Currently the form score treats all positions equally by weight — momentum adds direction.

**Step 1: Add `calcMomentum(formString, fieldSizes)` function**

```javascript
function calcMomentum(form) {
  // Parse form string to array of finish positions
  // Calculate linear regression slope of recent 4 runs
  // Normalize by field sizes if available
  // Return: {slope, label:'RISING'|'STEADY'|'FALLING', trend:[positions]}

  // RISING = slope < -0.5 (improving, positions getting smaller)
  // FALLING = slope > 0.5 (declining, positions getting larger)
  // STEADY = in between
}
```

**Step 2: Add momentum badge to runner table**

Small arrow badge next to form characters: ↑ green (RISING), → grey (STEADY), ↓ red (FALLING).

**Step 3: Add momentum to Top 10 pick cards as additional signal**

**Step 4: Track momentum accuracy in Performance tab**

After logging results, check: do RISING horses outperform STEADY/FALLING? Add a row to winner analysis breakdown: "By Momentum."

**Step 5: Commit**

---

### Task 4: Race Condition Fingerprinting

**Files:**
- Modify: `daily_racing_analyzer.html` — add fingerprint to race cards + Performance tab

**What it does:** Tags each race with a composite condition fingerprint (e.g., "AW-Small-Class5-Dominant") and looks up your historical accuracy for that exact fingerprint type. More granular than individual dimension analysis.

**Step 1: Add `getRaceFingerprint(race, pick)` function**

```javascript
function getRaceFingerprint(race, pick) {
  const fs = race.field_size || 12;
  const surface = classifySurface(race); // 'AW' or 'Turf'
  const sizeLabel = fs <= 6 ? 'Small' : fs <= 10 ? 'Medium' : 'Large';
  const gapLabel = pick.gap >= 12 ? 'Dominant' : pick.gap >= 5 ? 'Clear' : 'Tight';
  return `${surface}-${sizeLabel}-${gapLabel}`;
}
```

**Step 2: Store fingerprint with each race in resultsHistory**

When saving results, add `fingerprint` field to the race entry.

**Step 3: Build fingerprint accuracy table in Performance tab**

Group logged races by fingerprint, show placed rate per fingerprint. Highlight fingerprints with 80%+ rate.

**Step 4: Show fingerprint match on today's race cards**

Small badge: "AW-Small-Dominant (87% hist.)" on race cards that match high-accuracy fingerprints.

**Step 5: Commit**

---

### Task 5: Trainer/Jockey Hot Streak Tracker

**Files:**
- Modify: `daily_racing_analyzer.html` — add streak section to Combos tab

**What it does:** Scans logged results for trainers and jockeys currently on winning streaks (3+ wins in last 10 runs). Different from combos — this tracks individual momentum, not partnerships.

**Step 1: Add `computeStreaks()` function**

```javascript
function computeStreaks() {
  // For each trainer and jockey in resultsHistory:
  //   Get their last 10 results (chronological)
  //   Count current consecutive wins/places from most recent
  //   Calculate last-10 strike rate
  //   Flag as HOT if: 3+ wins in last 10 OR current streak >= 3

  // Returns: {
  //   hotTrainers: [{name, streak, last10Wins, last10Rate, recentRuns}],
  //   hotJockeys: [{name, streak, last10Wins, last10Rate, recentRuns}]
  // }
}
```

**Step 2: Render in Combos tab — new "Hot Streaks" section above combo table**

Visual: Flame badges with streak count, recent run indicators (W/P/L dots).

**Step 3: Cross-reference with today's runners**

If a hot-streak trainer/jockey has a runner today, flag it on the race card and in Top 10 picks.

**Step 4: Commit**

---

### Task 6: Value Detector (Hidden Edge Picks)

**Files:**
- Modify: `daily_racing_analyzer.html` — add to Top 10 picks section

**What it does:** Identifies picks where the model sees a big edge that might not be obvious. Specifically: picks where the score gap to 2nd is large (>10), the field is competitive (avg score moderate), but the confidence tier is only SOLID or STRONG — not TOP PICK. These are "value" picks where the model's composite analysis found something the raw score misses.

**Step 1: Add `detectValuePicks(picks)` function**

```javascript
function detectValuePicks(picks) {
  return picks.filter(p => {
    const isValue = p.gap >= 10 &&
                    p.composite >= 55 &&
                    ['SOLID', 'STRONG'].includes(p.confidence) &&
                    p.fieldSize >= 6;
    return isValue;
  }).map(p => ({
    ...p,
    valueReason: `+${p.gap} gap in ${p.fieldSize}-runner field · model dominant but not obvious favorite`
  }));
}
```

**Step 2: Add "VALUE" badge to qualifying picks in the Top 10 grid**

Purple/gold badge: "💎 VALUE" with tooltip showing why.

**Step 3: Track value pick performance in Performance tab**

After enough data: "Value picks placed rate: X%" — validates whether these hidden edges actually hit.

**Step 4: Commit**

---

## Execution Order

Recommended implementation order based on dependencies and immediate impact:

1. **Task 1 (Daily Betting Summary)** → Immediate daily decision tool
2. **Task 6 (Value Detector)** → Quick win, small code
3. **Task 3 (Form Momentum)** → Enhances scoring signal
4. **Task 2 (Threshold Optimizer)** → Needs some data history to be useful
5. **Task 4 (Race Fingerprinting)** → Builds on existing winner analysis
6. **Task 5 (Hot Streak Tracker)** → Enhances combos tab

Total estimate: ~2-3 hours for all 6 tasks.

---

## Additional Quick Wins (not full tasks)

- **Toast notifications** — Show green popup when results are saved successfully
- **Pick card "last time" note** — If same horse ran previously in logged data, show their last result
- **Performance caching** — Memoize `computeWinnerAnalysis` result to avoid recalculation on repeat tab opens
- **Mobile breakpoints** — Add 2 more responsive breakpoints for tablet/phone
- **Export picks to clipboard** — "Copy today's picks" button for sharing
