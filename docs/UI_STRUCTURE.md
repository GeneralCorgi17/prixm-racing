# Prixm UI Structure

**File:** `daily_racing_analyzer.html` (root dir, ~350KB, ~5600 lines)
**Stack:** Single-file HTML + inline CSS + vanilla JS. No framework, no build step. All functions global scope.

---

## Top-Level Layout

```
<body>
  .hdr                    ← header bar (title, buttons, date, status)
  .tab-bar                ← 6 tab buttons
  #landingView            ← Races tab (default)
  #detailView             ← Race detail (replaces landing on click)
  #perfView               ← Performance tab
  #combosView             ← Combos tab
  #trendsView             ← Trends tab
  #ozzyView               ← Ozzy tab
  #goldenView             ← Golden dashboard tab
  #modalContainer         ← Overlay modals (dynamically inserted)
  #betPanel               ← Right sidebar bet list (collapsible)
  #betFab                 ← Floating ticket button (bottom-right)
</body>
```

---

## Header Bar (`.hdr`)

Left: app title + subtitle
Right:
- `#dataSourceBadge` — shows embedded / pasted
- `📋 Load JSON` → `showPaste()`
- `🗑 Clear Data` → `clearStoredData()` (hidden until data loaded)
- `❓ Guide` → `showGuide()`
- `🧠 Ozzy` → `switchTab('ozzy')`
- `📄 PDF` → `exportPDF()`
- `#dateDisp` — date badge
- `#statusDisp` — status message
- `#statusBar` — rendered by `renderStatusBar()` — shows ✓/⏳ for: Results / Picks / Calibrated / Threshold / PDF

---

## Tab Bar (`.tab-bar`)

| Button ID | Label | Triggers |
|-----------|-------|----------|
| `tabRaces` | Races | `switchTab('races')` |
| `tabPerf` | Performance | `switchTab('performance')` |
| `tabCombos` | Combos | `switchTab('combos')` |
| `tabTrends` | Trends | `switchTab('trends')` |
| `tabOzzy` | 🧠 Ozzy | `switchTab('ozzy')` |
| `tabGolden` | Golden | `switchTab('golden')` |
| `dbStatusBadge` | — | `🟢 DB N races` or `🟡 JSON` — set during init(), margin-left:auto |

**`switchTab(tab)`** — toggles `.active` class, shows/hides view divs, calls render function for the selected tab.

---

## Global State (`st`)

```javascript
let st = {
  venue:            'all',     // active venue filter
  fieldFilter:      'all',     // '2-5' | '6-8' | '9-12' | '13+' | 'all'
  comboFilter:      false,     // false | 'combo' | 'nocombo'
  raceTypeFilter:   'all',     // 'eng_nh' | 'eng_hcp' | 'ire_nh' | 'ire_hcp' | 'all'
  confidenceFilter: 'all',     // 'TOP PICK' | 'STRONG' | 'SOLID' | 'MODERATE' | 'all'
  gapFilter:        'all',     // 'tight' | 'competitive' | 'clear' | 'all'
  openRace:         null,      // {vk, ri} when race detail open
  sort:             'score',   // runner sort key
  sortDir:          -1,        // 1 | -1
  expanded:         null,      // expanded row id in detail view
  detailTab:        'main',    // 'main' | 'deep'
  riMode:           'rank',    // results input mode: 'rank' | 'nr' | 'pu'
  h2hPair:          null       // H2H pair selection
};

let D = null;  // loaded race data: { date, generated_at, venues: { venueKey: { course, race_count, races[] } } }
```

---

## Races Tab (`#landingView`)

Default tab. Five sub-sections in order:

### 1. Prixm Picks (`#topPicksSection`)
Renderer: `renderTopPicks()`
- Progress bar (won / placed / lost / pending counts)
- Confidence threshold strip
- **Prixm picks cards** — `renderPrixmPicks(picks, hist)`: accent-bar cards with category dot (NAP/WIN/STRONG/PLACE), horse name, bet chip, edge bar, reasoning tags, verification report, Ozzy panel
- Top 10 picks grid + auto-calibration button

Pick pipeline:
- `getPrixmPicks(picks)` — applies edge threshold gates
- `getPrixmBetRec(pick, race)` — WIN / EW / TOP N / SKIP recommendation (Bradley-Terry softmax model)
- `calcCompetitiveProb(runner, race)` — CDP + competitive probability
- `runVerificationPass(runner, race, hist)` — CAS score + verdict (CONFIRMED / CONDITIONAL / FLAGGED)

### 2. Watchlist (`#watchlistSection`)
Renderer: `renderWatchlistPanel()` — tracked horses grid with current scores.

### 3. Venue Filter (`#venueBar`)
Renderer: `renderVenueBar()` — "All" + per-venue buttons with race count.
Filter: `filterVenue(v)`

### 4. Field Size Bar (`#fieldSizeBar`)
Renderer: `renderFieldSizeBar()` — five row-groups of filter buttons:

| Row | Filters | Function |
|-----|---------|----------|
| Field size | All / 2-5 / 6-8 / 9-12 / 13+ | `filterFieldSize(f)` |
| Race type | ENG NH / ENG HCP / IRE NH / IRE HCP | `filterRaceType(t)` |
| Combo | Combo only / Exclude combos | `setComboFilter(v)` |
| Confidence | Top Pick / Strong / Solid / Moderate | `filterConfidence(c)` |
| Gap | Tight (0–7.9) / Competitive (8–14.9) / Clear (15+) | `filterGap(g)` |

### 5. Race Cards (`#raceCards`)
Renderer: `renderRaceCards()` — applies all active filters, renders `.rc` card per race.

Each card shows: venue + time, race metadata (distance / going / type / field size / class), top pick preview, confidence spread, brief tags (edge, verdict, danger, combo, momentum).

Click → `openRace(venueKey, raceIdx)` → opens detail view.

Race card left border color (9px):
- Blue `#3b82f6` — England non-handicap
- Amber `#f59e0b` — England handicap
- Green `#10b981` — Ireland non-handicap
- Red `#f87171` — Ireland handicap

---

## Race Detail View (`#detailView`)

Opens on race card click. Back button → `goBack()` → returns to landing.

**Renderer:** `renderDetail()`

Two sub-tabs (`.dtab`):

### Main tab (`detailTab='main'`)
- Runners table (`.rtbl`) — all runners sorted by score
- Expandable rows (`.exp-row`) — 14-factor score breakdown per runner
- Variable grid (`.vtg`) — tick boxes for factor scores

### Deep Dive tab (`detailTab='deep'`)
- Verdict panel (`.verdict-panel`) — CAS, verification, confidence
- Head-to-Head matrix (`.h2h-wrap`) — runner vs runner probability grid
- Betting Signal Panel (`.betting-panel`) — Prixm bet rec + reasoning

### Results Input Panel (`.ri-panel`)
- Mode: Rank / NR / PU
- Horse tiles (click to assign finish position)
- Save / Undo / Reset

---

## Performance Tab (`#perfView`)

Renderer: `renderPerformance()`

| Panel | Description |
|-------|-------------|
| Engine banner | ENGINE_NAME + calibration cycle |
| Profile filter | All / AW / Turf Flat / NH |
| Handicap filter | All / Non-Handicap / Handicap |
| Surface status cards | Race count + calibration progress bar per surface |
| Calibration button | Gated by race threshold |
| Win prediction accuracy | Tiers: TOP PICK / STRONG / SOLID / MODERATE / WEAK / AVOID — Win%, Place%, Expected% |
| Lose prediction accuracy | Weak/Avoid — bottom half %, bot quartile %, last % |
| Factor predictive power | Spearman ρ for all 14 factors |
| Race winner analysis | 4 metric cards + sweet spots + weak spots + breakdown tables |
| Breakdown tables | By: Field Size / Surface / Race Type / Confidence Gap / Venue |
| Recent predictions | Last 20 races logged |
| Threshold optimizer | Placed rate by score threshold, optimal cutoff badge |

---

## Combos Tab (`#combosView`)

Renderer: `renderCombos()`
Shows combo analysis: horse+jockey, horse+trainer, jockey+trainer pair stats from results history.

---

## Trends Tab (`#trendsView`)

Renderer: `renderTrends()`
Historical performance trends over time.

---

## Ozzy Tab (`#ozzyView`)

Container: `#ozzyTabContent`
Renderer: `renderOzzyTab()` + `ozzyFillOzzyTab()` (from external scripts)

Shows: conviction library, per-position stats (BACKED/WITH IT/WATCHING/DOUBT/OFF IT), recent calls, daily reflections, lessons, audit log.

External scripts loaded:
```html
<script src="engine/ozzy/ozzy_prompts.js">
<script src="engine/ozzy/ozzy_engine.js">
<script src="engine/ozzy/ozzy_audit.js">
<script src="engine/ozzy/ozzy_ui.js">
```

---

## Golden + Silver Dashboard Tab (`#goldenView`)

Container: `#goldenContent`
Renderer: `renderGoldenDashboard()` (IIFE block `/* === GOLDEN DASHBOARD ===*/`)
Auto-polls every 60s — re-renders only if `_resultsHistory.races.length` changed and tab is visible.

### Golden Section

**Filter:** UK non-handicap · gap ≥18 · score ≥74 · SP >2.0 (ROI)
- `isUKVenue(venue)` — checks `(ire)` substring + `_IRE_TRACKS` set + `EXCLUDED_VENUES` list
- Handicap: `race.handicap === true` excluded
- Gap: top_score − second_score in `race.results`
- Score: top runner `predicted_score ≥ 74`

**Threshold change 2026-05-29:** was gap≥17 no score filter.

| Panel | Content |
|-------|---------|
| 1 — Headline | Golden SR · Golden ROI · UK Handicap SR · Break-even SR |
| 2 — Gap Bands | UK NH base: <15 / 15–18 / 18–21 / 21–24 / 24+ |
| 3 — Score Bands | Golden only: 74–75 / 75–80 / 80–85 / 85+ |
| 4 — Going | Golden only, grouped by going string |
| 5 — Sweet Spots | Gap≥18+Score80 / Good/GF+Gap≥18 / Turf / AW |
| 6 — Warning | Non-dismissible banner until 100+ golden picks |

Key functions (inside IIFE): `buildGoldenPicks` · `groupByGapBand` · `groupByScoreBand` · `groupByGoing` · `calcSweetSpots` · `buildBenchmarks` · `calcSR` · `calcROI` · `isUKVenue` · `getGap` · `getTopRunner` · `resultKnown`

Racecard badge: `getGoldenFlags(race)` + `renderGoldenFlag(gf)` — global scope, fires if gap≥18 + score≥74.

### Silver Section (below Golden, HR divider)

**Filter:** UK non-handicap · gap 10–12 · score ≥72 · Turf · SP >2.0 (ROI)
Turf inferred: going does NOT start with "Standard" (AW going).

| Panel | Content |
|-------|---------|
| Headline | Silver SR · Silver ROI · Break-even SR (slate `#94a3b8` colour) |
| Gap Bands | Silver only: 10–11 / 11–12 / 12–13 |
| Score Bands | Silver only: 75–80 / 80–85 / 85+ |
| Going | Silver only, grouped by going string |
| Warning | Non-dismissible banner until 50+ silver picks |

Key functions: `buildSilverPicks` · `groupBySilverGapBand` (inside IIFE). Reuses `groupByScoreBand` and `groupByGoing`.

Racecard badge: `getSilverFlags(race)` + `renderSilverFlag(sf)` — global scope, fires if gap 10–12 + score≥72 + not AW.

---

## Bet Panel (`#betPanel`)

FAB: `#betFab` (floating 🎫 button, bottom-right) → `toggleBetPanel()`
Renderer: `renderBetPanel()`

Contents: bet items (horse + type + time + venue), Export PNG → `exportBetImage()`, Clear All.

---

## Modals (`#modalContainer`)

Dynamically inserted as `.modal-bg` + `.modal`. Overlay click to close.

Spawned by: `showGuide()`, `showPaste()`, `runUnifiedCalibration()`, `submitPickResults()`, threshold analysis, PDF export confirm.

---

## CSS Custom Properties (Dark Theme)

```css
--bg:      #0a0f1a   /* page background */
--card:    #111827   /* card background */
--card2:   #1a2332   /* secondary card */
--accent:  #10b981   /* green — primary action */
--accent2: #3b82f6   /* blue — secondary */
--warn:    #f59e0b   /* amber — warning */
--danger:  #ef4444   /* red — danger */
--text:    #e5e7eb   /* default text */
--muted:   #9ca3af   /* muted / label text */
--border:  #374151   /* borders */
--gold:    #fbbf24   /* gold — premium/special */
```

---

## External Scripts

```
results_history.js          ← window._resultsHistoryFile (file:// fallback)
daily_race_data.js          ← window._dailyRaceDataFile  (file:// fallback)
engine/ozzy/ozzy_prompts.js
engine/ozzy/ozzy_engine.js
engine/ozzy/ozzy_audit.js
engine/ozzy/ozzy_ui.js
```

**Results history loading priority (init):**
1. `fetch('http://localhost:7432/api/results')` — SQLite server (1.5s timeout)
2. `window._resultsHistoryFile` — JS global from script tag
3. `fetch('results_history.json?t=...')` — JSON file
4. `localStorage.getItem('resultsHistory')` — only used when server offline

When server is live: `window._resultsHistory` set directly from DB, localStorage `resultsHistory` cleared.

---

## localStorage Keys

| Key | Purpose |
|-----|---------|
| `raceData` | Current day's race data |
| `raceDataPastedDate` | Date of manually pasted data |
| `resultsHistory` | All logged results + calibrations + weight profiles |
| `topPicks_YYYY-MM-DD` | Saved picks per date |
| `comboTracker` | Jockey/trainer combo stats |
| `horseWatchlist` | Tracked horses |
| `myBets` | Personal bet selections |
| `picksCalibration` | Picks calibration data |
| `calibWeights_[profile]` | Per-profile FM weights (aw / turf_flat / nh) |
| `ozzyMemory` | Ozzy convictions, stats, reflections, lessons, audit log |
| `ozzyDailyBriefs_YYYY-MM-DD` | Ozzy pick analyses per date (API call cache) |

---

## Key Functions Reference

| Function | Purpose |
|----------|---------|
| `switchTab(tab)` | Toggle active tab, show/hide views, call renderer |
| `render()` | Main async orchestrator — scores runners, generates picks, renders all |
| `renderTopPicks()` | Prixm picks section + top 10 grid |
| `renderPrixmPicks(picks, hist)` | Prixm pick cards (NAP/WIN/STRONG/PLACE) |
| `getPrixmPicks(picks)` | Filter picks by edge threshold |
| `getPrixmBetRec(pick, race)` | WIN/EW/TOP N/SKIP bet recommendation |
| `runVerificationPass(runner, race, hist)` | CAS score + CONFIRMED/CONDITIONAL/FLAGGED verdict |
| `calcCompetitiveProb(runner, race)` | Bradley-Terry softmax win probability |
| `buildCDP(runner, race)` | Class·Distance·Going·Course proven form cards |
| `renderRaceCards()` | Race card grid with all filters |
| `renderDetail()` | Race detail view |
| `renderPerformance()` | Performance tab analytics |
| `renderCombos()` | Combos tab |
| `renderTrends()` | Trends tab |
| `renderOzzyTab()` | Ozzy conviction tracker tab |
| `renderGoldenDashboard()` | Golden segment analytics tab |
| `renderVenueBar()` | Venue filter buttons |
| `renderFieldSizeBar()` | All filter buttons (field size/race type/combo/confidence/gap) |
| `renderBetPanel()` | Bet list sidebar |
| `renderWatchlistPanel()` | Watched horses grid |
| `toggleBetPanel()` | Show/hide bet sidebar |
| `toggleBet(horse, time, venue, score)` | Add/remove bet from list |
| `getRaceBorderColor(r)` | 9px left border color by country+handicap type |
| `getGoldenFlags(race)` | Returns golden flag data if race qualifies (gap≥18, score≥74, UK NH) |
| `renderGoldenFlag(gf)` | Renders `⭐ GOLDEN` banner HTML for race card |
| `getSilverFlags(race)` | Returns silver flag data if race qualifies (gap 10–12, score≥72, UK NH, Turf) |
| `renderSilverFlag(sf)` | Renders `🥈 SILVER` banner HTML for race card |
| `isIreland(course)` | Detect Irish venue |
| `exportBetImage()` | Export bet list as PNG |
| `exportPDF()` | Export full day as PDF |
| `showPaste()` | Open JSON paste modal |
| `showGuide()` | Open guide modal |
| `saveDayData()` | Persist picks/calibration to localStorage (with quota recovery) |
| `runUnifiedCalibration()` | Run calibration engine, show report modal |

---

*Last updated: 2026-05-28*
