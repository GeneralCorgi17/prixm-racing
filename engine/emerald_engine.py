#!/usr/bin/env python3
"""
☘ Emerald engine — scoring for Irish races (ROI + Northern Ireland), plus the Horse × Track
cross analysis and pace map used by BOTH engines.

Emerald = Prixm's base factors (re-capped) + three Irish factors, total max 118 so scores, gaps
and confidence tiers stay on the same scale as Prixm:

  form 18 · rating 14 · trainer 10 · jockey 9 · fitness 7 · class 7 · going 8 · course 6 ·
  distance 6 · age 5 · weight 7 · headgear 2 · spotlight 2          (= 101, Prixm base re-capped)
  draw_bias 5     — draw vs this track's known bias at this trip (replaces Prixm's generic draw)
  track_fit 6     — Horse × Track cross analysis (running style, sharp/galloping record,
                    direction, uphill finish, stamina, pace) — neutral 3 when there is no evidence
  stable_power 6  — Irish trainer/jockey tiers (Irish name formats) + logged strike rates + RTF

Going / course / distance use the horse's own logged runs (both engines' history) instead of
Prixm's constant 4/3/3 — neutral when the horse has no logged run at that condition.

Rules shared with the UI:
  * No data → no verdict / no check row (never an "unknown" flag). Neutral factor value.
  * Cross analysis for Prixm races is display-only; it only affects the score for Emerald races.
  * All history lookups use runs strictly BEFORE the race date (no look-ahead in the backfill).
"""
import json
import os
import re
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_ROOT, 'scripts'))

from fetch_daily_races import (  # noqa: E402
    calculate_composite_score, calculate_placement_probability, get_confidence_label,
    parse_distance_furlongs,
)

try:
    from results_fetcher import is_ireland, classify_run_style  # single source of truth
except Exception:  # pragma: no cover — fallback keeps the engine importable standalone
    def is_ireland(v):
        return '(ire)' in (v or '').lower()

    def classify_run_style(c):
        return None

ENGINE_NAME = 'Emerald'
PRIXM_MAX = {'form': 20, 'rating': 15, 'trainer': 12, 'jockey': 10, 'fitness': 8, 'class': 8, 'going': 8,
             'course': 6, 'distance': 6, 'age': 7, 'weight': 8, 'draw': 5, 'headgear': 3, 'spotlight': 2}
EMERALD_MAX = {'form': 18, 'rating': 14, 'trainer': 10, 'jockey': 9, 'fitness': 7, 'class': 7, 'going': 8,
               'course': 6, 'distance': 6, 'age': 5, 'weight': 7, 'headgear': 2, 'spotlight': 2,
               'draw_bias': 5, 'track_fit': 6, 'stable_power': 6}
assert sum(EMERALD_MAX.values()) == 118

# ── Irish stable knowledge (Irish racecard name formats) — prior only; logged strike rates refine it ──
IRE_TRAINER_TIERS = {
    3.5: ["w p mullins", "willie mullins", "a p o'brien", "aidan o'brien", "gordon elliott", "g elliott",
          "henry de bromhead", "h de bromhead", "joseph patrick o'brien", "joseph o'brien"],
    2.5: ["mrs john harrington", "jessica harrington", "g m lyons", "ger lyons", "d k weld", "dermot weld",
          "gavin cromwell", "p twomey", "paddy twomey", "donnacha aidan o'brien", "donnacha o'brien",
          "noel meade", "j p murtagh", "johnny murtagh", "emmet mullins", "j a stack", "w mccreery",
          "john c mcconnell", "m d o'callaghan", "tony martin", "a j martin", "henry de bromhead"],
    1.5: ["andrew slattery", "adrian mcguinness", "denis gerard hogan", "p j rothwell", "michael mulvany",
          "ross o'sullivan", "a oliver", "david marnane", "t g mccourt", "john joseph hanlon", "e mcnamara",
          "m c grassick", "ms claire o'connell", "paul w flynn", "john patrick ryan", "peter fahey"],
}
IRE_JOCKEY_TIERS = {
    2.0: ["paul townend", "p townend", "rachael blackmore", "jack kennedy", "j w kennedy", "mark walsh",
          "colin keane", "shane foley", "w j lee", "ryan moore", "wayne lordan", "dylan browne mcmonagle",
          "seamie heffernan", "declan mcdonogh", "chris hayes"],
    1.3: ["ben coen", "gary carroll", "ronan whelan", "danny mullins", "darragh o'keeffe", "sean o'keeffe",
          "keith donoghue", "sam ewing", "j m sheridan", "rory cleary", "gavin ryan", "billy lee",
          "donagh o'connor", "luke mcateer", "wesley joyce", "adam caffrey", "reese holohan"],
}


def _nm(s):
    return re.sub(r'\s+', ' ', re.sub(r"[^a-z' ]", ' ', (s or '').lower())).strip()


def _tier(name, tiers):
    n = _nm(name)
    if not n:
        return 0.0
    for val, names in sorted(tiers.items(), reverse=True):
        if any(n == x or n.endswith(' ' + x) or x in n for x in names):
            return val
    return 0.0


def norm_horse(name):
    return re.sub(r'[^a-z]', '', re.sub(r'\s*\([a-z]{2,3}\)\s*$', '', (name or '').lower()))


# ── Track profiles ───────────────────────────────────────────────────────────

_TP = None


def track_profiles():
    global _TP
    if _TP is None:
        path = os.path.join(_ROOT, 'track_profiles.js')
        try:
            with open(path, encoding='utf-8') as f:
                txt = f.read()
            marker = 'window._trackProfiles='
            _TP = json.loads(txt[txt.index(marker) + len(marker):].strip().rstrip(';'))
        except Exception:
            _TP = {}
    return _TP


def track_key(course):
    v = re.sub(r'\([^)]*\)', ' ', (course or '').lower()).replace('-', ' ')
    v = re.sub(r'^the\s+', '', ' '.join(v.split()))
    return v


def get_track(course):
    tp = track_profiles()
    k = track_key(course)
    if k in tp:
        return tp[k]
    for key in tp:  # "fontwell" ↔ "fontwell park", "newmarket july" → "newmarket"
        if k.startswith(key) or key.startswith(k):
            return tp[key]
    return None


# ── Condition helpers ────────────────────────────────────────────────────────

def going_cat(g):
    g = (g or '').lower()
    if not g:
        return None
    if 'standard' in g or g in ('slow', 'fast'):
        return 'aw'
    if 'heavy' in g:
        return 'heavy'
    if 'yielding to soft' in g or g.startswith('soft') or 'very soft' in g:
        return 'soft'
    if 'good to soft' in g or 'yielding' in g:      # Irish "Yielding" / "Good To Yielding"
        return 'gs'
    if 'good to firm' in g:
        return 'gf'
    if 'firm' in g or 'hard' in g:
        return 'firm'
    if 'good' in g:
        return 'good'
    return None


GOING_ADJ = {'heavy': {'heavy', 'soft'}, 'soft': {'soft', 'heavy', 'gs'}, 'gs': {'gs', 'soft', 'good'},
             'good': {'good', 'gs', 'gf'}, 'gf': {'gf', 'good', 'firm'}, 'firm': {'firm', 'gf'}, 'aw': {'aw'}}


def dist_band(f):
    if not f:
        return None
    if f <= 6:
        return '5-6f'
    if f <= 7.5:
        return '7f'
    if f <= 9:
        return '1m'
    if f <= 11.5:
        return '1m1-3f'
    if f <= 15:
        return '1m4-7f'
    if f <= 20:
        return '2m-2m4f'
    return '2m5f+'


def draw_band_key(f):
    if not f:
        return None
    return '5f' if f <= 5.5 else '6f' if f <= 6.5 else '7f' if f <= 7.5 else '1m' if f <= 8.5 else '1m2f+'


def places_for(field):
    field = field or 0
    return 1 if field <= 4 else 2 if field <= 7 else 3 if field <= 15 else 4


_WEAK = re.compile(r'\b(weakened|faded|tired|no extra|found little|lost place)\b')
_STRONG = re.compile(r'\b(stayed on|ran on|kept on|finished strongly|stayed on well|ran on well)\b')


# ── History index ────────────────────────────────────────────────────────────

class HistoryIndex:
    """Per-horse runs + trainer/jockey strike rates + empirical draw stats, from results_history."""

    def __init__(self, races):
        self.runs = defaultdict(list)
        self.trainer = defaultdict(list)
        self.jockey = defaultdict(list)
        self.draw = defaultdict(list)   # (track, draw band) -> [(date, rel_draw, placed)]
        for race in races or []:
            date = race.get('date', '')
            venue = race.get('venue', '')
            tk = track_key(venue)
            field = race.get('field_size') or len([r for r in race.get('results', []) if not r.get('non_runner')])
            pl = places_for(field)
            df = race.get('distance_f')
            for r in race.get('results', []):
                if r.get('non_runner'):
                    continue
                pos = r.get('finish_pos')
                won = pos == 1
                placed = bool(pos and pos <= pl)
                comment = r.get('run_comment') or ''
                self.runs[norm_horse(r.get('name'))].append({
                    'date': date, 'track': tk, 'going': going_cat(race.get('going')), 'dist': df,
                    'pos': pos, 'won': won, 'placed': placed, 'field': field,
                    'style': r.get('run_style') or classify_run_style(comment), 'comment': comment.lower(),
                    'nh': any(x in (race.get('race_type') or '').lower() for x in ('hurdle', 'chase', 'nh flat', 'bumper')),
                })
                if r.get('trainer'):
                    self.trainer[_nm(r['trainer'])].append((date, won))
                jk = r.get('jockey') or r.get('jockey_result')
                if jk:
                    self.jockey[_nm(jk)].append((date, won))
                if r.get('draw') and field and field >= 6 and df:
                    self.draw[(tk, draw_band_key(df))].append((date, (r['draw'] - 1) / max(1, field - 1), placed))
        for v in self.runs.values():
            v.sort(key=lambda x: x['date'], reverse=True)

    @classmethod
    def from_file(cls, path=None):
        path = path or os.path.join(_ROOT, 'results_history.json')
        try:
            with open(path, encoding='utf-8') as f:
                return cls(json.load(f).get('races', []))
        except Exception:
            return cls([])

    def horse(self, name, before):
        return [r for r in self.runs.get(norm_horse(name), []) if r['date'] < before]

    @staticmethod
    def _sr(rows, before, days=365):
        import datetime as dt
        try:
            cut = (dt.date.fromisoformat(before) - dt.timedelta(days=days)).isoformat()
        except Exception:
            cut = ''
        rs = [w for d, w in rows if cut <= d < before]
        return (sum(rs) / len(rs), len(rs)) if rs else (None, 0)

    def trainer_sr(self, name, before):
        return self._sr(self.trainer.get(_nm(name), []), before)

    def jockey_sr(self, name, before):
        return self._sr(self.jockey.get(_nm(name), []), before)

    def draw_stats(self, course, dist_f, before):
        rows = [x for x in self.draw.get((track_key(course), draw_band_key(dist_f)), []) if x[0] < before]
        return rows


# ── Factor scoring ───────────────────────────────────────────────────────────

def _form_score(runs, cap, neutral):
    """Placed/win rate at a condition → 0..cap, shrunk toward neutral by sample size. None if no runs."""
    n = len(runs)
    if not n:
        return None
    pr = sum(r['placed'] for r in runs) / n
    wr = sum(r['won'] for r in runs) / n
    raw = cap * (0.15 + 0.85 * (0.6 * pr + 0.4 * min(1.0, wr * 2)))
    return round(neutral + (raw - neutral) * n / (n + 2), 1)


def score_draw_bias(runner, race, track, hist, before):
    """0..5 (neutral 3). Static track bias, blended with logged draw results when there are enough."""
    draw, field, df = runner.get('draw'), race.get('field_size') or 0, race.get('distance_f')
    if not draw or field < 6 or not df:
        return 3.0, None
    rel = (draw - 1) / max(1, field - 1)          # 0 = lowest stall … 1 = highest
    band = draw_band_key(df)
    strength, direction = 0.0, None
    bias = ''
    if track:
        db = track.get('draw_bias') or {}
        bias = db.get(band) or db.get('1m+' if band in ('1m', '1m2f+') else '') or db.get('7f+' if band != '5f' else '') or db.get('all') or ''
        if 'low' in bias:
            direction = 'low'
        elif 'high' in bias:
            direction = 'high'
        strength = 1.0 if 'strong' in bias else 0.7 if ('moderate' in bias or 'camber' in bias) else 0.35 if 'slight' in bias else 0.0
    adv = (1 - rel) if direction == 'low' else rel if direction == 'high' else 0.5
    static = 3 + (adv - 0.5) * 4 * strength        # 1..5 at full strength
    rows = hist.draw_stats(race.get('course', ''), df, before) if hist else []
    if len(rows) >= 40:                              # empirical: placed rate of this third vs overall
        third = lambda x: 0 if x < 1 / 3 else 1 if x < 2 / 3 else 2
        mine = [p for _, x, p in rows if third(x) == third(rel)]
        overall = sum(p for _, _, p in rows) / len(rows)
        if mine and overall:
            ratio = (sum(mine) / len(mine)) / overall  # 1.0 = average
            emp = max(1.0, min(5.0, 3 + (ratio - 1) * 4))
            w = min(0.6, len(rows) / 400)
            static = static * (1 - w) + emp * w
    return round(max(0.0, min(5.0, static)), 1), {'direction': direction, 'strength': strength, 'bias': bias, 'rel': rel, 'band': band}


def score_stable_power(runner, hist, before):
    t_prior = _tier(runner.get('trainer'), IRE_TRAINER_TIERS)
    j_prior = _tier(runner.get('jockey'), IRE_JOCKEY_TIERS)
    t_sr, t_n = hist.trainer_sr(runner.get('trainer'), before) if hist else (None, 0)
    j_sr, j_n = hist.jockey_sr(runner.get('jockey'), before) if hist else (None, 0)
    t = t_prior
    if t_sr is not None and t_n >= 10:              # blend prior with logged Irish strike rate
        t_emp = min(3.5, t_sr / 0.25 * 3.5)
        w = t_n / (t_n + 30)
        t = t * (1 - w) + t_emp * w
    j = j_prior
    if j_sr is not None and j_n >= 10:
        j_emp = min(2.0, j_sr / 0.20 * 2.0)
        w = j_n / (j_n + 30)
        j = j * (1 - w) + j_emp * w
    rtf = runner.get('trainer_rtf')
    try:
        rtf = float(rtf)
    except (TypeError, ValueError):
        rtf = None
    r = 0.5 if rtf is None else 1.0 if rtf >= 60 else 0.5 if rtf >= 40 else 0.0
    return round(min(6.0, t + j + r), 1)


# ── Horse × Track cross analysis + pace map (both engines) ───────────────────

def horse_profile(runs):
    """Style + stamina + record by track character from logged runs. Keys absent when no evidence."""
    p = {}
    styled = [r['style'] for r in runs[:6] if r.get('style')]
    if len(styled) >= 2:
        top = max(set(styled), key=styled.count)
        if styled.count(top) >= max(2, len(styled) // 2):
            p['style'] = top
            p['style_n'] = (styled.count(top), len(styled))
    recent = [r for r in runs[:5] if r.get('comment')]
    if len(recent) >= 2:
        p['weak'] = sum(1 for r in recent if _WEAK.search(r['comment']))
        p['strong'] = sum(1 for r in recent if _STRONG.search(r['comment']))
        p['comment_n'] = len(recent)
    tp = track_profiles()

    def rec(pred):
        rs = [r for r in runs if (t := tp.get(r['track']) or get_track(r['track'])) and pred(t)]
        return (sum(r['placed'] for r in rs), len(rs))
    p['sharp'] = rec(lambda t: t.get('sharpness', 0) >= 0.65)
    p['gallop'] = rec(lambda t: t.get('sharpness', 1) <= 0.35)
    p['uphill'] = rec(lambda t: t.get('uphill_finish', 0) >= 0.6)
    p['level'] = rec(lambda t: t.get('uphill_finish', 1) <= 0.3)
    p['dirL'] = rec(lambda t: t.get('direction') == 'L')
    p['dirR'] = rec(lambda t: t.get('direction') == 'R')
    return p


STYLE_LABEL = {'FR': 'Front-runner', 'P': 'Prominent', 'MD': 'Mid-division', 'HU': 'Hold-up'}


def pace_map(runners, hist, before):
    lanes = {'FR': [], 'P': [], 'MD': [], 'HU': []}
    for r in runners:
        if r.get('non_runner'):
            continue
        prof = horse_profile(hist.horse(r.get('name'), before)) if hist else {}
        if prof.get('style'):
            lanes[prof['style']].append(r.get('name'))
    known = sum(len(v) for v in lanes.values())
    if known < 3:
        return None
    fr = lanes['FR']
    if not fr:
        verdict = 'No established front-runner — a slow early pace is likely; prominent racers favoured.'
    elif len(fr) == 1:
        verdict = f'Lone front-runner ({fr[0]}) — likely a steady pace and a possible easy lead; hold-up horses may struggle.'
    elif len(fr) == 2:
        verdict = f'Two pace-setters ({fr[0]}, {fr[1]}) — an even gallop is likely.'
    else:
        verdict = f'{len(fr)} front-runners — a strong pace is likely, which suits horses finishing from off the pace.'
    return {'FR': lanes['FR'], 'P': lanes['P'], 'MD': lanes['MD'], 'HU': lanes['HU'], 'fr_count': len(fr), 'verdict': verdict}


# ── Self-validation: every check type is measured against logged results ─────
# scripts/validate_track_fit.py writes engine/xa_validation.json: {check_key: {"n": int, "lift": float}}
# lift = placed rate of flagged runners ÷ placed rate expected for their score rank − 1.
VALIDATION_PATH = os.path.join(_HERE, 'xa_validation.json')
MIN_N, MIN_LIFT = 40, 0.05
_VAL = None


def validation():
    global _VAL
    if _VAL is None:
        try:
            with open(VALIDATION_PATH, encoding='utf-8') as f:
                _VAL = json.load(f).get('checks', {})
        except Exception:
            _VAL = {}
    return _VAL


def check_status(key, icon):
    """'valid' (proven in the right direction), 'unproven' (too few cases) or 'refuted'."""
    v = validation().get(key)
    if not v or v.get('n', 0) < MIN_N:
        return 'unproven'
    lift = v.get('lift', 0)
    if icon == '✅':
        return 'valid' if lift >= MIN_LIFT else 'refuted'
    return 'valid' if lift <= -MIN_LIFT else 'refuted'


def _empirical_draw(hist, race, runner, before):
    """Logged placed-rate of this runner's draw third at this track+trip vs the average. None if thin."""
    draw, field, df = runner.get('draw'), race.get('field_size') or 0, race.get('distance_f')
    if not draw or field < 6 or not df or not hist:
        return None
    rows = hist.draw_stats(race.get('course', ''), df, before)
    if len(rows) < 60:
        return None
    rel = (draw - 1) / max(1, field - 1)
    third = lambda x: 0 if x < 1 / 3 else 1 if x < 2 / 3 else 2
    mine = [p for _, x, p in rows if third(x) == third(rel)]
    overall = sum(p for _, _, p in rows) / len(rows)
    if len(mine) < 20 or not overall:
        return None
    return (sum(mine) / len(mine)) / overall, len(rows), ['low', 'middle', 'high'][third(rel)]


def cross_analysis(runner, race, track, hist, before, pace, draw_info=None, raw=False):
    """Horse × Track checks. Each check = [icon, demand, horse, key, status].
    Verdict ('s'|'q'|'u') is built ONLY from checks the logged results have validated; returns
    None when there is nothing to show (no evidence → blank, never 'unknown').
    raw=True skips validation (used by scripts/validate_track_fit.py to measure every check)."""
    if not track or not hist:
        return None
    runs = hist.horse(runner.get('name'), before)
    prof = horse_profile(runs) if runs else {}
    checks = []
    field = race.get('field_size') or 0

    def add(icon, demand, horse, key):
        checks.append([icon, demand, horse, key])
    # 1. Draw — from this track's logged draw results at this trip (static bias only as a fallback)
    emp = _empirical_draw(hist, race, runner, before)
    if emp:
        ratio, n, third = emp
        band = draw_band_key(race.get('distance_f'))
        if ratio >= 1.25:
            add('✅', f'Draw matters at {band} here', f"Drawn {runner['draw']} of {field} — {third} stalls place {ratio:.1f}× average ({n} runs)", 'draw_good')
        elif ratio <= 0.75:
            add('❌' if ratio <= 0.6 else '⚠️', f'Draw matters at {band} here', f"Drawn {runner['draw']} of {field} — {third} stalls place {ratio:.1f}× average ({n} runs)", 'draw_bad')
    elif draw_info and draw_info.get('direction') and draw_info['strength'] >= 0.7 and runner.get('draw'):
        rel, d = draw_info['rel'], runner['draw']
        good = rel <= 0.34 if draw_info['direction'] == 'low' else rel >= 0.66
        bad = rel >= 0.66 if draw_info['direction'] == 'low' else rel <= 0.34
        demand = f"{draw_info['direction'].title()} draw favoured at {draw_info['band']}"
        if good:
            add('✅', demand, f'Drawn {d} of {field}', f"draw_static_{draw_info['direction']}_good")
        elif bad:
            add('⚠️', demand, f'Drawn {d} of {field}', f"draw_static_{draw_info['direction']}_bad")
    sharp = track.get('sharpness', 0)
    df = race.get('distance_f') or 0
    # Races entirely on a straight course (Newmarket, Curragh straight mile, Hamilton 6f…) involve no turns
    turning = track.get('direction') in ('L', 'R', 'F8') and not (track.get('straight_course_f') and df and df <= track['straight_course_f'])

    def rate(t):
        return t[0] / t[1] if t[1] else 0.0
    # 2. Sharp track vs galloping type / running style
    if sharp >= 0.65 and turning:
        s_pl, s_n = prof.get('sharp', (0, 0))
        g_pl, g_n = prof.get('gallop', (0, 0))
        if s_n >= 2 and s_pl / s_n >= 0.4:
            add('✅', 'Sharp, turning track', f'{s_pl}/{s_n} placed on sharp tracks', 'sharp_record_good')
        elif s_n >= 2 and s_pl == 0 and g_n >= 2 and g_pl / g_n >= 0.4:
            add('❌', 'Sharp, turning track', f'Galloping type: 0/{s_n} placed on sharp tracks, {g_pl}/{g_n} on galloping', 'sharp_galloper_bad')
        if prof.get('style') == 'HU':
            a, b = prof['style_n']
            add('❌', 'Tight bends, short straight — hold-up horses struggle', f'Held up in {a} of last {b} runs', 'sharp_holdup_bad')
        elif prof.get('style') in ('FR', 'P'):
            a, b = prof['style_n']
            add('✅', 'Handy position is an advantage here', f"{STYLE_LABEL[prof['style']]} in {a} of last {b} runs", 'sharp_handy_good')
    elif sharp <= 0.3 and (track.get('straight_f') or 0) >= 4:
        g_pl, g_n = prof.get('gallop', (0, 0))
        if g_n >= 2 and g_pl / g_n >= 0.4:
            add('✅', 'Wide, galloping track', f'{g_pl}/{g_n} placed on galloping tracks', 'gallop_record_good')
    # 3. Uphill finish vs stamina
    if track.get('uphill_finish', 0) >= 0.6:
        if prof.get('comment_n'):
            n = prof['comment_n']
            if prof.get('weak', 0) >= 2 and prof.get('weak', 0) > prof.get('strong', 0):
                add('❌', 'Stiff uphill finish', f"Weakened late in {prof['weak']} of last {n} runs", 'uphill_weakener_bad')
            elif prof.get('strong', 0) >= 2:
                add('✅', 'Stiff uphill finish', f"Stayed/ran on in {prof['strong']} of last {n} runs", 'uphill_stayer_good')
        # Record comparisons need a contrast: 0/3 uphill means little if the horse never places anywhere
        up, lv = prof.get('uphill', (0, 0)), prof.get('level', (0, 0))
        if up[1] >= 2 and rate(up) >= 0.5 and (lv[1] < 2 or rate(up) >= rate(lv)):
            add('✅', 'Uphill finish', f'{up[0]}/{up[1]} placed on uphill finishes', 'uphill_record_good')
        elif up[1] >= 3 and up[0] == 0 and lv[1] >= 2 and rate(lv) >= 0.4:
            add('❌', 'Uphill finish', f'0/{up[1]} placed on uphill finishes, {lv[0]}/{lv[1]} on level tracks', 'uphill_record_bad')
    # 4. Direction (only when the race actually goes round a bend)
    dirn = track.get('direction')
    if dirn in ('L', 'R') and turning:
        same, other = prof.get('dir' + dirn, (0, 0)), prof.get('dir' + ('R' if dirn == 'L' else 'L'), (0, 0))
        label = 'Left-handed' if dirn == 'L' else 'Right-handed'
        way = 'left-handed' if dirn == 'L' else 'right-handed'
        if same[1] >= 3 and rate(same) >= 0.4 and (other[1] < 2 or rate(same) >= rate(other)):
            add('✅', label, f'{same[0]}/{same[1]} placed {way}', 'direction_good')
        elif same[1] >= 3 and same[0] == 0 and other[1] >= 2 and rate(other) >= 0.4:
            add('❌', label, f'0/{same[1]} placed {way}, {other[0]}/{other[1]} the other way', 'direction_bad')
    # 5. Pace
    if pace and prof.get('style') == 'HU' and pace['fr_count'] <= 1:
        add('⚠️', 'Hold-up horses need a strong pace', f"Only {pace['fr_count']} front-runner in the field", 'pace_holdup_bad')
    if pace and prof.get('style') == 'FR' and pace['fr_count'] == 1 and sharp >= 0.5:
        add('✅', 'Lone leader on a turning track', 'Likely to get an uncontested lead', 'pace_lone_leader_good')
    if not checks:
        return None
    if raw:
        return {'checks': checks}
    shown = []
    for c in checks:
        st = check_status(c[3], c[0])
        if st != 'refuted':                       # the data says this check doesn't matter → drop it
            shown.append(c + [st])
    valid = [c for c in shown if c[4] == 'valid']
    pos = sum(1 for c in valid if c[0] == '✅')
    neg = sum(1 for c in valid if c[0] == '❌')
    warn = sum(1 for c in valid if c[0] == '⚠️')
    if not shown:
        return None
    if not valid:
        v = None                                   # only unproven checks → detail rows, no badge
    elif neg >= 2 or (neg == 1 and pos == 0):
        v = 'u'
    elif neg == 1 or warn:
        v = 'q'
    else:
        v = 's'
    return {'verdict': v, 'checks': shown, 'pos': pos, 'neg': neg, 'warn': warn}


def track_fit_points(xa):
    if not xa:
        return 3.0
    return round(max(0.0, min(6.0, 3 + xa['pos'] * 0.8 - xa['neg'] * 1.2 - xa['warn'] * 0.5)), 1)


# ── Race-level entry points ──────────────────────────────────────────────────

def annotate_race(race, runners, hist, date, course=None):
    """Attach Horse × Track cross analysis (runner['track_fit']) and pace map (race['pace']).
    Display-only for Prixm races. Returns (track, pace, {name: (xa, draw_info)})."""
    course = course or race.get('course', '')
    track = get_track(course)
    race['course'] = race.get('course') or course
    pace = pace_map(runners, hist, date) if hist else None
    if pace:
        race['pace'] = pace
    out = {}
    for r in runners:
        _, draw_info = score_draw_bias(r, race, track, hist, date)
        xa = cross_analysis(r, race, track, hist, date, pace, draw_info)
        if xa:
            # checks: [icon, demand, horse, key, 'valid'|'unproven']; verdict None = rows only, no badge
            r['track_fit'] = {'verdict': xa['verdict'], 'checks': xa['checks']}
        else:
            r.pop('track_fit', None)
        out[r.get('name')] = (xa, draw_info)
    return track, pace, out


def score_race_emerald(race, runners, hist, date, course=None):
    """Score an Irish race in place. Keeps Prixm's score as prixm_score / prixm_breakdown."""
    course = course or race.get('course', '')
    track, pace, xas = annotate_race(race, runners, hist, date, course)
    fs = race.get('field_size') or len(runners)
    for r in runners:
        if 'prixm_score' not in r:
            if r.get('score') is not None and r.get('score_breakdown') and 'draw' in r['score_breakdown']:
                # Prixm already scored this runner (racecard fetch / archive) — keep that exact score
                r['prixm_score'], r['prixm_breakdown'] = r['score'], dict(r['score_breakdown'])
            else:
                p = calculate_composite_score(r, race, runners)
                r['prixm_score'], r['prixm_breakdown'] = p['total'], p['breakdown']
        pb = r['prixm_breakdown']
        bd = {}
        for f, mx in EMERALD_MAX.items():
            if f in PRIXM_MAX and f != 'draw':
                bd[f] = round(min(mx, (pb.get(f) or 0) * mx / PRIXM_MAX[f]), 1)
        runs = hist.horse(r.get('name'), date) if hist else []
        g = going_cat(race.get('going'))
        if g == 'aw':
            bd['going'] = 6.0
        elif g:
            v = _form_score([x for x in runs if x['going'] in GOING_ADJ.get(g, {g})], 8, 4.0)
            bd['going'] = v if v is not None else 4.0
        v = _form_score([x for x in runs if x['track'] == track_key(course)], 6, 3.0)
        bd['course'] = v if v is not None else 3.0
        df = race.get('distance_f') or parse_distance_furlongs(race.get('distance'))
        if df:
            v = _form_score([x for x in runs if x['dist'] and abs(x['dist'] - df) <= 1], 6, 3.0)
            bd['distance'] = v if v is not None else 3.0
        bd['draw_bias'], _ = score_draw_bias(r, race, track, hist, date)
        xa = xas.get(r.get('name'), (None, None))[0]
        bd['track_fit'] = track_fit_points(xa)
        bd['stable_power'] = score_stable_power(r, hist, date)
        total = round(sum(bd.values()), 1)
        r['score'] = total
        r['score_breakdown'] = bd
        r['confidence'] = get_confidence_label(total)
        r['probs'] = {f'top_{n}': calculate_placement_probability(total, n, fs) for n in [1, 2, 3, 4, 5, 6, 8, 10]}
        r['engine'] = 'emerald'
    race['engine'] = 'emerald'
    runners.sort(key=lambda x: x.get('score', 0), reverse=True)
    return runners


def process_card(output, hist=None, date=None):
    """Post-process a whole racecard dict (daily_race_data format): Emerald-score Irish races,
    cross-analyse every race. Mutates and returns output."""
    hist = hist or HistoryIndex.from_file()
    date = date or output.get('date') or ''
    for vkey, venue in (output.get('venues') or {}).items():
        course = venue.get('course') or vkey
        for race in venue.get('races', []):
            runners = race.get('runners', [])
            race.setdefault('course', course)
            if is_ireland(course):
                race['runners'] = score_race_emerald(race, runners, hist, date, course)
            else:
                annotate_race(race, runners, hist, date, course)
                race['engine'] = 'prixm'
    return output


if __name__ == '__main__':
    # Re-process today's card in place: python engine/emerald_engine.py [path]
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_ROOT, 'daily_race_data.json')
    with open(path, encoding='utf-8') as f:
        card = json.load(f)
    process_card(card)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(card, f, indent=2, default=str)
    if os.path.basename(path) == 'daily_race_data.json':
        # keep the file:// copy in sync (daily_race_data.js is gitignored — easy to forget)
        with open(os.path.join(os.path.dirname(path), 'daily_race_data.js'), 'w', encoding='utf-8') as f:
            f.write('window._raceDataFile=')
            json.dump(card, f, indent=2, default=str)
            f.write(';')
        dated = os.path.join(os.path.dirname(path), 'race_data', f"race_data_{card.get('date')}.json")
        if card.get('date') and os.path.exists(dated):
            with open(dated, 'w', encoding='utf-8') as f:
                json.dump(card, f, indent=2, default=str)
    print(f'Emerald processed {path}')
