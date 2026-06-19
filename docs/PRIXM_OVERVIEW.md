---
output:
  pdf_document: default
  html_document: default
---
# Prixm Racing Analyzer — Overview

A horse racing analysis tool that scores every runner in every race, generates structured betting picks, tracks your bets, logs results, and self-improves over time. Runs entirely in the browser — no server, no backend, no build tools.

---

## What it does in one sentence

Given a day's racecards, Prixm scores every horse across 14 factors, identifies the strongest competitive edges, generates tiered betting picks with stake recommendations, and learns from results over time to sharpen its own weights.

---

## The Scoring Engine

Every runner gets a score out of 118 across 14 weighted factors:

| Factor | Max | What it measures |
|--------|-----|-----------------|
| Form | 20 | Recent finishing positions |
| Rating | 15 | RPR / official rating |
| Trainer | 12 | Trainer's recent win % |
| Jockey | 10 | Jockey quality |
| Fitness | 8 | Days since last run |
| Class | 8 | Race class suitability |
| Going | 8 | Ground preference |
| Weight | 8 | Weight carried |
| Age | 7 | Age suitability |
| Course | 6 | Course form |
| Distance | 6 | Distance suitability |
| Draw | 5 | Stall position |
| Headgear | 3 | First-time headgear bonus |
| Spotlight | 2 | Expert opinion signal |

Scores are relative to the field. What matters is not the raw score but the **edge** — the competitive gap between a horse and its rivals.

---

## Prixm Picks

The picks engine identifies the strongest edges across all races and grades them:

| Category | Edge threshold | Meaning |
|----------|---------------|---------|
| NAP | ≥ 70 | Best bet of the day |
| WIN | ≥ 60 | Strong win candidate |
| STRONG | ≥ 50 | Solid selection |
| PLACE | ≥ 40 | Place prospect |

Each pick gets a **bet type recommendation** based on field size and competitive probability:
- Small fields (2–4 runners): WIN or skip
- 5–7 runners: WIN or TOP 2
- 8–15 runners: WIN or EW
- 16+ runners: WIN, EW, or TOP 4

The bet engine uses a **Bradley-Terry softmax model** (alpha=2.5) to calculate true competitive probability — separating picks that are genuinely dominant from picks that only score well in weak fields.

---

## CDP — Class · Distance · Going · Course

A four-card proven form check run on every runner. Each card is scored as a percentage of its factor maximum:

- **≥ 70%** → Proven (horse has demonstrated form in this condition)
- **40–69%** → Untested
- **< 40%** → Concern

CDP cards are used by the bet engine for reasoning tags and by Ozzy as context for his opinions.

---

## Verification Pass

Runs automatically on every NAP and WIN pick. A second analytical pass that doesn't change the score — it issues a verdict alongside it.

**Three phases:**
1. **Factor audit** — checks whether each positive factor is evidence-based or inferred from thin/stale data
2. **Counter-Argument Score (CAS)** — accumulates signals against the pick (bounce risk, going mismatch, class drop masking, compressed field, connection downgrade, etc.)
3. **Bayesian confidence update** — deflates inflated scores caused by phantom data and high CAS

**Verdict states:**
- ✅ CONFIRMED — case is solid, CAS < 31, ≤ 1 unverified positive
- ⚠️ CONDITIONAL — pick has merit but specific concerns exist, reduced stake advised
- 🚫 FLAGGED — pick is flattered by the model, recommend skip or watch only

---

## Ozzy — AI Tipster

An independent observer built on Claude Sonnet 4.6. Ozzy reads what the main engine produced and decides what he thinks. He is not a second scoring layer — he is a thinking observer who agrees, disagrees, or says nothing depending on whether he has something real to say.

**Opinion positions:**
| Position | Badge | What it means |
|----------|-------|---------------|
| BACKED | 🔥 | High conviction agreement — issues his own recommendation |
| WITH IT | ✅ | Agrees, nothing to add |
| WATCHING | 🤔 | Something bothers him but he can't fully articulate it yet |
| DOUBT | ⚠️ | Material problem the engine scored past |
| OFF IT | 🚫 | High conviction disagreement — recommends against, may name a counter |

**Silence is valid.** When Ozzy has no strong view, nothing renders. No placeholder. Absence of a panel is itself information.

**Conviction library** — Ozzy builds conditional rules from results history (e.g. "going score inflated with no recent soft ground form"). Convictions start as candidates, earn active status through results, and expire if their strike rate collapses.

**Self-awareness loop:**
1. Ozzy analyses picks before racing
2. Results logged → reasoning audit checks his calls vs outcomes
3. Ozzy writes a daily performance review of himself
4. Next day, his past reviews are fed back into his analysis context
5. He reads his own lessons and applies them

---

## Connection Change Detector

Compares today's jockey and trainer against the horse's last logged result. Flags changes with a badge (🔄J / 🔄T / 🔄J+T). Click to see old vs new stats and upgrade/downgrade direction.

---

## Data Flow

```
1. Fetch racecard
   racecard_fetcher.py  →  daily_race_data.json

2. View in UI
   daily_racing_analyzer.html loads daily_race_data.json
   → scores all runners → generates picks → Ozzy analyses NAP/WIN/STRONG

3. After racing
   results_fetcher.py  →  results_history.json
   → UI merges new results on next load
   → Ozzy retro audit fires automatically
   → Ozzy writes daily reflection

4. Calibration
   UI reads results_history → adjusts FM weights per surface profile (aw / turf_flat / nh)
```

---

## Key Files

| File | Purpose |
|------|---------|
| `daily_racing_analyzer.html` | Main UI — everything in one file |
| `tomorrow_picks.html` | Advance picks viewer (same engine, no results history) |
| `results_fetcher.py` | Scrapes results, matches to predictions, logs to history |
| `racecard_fetcher.py` | Scrapes racecards from Racing Post |
| `engine/ozzy/` | Ozzy AI tipster — engine, prompts, UI, audit |
| `daily_race_data.json` | Today's race data (loaded by UI) |
| `results_history.json` | All logged results (calibration + Ozzy learning) |
| `ozzy_memory.json` | Ozzy's conviction library, stats, reflections |

---

## Tech Stack

- Vanilla HTML + CSS + JavaScript — no frameworks, no build tools
- Single-file UI (~320KB inline)
- All storage in localStorage (no backend)
- Python scripts for data fetching (requests, BeautifulSoup)
- Ozzy uses Anthropic API (Claude Sonnet 4.6) — ~$0.05/day

---

## What "self-improving" means

The system improves in two ways:

1. **Weight calibration** — the calibration engine analyses results history and adjusts the 14 FM factor weights per surface profile. Factors that predict winners get more weight; factors that don't get less.

2. **Ozzy's conviction library** — Ozzy tracks conditional rules derived from results (not the same as FM weights). A conviction like "going score high but no recent soft form" fires when conditions match and is strengthened or weakened based on whether the horse won or lost. After enough fires, candidates become active convictions that influence Ozzy's opinions.

Neither improvement is automatic overconfidence — both require evidence before changing behaviour.
