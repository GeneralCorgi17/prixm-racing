# Prixm Racing Analyzer

Horse racing analysis tool. Scores runners across 14 weighted factors, generates picks, tracks bets, logs results, and self-calibrates weights over time.

## Project Structure

```
├── daily_racing_analyzer.html   # Main UI — single-file HTML+CSS+JS (~320KB)
├── tomorrow_picks.html          # Standalone advance picks viewer (same engine, no results history)
├── results_fetcher.py           # Scrapes race results, matches to predictions, logs to results_history
├── racecard_fetcher.py          # Scrapes racecards from Racing Post (HTML parsing)
├── racecard_fetcher_api.py      # Fetches racecards via API
├── Fetch Results.bat            # Windows launcher for results_fetcher (date menu: today/yesterday/specific)
├── Fetch Racecard.bat           # Windows launcher for racecard_fetcher
├── Fetch Racecard (API).bat     # Windows launcher for API fetcher
├── engine/
│   ├── fetch_daily_races.py     # Daily race data pipeline
│   └── calibration_engine.py    # Weight calibration engine
├── race_data/                   # Archived daily JSON files (race_data_YYYY-MM-DD.json)
├── daily_race_data.json         # Current day's race data (loaded by UI)
├── results_history.json         # All logged results (used for calibration + combo tracking)
├── results_history.js           # Same data wrapped in JS var for HTML <script> loading
├── debug_index.html             # Debug version of main UI
├── debug_race_result.html       # Debug version of results viewer
└── Prixm Daily Workflow.pdf     # Workflow documentation
```

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

Factor weights are defined in `FM` object at top of both HTML files. The calibration engine adjusts these based on logged results.

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

Only works in main UI (requires results_history). Not available in tomorrow_picks.html.

## EXCLUDED_VENUES

**CRITICAL**: Maintained in 3 files — all must be updated together:
1. `daily_racing_analyzer.html` — line ~2167, JS array
2. `tomorrow_picks.html` — line ~93, JS array
3. `results_fetcher.py` — line ~27, Python list

Current list: happy valley, rosehill, flemington, oaklawn park, gulfstream park, meydan, sha tin, chukyo, saint-cloud, bahrain, keeneland, randwick, aqueduct, santa anita, turffontein, palermo, abu dhabi, hanshin, longchamp, deauville, free to air, scoop, morphettville, worldwide stakes, dusseldorf, chantilly, fukushima, nakayama, krefeld, world pool, churchill downs, san siro, munich

Venue matching uses lowercase substring matching. Hyphens are normalized to spaces in `results_fetcher.py` (`normalize_venue()`).

## Data Flow

1. **Fetch racecard** → `racecard_fetcher.py` or `racecard_fetcher_api.py` → writes `daily_race_data.json` + `race_data/race_data_YYYY-MM-DD.json`
2. **View in UI** → `daily_racing_analyzer.html` loads `daily_race_data.json` (or paste JSON manually)
3. **After racing** → `results_fetcher.py` scrapes results, matches to predictions, appends to `results_history.json`
4. **Calibration** → UI's calibration engine reads `results_history.json`, adjusts FM weights per profile (aw/turf_flat/nh)

## localStorage Keys (Main UI)

| Key | Purpose |
|-----|---------|
| `raceData` | Current day's race data |
| `raceDataPastedDate` | Date of manually pasted data (prevents stale file overwrite) |
| `topPicks_YYYY-MM-DD` | Saved picks per date |
| `resultsHistory` | Cached results history |
| `comboTracker` | Jockey/trainer combination stats |
| `horseWatchlist` | Tracked horses |
| `myBets` | Personal bet selections with bet type |
| `picksCalibration` | Picks calibration data |

**Quota handling**: `saveDayData()` has recovery logic — on quota exceeded, clears old data (old topPicks, large caches) and retries. Alerts user if still failing.

## Key UI Features

- **Race card view** with expandable runner details (score breakdown, CDP, momentum, probabilities)
- **Prixm Picks** — Design C layout: accent bar, category dot+label, horse name, bet chip, edge bar with % fill, reasoning tags
- **Personal bet tracker** — BET button per runner, bet type selection (EW/WIN/TOP N), export as PNG
- **Combination tracker** — horse+jockey, horse+trainer, jockey+trainer combos from results history
- **Horse watchlist** — track specific horses across race days
- **Results logger** — fetches and logs race results
- **Weight calibration** — self-tuning factor weights from logged results

## Code Style

- Single-file HTML with inline CSS and JS (no build tools, no frameworks)
- All JS is vanilla — no React, no jQuery
- CSS uses custom properties (--bg, --card, --text, --muted, --accent, etc.)
- Dark theme only
- Functions are global scope, no modules
- Template literals for HTML generation
- Data stored in localStorage (no backend)

## Common Tasks

**Add venue to exclude list**: Update all 3 files (see EXCLUDED_VENUES section above).

**Modify scoring weights**: Edit `FM` object. Both HTML files have their own copy.

**Add a Prixm reasoning tag**: Edit `getPrixmBetRec()` in both `daily_racing_analyzer.html` and `tomorrow_picks.html`.

**Modify Prixm pick display**: Edit `renderPrixmPicks()` in main UI, and the render function in `tomorrow_picks.html`.

## Python Dependencies

- `requests`, `beautifulsoup4`, `lxml` — for scraping
- Standard library: `json`, `re`, `datetime`, `argparse`, `os`

## Windows Batch Files

All `.bat` files use `@echo off`, `cd /d "%~dp0"`, and call Python scripts. `Fetch Results.bat` has a date menu (1=today, 2=yesterday, 3=day before, 4=specific date).
