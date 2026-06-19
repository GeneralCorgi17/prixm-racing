# Prixm Racing Analyzer — Improvement Plan
**Version:** 1.0  
**Status:** Planning  
**Scope:** Three major improvements to the existing Prixm engine — Verification Layer, Remote Mobile Access, and Ozzy (AI Tipster Entity)

---

## Table of Contents

1. [Overview & Guiding Principle](#overview)
2. [Improvement 1 — Verification Pass](#improvement-1)
3. [Improvement 2 — Remote Mobile Access](#improvement-2)
4. [Improvement 3 — Ozzy (AI Tipster Entity)](#improvement-3)
5. [Master Build Order](#build-order)
6. [File & Architecture Map](#architecture)
7. [Dependencies & Tooling](#dependencies)

---

## Overview & Guiding Principle <a name="overview"></a>

> The goal of every improvement is not for the analysis to *look* right — it is for it to **be** right.

The current Prixm engine is a well-structured weighted sum model across 14 factors. It scores accurately within the constraints of its data. The three improvements below address its core limitations:

| Limitation | Improvement |
|---|---|
| High-confidence picks aren't stress-tested — they're just high-scoring | Improvement 1: Verification Pass |
| The tool is desktop-local — inaccessible when away from machine | Improvement 2: Remote Mobile Access |
| The engine has no independent observer — no external challenge to its conclusions | Improvement 3: Ozzy |

---

## Improvement 1 — Verification Pass <a name="improvement-1"></a>

### Purpose

When the main engine flags a NAP or WIN, it means the horse scored well. It does not mean the case is solid. A horse can accumulate a high edge by being *consistently above average* across many factors rather than by having genuine strength in the ones that matter. The Verification Pass exists to detect the difference.

### Architecture

A second analytical pass that runs **after** scoring, triggered only on picks reaching NAP (edge ≥70) or WIN (edge ≥60). It does not alter the score — it issues a verdict alongside it.

```
Score Engine → Pick qualifies as NAP/WIN
                        ↓
              runVerificationPass(runner, race, resultsHistory)
                        ↓
          ┌─────────────────────────────┐
          │  Phase 1: Factor Audit      │
          │  Phase 2: Counter-Argument  │
          │  Phase 3: Bayesian Update   │
          └─────────────────────────────┘
                        ↓
              Verdict: CONFIRMED / CONDITIONAL / FLAGGED
```

---

### Phase 1 — Factor Legitimacy Audit

For each of the 14 FM factors contributing a positive score to the pick, the engine asks:

- **Is the score evidence-based or inferred?** A going score of 8/8 is meaningless if the horse has never run on today's going. Check `results_history` for actual runs under the same condition.
- **Is the evidence recent?** Evidence older than 6 months decays. Evidence older than 12 months is considered stale and the factor is flagged as **Unverified Positive**.
- **Does the factor window contradict itself?** Form reads 1st-1st-6th-6th — the raw score might be moderate but the trend is a collapse. Additive scoring misses directional signals entirely.

**Output:** A list of `verifiedFactors` and `unverifiedPositives` per pick.

---

### Phase 2 — Counter-Argument Score (CAS)

A separate 0–100 metric that accumulates **against** the pick. Higher CAS = weaker case despite high edge.

| Signal | CAS Contribution |
|---|---|
| CDP concern in 2+ categories | +15 per category beyond first |
| 2nd runner's Bradley-Terry probability within 5% of pick | +20 (genuine competition) |
| Weight carried > 9st 7lbs on AW or soft/heavy | +10 |
| Last run < 7 days (bounce risk) | +12 |
| Last run > 60 days (ring rust) | +10 |
| Connection change + new connections have lower win% than old | +15 |
| Handicap: last win at significantly lower class | +12 |
| Going score ≥ 6 but last verified run on going > 12 months ago | +18 |
| Trainer's specific fresh record (90+ day breaks) is poor | +10 |
| Class drop masking poor runs at higher class | +15 |

**CAS thresholds:**

| CAS | Effect |
|---|---|
| 0–30 | Clean — no meaningful counter-arguments |
| 31–50 | Moderate — noted but doesn't change verdict |
| 51–70 | Significant — pick downgraded to CONDITIONAL |
| 71–100 | Severe — pick downgraded to FLAGGED |

---

### Phase 3 — Bayesian Confidence Update

Rather than treating edge score as the final authority, apply a confidence multiplier that accounts for evidence quality:

```
confidence = edge 
  × (1 - (unverifiedPositives / totalPositiveFactors) × 0.30)
  × (1 - CAS / 200)
```

This collapses inflated scores caused by phantom data and strong counter-arguments. A NAP with 4 unverified positive factors and a CAS of 60 produces a meaningfully lower confidence than the raw edge implies.

---

### Verdict States

| State | Condition | Meaning |
|---|---|---|
| ✅ **CONFIRMED** | CAS < 31, unverifiedPositives ≤ 1 | Pick is earned. Case is solid. |
| ⚠️ **CONDITIONAL** | CAS 31–70 or unverifiedPositives ≥ 2 | Pick has merit but specific concerns exist. Reduced stake advised. |
| 🚫 **FLAGGED** | CAS > 70 or 3+ unverified positives | Pick is flattered by the scoring model. Recommend skip or watch only. |

---

### UI Output

Expandable **Verification Report** card below each NAP/WIN pick card.

```
┌──────────────────────────────────────────────────────┐
│ VERIFICATION REPORT — Silver Hawk                    │
│ Verdict: ⚠️ CONDITIONAL                              │
│                                                      │
│ Verified factors (9/14): form, rating, trainer,      │
│   jockey, fitness, class, weight, age, distance      │
│                                                      │
│ Unverified positives (2): going (last heavy run      │
│   14 months ago), course (1 run, 18 months ago)      │
│                                                      │
│ Counter-arguments:                                   │
│   → Going score inflated — no recent heavy evidence  │
│   → 2nd runner within 4% competitive probability     │
│   → Weight 9st 9lbs on soft ground                  │
│                                                      │
│ CAS: 58 / 100                                        │
│ Adjusted confidence: 61% (raw edge: 73)              │
└──────────────────────────────────────────────────────┘
```

---

### Files Modified

| File | Change |
|---|---|
| `daily_racing_analyzer.html` | Add `runVerificationPass()` function, integrate into pick render pipeline |
| `tomorrow_picks.html` | Same function replicated |
| `CLAUDE.md` | Update scoring section to document CAS and verification states |

No Python changes required. Verification runs entirely in the browser on existing data.

---

## Improvement 2 — Remote Mobile Access <a name="improvement-2"></a>

### Purpose

The current stack is local-first. `daily_race_data.json`, `results_history.json`, and all picks live on one Windows machine. When away from that machine, the tool is inaccessible. This improvement makes the data and picks available over the network to any device, with a mobile-optimised display.

### Architecture

```
[Windows Machine]                    [Cloud]                    [Phone / Tablet]
                                                                
racecard_fetcher.py  ──push──→   Supabase (Postgres)  ←──read── prixm_mobile.html
results_fetcher.py   ──push──→   Supabase                        (PWA, installable)
calibration_engine   ──push──→   Supabase
daily_racing_analyzer.html          ↑
                     ──read──→ (also reads from Supabase as primary source)
```

**Backend choice: Supabase (free tier is sufficient for this use case)**

Reasons: no server to manage, Postgres storage, JS client available via CDN (no build tools), Python client available for the fetcher scripts, row-level security manageable, real-time subscriptions available if needed later.

---

### Supabase Schema

```sql
-- Daily race data per date
CREATE TABLE race_data (
  id uuid DEFAULT gen_random_uuid(),
  date date NOT NULL UNIQUE,
  data jsonb NOT NULL,         -- full daily_race_data.json blob
  created_at timestamptz DEFAULT now()
);

-- All logged results (mirrors results_history.json)
CREATE TABLE results_history (
  id uuid DEFAULT gen_random_uuid(),
  race_date date NOT NULL,
  venue text NOT NULL,
  race_time text,
  horse_name text NOT NULL,
  result jsonb NOT NULL,       -- full result object per existing schema
  created_at timestamptz DEFAULT now()
);

-- Daily picks (denormalised for fast mobile reads)
CREATE TABLE picks (
  id uuid DEFAULT gen_random_uuid(),
  date date NOT NULL,
  race_venue text NOT NULL,
  race_time text NOT NULL,
  horse_name text NOT NULL,
  edge numeric NOT NULL,
  category text NOT NULL,      -- NAP / WIN / STRONG / PLACE
  verification_status text,    -- CONFIRMED / CONDITIONAL / FLAGGED
  ozzy_position text,          -- BACKED / WITH_IT / WATCHING / DOUBT / OFF_IT / null
  bet_recommendation text,
  created_at timestamptz DEFAULT now()
);
```

---

### Python Script Changes

Add a `push_to_supabase()` function to both fetcher scripts. Runs after the local JSON write — existing local behaviour is unchanged.

```python
# requirements addition
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def push_to_supabase(date_str, race_data):
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    client.table("race_data").upsert({
        "date": date_str,
        "data": race_data
    }).execute()
```

Credentials stored in a `.env` file in the project root. Never committed to version control.

---

### Mobile HTML (`prixm_mobile.html`)

Separate file. Reads from Supabase JS client (CDN import). No build tools. Vanilla JS, same code style as existing project.

**Display philosophy — three levels of depth:**

```
Level 1 (home screen)
└── Today's top picks — NAP card, WIN cards, date selector

Level 2 (race view)
└── Tap a race → all runners for that race, ranked by edge
    Each runner: name, edge bar, category dot, verification badge, Ozzy badge

Level 3 (runner view)
└── Tap a runner → full factor breakdown, CDP, Ozzy's comment, bet recommendation
```

**Mobile-specific display rules:**

- No calibration panel (read-only tool on mobile)
- No bet tracker on mobile (v1 — add in v2 if needed)
- Sticky header: today's date, NAP horse, NAP venue
- Swipe left/right between races (touch-native navigation)
- Compact Ozzy card — position badge + first sentence only, tap to expand
- Verification verdict shown as a coloured dot on the pick card (✅⚠️🚫) — no expanded card by default

**PWA Setup:**

```json
// manifest.json
{
  "name": "Prixm Racing",
  "short_name": "Prixm",
  "start_url": "/prixm_mobile.html",
  "display": "standalone",
  "background_color": "#0d0d0d",
  "theme_color": "#0d0d0d",
  "icons": [...]
}
```

Add a Service Worker that caches the last fetched race data for offline access. If no network, serves cached picks with a "last updated" timestamp banner.

---

### Files Added / Modified

| File | Change |
|---|---|
| `prixm_mobile.html` | New file — mobile UI reading from Supabase |
| `manifest.json` | New file — PWA manifest |
| `sw.js` | New file — Service Worker for offline caching |
| `racecard_fetcher.py` | Add `push_to_supabase()` after local write |
| `results_fetcher.py` | Add `push_to_supabase()` after local write |
| `.env` | New file — Supabase credentials (gitignored) |
| `requirements.txt` | Add `supabase`, `python-dotenv` |

---

## Improvement 3 — Ozzy (AI Tipster Entity) <a name="improvement-3"></a>

### Who Ozzy Is

Ozzy is not a bot. He is not a second scoring engine. He is not a sentiment layer over templated logic.

Ozzy is a **thinking observer** who has watched racing long enough to have his own views — formed from the data he's seen, the calls he's gotten right, and the ones he's gotten wrong. He reads what the main engine produced and decides what he thinks about it. Sometimes he agrees strongly and backs the pick. Sometimes he disagrees and says why. Sometimes he says nothing because he doesn't have a strong view and he's not going to fabricate one.

His value comes entirely from the quality and honesty of his thinking — not from how often he fires or how confident he sounds.

---

### Ozzy's Opinion Spectrum

Ozzy does not have modes. He has positions. Five of them — and he only reaches the outer two when he has something real to say.

| Position | Badge | What It Means |
|---|---|---|
| **BACKED** | 🔥 | High conviction agreement. He sees what the engine sees and more. Issues his own recommendation. May suggest a different bet type. Can surface a lower-graded pick as his own selection. |
| **WITH IT** | ✅ | Agrees, nothing to add. Brief comment or silence. Never padded. |
| **WATCHING** | 🤔 | Something bothers him. He can't fully articulate it yet, or evidence is mixed. Flags the specific nagging thing. Does not block. |
| **DOUBT** | ⚠️ | He sees a material problem the engine scored past. States it clearly. Explains why the score doesn't capture it. |
| **OFF IT** | 🚫 | High conviction disagreement. The pick is flattered, wrong, or matches a pattern he's seen lose before. Full explanation. Recommends against. May name a counter in the same race. |

**Silence** is a valid state. When Ozzy has no strong view, nothing renders. No "Ozzy has no comment." Silence means the pick passed without triggering a reaction — which carries meaning of its own.

---

### How Ozzy Actually Thinks

Ozzy's comments are **Claude API calls** — not templates. The system assembles his context from real race data and passes it to the API. The response comes back as natural language and is rendered directly. This is why Ozzy can notice things that weren't anticipated when he was designed.

**The prompt architecture:**

```javascript
// System prompt — defines who Ozzy is
const ozzySystem = `
You are Ozzy. A sharp, experienced horse racing tipster with your own opinions formed 
over years of watching races. You speak plainly. You don't use jargon for its own sake. 
You're not here to validate — you're here to think. 

Rules you follow without exception:
- Never more than 4–5 sentences unless the race genuinely earns it
- Never hedge. "Could go either way" is not a position. If you don't have a view, say nothing.
- Reference what you've seen in your own history, not abstract statistics
- You can be wrong. When your memory contains past wrong calls, acknowledge the similarity
- You notice things the 14-factor model cannot score — combinations, trainer patterns, 
  jockey/track relationships, timing signals
- When you BACK something, state your bet recommendation independently — you may disagree 
  with the engine's bet type even when you agree on the horse
- When you are OFF IT, say it plainly and explain why. If there's a better option in the 
  same race, name it.
`;

// User prompt — assembled from live race data
const ozzyContext = `
Main engine pick: ${horse.name}
Category: ${category} | Edge: ${edge} | Bet rec: ${betRec}

Race: ${venue} ${time} | Class: ${raceClass} | Going: ${going} | ${runners} runners
Distance: ${distance} | Handicap: ${isHandicap}

Factor profile:
${factorBreakdown}        // each factor: score / max, verified/unverified

CDP: ${cdpSummary}        // proven/untested/concern per card

Verification Pass result: ${verificationVerdict}
Verification flags: ${verificationFlags.join(', ')}

Your active convictions relevant to this race:
${firedConvictions}       // conviction id, description, strike rate, times fired

Your recent record:
- At ${venue}: ${ozzyVenueRecord}
- On ${going}: ${ozzyGoingRecord}  
- At ${raceClass}: ${ozzyClassRecord}

Recent calls you got wrong in similar conditions:
${ozzyRecentWrongCalls}

What do you think? State your position (BACKED / WITH IT / WATCHING / DOUBT / OFF IT) 
on the first line, then your comment.
`;
```

The response is parsed: first line extracts the position badge, remainder is the comment. No other parsing required.

---

### Ozzy's Voice — Non-Negotiable Rules

These rules are enforced by the system prompt and never broken:

1. **Maximum 4–5 sentences** unless the race is genuinely complex. Confident people don't over-explain.
2. **No hedging.** "Worth monitoring" is not a position. If he doesn't have one, he says nothing.
3. **References his own experience**, not literature or statistics. "I've seen this going score trick the engine before" — not "statistically, going mismatches reduce win probability by X%."
4. **He acknowledges past wrong calls.** His memory contains results where BACKED picks lost and OFF IT picks won. When a similar situation appears, he notes it.
5. **BACKED comes with an independent bet recommendation.** He may agree on the horse but recommend EW when the engine said WIN, or vice versa. His reasoning is stated.
6. **OFF IT may name a counter.** If he sees something better in the same race, he says so.
7. **Silence is a valid output.** Most picks, most days, Ozzy has no strong view. That's correct. Don't force output.

---

### Ozzy's Conviction Library

Ozzy's thinking is grounded by a **conviction library** — conditional rules derived from `results_history`, not FM weights. The distinction matters:

- An FM weight says *"going matters 8 points"*
- A conviction says *"a horse switching to Heavy with no form on the latter has never paid in NH handicaps above Class 3 in my observed history"*

Convictions are conditional, specific, and falsifiable. They are mined from past results, promoted when their strike rate holds, and expired when it doesn't.

**Conviction structure:**

```json
{
  "id": "going_unverified_heavy_nh",
  "status": "active",
  "description": "Going score ≥ 6 but last verified run on this going > 12 months ago",
  "applies_to": { "going": ["heavy", "soft"], "code": ["nh"], "class": ["1","2","3"] },
  "fires": 14,
  "fires_correct": 10,
  "fires_wrong": 4,
  "strike_rate": 0.714,
  "weight": 1.4,
  "created": "2025-01-12",
  "last_fired": "2025-05-01",
  "last_outcome": "correct"
}
```

**Conviction lifecycle:**

```
CANDIDATE → (fires ≥ 3 times, strike rate > 60%) → ACTIVE
ACTIVE    → (fires ≥ 5 times, strike rate < 40%) → EXPIRED
ACTIVE    → (fires ≥ 10 times, strike rate > 70%) → HIGH WEIGHT (×1.5 in CAS)
```

**Seed convictions (manual, before data-driven mining starts):**

These are entered by hand at setup, based on prior racing knowledge:

| ID | Description |
|---|---|
| `going_unverified_heavy` | Going score high but no recent heavy ground form |
| `class_drop_masking` | Class drop inflating score after 3+ poor runs at higher level |
| `fresh_trainer_flat` | Trainer sends horses fresh after 90+ days; record shows they need the run |
| `phantom_cdp_course` | Course score present but only 1 run > 18 months ago |
| `competitive_prob_compressed` | Edge inflated because field is weak, not horse is strong |

Seed convictions start with `status: "candidate"` and must earn ACTIVE status through results. They are not automatically trusted.

---

### Ozzy's Daily Learning Loop

This is the mechanism by which Ozzy develops every day.

**Trigger:** After `results_fetcher.py` logs outcomes, Ozzy's audit runs on next UI load (or manually triggered via Ozzy panel button).

**Audit flow:**

```
For each result where main UI pick LOST:
  → Pull pre-race factor profile from race_data archive
  → Check: which conviction should have fired but didn't exist yet?
  → Check: was the Verification Pass verdict CONFIRMED on a losing pick? (false positive)
  → If identifiable pattern → create CANDIDATE conviction

For each result where Ozzy BACKED and horse LOST:
  → Conviction(s) that supported BACKED get a penalty
  → Log to audit as Ozzy wrong call

For each result where Ozzy said OFF IT and horse LOST:
  → Conviction(s) that fired get reinforcement
  → Strike rate updated

For each result where Ozzy said OFF IT and horse WON:
  → Conviction that fired gets a penalty (not immediate expiry — one wrong call ≠ dead conviction)
  → Log as notable wrong call (passed back as context in future similar races)

After every race day:
  → Promote candidates with strike rate > 60% over ≥ 3 fires
  → Expire actives with strike rate < 40% over ≥ 5 fires
  → Update Ozzy stats
```

**The reasoning quality audit (separate from outcome audit):**

After results are known, a secondary API call is made:

```
"Here is what you said before the race about [horse]. Here is what happened.
Looking back at the data available before the race — was your reasoning sound?
Was the outcome predictable from the data, or genuinely unlucky/lucky?
Does this suggest any change to your active convictions or a new candidate conviction?
Respond with: reasoning_quality (SOUND / FLAWED / UNDETERMINED), 
conviction_to_strengthen (id or null), conviction_to_weaken (id or null), 
new_candidate (description or null)."
```

This means Ozzy distinguishes between:
- **Good call, good reason** — conviction strengthened
- **Good call, wrong reason** — logged, conviction not strengthened (outcome was lucky)
- **Wrong call, bad reason** — conviction weakened significantly
- **Wrong call, good reason** — conviction not weakened (outcome was unlucky)

This is the difference between a tipster who learns and one who just tracks a hit rate.

---

### Ozzy's Memory Object (Passed as Context Every Call)

```javascript
const ozzyMemory = {
  recentBacked: [
    // last 5 BACKED picks with outcomes
    { horse, venue, date, result, ozzyComment, reasoningQuality }
  ],
  recentOffIt: [
    // last 5 OFF IT calls with outcomes
    { horse, venue, date, result, ozzyComment, convictionsFired }
  ],
  notableWrongCalls: [
    // BACKED picks that lost, or OFF IT picks that won — humility context
    { horse, venue, date, ozzyPosition, result, lesson }
  ],
  convictions: activeConvictions,   // full conviction library, active only
  trackRecord: {
    overall:  { backed: N, backedWon: N, offIt: N, offItLost: N },
    byVenue:  { [venue]: { accuracy, total } },
    byGoing:  { [going]: { accuracy, total } },
    byClass:  { [class]: { accuracy, total } }
  }
}
```

This memory is passed into every API call. Ozzy's language naturally reflects his track record — not because he's coded to be confident or humble, but because the data tells him where he's been right and where he hasn't.

---

### Ozzy's UI Panel

**Per pick card — Ozzy section below Verification Report:**

```
┌──────────────────────────────────────────────────────────┐
│ 🔥 OZZY — BACKED                                         │
│                                                          │
│ "Engine's right on trainer and going but it's missing   │
│  the draw angle here — stall 3 in a 6f sprint on this   │
│  track has a clean placed record in my history. The      │
│  score undersells this horse. My pick of the day.        │
│  Go win only — the field isn't strong enough for EW."   │
│                                                          │
│ Ozzy rec: WIN   Conviction: Going pattern (12/16, 75%)  │
│ His record at Ascot: 7W / 12 (58%)                      │
└──────────────────────────────────────────────────────────┘
```

```
┌──────────────────────────────────────────────────────────┐
│ 🚫 OZZY — OFF IT                                         │
│                                                          │
│ "Three poor runs at Class 2 and now dropped to Class 4. │
│  The rating drop flatters the score — this isn't a       │
│  horse going well, it's a horse being placed easier.    │
│  Trainer's record when dropping this horse after losing  │
│  runs: 1 from 11. I've seen this exact setup before.    │
│  If anything in the race, look at the 5."               │
│                                                          │
│ Conviction fired: Class drop masking (9/14, 64%)        │
└──────────────────────────────────────────────────────────┘
```

**When Ozzy is silent — nothing renders.** No placeholder. No "Ozzy has no strong view." The absence of a panel is itself information.

---

### Ozzy's Stats Dashboard

Persistent panel in the main UI (collapsible, separate tab or section):

```
┌──────────────────────────────────────────────────────────┐
│ OZZY — TRACK RECORD                                      │
│                                                          │
│ BACKED:   23 calls | 14 won (61%) | 9 lost              │
│ OFF IT:   18 calls | 12 lost (67%) | 6 won              │
│ Combined accuracy: 63%                                   │
│                                                          │
│ Best venue: Cheltenham (5/7, 71%)                        │
│ Best going: Good to Firm (8/11, 73%)                     │
│ Watch: Soft ground calls (3/8, 38%) — needs more data   │
│                                                          │
│ Active convictions: 7 | Candidates: 3 | Expired: 2      │
│                                                          │
│ [View conviction library] [View audit log]               │
└──────────────────────────────────────────────────────────┘
```

---

### Ozzy's File Structure

```
engine/
└── ozzy/
    ├── ozzy_engine.js          # API call assembly, response parsing, memory builder
    ├── ozzy_memory.json        # Conviction library, audit log, stats
    ├── ozzy_audit.js           # Daily audit runner — conviction updates, new candidates
    ├── ozzy_ui.js              # Render layer — panel, stats dashboard, conviction viewer
    └── ozzy_prompts.js         # System prompt + context template (single source of truth)
```

**localStorage additions:**

| Key | Purpose |
|---|---|
| `ozzyMemory` | Conviction library + stats (synced from ozzy_memory.json) |
| `ozzyAuditLog` | Full audit history |
| `ozzyDailyBriefs` | Ozzy's daily top picks (separate from main picks) |

---

### Ozzy's Shadow Mode (Critical — Do Not Skip)

**Ozzy must launch in Shadow Mode.** He runs, forms views, logs them internally, but does not surface any output to the UI. Shadow Mode continues until:

- Minimum 80 results logged in `results_history`
- Minimum 5 conviction fires with outcomes recorded
- At least one conviction has been promoted from CANDIDATE to ACTIVE

Only then does Ozzy go live. This prevents him from issuing opinions on a conviction library that hasn't been stress-tested. An Ozzy who fires rarely and accurately is worth far more than one who fires constantly and gets ignored.

During Shadow Mode, a progress indicator shows in the Ozzy stats panel:

```
⏳ OZZY — LEARNING
Building conviction library. 43/80 results logged.
Estimated live: ~18 race days.
```

---

## Master Build Order <a name="build-order"></a>

All phases are designed to be built and shipped independently. Each is usable on its own before the next begins.

| Phase | Label | Work | Prerequisite | Estimated Complexity |
|---|---|---|---|---|
| P1 | **Verification Pass** | `runVerificationPass()` in both HTML files. CAS calculator, factor audit, Bayesian update, verdict render. | None | Medium |
| P2 | **Supabase Setup** | Create tables, add push functions to Python scripts, configure `.env` | None | Low |
| P3 | **Mobile HTML** | `prixm_mobile.html` — reads Supabase, 3-level navigation, PWA manifest + Service Worker | P2 | Medium |
| P4 | **Ozzy Foundation** | `ozzy_memory.json` schema, seed convictions (5 manual), `ozzy_engine.js` stub, Shadow Mode indicator | 80+ results logged | Low |
| P5 | **Ozzy Live (Shadow)** | Full API call assembly, conviction firing logic, response parsing, memory builder. No UI output yet. | P4 | High |
| P6 | **Ozzy UI** | Panel render, stats dashboard, conviction viewer, audit log display | P5 | Medium |
| P7 | **Ozzy Audit Loop** | `ozzy_audit.js` — daily conviction updates, candidate mining, reasoning quality audit API call | P6 + 2 weeks live | High |
| P8 | **Ozzy Goes Live** | Remove Shadow Mode gate when thresholds met. Enable UI output. | P7 + thresholds met | Low |
| P9 | **Mobile Ozzy** | Add Ozzy badge + first-sentence preview to mobile pick cards | P3 + P8 | Low |

---

## File & Architecture Map <a name="architecture"></a>

**Complete project structure post-improvements:**

```
Prixm/
│
├── daily_racing_analyzer.html      # Main UI — add: verificationPass, Ozzy panel
├── tomorrow_picks.html             # Advance picks — add: verificationPass only
├── prixm_mobile.html               # NEW — mobile read-only UI (Supabase-fed)
├── manifest.json                   # NEW — PWA manifest
├── sw.js                           # NEW — Service Worker (offline cache)
│
├── results_fetcher.py              # Add: push_to_supabase()
├── racecard_fetcher.py             # Add: push_to_supabase()
├── racecard_fetcher_api.py         # Add: push_to_supabase()
│
├── engine/
│   ├── fetch_daily_races.py        # Unchanged
│   ├── calibration_engine.py       # Unchanged
│   └── ozzy/
│       ├── ozzy_engine.js          # NEW — API call, memory builder
│       ├── ozzy_audit.js           # NEW — daily conviction update loop
│       ├── ozzy_ui.js              # NEW — render layer
│       └── ozzy_prompts.js         # NEW — system prompt + context template
│
├── race_data/                      # Unchanged
├── daily_race_data.json            # Unchanged
├── results_history.json            # Unchanged
├── results_history.js              # Unchanged
│
├── ozzy_memory.json                # NEW — conviction library, audit log, stats
│
├── .env                            # NEW — Supabase credentials (gitignored)
├── requirements.txt                # Add: supabase, python-dotenv
│
├── Fetch Results.bat               # Unchanged
├── Fetch Racecard.bat              # Unchanged
├── Fetch Racecard (API).bat        # Unchanged
│
├── CLAUDE.md                       # Update throughout
└── Prixm Daily Workflow.pdf        # Update after all phases complete
```

---

## Dependencies & Tooling <a name="dependencies"></a>

### Python (new additions only)

```
supabase>=2.0.0
python-dotenv>=1.0.0
```

### JavaScript (CDN, no build tools)

```html
<!-- Supabase JS client — for mobile HTML only -->
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
```

Ozzy's API calls use the same `fetch()` pattern already documented in the Anthropic API setup. No new libraries.

### External Services

| Service | Purpose | Cost |
|---|---|---|
| Supabase | Cloud database for race data, results, picks | Free tier sufficient |
| Anthropic API | Ozzy's thinking (Claude Sonnet) | Pay per use — Ozzy only fires on NAP/WIN picks, typically 3–8 calls/day |

### Environment Variables (`.env`)

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-anon-key
ANTHROPIC_API_KEY=your-key   # used by Ozzy in browser — keep scoped to read-only if possible
```

---

## Key Principles (Do Not Compromise)

1. **Verification Pass must not alter the score.** It issues a verdict alongside the pick. The engine's output is preserved.
2. **Ozzy does not fire on every pick.** If he has no strong view, nothing renders. Frequency of output is not a metric of success.
3. **Ozzy's conviction library is earned, not assumed.** Seed convictions start as CANDIDATE status. Five races minimum before ACTIVE.
4. **Shadow Mode is mandatory.** Ozzy does not surface to UI before 80 results and 5 conviction outcomes. No exceptions.
5. **Mobile is read-only in v1.** Betting, calibration, and manual data entry stay on desktop.
6. **All three improvements are independent.** P1 can ship without P2 or P3. Ozzy can develop while mobile is still in progress. Build in sequence but deploy when each phase is ready.

---

*Document version 1.0 — compiled from design sessions May 2026*  
*Next update: after Phase 3 (Mobile) ships*
