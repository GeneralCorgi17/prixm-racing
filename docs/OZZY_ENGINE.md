# Ozzy Engine

Ozzy is an AI tipster layer built on top of the Prixm scoring engine. He analyses each NAP/WIN/STRONG pick using the Anthropic API, forms his own opinions, tracks his performance, and self-improves over time through a reflection loop.

---

## Files

| File | Role |
|------|------|
| `engine/ozzy/ozzy_engine.js` | Core: API call, memory load/save, shadow mode, conviction firing, brief cache, UI fill functions |
| `engine/ozzy/ozzy_prompts.js` | All prompts: system prompt + `buildOzzyContext()` context builder |
| `engine/ozzy/ozzy_audit.js` | All post-result processing: retro audit, reasoning audit, stats rebuild, day reflection, lesson extraction, streak reflection |
| `engine/ozzy/ozzy_ui.js` | All rendering: pick panel, tab cards, stats dashboard, conviction library, performance review section |

---

## Positions

| Position | Meaning | Stat tracked |
|----------|---------|--------------|
| BACKED | Explicit bet recommendation | wins / total |
| WITH IT | Agrees with engine, no strong view | wins / total |
| WATCHING | Interested, not committing | wins / total |
| DOUBT | Has concerns — don't back | avoided losses / total (avoidance %) |
| OFF IT | Actively opposes — don't bet | called losses / total (opposition %) |

DOUBT and OFF IT both trigger an `confirm()` warning dialog if user clicks BET on that horse.

---

## Memory (`ozzyMemory` in localStorage)

```
memory.convictions[]         — active/candidate/expired conviction rules
memory.stats.overall         — per-position stats {backed,with_it,watching,doubt,off_it}
memory.stats.by_venue        — win% per venue (on-pick calls)
memory.stats.by_going        — win% per going (on-pick calls)
memory.recent_backed[]       — last 10 BACKED calls with outcomes
memory.recent_off_it[]       — last 10 OFF IT calls with outcomes
memory.notable_wrong_calls[] — last 10 wrong calls with lesson field
memory.daily_reflections[]   — last 30 daily reflections (date, text, generated)
memory.lessons[]             — last 20 extracted lessons (date, lesson, applies_to, type)
memory.alerts[]              — streak warnings (3 consecutive BACKED losses)
memory.audit_log[]           — full event log (last 200 entries)
memory.shadow_mode           — thresholds config
```

---

## Daily Brief Cache

Each pick analysis is cached in localStorage as `ozzyDailyBriefs_YYYY-MM-DD`.  
Structure per brief: `{horse, venue, time, date, position, comment, edge, category, conviction_ids, shadow_mode, silent, raw_response}`

`silent: true` = Ozzy had no concerns and no fired convictions → skipped API call, stored WITH IT automatically.  
`ozzyAnalysePick()` always checks cache first — no duplicate API calls.

To force re-analysis: `localStorage.removeItem('ozzyDailyBriefs_' + today)` in browser console.

---

## Shadow Mode

Ozzy stays silent until thresholds are met:
- `results_threshold: 80` — at least 80 results in history
- `conviction_fire_threshold: 5` — at least 5 total conviction fires
- `active_conviction_threshold: 1` — at least 1 active conviction

Currently OUT of shadow mode (1062+ results, 1 active conviction).

---

## Conviction System

Convictions are pattern rules that fire against picks. Lifecycle:
- **candidate** → fires ≥3 times AND strike rate >60% → **active**
- **active** → fires ≥5 times AND strike rate <40% → **expired**
- Active conviction with ≥10 fires and >70% strike rate gets `weight: 1.5`

Seed convictions (all start as candidate):
- `going_unverified_heavy` — going score ≥6 but no verified soft/heavy run
- `class_drop_masking` — class drop inflating score after poor runs
- `fresh_trainer_flat` — trainer sends horse fresh (90d+), poor fresh record
- `phantom_cdp_course` — course score from single run 18+ months ago
- `competitive_prob_compressed` — top 2 Bradley-Terry gap ≤5%

---

## Auto-Trigger Chain (on results load)

When `Fetch Results.bat` is run and the UI reloads:

```
load() detects new races (added > 0)
  └── 600ms → ozzyRetroAudit(date)
                fires convictions against each race's engine top pick
                logs retro_audit_complete (skip guard for future runs)
  └── 600ms → ozzyRunReasoningAudit(date)
                for each BACKED/OFF IT brief: secondary API call assesses reasoning quality
                backfills lesson on wrong calls
                triggers ozzyDayReflection at end
  └── 600ms → ozzyRebuildStats()
                full recompute of per-position stats from ALL dates+briefs
                no guard — always correct
  └── 2100ms → ozzyDayReflection(date)
                 Ozzy compares pre-race comments vs actual results
                 writes narrative reflection (3–5 sentences)
                 stores in memory.daily_reflections[]
                 triggers ozzyExtractLessons at end
                   └── ozzyExtractLessons(date, text, memory)
                         Haiku call extracts 1-3 actionable lessons as JSON
                         stores in memory.lessons[]

3s fallback (always, even if added===0):
  ozzyRebuildStats()
  ozzyDayReflection(today)   ← skip guard prevents duplicate reflection
```

---

## Analysis Context (`buildOzzyContext`)

Every pick analysis includes:
- Factor profile (score breakdown)
- CDP summary (Course/Distance/Going/Class)
- Verification pass result (CAS score, flags)
- Active convictions that fired on this pick
- Recent BACKED record (last 5)
- Recent OFF IT record (last 5)
- Wrong calls with lessons (last 3)
- Extracted failure patterns from lessons[] (last 5)
- Daily reflections (last 3)
- Per-position track record (BACKED/WITH IT/WATCHING/DOUBT/OFF IT win%)
- Venue and going accuracy

---

## Stats Rebuild Logic

`ozzyRebuildStats()` in `ozzy_audit.js`:
1. Gets all unique dates from `results_history.races`
2. For each date, gets Ozzy's daily briefs from localStorage
3. For each brief, searches that date's races for the horse by name + finish_pos
4. Increments per-position counter based on `brief.position` and `won` (finish_pos===1)
5. BACKED/WITH IT/WATCHING also update by_venue and by_going accuracy
6. Fully overwrites `memory.stats` — no accumulation, always correct

---

## Nuance: Luck vs Bad Reasoning

System prompt instructs Ozzy:
- Fell / pulled up / hampered / non-runner = bad luck, NOT a reasoning failure
- Reasoning audit marks these as `UNDETERMINED` not `FLAWED`
- Day reflection system prompt includes same instruction
- Don't make drastic conviction changes from a single loss without examining race run

---

## API Calls Summary

| Call | Model | Max tokens | When |
|------|-------|-----------|------|
| Pick analysis | claude-sonnet-4-6 | 500 | Per NAP/WIN/STRONG on tab open (cached) |
| Reasoning audit | claude-sonnet-4-6 | 200 | Per BACKED/OFF IT call after results load |
| Day reflection | claude-sonnet-4-6 | 400 | Once per date after results load |
| Lesson extraction | claude-haiku-4-5 | 300 | Once per date, chained from reflection |
| Streak reflection | claude-sonnet-4-6 | 300 | After 3 consecutive BACKED losses |
