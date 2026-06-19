# Prixm Racing Analyzer

Horse racing analysis tool. Scores runners across 14 weighted factors, generates picks, tracks bets, logs results, and self-calibrates weights over time.

## Project Structure

```
├── daily_racing_analyzer.html   # Main UI — single-file HTML+CSS+JS (~350KB)
├── DASHBOARD_Implement.md       # Golden dashboard requirements spec
├── Start App.bat                # Launch server + browser (use this daily)
├── Fetch Results.bat            # Run results_fetcher.py (date menu: today/yesterday/specific)
├── Fetch Racecard.bat           # Run racecard_fetcher.py
├── Fetch Racecard (API).bat     # Run racecard_fetcher_api.py
├── Export Qualifying.bat        # Run qualifying_exporter.py → rebuilds output/qualifying_picks.xlsx
├── Backfill SP Prices.bat       # Backfill SP prices for past qualifying picks
├── race_data.db                 # SQLite database — PRIMARY store for all results (WAL mode)
├── daily_race_data.json         # Current day's race data (loaded by UI)
├── daily_race_data.js           # Same data wrapped in JS var for HTML <script> loading (file:// fallback)
├── results_history.json         # JSON export of race_data.db — kept in sync, used as fallback
├── results_history.js           # Same data wrapped in JS var for HTML <script> loading
├── ozzy_memory.json             # Ozzy's conviction library, stats, reflections, lessons (synced to localStorage)
├── scripts/
│   ├── db_server.py             # SQLite HTTP server — port 7432, stdlib only, no pip needed
│   ├── migrate_to_sqlite.py     # One-time migration: results_history.json → race_data.db
│   ├── results_fetcher.py       # Scrapes race results, matches to predictions, dual-writes JSON + SQLite
│   ├── racecard_fetcher.py      # Scrapes racecards from Racing Post (HTML parsing)
│   ├── racecard_fetcher_api.py  # Fetches racecards via API
│   ├── qualifying_exporter.py   # Builds output/qualifying_picks.xlsx from race_data + results_history
│   └── check_qualifiers.py      # Startup checker — prints today's qualifying pick status
├── engine/
│   ├── fetch_daily_races.py     # Daily race data pipeline
│   ├── calibration_engine.py    # Weight calibration engine
│   └── ozzy/
│       ├── ozzy_engine.js       # Core: API calls, memory load/save, shadow mode, conviction firing
│       ├── ozzy_prompts.js      # System prompt + context builder, lesson relevance filter
│       ├── ozzy_audit.js        # Post-result chain: retro audit, reasoning audit, stats rebuild, reflection, lessons
│       └── ozzy_ui.js           # Rendering: pick panel, stats dashboard, conviction library
├── race_data/                   # Archived daily JSON files (race_data_YYYY-MM-DD.json)
├── output/
│   └── qualifying_picks.xlsx    # Auto-generated qualifying picks (see thresholds below)
├── debug/
│   ├── debug_index.html         # Debug version of main UI
│   └── debug_race_result.html   # Debug version of results viewer
└── docs/
    ├── UI_STRUCTURE.md          # Full UI map: all tabs, panels, functions, state, localStorage keys
    ├── OZZY_ENGINE.md           # Ozzy technical reference (streak reflection removed in v0.5 — API calls table stale)
    ├── PRIXM_IMPROVEMENT_PLAN.md
    ├── PRIXM_OVERVIEW.md
    ├── MIGRATION.md
    └── Prixm Daily Workflow.pdf
```

## SQLite Backend

**Primary data store** as of 2026-05-28. `race_data.db` replaces localStorage as the source of truth.

| Component | File | Notes |
|-----------|------|-------|
| DB server | `scripts/db_server.py` | stdlib only, port 7432, WAL mode, CORS * |
| Migration | `scripts/migrate_to_sqlite.py` | one-time, safe to re-run |
| Launcher  | `Start App.bat` | checks if server running, starts if not, opens browser |

**API endpoints:**
- `GET  /api/health` → `{"status":"ok","races":N}`
- `GET  /api/results` → full `results_history` format JSON
- `POST /api/results` → upsert one race record
- `DELETE /api/results/{date}/{venue}/{time}` → remove race

**HTML loading priority:** localhost:7432 → `_resultsHistoryFile` JS global → `results_history.json` fetch → localStorage.
Tab bar shows `🟢 DB N races` (server live) or `🟡 JSON` (fallback).

**Dual-write:** `results_fetcher.py` writes to SQLite (via `_write_to_sqlite(entry)`) AND JSON after every fetch.
JSON stays in sync as permanent fallback. SQLite is primary.

---

## Segment Classification

Every logged race gets a `segment` field at log time (`results_fetcher.py → classify_segment()`). Never recalculated later.

| Segment | Criteria |
|---------|----------|
| `golden` | non-hcap · gap ≥18 · score ≥74 |
| `silver` | non-hcap · gap 10–<12 · score ≥72 · Turf |
| `dead_zone` | non-hcap · gap 12–18 (log only, never bet or analyse) |
| `bronze` | non-hcap · gap 8–<10 · score ≥74 · Going = Good or Good To Firm |
| `handicap` | handicap race (any gap) |
| `other` | everything else non-hcap |

**Dead zone (gap 12–18):** logged for completeness, never included in any pick segment or analysis.
**Silver gap is strictly <12** — gap 12+ is dead zone, never silver.

`classify_segment(is_hcap, gap, top_score, surface, going='')` — signature updated 2026-05-31 to accept going for bronze detection.

Historical records backfilled 2026-05-28 (1,561 races). Current counts: golden 37 · silver 24 · dead_zone 69 · handicap 1072 · other 359.

---

## Golden Segment

**Filter (from 2026-05-29):** UK, non-handicap, gap ≥18, score ≥74, SP >2.0 (ROI calc)
**Previous threshold (before 2026-05-29):** gap ≥17, no score filter

Displayed on racecard as `⭐ GOLDEN` banner via `getGoldenFlags()` + `renderGoldenFlag()`.

Gap sub-bands (racecard + dashboard): 18–20 (good) · 20–23 (great) · 23+ (elite)

### Golden Dashboard Tab

Analytics for all historical golden picks. Auto-polls every 60s.

| Panel | Content |
|-------|---------|
| 1 — Headline | Golden SR · Golden ROI · UK Handicap SR · Break-even SR |
| 2 — Gap Bands | UK NH base: <15 / 15–18 / 18–21 / 21–24 / 24+ |
| 3 — Score Bands | Golden only: 74–75 / 75–80 / 80–85 / 85+ |
| 4 — Going | Golden only, grouped by going string |
| 5 — Sweet Spots | Gap≥18+Score80 / Good/GF+Gap≥18 / Turf / AW |
| 6 — Silver Section | Separate section below Golden (HR divider) |
| 7 — Bronze Section | Separate section below Silver (HR divider) |

---

## Silver Segment

**Filter:** UK, non-handicap, gap 10–12, score ≥72, Turf (AW excluded via Standard going), SP >2.0 (ROI calc)
**Dead zone gap 12–18 is excluded** — not golden, not silver, never bet.

Displayed on racecard as `🥈 SILVER` banner via `getSilverFlags()` + `renderSilverFlag()`.
Turf detected from going: `Standard`/`Standard To Slow` = AW (no `surface` field on racecard data).

Silver section lives below Golden in the Golden tab (HR divider). Shows: SR, ROI, gap sub-bands (10–11 · 11–12), score bands (75–80/80–85/85+), going breakdown.

---

## Bronze Segment

**Filter:** UK, non-handicap, gap 8–<10, score ≥74, Going = Good or Good To Firm, SP >2.0 (ROI calc)
**Track only** — no real bets until 30+ picks logged.

Displayed on racecard as `🥉 BRONZE` banner via `getBronzeFlags()` + `renderBronzeFlag()`.
Going matched via normalized lowercase: `good` or `goodtofirm` (hyphens/spaces stripped).

Bronze section lives below Silver in the Golden tab (HR divider). Shows: SR, ROI, gap sub-bands (8–9 · 9–10), score bands (74–75/75–80/80–85/85+), going breakdown.

---

## Scoring Engine

14 weighted factors with configurable max scores:

| Factor | Max | Description |
|--------|-----|-------------|
| form | 20 | Recent finishing positions |
| rating | 15 | RPR/official rating |
| trainer | 12 | Trainer recent form % |
| jockey | 10 | Jockey quality |
| fitness | 8 | Days since last run |
| class | 8 | Race class suitability |
| going | 8 | Ground preference |
| weight | 8 | Weight carried |
| age | 7 | Age factor |
| course | 6 | Course form |
| distance | 6 | Distance suitability |
| draw | 5 | Draw position |
| headgear | 3 | Headgear (first-time bonus) |
| spotlight | 2 | Expert opinion |

**MAX_SCORE** = sum of all maximums (currently 118)

Factor weights are defined in `FM` object at top of `daily_racing_analyzer.html`. The calibration engine adjusts these based on logged results.

## Prixm Picks Engine

Selects top picks from all races using edge score (competitive advantage over field).

**Quality gate**: edge ≥ 40 to qualify as a Prixm pick.

**Categories** (by edge threshold):
- **NAP** — best bet of the day (highest edge, ≥70)
- **WIN** — strong win candidate (edge ≥60)
- **STRONG** — solid selection (edge ≥50)
- **PLACE** — place prospect (edge ≥40)

### Smart Bet Type Engine (`getPrixmBetRec`)

Separates pick quality from bet recommendation. Respects bookmaker place terms as hard constraints:

| Field Size | Place Terms | Bet Options |
|-----------|-------------|-------------|
| 2-4 | WIN only | WIN or SKIP |
| 5-7 | 2 places | WIN, TOP 2, SKIP |
| 8-15 | 3 places | WIN, EW, TOP 3, SKIP |
| 16+ | 4 places | WIN, EW, TOP 4, SKIP |

Uses Bradley-Terry softmax competitive probability model (alpha=2.5) via `calcCompetitiveProb()`.

Generates reasoning tags (pos/neg/neu) from: gap, CDP, momentum, field size, handicap flag, score %, connection changes.

## CDP (Class · Distance · Going · Course)

Proven form analysis. Each factor scored as percentage of its max:
- ≥70% → Proven
- 40-69% → Untested
- <40% → Concern

`buildCDP(runner, race)` returns `{cards, proven, total, scoreCls, scoreCol, summaryText}`. The `cards` array is used by the bet engine for reasoning tags.

## Connection Change Detector

Compares today's jockey/trainer against the horse's **last logged result** in `results_history`. Flags changes with a compact badge (🔄J / 🔄T / 🔄J+T) on the jockey/trainer line. Click to see dropdown with old→new stats (win%, place%) and upgrade/downgrade/lateral direction.

Also adds neutral reasoning tags in Prixm picks: "🔄 New Jockey" / "🔄 New Trainer".

Only works in main UI (requires results_history).

## Verification Pass

Runs after scoring on NAP (edge ≥70) and WIN (edge ≥60) picks. Issues a verdict without altering the score.

**Three phases:**
1. **Factor Legitimacy Audit** — classifies each contributing factor as verified/unverified using `results_history`. Evidence >12 months old = Unverified Positive.
2. **Counter-Argument Score (CAS)** — 0–100 metric accumulated against the pick. Signals include: CDP concerns, competitive probability gap ≤5%, weight/going mismatches, connection change to weaker connections, bounce/ring-rust risk, class drop masking.
3. **Bayesian Confidence Update** — `confidence = edge × (1 - unverifiedRatio × 0.30) × (1 - CAS/200)`

**Verdict states:**

| State | Condition |
|-------|-----------|
| ✅ CONFIRMED | CAS < 31, ≤1 unverified positive |
| ⚠️ CONDITIONAL | CAS 31–70 or ≥2 unverified positives |
| 🚫 FLAGGED | CAS > 70 or 3+ unverified positives |

`runVerificationPass(runner, race, resultsHistory)` in `daily_racing_analyzer.html`. Verdict and CAS score passed to Ozzy's context.

---

## Ozzy Engine (v0.6)

AI tipster layer built on Claude API. Reads NAP/WIN/STRONG picks, forms independent opinions, self-improves through a daily reflection loop. All files in `engine/ozzy/`.

Public explainer: `OzzyEngine0.5.md` (root). Technical reference: `docs/OZZY_ENGINE.md`.

### Positions

| Position | Badge | Meaning |
|----------|-------|---------|
| BACKED | 🔥 | High conviction agreement. Issues independent bet rec. May differ from engine's. |
| WITH IT | ✅ | Agrees, nothing meaningful to add. Often silent — no panel rendered. |
| WATCHING | 🤔 | Interested but not committing. Flags specific nagging concern. |
| DOUBT | ⚠️ | Material concern engine scored past. Advises against. |
| OFF IT | 🚫 | High conviction disagreement. Full explanation. May name counter in same race. |

WITH IT with comment <20 words → `render: false` (enforced in `parseOzzyResponse()`) → no panel. Silence is valid output.

BACKED requires structured second line: `BET: [WIN/EW/TOP N/SKIP] | CONFIDENCE: [HIGH/MODERATE/SPECULATIVE]`. Parser extracts `betRec` and `confidence` as discrete fields.

### Shadow Mode

Ozzy stays silent until: 80+ results logged, 5+ conviction fires, ≥1 active conviction. **Currently DISABLED** (`OZZY_ENABLED = false`, line 3 of `engine/ozzy/ozzy_engine.js`). 1561+ results in history. To re-enable: set `true`.

### Conviction System

Pattern rules that fire against picks. Not FM weights — convictions are specific and falsifiable.

**Lifecycle:** candidate → (fires ≥3, strike rate >60%) → **active** → (fires ≥5, <40%) → **expired**. Active with ≥10 fires and >70% strike rate gets `weight: 1.5`.

**Seed convictions:**

| ID | Description |
|----|-------------|
| `going_unverified_heavy` | Going score ≥6 but no verified soft/heavy run in last 12 months |
| `class_drop_masking` | Class drop inflating score after 3+ poor runs at higher class |
| `fresh_trainer_flat` | Trainer sends horse fresh (90d+), poor fresh record |
| `phantom_cdp_course` | Course score from single run 18+ months ago |
| `competitive_prob_compressed` | Top-2 Bradley-Terry gap ≤5% — weak field inflating edge |

New convictions auto-generated by reasoning audit when Ozzy identifies new patterns.

### Auto-Trigger Chain (on results load)

```
load() detects new races (added > 0)
  → 600ms: ozzyRetroAudit(date)      fires convictions against engine picks; logs retro_audit_complete
             skip path ALSO chains → ozzyDayReflection (v0.6 fix — was silently dropping reflection)
  → ozzyRunReasoningAudit(date)      per BACKED/OFF IT: secondary API call on reasoning quality
  → ozzyRebuildStats()               full recompute of all position stats from all dates+briefs
  → 2100ms: ozzyDayReflection(date)  3–5 sentence post-race self-assessment
              → ozzyExtractLessons() extracts 1–3 actionable lessons (Haiku call), stores in memory.lessons[]

3s fallback (always, even if added===0):
  ozzyRebuildStats()
  ozzyDayReflection(today) ← skip guard prevents duplicate
```

All steps have skip guards. `ozzyDayReflection` only generates once per date.

### API Calls

| Call | Model | Max tokens | When |
|------|-------|-----------|------|
| Pick analysis | claude-sonnet-4-6 | 500 | Per NAP/WIN/STRONG on tab open (cached per day) |
| Reasoning audit | claude-sonnet-4-6 | 200 | Per BACKED/OFF IT call after results load |
| Day reflection | claude-sonnet-4-6 | 400 | Once per date after results load |
| Lesson extraction | claude-haiku-4-5 | 300 | Once per date, chained from reflection |

JSON-returning calls (reasoning audit, lesson extraction, conviction mining) use a minimal system prompt — full character prompt breaks JSON parsing.

### Key Functions

| Function | File | Purpose |
|----------|------|---------|
| `ozzyAnalysePick(pick, race)` | ozzy_engine.js | Main entry: check cache, fire convictions, call API |
| `buildOzzyContext(pick, race, memory)` | ozzy_prompts.js | Assemble full prompt context |
| `buildRelevantLessons(memory, race)` | ozzy_prompts.js | Filter lessons by going/venue/class/code (exact normalised match, not substring) |
| `sanitiseMemoryForContext(memory)` | ozzy_engine.js | Strip `alerts`, `audit_log`, `shadow_mode` before API serialisation |
| `parseOzzyResponse(text)` | ozzy_engine.js | Extract position + comment; enforce WITH IT silence rule |
| `ozzyRebuildStats()` | ozzy_audit.js | Full recompute of per-position stats — always correct, no accumulation |
| `ozzyDayReflection(date)` | ozzy_audit.js | Post-race narrative; chains to lesson extraction |

### Ozzy Memory (`ozzyMemory` in localStorage)

```
memory.convictions[]         — conviction rules (candidate/active/expired)
memory.stats.overall         — per-position stats {backed, with_it, watching, doubt, off_it}
memory.stats.by_venue        — win% per venue
memory.stats.by_going        — win% per going
memory.recent_backed[]       — last 10 BACKED calls with outcomes
memory.recent_off_it[]       — last 10 OFF IT calls with outcomes
memory.notable_wrong_calls[] — last 10 wrong calls with lesson field
memory.daily_reflections[]   — last 30 daily reflections (45-day archive)
memory.lessons[]             — last 20 extracted lessons with condition tags (going, code, class, venue)
memory.alerts[]              — internal only (stripped from API context)
memory.audit_log[]           — full event log, last 200 entries (stripped from API context)
```

Lesson schema: `{ text, conditions: {going, code, class, venue}, created, source_reflection }`. `null` condition = matches all.

### v0.6 Bug Fixes (May 2026)

- **Reflection chain broken by retro audit skip guard** — skip path now chains to `ozzyDayReflection()` before returning
- **Lesson sort using wrong field** — `b.date` → `b.created||b.date`; map also falls back `l.lesson||l.text`
- **Going/venue match too loose** — substring match replaced with exact normalised match (`norm = g => g.toLowerCase().replace(/[\s-]+/g,'_')`)

---

## EXCLUDED_VENUES

**CRITICAL**: Maintained in 2 files — both must be updated together:
1. `daily_racing_analyzer.html` — JS array (search `EXCLUDED_VENUES`)
2. `scripts/results_fetcher.py` — Python list (line ~28)

`scripts/qualifying_exporter.py` has its own comprehensive list at line ~89 (managed separately — also includes Irish tracks via `_IRE_TRACKS` set).

Current list (results_fetcher + HTML):
- **Asia/HK/ME**: happy valley, sha tin, meydan, abu dhabi, bahrain, hanshin, chukyo, fukushima, nakayama, tokyo, niigata, kyoto
- **Australasia**: rosehill, flemington, morphettville, eagle farm, doomben, hawkesbury, ascot aus, gold coast
- **South Africa**: turffontein, scottsville
- **USA/Canada**: oaklawn park, gulfstream park, keeneland, aqueduct, santa anita, belmont park, churchill downs, laurel park, woodbine
- **France**: saint cloud, longchamp, deauville, chantilly, auteuil, compiegne, toulouse, bordeaux
- **Germany/Italy**: san siro, munich, dusseldorf, krefeld, cologne, koln, randwick
- **Ireland**: punchestown, leopardstown, curragh, naas, cork, killarney, gowran park, roscommon, navan, limerick, clonmel, wexford, tramore, kilbeggan, ballinrobe, sligo, down royal, bellewstown, downpatrick, dundalk, tipperary, fairyhouse, galway, laytown
- **Meta**: free to air, scoop, worldwide stakes, world pool

Venue matching uses lowercase substring. Hyphens normalized to spaces in `results_fetcher.py` (`normalize_venue()`).
Irish venues also caught by `(IRE)` suffix check before list lookup.

## Data Flow

1. **Fetch racecard** → `scripts/racecard_fetcher.py` or `scripts/racecard_fetcher_api.py` → writes `daily_race_data.json` + `race_data/race_data_YYYY-MM-DD.json`
2. **View in UI** → `Start App.bat` starts `scripts/db_server.py` + opens `daily_racing_analyzer.html`
3. **After racing** → `scripts/results_fetcher.py` scrapes results, matches predictions, dual-writes `results_history.json` + `race_data.db`
4. **Calibration** → UI's calibration engine reads results history, adjusts FM weights per profile (aw/turf_flat/nh)
5. **Qualifying Excel** → `Export Qualifying.bat` → `scripts/qualifying_exporter.py` → rebuilds `output/qualifying_picks.xlsx`

## localStorage Keys (Main UI)

| Key | Purpose |
|-----|---------|
| `raceData` | Current day's race data |
| `raceDataPastedDate` | Date of manually pasted data (prevents stale file overwrite) |
| `topPicks_YYYY-MM-DD` | Saved picks per date |
| `resultsHistory` | Results cache — cleared automatically when DB server is live |
| `comboTracker` | Jockey/trainer combination stats |
| `horseWatchlist` | Tracked horses |
| `myBets` | Personal bet selections with bet type |
| `picksCalibration` | Picks calibration data |
| `ozzyMemory` | Ozzy conviction library, stats, reflections, lessons, audit log |
| `ozzyDailyBriefs_YYYY-MM-DD` | Ozzy's pick analyses per date (cache — prevents duplicate API calls) |

**Quota handling**: `saveDayData()` has recovery logic — on quota exceeded, clears old data (old topPicks, large caches) and retries. Alerts user if still failing.

## Key UI Features

- **Race card view** with expandable runner details (score breakdown, CDP, momentum, probabilities)
- **Race card border colors** — 9px left border on each card indicates country + handicap type:
  - 🔵 Blue `#3b82f6` — England, Non-Handicap
  - 🟡 Amber `#f59e0b` — England, Handicap
  - 🟢 Green `#10b981` — Ireland, Non-Handicap
  - 🔴 Red `#f87171` — Ireland, Handicap
  - Powered by `isIreland(course)` + `IRE_TRACKS` set + `getRaceBorderColor(r)` (global scope, just above `renderRaceCards`)
  - Legend and filter buttons shown in Race Type row of filter bar (below Field Size row)
- **Race Type filter** — filter cards by ENG NH / ENG HCP / IRE NH / IRE HCP (toggleable, state in `st.raceTypeFilter`)
- **Confidence + Gap filters** — filter cards by confidence tier (TOP PICK/STRONG/SOLID/MODERATE) and gap band (Tight/Competitive/Clear)
- **Golden flag** — `⭐ GOLDEN` banner on qualifying race cards (gap≥18, score≥74, UK NH) via `getGoldenFlags()` / `renderGoldenFlag()`
- **Silver flag** — `🥈 SILVER` banner on qualifying race cards (gap 10–<12, score≥72, UK NH, Turf) via `getSilverFlags()` / `renderSilverFlag()`
- **Bronze flag** — `🥉 BRONZE` banner on qualifying race cards (gap 8–<10, score≥74, UK NH, Good/GF) via `getBronzeFlags()` / `renderBronzeFlag()`
- **DB status badge** — `#dbStatusBadge` in tab bar: `🟢 DB N races` (server live) or `🟡 JSON` (fallback)
- **Prixm Picks** — Design C layout: accent bar, category dot+label, horse name, bet chip, edge bar with % fill, reasoning tags
- **Personal bet tracker** — BET button per runner, bet type selection (EW/WIN/TOP N), export as PNG
- **Combination tracker** — horse+jockey, horse+trainer, jockey+trainer combos from results history
- **Horse watchlist** — track specific horses across race days
- **Results logger** — fetches and logs race results
- **Weight calibration** — self-tuning factor weights from logged results
- **Golden Dashboard tab** — analytics: Golden (gap≥18 score≥74) + Silver (gap 10–<12 score≥72 Turf) + Bronze (gap 8–<10 score≥74 Good/GF) sections. Auto-polls every 60s.

## Code Style

- Single-file HTML with inline CSS and JS (no build tools, no frameworks)
- All JS is vanilla — no React, no jQuery
- CSS uses custom properties (--bg, --card, --text, --muted, --accent, etc.)
- Dark theme only
- Functions are global scope, no modules
- Template literals for HTML generation
- Primary data store: SQLite (`race_data.db`) via local HTTP server. localStorage used for UI state + fallback cache only.

## Common Tasks

**Add venue to exclude list**: Update 2 files — `daily_racing_analyzer.html` (search `EXCLUDED_VENUES`) + `scripts/results_fetcher.py` line ~28. Also update `scripts/qualifying_exporter.py` line ~89 separately (has its own list).

**Modify scoring weights**: Edit `FM` object in `daily_racing_analyzer.html`.

**Add a Prixm reasoning tag**: Edit `getPrixmBetRec()` in `daily_racing_analyzer.html`.

**Modify Prixm pick display**: Edit `renderPrixmPicks()` in `daily_racing_analyzer.html`.

**Force Ozzy re-analysis**: `localStorage.removeItem('ozzyDailyBriefs_' + today)` in browser console.

**Modify Ozzy system prompt**: Edit `OZZY_SYSTEM_PROMPT` in `engine/ozzy/ozzy_prompts.js`.

**Add/edit Ozzy conviction**: Modify seed array in `engine/ozzy/ozzy_engine.js` (new convictions start as `candidate`).

**Reset Ozzy memory**: `localStorage.removeItem('ozzyMemory')` — clears all stats, convictions, reflections. Use with caution.

**Modify Verification Pass**: Edit `runVerificationPass()` in `daily_racing_analyzer.html`. CAS signal weights are defined inline in that function.

**Rebuild qualifying Excel**: Run `Export Qualifying.bat` or `python scripts/qualifying_exporter.py`. Output: `output/qualifying_picks.xlsx`.

**Modify Golden Dashboard**: Edit `renderGoldenDashboard()` IIFE block in `daily_racing_analyzer.html` (search `GOLDEN DASHBOARD`).

**Modify Silver segment filter**: Edit `buildSilverPicks()` (dashboard) and `getSilverFlags()` (racecard badge) in `daily_racing_analyzer.html`.

**Modify Bronze segment filter**: Edit `buildBronzePicks()` (dashboard) and `getBronzeFlags()` (racecard badge) in `daily_racing_analyzer.html`. Also edit `classify_segment()` in `scripts/results_fetcher.py`.

**Start the app**: Run `Start App.bat` — starts `scripts/db_server.py` on port 7432, opens browser.

**Rebuild SQLite from JSON**: `python scripts/migrate_to_sqlite.py` — safe to re-run, upserts all races.

**Query SQLite directly**: `sqlite3 race_data.db` → `SELECT segment, COUNT(*) FROM races GROUP BY segment;`

**Modify segment logic**: Edit `classify_segment()` in `scripts/results_fetcher.py`. Backfill existing records by running the inline backfill snippet (see migrate_to_sqlite.py for the pattern).

## Python Dependencies

- `requests`, `beautifulsoup4`, `lxml` — for scraping
- `openpyxl` — for Excel export
- `sqlite3`, `http.server` — stdlib, used by db_server.py (no pip needed)
- Standard library: `json`, `re`, `datetime`, `argparse`, `os`

## Windows Batch Files

All `.bat` files use `@echo off`, `cd /d "%~dp0"`, and call Python scripts in `scripts/`.

| File | Script called | Notes |
|------|--------------|-------|
| `Start App.bat` | `scripts/db_server.py` + browser | **Use this daily** — starts server, opens HTML |
| `Fetch Results.bat` | `scripts/results_fetcher.py` | Date menu: 1=today, 2=yesterday, 3=day before, 4=specific |
| `Fetch Racecard.bat` | `scripts/racecard_fetcher.py` | HTML scrape from Racing Post |
| `Fetch Racecard (API).bat` | `scripts/racecard_fetcher_api.py` | API-based fetch |
| `Export Qualifying.bat` | `scripts/qualifying_exporter.py` | Rebuilds `output/qualifying_picks.xlsx` |
| `Backfill SP Prices.bat` | backfill script | Fills missing SP prices in past qualifying rows |

## Qualifying Excel Thresholds

`output/qualifying_picks.xlsx` — rebuilt by `Export Qualifying.bat`.

| Period | Gap | Score | Other |
|--------|-----|-------|-------|
| Before 2026-05-29 | ≥17 | none | non-HCP, England, SP >2.0 |
| From 2026-05-29   | ≥18 | ≥74  | non-HCP, England, SP >2.0 |

Silver sheet rows: gap 10–<12, score ≥72, Turf, SP >2.0
Bronze sheet rows: gap 8–<10, score ≥74, Good/GF, SP >2.0

**Default stake: £10 (1U).** Set in `O2` (main sheet) and `M2` (watch sheet). User-editable.

**SP<2 Watch List sheet** — second sheet in `qualifying_picks.xlsx`. All Golden/Silver/Bronze picks where SP ≤2.0 are automatically moved here on rebuild. Includes stake calc (£10 default in `M2`, Net in col K, balance in `N2`). Diagnostic only — no real bets.

Constants in `qualifying_exporter.py`: `MIN_GAP=17`, `MIN_GAP_NEW=18`, `MIN_SCORE_NEW=74`, `NEW_THRESHOLD_DATE='2026-05-29'`, `STAKE_CELL='$O$2'`, `W_STAKE_CELL='$M$2'`.
