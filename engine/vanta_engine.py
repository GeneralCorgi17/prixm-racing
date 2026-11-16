#!/usr/bin/env python3
"""
Vanta engine — scoring for French gallop races (Flat / Hurdle / Chase / Cross). Added 2026-11-16.

STARTER (until a profile is recalibrated): Prixm's base factors re-capped + four French factors,
total max 118 so scores, gaps and confidence tiers stay on the same scale as Prixm and Emerald:

  form 19 · rating 14 · trainer 10 · jockey 9 · fitness 7 · class 7 · going 7 · weight 7 · age 6 ·
  course 5 · distance 5 · headgear 2 · spotlight 1                 (= 99, Prixm base re-capped)
  draw_bias 5     — stall (PMU placeCorde) vs this track's bias at this trip, blended with the
                    logged French stall results once there are enough
  track_fit 5     — Horse × Track cross analysis (shared with Prixm/Emerald), neutral 2.5
  stable_power 5  — French trainer/jockey tiers (PMU name format "A.FABRE") + logged strike rates
  class_earn 4    — career earnings per run vs the rest of the field (France's class signal), neutral 2

Going / course / distance use the horse's own logged runs (neutral when none), like Emerald.
Each runner keeps prixm_score / prixm_breakdown so the Starter can be compared with Prixm.

Vanta 1.0 = the first time a profile (fr_flat / fr_nh) reaches 1000 logged races AND the user
clicks Apply on the recalibration in the Vanta tab. From then on that profile uses its own
calibrated weights (applied in the HTML, like Prixm/Emerald) and the Prixm comparison is hidden.

Rules: history lookups use runs strictly BEFORE the race date. No market prices as inputs.
"""
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_ROOT, 'scripts'))

from emerald_engine import (  # noqa: E402
    PRIXM_MAX, HistoryIndex, GOING_ADJ, _form_score, _nm, annotate_race, going_cat, score_draw_bias,
    track_fit_points, track_key, calculate_composite_score, calculate_placement_probability,
    get_confidence_label, parse_distance_furlongs,
)

ENGINE_NAME = 'Vanta'
VANTA_MAX = {'form': 19, 'rating': 14, 'trainer': 10, 'jockey': 9, 'fitness': 7, 'class': 7, 'going': 7,
             'weight': 7, 'age': 6, 'course': 5, 'distance': 5, 'headgear': 2, 'spotlight': 1,
             'draw_bias': 5, 'track_fit': 5, 'stable_power': 5, 'class_earn': 4}
assert sum(VANTA_MAX.values()) == 118

# ── French stable knowledge — surnames as PMU/RP print them; prior only, logged strike rates refine it ──
FR_TRAINER_TIERS = {
    2.8: ['fabre', 'rouget', 'graffard', 'ferland', 'macaire', 'nicolle', 'chaille chaille'],
    2.0: ['bary', 'laffon parias', 'rossi', 'head maarek', 'delzangles', 'clement', 'wattel', 'pantall',
          'chappet', 'smaga', 'brandt', 'cottin', 'bressou', 'lerner', 'caullery', 'boutin', 'lacombe',
          'cherel', 'lageneste', 'lecoiffier', 'fouin', 'peltier', 'vermeulen', 'decouz', 'collet'],
    1.2: ['reynier', 'escuder', 'barberot', 'rohaut', 'boudot', 'monfort', 'phelippon', 'baudron',
          'vidal', 'henderson', 'mikhalides', 'guillochon', 'zuliani', 'labate', 'foresi', 'sigaud',
          'perret', 'andreu', 'ricard', 'lyon', 'requena', 'chalvet', 'aubry', 'lenoir'],
}
FR_JOCKEY_TIERS = {
    2.2: ['soumillon', 'barzalona', 'demuro', 'guyon', 'pasquier', 'boudot', 'lemaitre', 'reveley',
          'nabet', 'de giles', 'lestrade'],
    1.4: ['crastus', 'pouchin', 'madamet', 'bachelot', 'mosse', 'hamelin', 'piccone', 'murzabayev',
          'besnier', 'grandin', 'velon', 'trullier', 'mendizabal', 'eyquem', 'seigneul', 'charron',
          'beaurain', 'plouganou', 'meunier', 'gelhay', 'lemercier', 'zuliani', 'orani', 'bertras',
          'guillaume', 'gauffenic', 'lerner', 'veron', 'santiago', 'speicher', 'wargnier'],
}


def _surname(name):
    """'A.FABRE' / 'Andre Fabre' / 'MME C.HEAD-MAAREK' -> 'fabre' / 'head maarek'."""
    n = _nm((name or '').replace('.', ' ').replace('-', ' ').replace('&', ' '))
    toks = [t for t in n.split() if t not in ('mme', 'mlle', 'm', 'mr', 'ms', 'de', 'du') and len(t) > 1]
    return ' '.join(toks)


def _fr_tier(name, tiers):
    s = _surname(name)
    if not s:
        return 0.0
    for val, names in sorted(tiers.items(), reverse=True):
        if any(s == x or s.endswith(' ' + x) or (' ' in x and x in s) for x in names):
            return val
    return 0.0


def classify_profile(race):
    rt = (race.get('race_type') or race.get('type') or '').lower()
    return 'fr_nh' if any(x in rt for x in ('hurdle', 'chase', 'nh flat', 'bumper', 'cross')) else 'fr_flat'


def score_stable_power(runner, hist, before):
    """0..5: trainer (≤2.8) + jockey (≤2.2) — French tiers blended with logged French strike rates."""
    t = _fr_tier(runner.get('trainer'), FR_TRAINER_TIERS)
    j = _fr_tier(runner.get('jockey'), FR_JOCKEY_TIERS)
    if hist:
        t_sr, t_n = hist.trainer_sr(runner.get('trainer'), before)
        if t_sr is not None and t_n >= 10:
            w = t_n / (t_n + 30)
            t = t * (1 - w) + min(2.8, t_sr / 0.22 * 2.8) * w
        j_sr, j_n = hist.jockey_sr(runner.get('jockey'), before)
        if j_sr is not None and j_n >= 10:
            w = j_n / (j_n + 30)
            j = j * (1 - w) + min(2.2, j_sr / 0.18 * 2.2) * w
    return round(min(5.0, t + j), 1)


def class_earn_points(runners):
    """{name: 0..4} — career earnings per run, ranked within the field (log scale). Neutral 2 when
    fewer than 3 runners have a record; a debutant gets 1.5."""
    vals = {}
    for r in runners:
        c = r.get('career') or {}
        runs = c.get('runs')
        if runs:
            vals[r.get('name')] = math.log1p((c.get('earn') or 0) / runs)
    out = {}
    if len(vals) < 3:
        return {r.get('name'): 2.0 for r in runners}
    ordered = sorted(vals.values())
    n = len(ordered)
    for r in runners:
        nm = r.get('name')
        c = r.get('career') or {}
        if nm in vals:
            below = sum(1 for v in ordered if v < vals[nm])
            same = sum(1 for v in ordered if v == vals[nm])
            pct = (below + (same - 1) / 2) / max(1, n - 1)
            out[nm] = round(0.5 + 3.5 * pct, 1)
        else:
            out[nm] = 1.5 if c.get('runs') == 0 else 2.0
    return out


def score_race_vanta(race, runners, hist, date, course=None):
    """Score a French race in place. Keeps Prixm's score as prixm_score / prixm_breakdown."""
    course = course or race.get('course', '')
    race['course'] = race.get('course') or course
    track, pace, xas = annotate_race(race, runners, hist, date, course)
    fs = race.get('field_size') or len(runners)
    earn = class_earn_points(runners)
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
        for f, mx in VANTA_MAX.items():
            if f in PRIXM_MAX and f != 'draw':
                bd[f] = round(min(mx, (pb.get(f) or 0) * mx / PRIXM_MAX[f]), 1)
        runs = hist.horse(r.get('name'), date) if hist else []
        g = going_cat(race.get('going'))
        if g == 'aw':
            bd['going'] = 5.0
        elif g:
            v = _form_score([x for x in runs if x['going'] in GOING_ADJ.get(g, {g})], 7, 3.5)
            bd['going'] = v if v is not None else 3.5
        v = _form_score([x for x in runs if x['track'] == track_key(course)], 5, 2.5)
        bd['course'] = v if v is not None else 2.5
        df = race.get('distance_f') or parse_distance_furlongs(race.get('distance'))
        if df:
            v = _form_score([x for x in runs if x['dist'] and abs(x['dist'] - df) <= 1], 5, 2.5)
            bd['distance'] = v if v is not None else 2.5
        bd['draw_bias'], _ = score_draw_bias(r, race, track, hist, date)
        xa = xas.get(r.get('name'), (None, None))[0]
        bd['track_fit'] = round(track_fit_points(xa) * 5 / 6, 1)
        bd['stable_power'] = score_stable_power(r, hist, date)
        bd['class_earn'] = earn.get(r.get('name'), 2.0)
        total = round(sum(bd.values()), 1)
        r['score'] = total
        r['score_breakdown'] = bd
        r['confidence'] = get_confidence_label(total)
        r['probs'] = {f'top_{n}': calculate_placement_probability(total, n, fs) for n in [1, 2, 3, 4, 5, 6, 8, 10]}
        r['engine'] = 'vanta'
    race['engine'] = 'vanta'
    race['profile'] = classify_profile(race)
    runners.sort(key=lambda x: x.get('score', 0), reverse=True)
    return runners


if __name__ == '__main__':
    # Re-process today's card in place (all three engines): python engine/vanta_engine.py [path]
    import subprocess
    sys.exit(subprocess.call([sys.executable, os.path.join(_HERE, 'emerald_engine.py')] + sys.argv[1:]))
