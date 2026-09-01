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
├── Fetch Weather Signal.bat     # Manual re-run of weather_fetcher.py — normally runs automatically from Fetch Racecard(.bat/(API).bat)
├── race_data.db                 # SQLite database — PRIMARY store for all results (WAL mode)
├── daily_race_data.json         # Current day's race data (loaded by UI)
├── daily_race_data.js           # Same data wrapped in JS var for HTML <script> loading (file:// fallback)
├── results_history.json         # JSON export of race_data.db — kept in sync, used as fallback
├── results_history.js           # Same data wrapped in JS var for HTML <script> loading
├── weather_signal.json          # Venue-level going-shift forecast (improvement.md Feature 2), gitignored
├── weather_signal.js            # Same, wrapped in window._weatherSignalFile for file:// loading, gitignored
├── ozzy_memory.json             # Ozzy's conviction library, stats, reflections, lessons (synced to localStorage)
├── scripts/
│   ├── db_server.py             # SQLite HTTP server — port 7432, stdlib only, no pip needed
│   ├── migrate_to_sqlite.py     # One-time migration: results_history.json → race_data.db
│   ├── backfill_distance_class.py # One-off: backfill races.distance_f/race_class from race_data/ archives
│   ├── weather_fetcher.py       # Fetches OpenWeatherMap forecast per venue, writes weather_signal.json/.js
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
- `PATCH /api/runner` → set Watchback manual-input fields on one runner (body: `date,venue,time,name` + any of `interference,interference_type,position_in_race,finishing_trend`). SQLite only, not dual-written to JSON. See Watchback System below.
- `DELETE /api/results/{date}/{venue}/{time}` → remove race

**Schema additions (2026-09-01, improvement.md):** `races.distance_f` (REAL), `races.race_class` (TEXT) — backfilled for existing rows via `scripts/backfill_distance_class.py`, captured go-forward by `results_fetcher.py`. `runners.winner_sp`/`winner_name` (auto-derived at fetch time), `runners.interference`/`interference_type`/`position_in_race`/`finishing_trend` (manual-input only, never scraped — see Watchback System below).

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

## STAT+ Panel

Per-horse conditions SR (Going/Distance/Course/Class/Trainer/Jockey), added 2026-09-01 (`improvement.md` Feature 1). **Not** a full Racing Post running history — built entirely from horses we've already logged in `results_history` (horse-name match), the same pattern as the Connection Change Detector. A horse with no prior logged runs shows "No logged history".

- `buildStatPlus(runner, race)` / `renderStatPlusSection(runner, race)` in `daily_racing_analyzer.html` (near `getConnectionStats`).
- Needs ≥3 runs at a condition to show a % (else `-`), thresholds ✅≥50% / ⚠️25–49% / ❌<25% — matches spec.
- Going/Course bands work off existing `results_history` fields (`going`, `venue`). Distance bands (≤5f/6f/7f/1m/1m1f-1m3f/1m4f+/2m+) and Class bands need `races.distance_f`/`race_class` — added to the SQLite schema 2026-09-01, backfilled via `scripts/backfill_distance_class.py` (~68% of historical races have both fields; older/NH races with fractional-furlong distances can be missing `distance_f` at source — a pre-existing `racecard_fetcher.py` parsing gap, not fixed).
- Rendered as a collapsible panel in `renderExpandedRow` (`toggleSection('sp_${uid}')`), same idiom as Factor Breakdown/CDP.

## Weather / Going Signal

Soft signal flagging when forecast rain is likely to change the going before a race, cross-referenced against each horse's STAT+ going SR. `improvement.md` Feature 2. **Never changes segment classification or auto-excludes a pick** — display only.

- `scripts/weather_fetcher.py` — fetches OpenWeatherMap's free "5 day / 3 hour forecast" per unique UK venue on today's card, applies a static `TRACK_DRAINAGE` (fast/average/slow/aw) + `GOING_TRANSITIONS` lookup, writes the venue-level physical prediction to `weather_signal.json` + `weather_signal.js` (file:// fallback, same pattern as `daily_race_data.js`). Cached 30 min per venue/hour in `weather_cache.json`.
- **Runs automatically** as the last step of `Fetch Racecard.bat` and `Fetch Racecard (API).bat` (every option — today/tomorrow/day after/specific — calls `weather_fetcher.py` with the matching date right after the racecard fetch). No separate step needed day to day. `Fetch Weather Signal.bat` still exists for a manual re-run later (e.g. to refresh closer to race time, or the first run after adding an API key). CLI: `--date YYYY-MM-DD` / `--tomorrow` / `--day-after` (mirrors `racecard_fetcher.py`'s flags), defaults to today.
- Never fails the racecard fetch — no API key just prints setup instructions and exits 0 (no `sys.exit`), so the `.bat` continues normally either way.
- **Requires an OpenWeatherMap API key** — not bundled. Set env var `OPENWEATHERMAP_API_KEY` or create `scripts/weather_api_key.txt` (gitignored). Without a key the script prints setup instructions and exits cleanly; the UI feature simply doesn't activate (no error).
- `buildWeatherFlag(runner, race)` / `renderWeatherBanner(runner, race)` in `daily_racing_analyzer.html` combine the venue-level Python signal with the horse's own STAT+ going SR to produce the per-horse flag: 🟢 IMPROVING / 🔴 DETERIORATING / 🟡 NEUTRAL / ⚫ AW / ⚠️ UNPROVEN. Only shown if precipitation probability > 40% and a real going-category shift is predicted (spec's display rule).
- `going_changed` from the original spec (declared-vs-actual going drift) is **not implemented** — schema only stores one going value per race.

## Watchback System

Quality-of-loss tracking — distinguishes horses beaten by a better one on the day from genuinely wrong selections. `improvement.md` Feature 3. **Informational only — never changes segment classification or P&L. A loss is a loss.**

- `classifyRun(pick)` in `daily_racing_analyzer.html` → `WIN | NEAR_MISS | UNLUCKY | COMPETITIVE | BEATEN_FAIRLY | WELL_BEATEN` (or `null` if no beaten-distance logged), exact thresholds from spec.
- Auto-derived fields: `distance_beaten` (existing), `winner_sp`/`winner_name` (added to every runner's own result row at fetch time by `results_fetcher.py`).
- Manual-input-only fields (never scraped): `interference`, `interference_type`, `position_in_race`, `finishing_trend` — set via the `PATCH /api/runner` endpoint (`scripts/db_server.py`), driven from the Watchback tab's "Needs Manual Tagging" table (`window._wbSave`, `patchRunnerWatchback()`). `going_changed` is intentionally not implemented (see Weather / Going Signal above).
- `getPickResult()` attaches `res.watchback` to every sidebar pick result; the classification badge renders in the pick-card footer (`watchbackLine()`).
- **Watchback tab** (`window.renderWatchbackDashboard`, own top-level tab) — aggregate summary + "Adjusted competitive rate" (WIN+NEAR_MISS+UNLUCKY ÷ classified). "Picks" population = TOP PICK + STRONG confidence-tier runners from `results_history` — Prixm's NAP/WIN/STRONG/PLACE edge categories aren't persisted historically, so this is the closest available proxy (flagged in the panel's own UI copy).

**Forward signal** (added 2026-09-01, `Prixm_Watchback_Spec.md`) — on an *upcoming* race, each horse's most recent resulted run's watchback classification is surfaced as context, display-only:
- `getWatchbackContext(horseName)` — most recent resulted run for that horse across `results_history`; returns `null` if that run has no `beaten_distance` (nothing to classify) or is >60 days old (staleness cutoff — spec is explicit that stale means show nothing, not a fallback).
- `getWatchbackBadge(runner, race)` — small 🟢/🟡/⚪/🔴 icon appended to the horse name in the runner row (next to `getCourseSpecialistBadge`), tooltip has the full context line.
- `renderWatchbackContextBanner(runner, race)` — fuller one-line banner in `renderExpandedRow`, same visual language as the Weather banner, above it.
- **Absolute rule (spec's own wording): must never change `predicted_score`, gap, or segment qualification.** Nothing in either function writes to a runner or race object — both are pure reads returning display strings.
- Step 3 from the spec (small score boost for horses coming off NEAR_MISS/UNLUCKY) is **explicitly not implemented** — spec requires 50+ validated cases first, same gate as the Phase 5 engine changes below.

## Track Profile Database

Static lookup of UK track characteristics (shape, draw bias, running styles, caution flags) — display/soft-signal only, **never modifies `predicted_score`**. `improvement.md` Feature 4.

- `TRACK_PROFILES` object in `daily_racing_analyzer.html`, seeded with ~20 major UK tracks (Chester, Epsom, Goodwood, Cheltenham, Newmarket, Ascot, York, Doncaster, Newbury, Sandown, Haydock, Aintree, Kempton, Lingfield, Wolverhampton, Nottingham, Leicester, Salisbury, Windsor, Beverley). Extend the object to add more.
- `getTrackProfile(course)` / `isTrackProfiled(course)` / `renderTrackProfileSection(runner, race)` — same "soft display-only exception" idiom as `isIreland`/`isLongchamp`, sits right next to them.
- Rendered as a collapsible panel in `renderExpandedRow`, only when the race's course has a seeded profile.

## RPR Divergence Flag

`rprDivergenceFlag(orVal, rprVal)` in `daily_racing_analyzer.html` (`improvement.md` Feature 5). RPR (`rpr`) was already scraped and displayed; OR (`ofr`) was scraped but never shown — now displayed alongside RPR in the expanded row's meta line, plus a small icon in the RPR table column. `diff≥10` → UNDERRATED (⬆️), `diff≤-10` → OVERRATED (⬇️).

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
- **France**: saint cloud, chantilly, auteuil, compiegne, toulouse, bordeaux
- **Germany/Italy**: san siro, munich, dusseldorf, krefeld, cologne, koln, randwick
- **Ireland**: punchestown, leopardstown, curragh, naas, cork, killarney, gowran park, roscommon, navan, limerick, clonmel, wexford, tramore, kilbeggan, ballinrobe, sligo, down royal, bellewstown, downpatrick, dundalk, tipperary, fairyhouse, galway, laytown
- **Meta**: free to air, scoop, worldwide stakes, world pool

Venue matching uses lowercase substring. Hyphens normalized to spaces in `results_fetcher.py` (`normalize_venue()`).
Irish venues also caught by `(IRE)` suffix check before list lookup.

**Longchamp exception (2026-07-13)**: unhidden from race card display only. Removed from `EXCLUDED_VENUES` JS array in `daily_racing_analyzer.html`; new `isLongchamp(course)` helper explicitly re-excludes it from `getTop10Picks`, `getGoldenFlags`/`getSilverFlags`/`getBronzeFlags`, and `isExcludedVenue` (used by results/pick-performance analysis). `results_fetcher.py` and `qualifying_exporter.py` lists untouched — Longchamp results/stats still fully excluded from results_history, stats, and analysis. Same pattern as Ireland (`isIreland()`) — display without counting toward any analysis.

**Deauville exception (2026-08-16)**: same pattern as Longchamp. Removed from `EXCLUDED_VENUES` JS array; new `isDeauville(course)` helper re-excludes it from `getTop10Picks`, `getGoldenFlags`/`getSilverFlags`/`getBronzeFlags`, and `isExcludedVenue`. `results_fetcher.py` and `qualifying_exporter.py` lists untouched — Deauville results/stats still fully excluded from results_history, stats, and analysis.

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

**Add a track to Track Profile**: Add an entry to `TRACK_PROFILES` in `daily_racing_analyzer.html` (search `TRACK PROFILE DATABASE`), same shape as the existing ~20.

**Add a venue to Weather Signal coverage**: Add coordinates to `VENUE_COORDS` (and a drainage rating to `TRACK_DRAINAGE`) in `scripts/weather_fetcher.py`.

**Modify STAT+ bands/thresholds**: Edit `buildStatPlus()`/`distanceBand()` in `daily_racing_analyzer.html` (search `STAT+ PANEL`).

**Set up Weather Signal**: Get a free OpenWeatherMap key, set `OPENWEATHERMAP_API_KEY` env var (or `scripts/weather_api_key.txt`). Once set, it fetches automatically every time you run `Fetch Racecard.bat`/`Fetch Racecard (API).bat` — no separate step. Use `Fetch Weather Signal.bat` only to force a manual re-run.

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
| `Fetch Weather Signal.bat` | `scripts/weather_fetcher.py` | Manual-only — runs automatically from Fetch Racecard(.bat/(API).bat) already. Needs `OPENWEATHERMAP_API_KEY` — see Weather / Going Signal above |

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
