# Validation Report — Daily Horse Racing Analyzer

**Date**: 2026-03-25
**Overall Assessment**: Share with noted caveats

The scoring engine is structurally sound with research-backed factor logic. The probability model produces realistic outputs. Several medium-priority issues exist that could improve predictive accuracy and user experience over time.

---

## 1. Scoring Engine — Methodology Review

### What's working well

- **Form weighting** (0-20): Recency-weighted with 5-4-3-2-1 decay across last 5 runs. DNF penalty included. Solid.
- **Age scoring** (0-7): Race-type and distance-specific peaks (e.g. chasers 7-9, sprinters 3-4). Research-backed and well-differentiated.
- **Weight scoring** (0-8): Separates handicap vs non-handicap logic correctly. Relative-to-field approach is right.
- **Going/Course/Distance** (0-8/6/6): Dict and string parsing handles multiple data formats. Adjacent-going lookup is smart.
- **Fitness** (0-8): 14-42 day sweet spot is correct per racing research (Timeform benchmarks).

### Issues Found

**1. [Medium] Trainer scoring double-counts elite trainers**

`score_trainer()` returns up to 12 for elite names, then `score_trainer_rtf()` adds 0-5 on top. Line 686 caps at 12, but the issue is: if a trainer is elite AND has 25%+ RTF, they still only get 12 — same as an elite trainer with 5% RTF. The RTF bonus is wasted on elites and only helps unknowns. This means the trainer factor doesn't differentiate between an elite in-form vs elite out-of-form.

**Fix**: Weight the final trainer score as `(name_score * 0.4 + rtf_score * 0.6)` scaled to 12, so form always matters.

**2. [Medium] Draw scoring is oversimplified**

Currently a flat thirds split (low=4, mid=3, high=2). In reality, draw bias is course-specific and distance-specific. At Wolverhampton (tight AW track), low draws are strongly favoured at 5f-7f but neutral at 1m4f+. At York, high draws are favoured on the straight course.

**Fix**: Add a course-draw lookup table for the ~15 most common courses, keyed by distance bucket. Fall back to current thirds logic for unknowns.

**3. [Low] Headgear scoring has minimal range**

Range is just 2-3 points. No headgear = 2, headgear = 2, first-time = 3. This means the factor never scores 0 or 1, so it barely differentiates. A horse removing headgear (potentially negative signal) scores the same as one that's never worn any.

**Fix**: 0 = removing headgear, 1 = long-term headgear with declining form, 2 = no headgear, 3 = first-time.

**4. [Low] Spotlight NLP is keyword-based**

Keyword matching catches obvious cases but misses nuance ("could be anything" = positive in racing parlance, not caught). Max 2 points limits impact anyway.

**No fix needed** — the calibration engine will naturally down-weight this factor if it doesn't correlate with results.

---

## 2. Probability Model — Calculation Checks

### Model formula
```
prob = baseline + skill² × (1 - baseline) × 0.75
where baseline = topN / fieldSize, skill = score / 118
```

### Spot-check results (9-runner field)

| Score | % of Max | Win % | Top 3 % | Reasonable? |
|-------|----------|-------|---------|-------------|
| 94    | 80%      | 53%   | 68%     | Slightly high for a single race |
| 82    | 69%      | 45%   | 62%     | OK |
| 72    | 61%      | 39%   | 56%     | OK |
| 55    | 47%      | 30%   | 48%     | OK |
| 45    | 38%      | 25%   | 44%     | OK |

### Issues Found

**5. [Medium] Win probabilities for top-scored horse in small fields are inflated**

In a 6-runner race, a horse scoring 94/118 gets a 60%+ win probability. Real-world favourite win rates in 6-runner races are ~35-45% even for strong favourites. The `0.75` multiplier was tuned for 9-runner fields but doesn't scale down for small fields where randomness has more impact.

**Fix**: Add a field-size dampener: `dampener = 1 - 0.03 * max(0, 9 - fieldSize)`. This reduces the skill effect in small fields where outcomes are more volatile.

**6. [Low] getBetType thresholds don't account for race type**

A 40% win probability in a 5-runner novice chase (where favourites win ~40%) means something very different from 40% in a 20-runner handicap hurdle (where 40% would be exceptional). Currently both get the same WIN recommendation.

**Fix**: Scale thresholds by field size and race type (handicap/non-handicap).

---

## 3. DEEP DIVE Tab — Analytical Pitfalls

**7. [Medium] Pace analysis uses form digits, not running style**

The pace scenario checks if the first 3 form characters contain "1" or "2". But a horse finishing 1st could be a hold-up horse that came from behind. The form digit tells you finishing position, not running style. A front-runner who finishes 6th would NOT be flagged.

**Fix**: This would need running-style data from Racing Post (if available in scrape). Without it, add a caveat: "Based on recent finishing positions — actual running styles may differ."

**8. [Low] Head-to-head matrix counts raw factor wins, not weighted wins**

Horse A beating Horse B on "headgear" (max 3 pts) counts the same as beating them on "form" (max 20 pts). A horse could "win" 9/14 factors but lose on the 3 highest-weighted ones and still be weaker overall.

**Fix**: Show weighted advantage (sum of score differences where positive) alongside raw factor count. E.g. "9/14 factors (+12.5 pts)" vs "5/14 factors (+15.0 pts)" — immediately reveals who's actually stronger.

**9. [Low] Danger horse detection threshold is arbitrary**

Currently: first horse outside top 2 with ≥3 factors at ≥85% of max. This could flag a horse that maxes on headgear (3/3), draw (5/5), and spotlight (2/2) — all low-impact factors — while missing one that maxes on form and going.

**Fix**: Only count high-weight factors (form, rating, going, weight, trainer) for danger detection.

---

## 4. UI/UX — Improvement Proposals

**10. [High] Add race-by-race P&L tracker**

You're logging results but not tracking whether your picks made money. After logging, the system knows your predicted top pick and the actual winner. Add a running P&L column: if you backed the top pick at estimated SP, did it win? This is the ultimate measure of model quality — more meaningful than Spearman correlation alone.

**11. [High] Show score delta from field average on each horse**

Currently each horse shows raw score (e.g. 82/118). More useful: show how far above/below field average. In a weak race where everyone scores 40-55, a 55 is the standout. In a strong race where everyone scores 70-90, a 72 is the weakest. The raw number doesn't tell you this — the delta does.

**12. [Medium] Add a "confidence spread" metric per race**

Show the gap between 1st and 2nd scored horse as a headline number on each race card. Large gap = more confident selection. Small gap = competitive/risky. This already exists in the DEEP DIVE verdict but should be visible on the landing cards without needing to click in.

**13. [Medium] Colour-code the day bar by logged status**

When you have multiple days stored, the day buttons should show how many races were logged vs total. E.g. "Tue 24 Mar (4/10)" in green if fully logged, amber if partial. Helps you quickly see which days still need results input.

**14. [Low] Add keyboard shortcuts for results logging**

When ranking results, clicking tiles works but is slow for 12+ runner races. Add number keys (1-9, 0) to rank by saddle cloth number, and 'N' for NR mode toggle. Power users would log a full race card in seconds.

---

## 5. Required Caveats

- **The model cannot account for track conditions on race day** (rain arriving mid-card, ground changing). Going score is based on declared going, which can change.
- **Trainer/jockey scoring relies on a hardcoded elite list** that will go stale. The calibration engine won't fix this because it only adjusts factor weights, not the scoring logic within each factor.
- **Probability outputs are estimates, not odds.** They don't factor in market knowledge (money, inside info, gambler sentiment). A horse with 30% model probability might be 5/1 or 2/1 depending on market conditions.
- **Pace analysis is an approximation** — it uses finishing positions as a proxy for running style, which is inaccurate for hold-up horses that finish 1st.

---

## Priority Actions

| # | Issue | Impact | Effort |
|---|-------|--------|--------|
| 10 | P&L tracker | High (validates whole model) | Medium |
| 11 | Score delta from average | High (better interpretation) | Low |
| 5 | Small-field probability dampener | Medium (accuracy) | Low |
| 1 | Trainer RTF weighting | Medium (accuracy) | Low |
| 12 | Confidence spread on cards | Medium (UX) | Low |
| 8 | Weighted H2H advantage | Medium (DEEP DIVE accuracy) | Low |
| 2 | Course-specific draw table | Medium (accuracy) | Medium |
| 13 | Day bar logged status | Low (UX) | Low |
| 14 | Keyboard shortcuts | Low (UX) | Low |
