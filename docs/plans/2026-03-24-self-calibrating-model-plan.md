# Self-Calibrating Racing Model — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a results logging UI, performance tracking dashboard, and human-approved weight calibration engine to the horse racing analyzer.

**Architecture:** Three new components — (1) `calibration_engine.py` handles Spearman correlation, weight proposals, and backtesting server-side; (2) `results_history.json` is the append-only data store; (3) the HTML dashboard gets a Results Input panel, Performance tab, and Calibration Report modal. The dashboard is self-contained (single HTML file) and reads/writes `results_history.json` via fetch (same pattern as `daily_race_data.json`).

**Tech Stack:** Python 3.8+ (stdlib only — `statistics`, `json`, `math`), vanilla JS/HTML/CSS (no frameworks, matching existing dashboard patterns).

---

### Task 1: Create results_history.json Scaffold

**Files:**
- Create: `BB Analyzer/results_history.json`

**Step 1: Create the initial empty history file**

```json
{
  "version": 1,
  "races": [],
  "calibrations": [],
  "weight_profiles": {
    "aw": {"form": 20, "rating": 15, "trainer": 12, "jockey": 10, "fitness": 8, "class": 8, "going": 8, "course": 6, "distance": 6, "age": 7, "weight": 8, "draw": 5, "headgear": 3, "spotlight": 2},
    "turf_flat": {"form": 20, "rating": 15, "trainer": 12, "jockey": 10, "fitness": 8, "class": 8, "going": 8, "course": 6, "distance": 6, "age": 7, "weight": 8, "draw": 5, "headgear": 3, "spotlight": 2},
    "nh": {"form": 20, "rating": 15, "trainer": 12, "jockey": 10, "fitness": 8, "class": 8, "going": 8, "course": 6, "distance": 6, "age": 7, "weight": 8, "draw": 5, "headgear": 3, "spotlight": 2}
  }
}
```

**Step 2: Verify file is valid JSON**

Run: `python3 -c "import json; json.load(open('BB Analyzer/results_history.json')); print('OK')"`
Expected: `OK`

---

### Task 2: Build calibration_engine.py — Profile Classification

**Files:**
- Create: `BB Analyzer/calibration_engine.py`

**Step 1: Write the profile classifier with test**

```python
#!/usr/bin/env python3
"""Calibration engine: correlations, weight proposals, backtesting."""
import json
import math
import os
from pathlib import Path

HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results_history.json')
FACTORS = ['form', 'rating', 'trainer', 'jockey', 'fitness', 'class',
           'going', 'course', 'distance', 'age', 'weight', 'draw',
           'headgear', 'spotlight']
DEFAULT_WEIGHTS = {f: w for f, w in zip(FACTORS, [20,15,12,10,8,8,8,6,6,7,8,5,3,2])}
TARGET_SUM = sum(DEFAULT_WEIGHTS.values())  # 118
MIN_RACES = 50
MAX_SWING = 0.4  # ±40% cap per factor


def classify_profile(surface, race_type):
    """Classify a race into aw/turf_flat/nh profile."""
    rt = (race_type or '').lower()
    surf = (surface or '').lower()
    if surf == 'aw' or surf == 'all-weather':
        return 'aw'
    if any(x in rt for x in ['hurdle', 'chase', 'nh flat', 'bumper', 'national hunt']):
        return 'nh'
    return 'turf_flat'
```

**Step 2: Test the classifier**

Run: `python3 -c "from calibration_engine import classify_profile; print(classify_profile('AW','Flat'), classify_profile('Turf','Chase'), classify_profile('Turf','Flat'))"`
Expected: `aw nh turf_flat`

---

### Task 3: Build calibration_engine.py — History I/O & Save Results

**Files:**
- Modify: `BB Analyzer/calibration_engine.py`

**Step 1: Add load/save history and save_race_results function**

```python
def load_history():
    """Load results history from disk."""
    if not os.path.exists(HISTORY_PATH):
        return {"version": 1, "races": [], "calibrations": [], "weight_profiles": {
            "aw": dict(DEFAULT_WEIGHTS), "turf_flat": dict(DEFAULT_WEIGHTS), "nh": dict(DEFAULT_WEIGHTS)
        }}
    with open(HISTORY_PATH) as f:
        return json.load(f)


def save_history(history):
    """Write results history to disk (atomic-ish)."""
    tmp = HISTORY_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(history, f, indent=2)
    os.replace(tmp, HISTORY_PATH)


def save_race_results(race_key, results_list, race_data, runners_data):
    """Save finishing positions for a race.

    Args:
        race_key: dict with date, venue, time
        results_list: list of {name, finish_pos} (1-indexed, partial OK)
        race_data: the race dict from daily_race_data.json
        runners_data: list of runner dicts with score/breakdown from predictions
    """
    history = load_history()
    profile = classify_profile(race_data.get('surface', ''), race_data.get('race_type', ''))

    # Build results with predicted scores
    results = []
    for res in results_list:
        name = res['name']
        # Find this runner in predictions
        pred = next((r for r in runners_data if r.get('name') == name), {})
        results.append({
            'name': name,
            'finish_pos': res['finish_pos'],
            'non_runner': res.get('non_runner', False),
            'predicted_score': pred.get('score', 0),
            'predicted_confidence': pred.get('confidence', ''),
            'score_breakdown': pred.get('score_breakdown', {})
        })

    race_entry = {
        'date': race_key['date'],
        'venue': race_key['venue'],
        'time': race_key['time'],
        'race_name': race_data.get('name', ''),
        'field_size': race_data.get('field_size', len(runners_data)),
        'going': race_data.get('going', ''),
        'surface': race_data.get('surface', ''),
        'race_type': race_data.get('race_type', ''),
        'profile': profile,
        'results': results
    }

    # Prevent duplicates
    dup_key = (race_entry['date'], race_entry['venue'], race_entry['time'])
    history['races'] = [r for r in history['races']
                        if (r['date'], r['venue'], r['time']) != dup_key]
    history['races'].append(race_entry)
    save_history(history)
    return race_entry
```

**Step 2: Test save and load round-trip**

Run:
```python
python3 -c "
import json, os, sys
sys.path.insert(0, 'BB Analyzer')
from calibration_engine import save_race_results, load_history

# Test with mock data
race_key = {'date': '2026-03-24', 'venue': 'Test', 'time': '14:00'}
results = [{'name': 'Horse A', 'finish_pos': 1}, {'name': 'Horse B', 'finish_pos': 2}]
race_data = {'name': 'Test Race', 'field_size': 5, 'going': 'Good', 'surface': 'Turf', 'race_type': 'Flat'}
runners = [{'name': 'Horse A', 'score': 80, 'confidence': 'TOP PICK', 'score_breakdown': {'form': 18}},
           {'name': 'Horse B', 'score': 60, 'confidence': 'STRONG', 'score_breakdown': {'form': 12}}]
save_race_results(race_key, results, race_data, runners)
h = load_history()
assert len(h['races']) >= 1
r = h['races'][-1]
assert r['profile'] == 'turf_flat'
assert r['results'][0]['predicted_score'] == 80
print('PASS')
"
```
Expected: `PASS`

---

### Task 4: Build calibration_engine.py — Spearman Correlation & Performance Stats

**Files:**
- Modify: `BB Analyzer/calibration_engine.py`

**Step 1: Add Spearman rank correlation (stdlib only, no scipy)**

```python
def _rank(values):
    """Assign ranks to values (1=best). Handles ties with average rank."""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 1) / 2  # 1-indexed average
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def spearman_rho(x, y):
    """Spearman rank correlation coefficient between two lists."""
    if len(x) != len(y) or len(x) < 3:
        return 0.0
    rx = _rank(x)
    ry = _rank(y)
    n = len(x)
    d_sq = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1 - (6 * d_sq) / (n * (n * n - 1))
```

**Step 2: Add performance statistics calculator**

```python
def get_performance_stats(profile_filter=None):
    """Calculate accuracy stats per confidence tier.

    Returns dict with:
      - tiers: list of {tier, count, win_rate, top3_rate, expected_top3}
      - factor_correlations: {factor_name: spearman_rho}
      - race_count: total races per profile
      - cumulative: list of {date, rolling_top3_rate} for line chart
    """
    history = load_history()
    races = history['races']
    if profile_filter:
        races = [r for r in races if r.get('profile') == profile_filter]

    # Flatten to individual runner results (need finish_pos and predicted data)
    runners = []
    for race in races:
        for res in race.get('results', []):
            if res.get('non_runner') or not res.get('finish_pos'):
                continue
            runners.append({
                'finish_pos': res['finish_pos'],
                'score': res.get('predicted_score', 0),
                'confidence': res.get('predicted_confidence', ''),
                'breakdown': res.get('score_breakdown', {}),
                'field_size': race.get('field_size', 12),
                'date': race.get('date', '')
            })

    if not runners:
        return {'tiers': [], 'factor_correlations': {}, 'race_count': 0, 'profile_counts': {}, 'cumulative': []}

    # --- Tier accuracy ---
    tier_order = ['TOP PICK', 'STRONG', 'SOLID', 'MODERATE', 'WEAK', 'AVOID']
    tiers = []
    for tier in tier_order:
        tier_runners = [r for r in runners if r['confidence'] == tier]
        if not tier_runners:
            continue
        wins = sum(1 for r in tier_runners if r['finish_pos'] == 1)
        top3 = sum(1 for r in tier_runners if r['finish_pos'] <= 3)
        count = len(tier_runners)
        # Expected top3 based on average field size
        avg_fs = sum(r['field_size'] for r in tier_runners) / count
        expected_top3 = min(3 / avg_fs, 1.0) if avg_fs > 0 else 0.33
        tiers.append({
            'tier': tier,
            'count': count,
            'win_rate': round(wins / count * 100, 1),
            'top3_rate': round(top3 / count * 100, 1),
            'expected_top3': round(expected_top3 * 100, 1)
        })

    # --- Factor correlations ---
    # We want NEGATIVE correlation: high factor score → low finish position (= good)
    # So we negate finish_pos for intuitive display (positive rho = factor helps)
    factor_corrs = {}
    for factor in FACTORS:
        factor_scores = []
        finish_positions = []
        for r in runners:
            fs = r['breakdown'].get(factor)
            if fs is not None:
                factor_scores.append(fs)
                finish_positions.append(-r['finish_pos'])  # negate so high = good
        if len(factor_scores) >= 10:
            factor_corrs[factor] = round(spearman_rho(factor_scores, finish_positions), 3)

    # --- Cumulative accuracy (rolling 20-race window for top picks) ---
    top_pick_runs = sorted(
        [r for r in runners if r['confidence'] in ('TOP PICK', 'STRONG')],
        key=lambda r: r['date']
    )
    cumulative = []
    window = 20
    for i in range(window, len(top_pick_runs) + 1):
        chunk = top_pick_runs[i - window:i]
        t3 = sum(1 for r in chunk if r['finish_pos'] <= 3)
        cumulative.append({
            'index': i,
            'date': chunk[-1]['date'],
            'rolling_top3_rate': round(t3 / window * 100, 1)
        })

    # Profile counts
    all_races = history['races']
    profile_counts = {}
    for p in ['aw', 'turf_flat', 'nh']:
        profile_counts[p] = len([r for r in all_races if r.get('profile') == p])

    return {
        'tiers': tiers,
        'factor_correlations': factor_corrs,
        'race_count': len(races),
        'profile_counts': profile_counts,
        'cumulative': cumulative
    }
```

**Step 3: Test with synthetic data**

Run:
```python
python3 -c "
from calibration_engine import spearman_rho, _rank
# Perfect positive correlation
assert abs(spearman_rho([1,2,3,4,5], [1,2,3,4,5]) - 1.0) < 0.001
# Perfect negative correlation
assert abs(spearman_rho([1,2,3,4,5], [5,4,3,2,1]) - (-1.0)) < 0.001
# Zero-ish for random
import random; random.seed(42)
x = list(range(20)); y = list(range(20)); random.shuffle(y)
r = spearman_rho(x, y)
assert -0.5 < r < 0.5
print('PASS')
"
```
Expected: `PASS`

---

### Task 5: Build calibration_engine.py — Weight Proposal & Backtest

**Files:**
- Modify: `BB Analyzer/calibration_engine.py`

**Step 1: Add weight proposal engine**

```python
def propose_new_weights(profile):
    """Propose new factor weights based on rank correlation analysis.

    Returns None if insufficient data (<50 races), otherwise returns dict with:
      - old_weights, new_weights, correlations, backtest, races_used
    """
    history = load_history()
    races = [r for r in history['races'] if r.get('profile') == profile]

    if len(races) < MIN_RACES:
        return None

    # Get current weights for this profile
    old_weights = history.get('weight_profiles', {}).get(profile, dict(DEFAULT_WEIGHTS))

    # Compute correlations
    stats = get_performance_stats(profile_filter=profile)
    correlations = stats['factor_correlations']

    if not correlations:
        return None

    # Propose new weights: scale by correlation strength
    # new = old × (1 + rho × k), then normalize to TARGET_SUM
    k = 0.5  # conservative adjustment factor
    raw_new = {}
    for factor in FACTORS:
        rho = correlations.get(factor, 0)
        multiplier = 1 + rho * k
        # Cap swing at ±MAX_SWING
        multiplier = max(1 - MAX_SWING, min(1 + MAX_SWING, multiplier))
        raw_new[factor] = old_weights.get(factor, DEFAULT_WEIGHTS[factor]) * multiplier

    # Normalize to TARGET_SUM, round to integers, fix rounding error
    raw_sum = sum(raw_new.values())
    new_weights = {}
    for factor in FACTORS:
        new_weights[factor] = max(1, round(raw_new[factor] / raw_sum * TARGET_SUM))

    # Fix rounding error: adjust largest weight
    diff = TARGET_SUM - sum(new_weights.values())
    if diff != 0:
        biggest = max(FACTORS, key=lambda f: new_weights[f])
        new_weights[biggest] += diff

    # --- Backtest ---
    # Re-score all historical runners with old vs new weights and compare top3 hit rates
    def score_with_weights(breakdown, weights):
        return sum(min(breakdown.get(f, 0), weights.get(f, 0)) for f in FACTORS)

    old_top3, new_top3, total = 0, 0, 0
    for race in races:
        fs = race.get('field_size', 12)
        scored_old = []
        scored_new = []
        for res in race.get('results', []):
            if res.get('non_runner') or not res.get('finish_pos'):
                continue
            bd = res.get('score_breakdown', {})
            scored_old.append((score_with_weights(bd, old_weights), res['finish_pos']))
            scored_new.append((score_with_weights(bd, new_weights), res['finish_pos']))

        # Sort by predicted score desc, check if top-predicted finishes top 3
        scored_old.sort(key=lambda x: -x[0])
        scored_new.sort(key=lambda x: -x[0])

        if scored_old:
            total += 1
            if scored_old[0][1] <= 3:
                old_top3 += 1
            if scored_new[0][1] <= 3:
                new_top3 += 1

    backtest = {
        'old_top_pick_top3_rate': round(old_top3 / total * 100, 1) if total else 0,
        'new_top_pick_top3_rate': round(new_top3 / total * 100, 1) if total else 0,
        'races_tested': total
    }

    return {
        'profile': profile,
        'races_used': len(races),
        'old_weights': old_weights,
        'new_weights': new_weights,
        'correlations': correlations,
        'backtest': backtest
    }


def apply_weights(profile, new_weights):
    """Apply calibrated weights after user approval."""
    history = load_history()
    old_weights = history.get('weight_profiles', {}).get(profile, dict(DEFAULT_WEIGHTS))

    # Log calibration event
    from datetime import datetime
    history.setdefault('calibrations', []).append({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'profile': profile,
        'races_used': len([r for r in history['races'] if r.get('profile') == profile]),
        'old_weights': old_weights,
        'new_weights': new_weights,
        'applied': True
    })

    # Update profile weights
    history.setdefault('weight_profiles', {})[profile] = new_weights
    save_history(history)
    return True


def reject_calibration(profile, proposal):
    """Log that user rejected a calibration proposal."""
    history = load_history()
    from datetime import datetime
    history.setdefault('calibrations', []).append({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'profile': profile,
        'races_used': proposal.get('races_used', 0),
        'old_weights': proposal.get('old_weights', {}),
        'new_weights': proposal.get('new_weights', {}),
        'applied': False
    })
    save_history(history)
```

**Step 2: Test weight proposal with deterministic synthetic data**

Run:
```python
python3 -c "
import json, sys
sys.path.insert(0, 'BB Analyzer')
from calibration_engine import load_history, save_history, propose_new_weights, FACTORS, DEFAULT_WEIGHTS

# Seed 60 synthetic races where 'form' strongly predicts finish position
h = load_history()
import random; random.seed(99)
for i in range(60):
    runners = []
    for j in range(8):
        bd = {f: random.randint(0, DEFAULT_WEIGHTS[f]) for f in FACTORS}
        # Make form strongly correlated with good finishing
        bd['form'] = 18 - j * 2  # rank 1 gets form=18, rank 8 gets form=4
        runners.append({
            'name': f'Horse_{j}', 'finish_pos': j+1, 'non_runner': False,
            'predicted_score': sum(bd.values()), 'predicted_confidence': 'SOLID',
            'score_breakdown': bd
        })
    h['races'].append({
        'date': f'2026-03-{(i%28)+1:02d}', 'venue': 'Test', 'time': f'{12+i%6}:00',
        'race_name': f'Race {i}', 'field_size': 8, 'going': 'Good',
        'surface': 'AW', 'race_type': 'Flat', 'profile': 'aw',
        'results': runners
    })
save_history(h)

p = propose_new_weights('aw')
assert p is not None, 'Should have enough races'
assert p['new_weights']['form'] > DEFAULT_WEIGHTS['form'], f'Form should increase: {p[\"new_weights\"][\"form\"]} vs {DEFAULT_WEIGHTS[\"form\"]}'
assert sum(p['new_weights'].values()) == 118, f'Weights must sum to 118: {sum(p[\"new_weights\"].values())}'
print(f'Form correlation: {p[\"correlations\"].get(\"form\", 0):.3f}')
print(f'Form weight: {DEFAULT_WEIGHTS[\"form\"]} -> {p[\"new_weights\"][\"form\"]}')
print(f'Backtest: {p[\"backtest\"]}')
print('PASS')
"
```
Expected: `PASS`, Form correlation positive, Form weight increased.

**Step 3: Clean up test data from results_history.json**

Re-create the clean initial file from Task 1.

---

### Task 6: Add CLI for calibration_engine.py

**Files:**
- Modify: `BB Analyzer/calibration_engine.py`

**Step 1: Add main() with CLI subcommands**

```python
def main():
    """CLI interface for calibration engine."""
    import argparse
    parser = argparse.ArgumentParser(description='Racing model calibration engine')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('stats', help='Show performance statistics')
    sub.add_parser('propose', help='Propose new weights for a profile')
    sub.add_parser('status', help='Show race counts per profile')

    args = parser.parse_args()

    if args.command == 'status':
        h = load_history()
        for p in ['aw', 'turf_flat', 'nh']:
            count = len([r for r in h['races'] if r.get('profile') == p])
            ready = '✓ READY' if count >= MIN_RACES else f'{count}/{MIN_RACES}'
            print(f'  {p:12s}: {count:4d} races  [{ready}]')

    elif args.command == 'stats':
        for profile in [None, 'aw', 'turf_flat', 'nh']:
            label = profile or 'ALL'
            stats = get_performance_stats(profile_filter=profile)
            if not stats['tiers']:
                continue
            print(f'\n=== {label.upper()} ({stats["race_count"]} races) ===')
            print(f'{"Tier":<12} {"Count":>6} {"Win%":>6} {"Top3%":>6} {"Exp%":>6}')
            for t in stats['tiers']:
                print(f'{t["tier"]:<12} {t["count"]:>6} {t["win_rate"]:>5.1f}% {t["top3_rate"]:>5.1f}% {t["expected_top3"]:>5.1f}%')
            if stats['factor_correlations']:
                print(f'\nFactor correlations:')
                for f, rho in sorted(stats['factor_correlations'].items(), key=lambda x: -x[1]):
                    bar = '█' * int(abs(rho) * 20)
                    sign = '+' if rho > 0 else '-'
                    print(f'  {f:<12} {sign}{abs(rho):.3f} {bar}')

    elif args.command == 'propose':
        for profile in ['aw', 'turf_flat', 'nh']:
            p = propose_new_weights(profile)
            if p is None:
                count = len([r for r in load_history()['races'] if r.get('profile') == profile])
                print(f'{profile}: Need {MIN_RACES - count} more races')
                continue
            print(f'\n=== {profile.upper()} Calibration Proposal ({p["races_used"]} races) ===')
            print(f'{"Factor":<12} {"Current":>8} {"Proposed":>8} {"Change":>8} {"Corr":>8}')
            for f in FACTORS:
                old = p['old_weights'].get(f, 0)
                new = p['new_weights'].get(f, 0)
                diff = new - old
                corr = p['correlations'].get(f, 0)
                arrow = '↑' if diff > 0 else ('↓' if diff < 0 else '–')
                print(f'  {f:<12} {old:>6} {new:>6}   {arrow}{abs(diff):>3}    {corr:>+.3f}')
            bt = p['backtest']
            print(f'\nBacktest top-pick top-3 rate: {bt["old_top_pick_top3_rate"]}% → {bt["new_top_pick_top3_rate"]}% ({bt["races_tested"]} races)')

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
```

**Step 2: Test CLI**

Run: `cd "BB Analyzer" && python3 calibration_engine.py status`
Expected: Shows race counts per profile (all zeros if history is clean).

---

### Task 7: Add fetch_daily_races.py — Weight Profile Loading

**Files:**
- Modify: `BB Analyzer/fetch_daily_races.py`

**Step 1: Add function to load weights from history**

At the top of `fetch_daily_races.py`, after imports, add:

```python
def load_weight_profile(profile):
    """Load calibrated weights for a surface profile from results_history.json.
    Falls back to defaults if file doesn't exist or profile not found."""
    history_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results_history.json')
    try:
        with open(history_path) as f:
            history = json.load(f)
        return history.get('weight_profiles', {}).get(profile, None)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
```

**Step 2: Modify calculate_composite_score to accept custom weights**

Change the function signature:

```python
def calculate_composite_score(runner, race_data, all_runners, custom_weights=None):
```

After computing `scores` dict and merging `trainer_rtf`, add:

```python
    # Apply custom weights if provided (from calibration)
    if custom_weights:
        weighted_total = sum(
            min(scores.get(f, 0), custom_weights.get(f, 99))
            for f in scores
        )
        max_possible = sum(custom_weights.get(f, 0) for f in scores)
    else:
        weighted_total = total
        max_possible = 118

    return {
        'total': weighted_total,
        'breakdown': scores,
        'max_possible': max_possible
    }
```

Also remove the `min(total, 100)` cap on line 677 — the old code caps at 100 but max is 118.

**Step 3: Test that default behavior is unchanged**

Run the same test from earlier:
```python
python3 -c "
import sys; sys.path.insert(0, 'BB Analyzer')
from fetch_daily_races import calculate_composite_score
r = {'form':'1-2-1','official_rating':85,'trainer':'W P Mullins','jockey':'P Townend',
     'days_since_run':21,'age':6,'weight_lbs':160,'draw':3,'headgear':'','spotlight':'Good',
     'going_record':{},'course_record':{},'distance_record':{}}
race = {'field_size':9,'going':'Good','distance_f':'2m4f','class':3}
result = calculate_composite_score(r, race, [r])
assert result['total'] > 0
assert len(result['breakdown']) == 14
print(f'Score: {result[\"total\"]}/118 PASS')
"
```

---

### Task 8: Dashboard — Add Results Input (Click-to-Rank) UI

**Files:**
- Modify: `BB Analyzer/daily_racing_analyzer.html`

**Step 1: Add CSS for results input panel**

Add after existing CSS (before `</style>`):

```css
/* Results input */
.ri-panel{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-top:12px}
.ri-tiles{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.ri-tile{padding:8px 14px;border-radius:8px;border:1px solid var(--border);cursor:pointer;font-size:13px;transition:all .15s;background:var(--bg)}
.ri-tile:hover{border-color:var(--accent);background:#1a1a2e}
.ri-tile.ranked{background:var(--accent);color:#fff;border-color:var(--accent)}
.ri-tile.nr{background:#333;color:#777;text-decoration:line-through;border-color:#444}
.ri-badge{display:inline-block;min-width:20px;height:20px;line-height:20px;text-align:center;border-radius:50%;background:var(--accent);color:#fff;font-size:11px;font-weight:700;margin-right:6px}
.ri-actions{display:flex;gap:8px;margin-top:12px}
.ri-actions button{padding:6px 14px;border-radius:6px;border:none;cursor:pointer;font-size:12px;font-weight:600}
.ri-save{background:var(--accent);color:#fff}
.ri-save:disabled{opacity:0.4;cursor:not-allowed}
.ri-undo{background:var(--card);color:var(--fg);border:1px solid var(--border) !important}
.ri-nr{background:#2a1a1a;color:#ef4444;border:1px solid #3a2020 !important}
```

**Step 2: Add JS functions for results input**

Add before `load()` at end of `<script>`:

```javascript
// === RESULTS INPUT ===
let resultState = {}; // {venueKey_raceIdx: {ranked: [{name,pos}], nrs: [name]}}

function showResultsInput(venueKey, raceIdx) {
  const venue = D.venues[venueKey];
  const race = venue.races[raceIdx];
  const key = venueKey + '_' + raceIdx;
  if (!resultState[key]) resultState[key] = {ranked: [], nrs: []};
  const rs = resultState[key];

  const panel = document.getElementById('resultsPanel_' + key);
  if (panel) { panel.remove(); return; } // toggle off

  const container = document.getElementById('raceCard_' + key);
  if (!container) return;

  const html = `<div class="ri-panel" id="resultsPanel_${key}">
    <div style="font-weight:700;margin-bottom:6px">Log Results — click horses in finishing order</div>
    <div class="ri-tiles" id="riTiles_${key}">
      ${race.runners.map(r => {
        const ranked = rs.ranked.find(x => x.name === r.name);
        const isNR = rs.nrs.includes(r.name);
        const cls = ranked ? 'ranked' : (isNR ? 'nr' : '');
        const badge = ranked ? `<span class="ri-badge">${ranked.pos}</span>` : '';
        return `<div class="ri-tile ${cls}" onclick="rankRunner('${key}','${r.name.replace(/'/g,"\\'")}')">
          ${badge}${r.name}
        </div>`;
      }).join('')}
    </div>
    <div class="ri-actions">
      <button class="ri-save" onclick="saveResults('${venueKey}',${raceIdx})" ${rs.ranked.length < 3 ? 'disabled' : ''}>
        Save Results (${rs.ranked.length} ranked)
      </button>
      <button class="ri-undo" onclick="undoRank('${key}')">Undo Last</button>
      <button class="ri-nr" onclick="toggleNRMode('${key}')">Mark NR</button>
    </div>
  </div>`;
  container.insertAdjacentHTML('beforeend', html);
}

function rankRunner(key, name) {
  const rs = resultState[key] || (resultState[key] = {ranked: [], nrs: []});
  // If already ranked or NR, skip
  if (rs.ranked.find(x => x.name === name) || rs.nrs.includes(name)) return;
  rs.ranked.push({name: name, pos: rs.ranked.length + 1});
  // Re-render panel
  const parts = key.split('_');
  showResultsInput(parts[0], parseInt(parts[1]));
  showResultsInput(parts[0], parseInt(parts[1]));
}

function undoRank(key) {
  const rs = resultState[key];
  if (!rs) return;
  if (rs.ranked.length > 0) rs.ranked.pop();
  const parts = key.split('_');
  showResultsInput(parts[0], parseInt(parts[1]));
  showResultsInput(parts[0], parseInt(parts[1]));
}

function toggleNRMode(key) {
  // Simple: prompt for NR name (could be enhanced later)
  const rs = resultState[key];
  if (!rs) return;
  const parts = key.split('_');
  const vk = parts[0], ri = parseInt(parts[1]);
  const race = D.venues[vk].races[ri];
  const available = race.runners.filter(r =>
    !rs.ranked.find(x => x.name === r.name) && !rs.nrs.includes(r.name)
  );
  if (!available.length) return;
  // Mark next clicked as NR by adding a temp flag
  // For simplicity, mark the first unranked as NR (user can undo)
  const name = prompt('Enter non-runner name (or click Cancel):\n\nAvailable: ' +
    available.map(r => r.name).join(', '));
  if (name && available.find(r => r.name.toLowerCase() === name.toLowerCase())) {
    const match = available.find(r => r.name.toLowerCase() === name.toLowerCase());
    rs.nrs.push(match.name);
    showResultsInput(vk, ri);
    showResultsInput(vk, ri);
  }
}

async function saveResults(venueKey, raceIdx) {
  const key = venueKey + '_' + raceIdx;
  const rs = resultState[key];
  if (!rs || rs.ranked.length < 1) return;

  const venue = D.venues[venueKey];
  const race = venue.races[raceIdx];

  const payload = {
    race_key: {date: D.date, venue: venueKey, time: race.time},
    results: rs.ranked.map(r => ({name: r.name, finish_pos: r.pos})),
    non_runners: rs.nrs,
    race_data: {
      name: race.name, field_size: race.field_size, going: race.going,
      surface: race.surface || '', race_type: race.race_type || ''
    },
    runners_data: race.runners.map(r => ({
      name: r.name, score: r.score, confidence: r.confidence,
      score_breakdown: r.score_breakdown
    }))
  };

  // Save to results_history.json via local fetch (only works via HTTP server)
  // Fallback: save to localStorage and offer download
  try {
    const existing = await fetch('results_history.json?t=' + Date.now()).then(r => r.ok ? r.json() : null);
    const history = existing || {version:1, races:[], calibrations:[], weight_profiles:{}};

    const profile = classifyProfile(race.surface, race.race_type);
    const entry = {
      date: D.date, venue: venueKey, time: race.time,
      race_name: race.name, field_size: race.field_size,
      going: race.going, surface: race.surface || '',
      race_type: race.race_type || '', profile: profile,
      results: payload.results.map(r => {
        const pred = race.runners.find(x => x.name === r.name) || {};
        return {
          name: r.name, finish_pos: r.finish_pos, non_runner: false,
          predicted_score: pred.score || 0, predicted_confidence: pred.confidence || '',
          score_breakdown: pred.score_breakdown || {}
        };
      })
    };

    // Remove duplicate
    const dupKey = entry.date + entry.venue + entry.time;
    history.races = history.races.filter(r => (r.date + r.venue + r.time) !== dupKey);
    history.races.push(entry);

    // Store in memory for performance tab
    window._resultsHistory = history;

    // Offer download
    const blob = new Blob([JSON.stringify(history, null, 2)], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'results_history.json';
    a.click();

    alert('Results saved! The file has been downloaded. Place it in the same folder as this dashboard.');
    // Mark as saved visually
    const panel = document.getElementById('resultsPanel_' + key);
    if (panel) panel.innerHTML = '<div style="color:var(--accent);font-weight:700;padding:10px">✓ Results saved</div>';
  } catch(e) {
    alert('Error saving: ' + e.message);
  }
}

function classifyProfile(surface, raceType) {
  const rt = (raceType || '').toLowerCase();
  const s = (surface || '').toLowerCase();
  if (s === 'aw' || s === 'all-weather') return 'aw';
  if (['hurdle','chase','nh flat','bumper'].some(x => rt.includes(x))) return 'nh';
  return 'turf_flat';
}
```

**Step 3: Add "Log Results" button to race cards**

In `renderRaceCards()`, find where each race card is built and add a results button. The card `div` needs an ID for the results panel to attach to.

Locate the race card template in `renderRaceCards()` and add:
- `id="raceCard_${vk}_${i}"` to the card wrapper
- A "Log Results" button that calls `showResultsInput(vk, i)`

---

### Task 9: Dashboard — Add Performance Tab

**Files:**
- Modify: `BB Analyzer/daily_racing_analyzer.html`

**Step 1: Add Performance tab toggle to header**

Add a tab bar under the header:

```html
<div class="tab-bar" style="display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:0">
  <button class="tab-btn active" id="tabRaces" onclick="switchTab('races')">Races</button>
  <button class="tab-btn" id="tabPerf" onclick="switchTab('performance')">Performance</button>
</div>
```

CSS for tabs:
```css
.tab-btn{padding:10px 20px;background:none;border:none;color:var(--muted);cursor:pointer;font-size:13px;font-weight:600;border-bottom:2px solid transparent}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent)}
```

**Step 2: Add Performance view container**

```html
<div id="perfView" style="display:none;padding:20px 28px;max-width:1200px;margin:0 auto">
  <div id="perfContent">Loading performance data...</div>
</div>
```

**Step 3: Add switchTab and renderPerformance functions**

```javascript
function switchTab(tab) {
  document.getElementById('tabRaces').classList.toggle('active', tab==='races');
  document.getElementById('tabPerf').classList.toggle('active', tab==='performance');
  document.getElementById('landingView').style.display = tab==='races' ? 'block' : 'none';
  document.getElementById('detailView').style.display = 'none';
  document.getElementById('perfView').style.display = tab==='performance' ? 'block' : 'none';
  if (tab === 'performance') renderPerformance();
}

async function renderPerformance() {
  const el = document.getElementById('perfContent');

  // Load history
  let history = window._resultsHistory;
  if (!history) {
    try {
      const r = await fetch('results_history.json?t=' + Date.now());
      if (r.ok) history = await r.json();
    } catch(e) {}
  }

  if (!history || !history.races || !history.races.length) {
    el.innerHTML = `<div class="nodata"><h2>No Results Logged Yet</h2>
      <p>Log finishing positions using the "Log Results" button on each race card.</p>
      <p>After logging 50+ races per surface type, calibration becomes available.</p></div>`;
    return;
  }

  // Profile filter
  const profiles = ['all', 'aw', 'turf_flat', 'nh'];
  const profileLabels = {all: 'All', aw: 'AW', turf_flat: 'Turf Flat', nh: 'National Hunt'};

  // Compute stats per profile (client-side mirror of calibration_engine.py)
  function computeStats(profileFilter) {
    let races = history.races;
    if (profileFilter && profileFilter !== 'all') races = races.filter(r => r.profile === profileFilter);

    const runners = [];
    races.forEach(race => {
      (race.results || []).forEach(res => {
        if (res.non_runner || !res.finish_pos) return;
        runners.push({
          finish_pos: res.finish_pos, score: res.predicted_score || 0,
          confidence: res.predicted_confidence || '', breakdown: res.score_breakdown || {},
          field_size: race.field_size || 12, date: race.date
        });
      });
    });

    // Tier accuracy
    const tierOrder = ['TOP PICK','STRONG','SOLID','MODERATE','WEAK','AVOID'];
    const tiers = tierOrder.map(tier => {
      const tr = runners.filter(r => r.confidence === tier);
      if (!tr.length) return null;
      const wins = tr.filter(r => r.finish_pos === 1).length;
      const top3 = tr.filter(r => r.finish_pos <= 3).length;
      const avgFs = tr.reduce((a,r) => a + r.field_size, 0) / tr.length;
      return {
        tier, count: tr.length,
        win_rate: (wins/tr.length*100).toFixed(1),
        top3_rate: (top3/tr.length*100).toFixed(1),
        expected_top3: (Math.min(3/avgFs,1)*100).toFixed(1)
      };
    }).filter(Boolean);

    // Factor correlations (simplified Spearman)
    function spearman(x, y) {
      if (x.length < 10) return 0;
      const rank = arr => {
        const sorted = arr.map((v,i) => [v,i]).sort((a,b) => a[0]-b[0]);
        const ranks = new Array(arr.length);
        let i = 0;
        while (i < sorted.length) {
          let j = i;
          while (j < sorted.length && sorted[j][0] === sorted[i][0]) j++;
          const avg = (i+j+1)/2;
          for (let k=i; k<j; k++) ranks[sorted[k][1]] = avg;
          i = j;
        }
        return ranks;
      };
      const rx = rank(x), ry = rank(y);
      const n = x.length;
      const dsq = rx.reduce((a,v,i) => a + (v-ry[i])**2, 0);
      return 1 - 6*dsq/(n*(n*n-1));
    }

    const factors = ['form','rating','trainer','jockey','fitness','class','going','course','distance','age','weight','draw','headgear','spotlight'];
    const correlations = {};
    factors.forEach(f => {
      const pairs = runners.filter(r => r.breakdown[f] !== undefined);
      if (pairs.length >= 10) {
        correlations[f] = parseFloat(spearman(
          pairs.map(r => r.breakdown[f]),
          pairs.map(r => -r.finish_pos)
        ).toFixed(3));
      }
    });

    // Profile race counts
    const profileCounts = {};
    ['aw','turf_flat','nh'].forEach(p => {
      profileCounts[p] = history.races.filter(r => r.profile === p).length;
    });

    return {tiers, correlations, race_count: races.length, profileCounts, runners};
  }

  let currentProfile = 'all';

  function renderPerfHTML(profile) {
    const stats = computeStats(profile);

    let html = `<div style="display:flex;gap:8px;margin-bottom:16px">
      ${profiles.map(p => `<button class="vbtn${p===profile?' active':''}"
        onclick="document.querySelectorAll('#perfContent .vbtn').forEach(b=>b.classList.remove('active'));this.classList.add('active');window._renderPerfProfile('${p}')"
        style="font-size:12px">${profileLabels[p]}</button>`).join('')}
    </div>`;

    // Race counters
    html += `<div style="display:flex;gap:16px;margin-bottom:16px">
      ${['aw','turf_flat','nh'].map(p => {
        const c = stats.profileCounts[p] || 0;
        const ready = c >= 50;
        return `<div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 16px;flex:1">
          <div style="font-size:11px;color:var(--muted)">${profileLabels[p]}</div>
          <div style="font-size:20px;font-weight:700;color:${ready?'var(--accent)':'var(--fg)'}">${c}</div>
          <div style="font-size:11px;color:${ready?'var(--accent)':'var(--muted)'}">
            ${ready ? '✓ Calibration ready' : `${c}/50 for calibration`}
          </div>
        </div>`;
      }).join('')}
    </div>`;

    // Accuracy table
    if (stats.tiers.length) {
      html += `<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px">
        <h3 style="margin:0 0 10px 0;font-size:14px">Prediction Accuracy</h3>
        <table style="width:100%;font-size:13px;border-collapse:collapse">
          <tr style="color:var(--muted);font-size:11px;text-align:left">
            <th style="padding:6px 8px">Tier</th><th>Races</th><th>Win %</th><th>Top 3 %</th><th>Expected %</th><th>Calibration</th>
          </tr>
          ${stats.tiers.map(t => {
            const diff = parseFloat(t.top3_rate) - parseFloat(t.expected_top3);
            const cal = diff > 5 ? '✅ Beating random' : (diff < -5 ? '⚠️ Underperforming' : '➖ Near baseline');
            return `<tr style="border-top:1px solid var(--border)">
              <td style="padding:6px 8px;font-weight:600">${t.tier}</td>
              <td>${t.count}</td><td>${t.win_rate}%</td><td>${t.top3_rate}%</td>
              <td style="color:var(--muted)">${t.expected_top3}%</td><td>${cal}</td>
            </tr>`;
          }).join('')}
        </table>
      </div>`;
    }

    // Factor correlations bar chart
    if (Object.keys(stats.correlations).length) {
      const sorted = Object.entries(stats.correlations).sort((a,b) => b[1]-a[1]);
      const maxAbs = Math.max(...sorted.map(([,v]) => Math.abs(v)), 0.01);
      html += `<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px">
        <h3 style="margin:0 0 10px 0;font-size:14px">Factor Predictive Power (Spearman ρ)</h3>
        ${sorted.map(([f, rho]) => {
          const pct = Math.abs(rho) / maxAbs * 100;
          const color = rho > 0.1 ? 'var(--accent)' : (rho < -0.05 ? '#ef4444' : '#666');
          return `<div style="display:flex;align-items:center;margin:4px 0;font-size:12px">
            <span style="width:80px;color:var(--muted)">${f}</span>
            <div style="flex:1;height:18px;background:var(--bg);border-radius:4px;overflow:hidden;margin:0 8px">
              <div style="width:${pct}%;height:100%;background:${color};border-radius:4px"></div>
            </div>
            <span style="width:50px;text-align:right;color:${color};font-weight:600">${rho > 0 ? '+' : ''}${rho.toFixed(3)}</span>
          </div>`;
        }).join('')}
        <div style="font-size:10px;color:var(--muted);margin-top:8px">Positive = factor score predicts better finishes. Negative = factor misleads the model.</div>
      </div>`;
    }

    // Calibration button
    const profileToCalibrate = profile === 'all' ? null : profile;
    if (profileToCalibrate) {
      const count = stats.profileCounts[profileToCalibrate] || 0;
      if (count >= 50) {
        html += `<button class="vbtn" style="background:var(--accent);color:#fff;padding:10px 20px;font-size:13px"
          onclick="runCalibration('${profileToCalibrate}')">
          Run Calibration for ${profileLabels[profileToCalibrate]} (${count} races)
        </button>`;
      }
    }

    el.innerHTML = html;
  }

  window._renderPerfProfile = renderPerfHTML;
  renderPerfHTML(currentProfile);
}
```

---

### Task 10: Dashboard — Calibration Report Modal

**Files:**
- Modify: `BB Analyzer/daily_racing_analyzer.html`

**Step 1: Add runCalibration function and report modal**

```javascript
async function runCalibration(profile) {
  // Client-side calibration (mirrors calibration_engine.py logic)
  let history = window._resultsHistory;
  if (!history) {
    try { history = await fetch('results_history.json?t='+Date.now()).then(r=>r.json()); } catch(e) {}
  }
  if (!history) { alert('No history data'); return; }

  const races = history.races.filter(r => r.profile === profile);
  if (races.length < 50) { alert('Need 50+ races, have ' + races.length); return; }

  const factors = ['form','rating','trainer','jockey','fitness','class','going','course','distance','age','weight','draw','headgear','spotlight'];
  const oldWeights = history.weight_profiles?.[profile] || Object.fromEntries(
    factors.map((f,i) => [f, [20,15,12,10,8,8,8,6,6,7,8,5,3,2][i]])
  );
  const targetSum = 118;

  // Compute correlations (same Spearman as performance tab)
  const runners = [];
  races.forEach(race => {
    (race.results||[]).forEach(res => {
      if (res.non_runner || !res.finish_pos) return;
      runners.push({fp: res.finish_pos, bd: res.score_breakdown || {}});
    });
  });

  function spearman(x,y) {
    if(x.length<10) return 0;
    const rank=arr=>{const s=arr.map((v,i)=>[v,i]).sort((a,b)=>a[0]-b[0]);const r=new Array(arr.length);let i=0;while(i<s.length){let j=i;while(j<s.length&&s[j][0]===s[i][0])j++;const avg=(i+j+1)/2;for(let k=i;k<j;k++)r[s[k][1]]=avg;i=j}return r};
    const rx=rank(x),ry=rank(y),n=x.length;
    return 1-6*rx.reduce((a,v,i)=>a+(v-ry[i])**2,0)/(n*(n*n-1));
  }

  const correlations = {};
  factors.forEach(f => {
    const pairs = runners.filter(r => r.bd[f] !== undefined);
    if (pairs.length >= 10) correlations[f] = parseFloat(spearman(pairs.map(r=>r.bd[f]), pairs.map(r=>-r.fp)).toFixed(3));
  });

  // Propose weights
  const k = 0.5, maxSwing = 0.4;
  const raw = {};
  factors.forEach(f => {
    const rho = correlations[f] || 0;
    const mult = Math.max(1-maxSwing, Math.min(1+maxSwing, 1 + rho * k));
    raw[f] = (oldWeights[f] || 1) * mult;
  });
  const rawSum = Object.values(raw).reduce((a,b)=>a+b,0);
  const newWeights = {};
  factors.forEach(f => newWeights[f] = Math.max(1, Math.round(raw[f]/rawSum*targetSum)));
  const diff = targetSum - Object.values(newWeights).reduce((a,b)=>a+b,0);
  if (diff) { const big = factors.reduce((a,b)=>newWeights[a]>newWeights[b]?a:b); newWeights[big] += diff; }

  // Backtest
  let oldT3=0, newT3=0, total=0;
  races.forEach(race => {
    const res = (race.results||[]).filter(r => !r.non_runner && r.finish_pos);
    if (!res.length) return;
    const scoreWith = (bd, w) => factors.reduce((a,f) => a + Math.min(bd[f]||0, w[f]||0), 0);
    const oldSorted = [...res].sort((a,b) => scoreWith(b.score_breakdown||{},oldWeights) - scoreWith(a.score_breakdown||{},oldWeights));
    const newSorted = [...res].sort((a,b) => scoreWith(b.score_breakdown||{},newWeights) - scoreWith(a.score_breakdown||{},newWeights));
    total++;
    if (oldSorted[0].finish_pos <= 3) oldT3++;
    if (newSorted[0].finish_pos <= 3) newT3++;
  });

  // Show report modal
  const profileLabels = {aw:'AW', turf_flat:'Turf Flat', nh:'National Hunt'};
  let reportHTML = `<div class="modal-bg" onclick="if(event.target===this)closeModal()"><div class="modal" style="max-width:700px">
    <button class="mclose" onclick="closeModal()">&times;</button>
    <h2>Calibration Report — ${profileLabels[profile]}</h2>
    <p style="color:var(--muted);margin-bottom:12px">${races.length} races analysed</p>

    <table style="width:100%;font-size:12px;border-collapse:collapse;margin-bottom:16px">
      <tr style="color:var(--muted);font-size:11px"><th style="text-align:left;padding:4px">Factor</th><th>Current</th><th>Proposed</th><th>Change</th><th>Correlation</th></tr>
      ${factors.map(f => {
        const o = oldWeights[f]||0, n = newWeights[f]||0, d = n-o;
        const rho = correlations[f]||0;
        const arrow = d>0?'↑':d<0?'↓':'–';
        const color = d>0?'var(--accent)':d<0?'#ef4444':'var(--muted)';
        return `<tr style="border-top:1px solid var(--border)">
          <td style="padding:4px;font-weight:600">${f}</td>
          <td style="text-align:center">${o}</td>
          <td style="text-align:center;color:${color};font-weight:700">${n}</td>
          <td style="text-align:center;color:${color}">${arrow}${Math.abs(d)}</td>
          <td style="text-align:center;color:${rho>0.1?'var(--accent)':rho<-0.05?'#ef4444':'var(--muted)'}">${rho>0?'+':''}${rho.toFixed(3)}</td>
        </tr>`;
      }).join('')}
    </table>

    <div style="background:var(--bg);border-radius:8px;padding:12px;margin-bottom:16px">
      <div style="font-weight:700;margin-bottom:4px">Backtest Results (${total} races)</div>
      <div>Current weights → top pick finishes top 3: <b>${total?Math.round(oldT3/total*100):0}%</b></div>
      <div>Proposed weights → top pick finishes top 3: <b style="color:${newT3>oldT3?'var(--accent)':'#ef4444'}">${total?Math.round(newT3/total*100):0}%</b></div>
    </div>

    <div style="display:flex;gap:10px">
      <button onclick="applyCalibration('${profile}',${JSON.stringify(newWeights).replace(/"/g,'&quot;')})"
        style="flex:1;padding:10px;border:none;border-radius:8px;background:var(--accent);color:#fff;font-weight:700;cursor:pointer;font-size:14px">
        ✓ Apply New Weights
      </button>
      <button onclick="rejectCalibration('${profile}');closeModal()"
        style="flex:1;padding:10px;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--fg);font-weight:600;cursor:pointer;font-size:14px">
        ✗ Keep Current
      </button>
    </div>
  </div></div>`;

  document.getElementById('modalContainer').innerHTML = reportHTML;

  // Store proposal for apply/reject
  window._lastProposal = {profile, races_used: races.length, old_weights: oldWeights, new_weights: newWeights, correlations};
}

function applyCalibration(profile, newWeights) {
  let history = window._resultsHistory || {version:1,races:[],calibrations:[],weight_profiles:{}};
  const oldWeights = history.weight_profiles?.[profile] || {};

  history.calibrations = history.calibrations || [];
  history.calibrations.push({
    date: new Date().toISOString().slice(0,10), profile,
    races_used: history.races.filter(r=>r.profile===profile).length,
    old_weights: oldWeights, new_weights: newWeights, applied: true
  });
  history.weight_profiles = history.weight_profiles || {};
  history.weight_profiles[profile] = newWeights;
  window._resultsHistory = history;

  // Download updated history
  const blob = new Blob([JSON.stringify(history,null,2)], {type:'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'results_history.json'; a.click();

  closeModal();
  alert('Weights updated! Save the downloaded results_history.json to the dashboard folder.');
  renderPerformance();
}

function rejectCalibration(profile) {
  let history = window._resultsHistory || {version:1,races:[],calibrations:[],weight_profiles:{}};
  const p = window._lastProposal || {};
  history.calibrations = history.calibrations || [];
  history.calibrations.push({
    date: new Date().toISOString().slice(0,10), profile,
    races_used: p.races_used||0, old_weights: p.old_weights||{},
    new_weights: p.new_weights||{}, applied: false
  });
  window._resultsHistory = history;
}
```

---

### Task 11: Wire renderRaceCards to include Log Results button and card IDs

**Files:**
- Modify: `BB Analyzer/daily_racing_analyzer.html` — function `renderRaceCards()`

**Step 1: Find the race card rendering loop and add:**

1. Unique `id="raceCard_${vk}_${i}"` on each card container
2. A "Log Results" button after race card content:

```javascript
`<button class="vbtn" onclick="event.stopPropagation();showResultsInput('${vk}',${i})"
  style="font-size:10px;margin-top:6px">📝 Log Results</button>`
```

**Step 2: Test by opening the HTML and verifying "Log Results" buttons appear**

---

### Task 12: Integration Test — Full Round-Trip

**Step 1: Open the dashboard, verify all tabs render (Races / Performance)**

**Step 2: Click "Log Results" on a race, rank 3 horses, save**

**Step 3: Switch to Performance tab, verify it shows 1 race logged**

**Step 4: Run `python3 calibration_engine.py status` to confirm CLI matches**

**Step 5: Verify the downloaded results_history.json has correct structure**

---

### Task 13: Load Calibrated Weights into Scoring

**Files:**
- Modify: `BB Analyzer/daily_racing_analyzer.html`

**Step 1: On dashboard load, check results_history.json for calibrated weight profiles**

In the `load()` function, after loading D, also try to load `results_history.json` and if weight profiles differ from defaults, use them for recalculating display scores.

```javascript
// After D is loaded, check for calibrated weights
try {
  const rh = await fetch('results_history.json?t='+Date.now());
  if (rh.ok) {
    window._resultsHistory = await rh.json();
    // Check if any weights differ from default
    const wp = window._resultsHistory.weight_profiles || {};
    if (Object.keys(wp).length) window._weightProfiles = wp;
  }
} catch(e) {}
```

The FM constant and MAX_SCORE remain the same (118) but the dashboard can display which weight profile is active and note if weights have been calibrated.

---
