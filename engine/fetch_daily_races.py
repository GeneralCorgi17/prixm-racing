#!/usr/bin/env python3
"""
Daily Horse Racing Fetcher & Analyzer
Fetches race cards from Racing Post via rpscrape, scores each horse,
and outputs JSON for the dashboard.

Usage:
  python fetch_daily_races.py              # Fetch today's races
  python fetch_daily_races.py --date 2026-03-25  # Fetch specific date
  python fetch_daily_races.py --tomorrow   # Fetch tomorrow's races
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def load_weight_profile(profile):
    """Load calibrated weights for a surface profile from results_history.json.
    Falls back to None if file doesn't exist or profile not found."""
    history_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results_history.json')
    try:
        with open(history_path) as f:
            history = json.load(f)
        return history.get('weight_profiles', {}).get(profile, None)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def parse_distance_furlongs(dist):
    """Convert a distance string like '2m4f', '7f', '1m' to numeric furlongs.
    If already numeric, returns as-is. Returns None if unparseable."""
    if dist is None:
        return None
    if isinstance(dist, (int, float)):
        return float(dist)
    s = str(dist).strip().lower()
    # Try direct numeric
    try:
        return float(s)
    except ValueError:
        pass
    # Parse patterns like '2m4f', '1m', '7f', '2m4f110y'
    m = re.match(r'(\d+)m\s*(\d+)f', s)
    if m:
        return int(m.group(1)) * 8 + int(m.group(2))
    m = re.match(r'(\d+)m', s)
    if m:
        return int(m.group(1)) * 8
    m = re.match(r'(\d+)f', s)
    if m:
        return int(m.group(1))
    return None


# === CONFIGURATION ===

RPSCRAPE_DIR = os.path.expanduser("~/rpscrape")  # Adjust if rpscrape is elsewhere
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Target venues (lowercase for matching)
TARGET_VENUES = [
    "lingfield", "wolverhampton", "dundalk", "newbury",
    "newcastle", "exeter", "kempton", "cheltenham",
    "ascot", "sandown", "haydock", "doncaster", "york",
    "leopardstown", "fairyhouse", "punchestown", "aintree",
    "wincanton", "huntingdon", "catterick", "wetherby",
    "chepstow", "warwick", "plumpton", "fontwell",
    "market rasen", "sedgefield", "musselburgh", "ayr",
    "perth", "carlisle", "bangor", "ludlow", "taunton",
    "uttoxeter", "stratford", "southwell", "cartmel",
    "hexham", "ffos las", "hereford", "towcester",
    "cork", "galway", "limerick", "navan", "naas",
    "thurles", "tipperary", "kilbeggan", "gowran park",
    "down royal", "downpatrick", "ballinrobe", "clonmel",
    "tramore", "wexford", "listowel", "killarney", "sligo",
    "roscommon", "bellewstown", "laytown",
]

# Elite trainers (NH + Flat, UK + Ireland)
ELITE_TRAINERS = {
    # Tier 1 - Championship level
    "W Mullins": 95, "Willie Mullins": 95,
    "N Henderson": 92, "Nicky Henderson": 92,
    "P Nicholls": 88, "Paul Nicholls": 88,
    "D Skelton": 85, "Dan Skelton": 85,
    "G Elliott": 87, "Gordon Elliott": 87,
    "H De Bromhead": 84, "Henry De Bromhead": 84,
    # Tier 2
    "G Cromwell": 75, "Gavin Cromwell": 75,
    "J O'Neill": 72, "Jonjo O'Neill": 72,
    "O Murphy": 70, "Olly Murphy": 70,
    "B Pauling": 70, "Ben Pauling": 70,
    "L Russell": 68, "Lucinda Russell": 68,
    "K Bailey": 67, "Kim Bailey": 67,
    "N Twiston-Davies": 68, "Nigel Twiston-Davies": 68,
    "A King": 67, "Alan King": 67,
    "V Williams": 67, "Venetia Williams": 67,
    "E Lavelle": 65, "Emma Lavelle": 65,
    "C Tizzard": 65, "Colin Tizzard": 65,
    "J Tizzard": 65, "Joe Tizzard": 65,
    # Flat elite
    "A O'Brien": 95, "Aidan O'Brien": 95,
    "C Appleby": 90, "Charlie Appleby": 90,
    "J Gosden": 88, "John Gosden": 88,
    "W Haggas": 85, "William Haggas": 85,
    "R Varian": 82, "Roger Varian": 82,
    "A Balding": 80, "Andrew Balding": 80,
    "Sir M Stoute": 80, "Sir Michael Stoute": 80,
    "K Ryan": 75, "Kevin Ryan": 75,
    "R Hannon": 75, "Richard Hannon": 75,
    "S Crisford": 73, "Simon Crisford": 73,
    "H Palmer": 72, "Hugo Palmer": 72,
}

# Top jockeys
ELITE_JOCKEYS = {
    # NH
    "P Townend": 95, "Paul Townend": 95,
    "N De Boinville": 92, "Nico De Boinville": 92,
    "H Cobden": 88, "Harry Cobden": 88,
    "H Skelton": 85, "Harry Skelton": 85,
    "M Walsh": 85, "Mark Walsh": 85,
    "J Kennedy": 83, "Jack Kennedy": 83,
    "R Blackmore": 85, "Rachael Blackmore": 85,
    "B Jones": 72, "Ben Jones": 72,
    "S Bowen": 70, "Sean Bowen": 70,
    "J McGrath": 68, "J J Slevin": 68,
    "D Jacob": 70, "Daryl Jacob": 70,
    "B Powell": 68, "Brendan Powell": 68,
    # Flat
    "R Moore": 95, "Ryan Moore": 95,
    "W Buick": 92, "William Buick": 92,
    "T Marquand": 88, "Tom Marquand": 88,
    "J Doyle": 85, "James Doyle": 85,
    "O Murphy": 82, "Oisin Murphy": 82,
    "B De Sousa": 78, "Silvestre De Sousa": 78,
    "R Havlin": 75, "Robert Havlin": 75,
}


def parse_form(form_str):
    """Parse form string like '12341' into list of positions.
    Form chars: 1-9 = position, 0 = 10+, P = pulled up, F = fell, U = unseated, R = refused, - = no form"""
    if not form_str:
        return []
    results = []
    for c in form_str:
        if c.isdigit():
            results.append(int(c) if c != '0' else 10)
        elif c in ('P', 'p'):
            results.append(99)  # pulled up
        elif c in ('F', 'f'):
            results.append(98)  # fell
        elif c in ('U', 'u'):
            results.append(97)  # unseated
        elif c in ('R', 'r'):
            results.append(96)  # refused
        elif c == '-':
            continue
    return results


def score_form(form_positions, field_size=None):
    """Score recent form (0-20 points)"""
    if not form_positions:
        return 5  # neutral for unknown form

    score = 0
    weights = [5, 4, 3, 2, 1]  # most recent weighted highest

    for i, pos in enumerate(form_positions[:5]):
        w = weights[i] if i < len(weights) else 1
        if pos == 1:
            score += w * 4
        elif pos == 2:
            score += w * 3
        elif pos == 3:
            score += w * 2.5
        elif pos <= 5:
            score += w * 1.5
        elif pos <= 8:
            score += w * 0.5
        elif pos >= 96:  # DNF
            score -= w * 1

    return min(max(round(score / 3), 0), 20)


def score_rating(rpr, ofr, ts, runners_ratings):
    """Score horse's rating relative to field (0-15 points)"""
    rating = rpr or ofr or ts or 0
    if rating == 0:
        return 5

    if runners_ratings:
        avg = sum(runners_ratings) / len(runners_ratings)
        max_r = max(runners_ratings) if runners_ratings else rating
        if max_r == avg:
            return 8
        relative = (rating - avg) / (max_r - avg) if max_r > avg else 0
        return min(max(round(relative * 15), 0), 15)

    return min(max(round(rating / 12), 0), 15)


def score_trainer(trainer_name):
    """Score trainer quality (0-12 points)"""
    for name, val in ELITE_TRAINERS.items():
        if name.lower() in (trainer_name or "").lower():
            return min(round(val / 8), 12)

    # Parse trainer RTF if available
    return 4  # default for unknown trainer


def score_trainer_rtf(rtf_string):
    """Parse trainer recent-to-form string like '2-15 (13.3%)' and score it"""
    if not rtf_string:
        return 0

    # Ensure we only run regex on strings
    if not isinstance(rtf_string, str):
        rtf_string = str(rtf_string)

    match = re.search(r'(\d+)-(\d+)\s*\((\d+\.?\d*)%\)', rtf_string)
    if match:
        wins = int(match.group(1))
        runs = int(match.group(2))
        pct = float(match.group(3))
        if pct >= 25:
            return 5
        elif pct >= 18:
            return 4
        elif pct >= 12:
            return 3
        elif pct >= 8:
            return 2
        return 1
    return 0

def score_jockey(jockey_name):
    """Score jockey quality (0-10 points)"""
    for name, val in ELITE_JOCKEYS.items():
        if name.lower() in (jockey_name or "").lower():
            return min(round(val / 10), 10)
    return 3  # default


def score_fitness(days_since_last_run):
    """Score fitness/freshness (0-8 points)"""
    if days_since_last_run is None:
        return 4
    if 14 <= days_since_last_run <= 42:
        return 8  # ideal: 2-6 weeks
    elif 7 <= days_since_last_run <= 56:
        return 6  # acceptable
    elif days_since_last_run <= 7:
        return 4  # quick turnaround - ok but maybe tired
    elif days_since_last_run <= 90:
        return 4  # slightly concerning gap
    elif days_since_last_run <= 180:
        return 2  # long absence
    return 1  # very long absence


def score_class_change(race_class, ofr, field_ratings):
    """Score class drop/rise (0-8 points)"""
    if not ofr or not field_ratings:
        return 4  # neutral

    avg = sum(field_ratings) / len(field_ratings)
    diff = ofr - avg

    if diff > 10:
        return 8  # well in (dropping class)
    elif diff > 5:
        return 7
    elif diff > 0:
        return 6  # slightly ahead
    elif diff > -5:
        return 4  # at level
    elif diff > -10:
        return 2  # rising in class
    return 1  # out of depth


def score_age(age, race_type, distance_f):
    """Score horse's age suitability (0-7 points).

    Research-backed optimal ages:
    - NH (Hurdles): Peak 6-8, competitive 5-9, decline 10+
    - NH (Chases): Peak 7-9, competitive 6-10, decline 11+
    - NH (Bumpers): Peak 5-6
    - Flat (Sprint 5-7f): Peak 3-4
    - Flat (Mile 8-10f): Peak 3-5
    - Flat (Staying 12f+): Peak 4-6
    """
    if not age:
        return 3  # unknown

    rt = (race_type or '').lower()
    df = parse_distance_furlongs(distance_f) or 16

    if 'chase' in rt:
        # Chasers peak 7-9
        if 7 <= age <= 9: return 7
        elif age == 6 or age == 10: return 5
        elif age == 5 or age == 11: return 3
        elif age >= 12: return 1  # over the hill
        return 2
    elif 'hurdle' in rt:
        # Hurdlers peak 6-8
        if 6 <= age <= 8: return 7
        elif age == 5 or age == 9: return 5
        elif age == 4 or age == 10: return 3
        elif age >= 11: return 1
        return 2
    elif 'nh flat' in rt or 'bumper' in rt:
        # Bumpers peak 5-6
        if 5 <= age <= 6: return 7
        elif age == 4: return 5
        elif age == 7: return 3
        return 1
    else:
        # Flat racing - age advantage depends heavily on distance
        if df <= 7:  # Sprint
            if 3 <= age <= 4: return 7
            elif age == 5: return 5
            elif age == 6: return 3
            elif age >= 7: return 2
            return 3
        elif df <= 10:  # Mile
            if 3 <= age <= 5: return 7
            elif age == 6: return 5
            elif age >= 7: return 3
            return 3
        else:  # Staying
            if 4 <= age <= 6: return 7
            elif age == 3 or age == 7: return 5
            elif age >= 8: return 3
            return 3


def score_weight(lbs, field_weights, race_type, handicap, age):
    """Score weight advantage (0-8 points).

    Key factors:
    - In handicaps: lower weight = big advantage (assigned based on ability)
    - In non-handicaps: weight differences smaller but still relevant
    - Weight carried relative to field average
    - Penalty carriers (top weight) historically underperform
    - Light-weighted horses in big-field handicaps overperform
    """
    if not lbs or not field_weights:
        return 4  # neutral

    avg_w = sum(field_weights) / len(field_weights)
    min_w = min(field_weights) if field_weights else lbs
    max_w = max(field_weights) if field_weights else lbs
    diff = avg_w - lbs  # positive = carrying less than average
    spread = max_w - min_w if max_w > min_w else 1

    if handicap:
        # In handicaps, weight is the equaliser — lighter = advantage
        # A horse carrying 10st vs 12st has a massive edge
        relative = (max_w - lbs) / spread  # 1.0 = lightest, 0.0 = heaviest
        if relative >= 0.8: return 8   # near bottom weight
        elif relative >= 0.6: return 7
        elif relative >= 0.4: return 5  # mid-weight
        elif relative >= 0.2: return 3
        return 1  # top weight — historically poor strike rate
    else:
        # Non-handicaps: smaller weight differences, mainly age/sex allowances
        if diff > 7: return 7   # getting significant allowance
        elif diff > 3: return 6
        elif diff >= 0: return 5  # at or below average
        elif diff > -3: return 4
        elif diff > -7: return 3
        return 2  # giving away a lot


def score_draw(draw, field_size, course_name):
    """Score draw advantage (flat races only) (0-5 points)"""
    if draw is None or field_size is None or field_size < 8:
        return 3  # neutral for small fields or jumps

    # General draw biases (simplified)
    # Low draws tend to be favourable at many courses
    third = field_size / 3
    if draw <= third:
        return 4  # low draw generally good
    elif draw <= third * 2:
        return 3  # middle
    return 2  # high draw


def score_headgear(headgear, headgear_first):
    """Score headgear changes (0-3 points)"""
    if headgear_first:
        return 3  # first-time headgear is a positive signal
    if headgear:
        return 2  # wearing headgear (established)
    return 2  # no headgear (neutral)


def score_spotlight(spotlight_text):
    """Parse expert commentary for positive/negative signals (0-2 points)"""
    if not spotlight_text:
        return 1

    text = spotlight_text.lower()
    positive = ['progressive', 'improved', 'unexposed', 'well treated', 'interesting',
                'fancied', 'strong chance', 'leading contender', 'promising', 'exciting',
                'should go close', 'looks the one', 'big chance', 'key player',
                'well handicapped', 'ahead of mark', 'open to improvement']
    negative = ['disappointing', 'regressive', 'out of form', 'hard to fancy',
                'questions to answer', 'needs to improve', 'opposition looks too strong',
                'exposed', 'higher than ideal', 'struggling']

    pos_count = sum(1 for p in positive if p in text)
    neg_count = sum(1 for n in negative if n in text)

    if pos_count > neg_count + 1:
        return 2
    elif pos_count > neg_count:
        return 1.5
    elif neg_count > pos_count:
        return 0.5
    return 1


def score_going_preference(runner_going_record, race_going):
    """Score how well this horse handles today's ground conditions (0-8 points).

    Going is one of THE most important factors in horse racing.
    A mud lover on firm ground (or vice versa) is severely compromised.

    Runner data should include 'going_record' dict, e.g.:
      {"Heavy": "3-1-0-2", "Soft": "2-0-1-3", "Good": "0-1-0-5"}
    Format: "wins-seconds-thirds-runs" or just win strike rate on that going.

    If no going record is available, we parse the spotlight/comment for going clues.
    """
    if not race_going:
        return 4  # neutral

    going = race_going.lower().strip()

    # Map going descriptions to categories
    going_cat = 'good'  # default
    if 'heavy' in going:
        going_cat = 'heavy'
    elif 'soft' in going:
        going_cat = 'soft'
    elif 'good to soft' in going or 'yielding' in going:
        going_cat = 'good_to_soft'
    elif 'good to firm' in going:
        going_cat = 'good_to_firm'
    elif 'firm' in going or 'hard' in going:
        going_cat = 'firm'
    elif 'standard' in going or 'slow' in going:
        going_cat = 'standard'  # AW
    elif 'good' in going:
        going_cat = 'good'

    if not runner_going_record or not isinstance(runner_going_record, dict):
        return 4  # no data — neutral

    # Check if horse has form on this going category
    # going_record keys should match going categories
    # Look for exact match first, then adjacent going
    adjacent = {
        'heavy': ['heavy', 'soft'],
        'soft': ['soft', 'heavy', 'good_to_soft'],
        'good_to_soft': ['good_to_soft', 'soft', 'good'],
        'good': ['good', 'good_to_soft', 'good_to_firm'],
        'good_to_firm': ['good_to_firm', 'good', 'firm'],
        'firm': ['firm', 'good_to_firm'],
        'standard': ['standard'],  # AW — going rarely matters
    }

    # For AW (standard), going is mostly irrelevant
    if going_cat == 'standard':
        return 6  # slight positive — AW negates going as a variable

    search_order = adjacent.get(going_cat, [going_cat])
    for g in search_order:
        for key, val in runner_going_record.items():
            if g in key.lower().replace('-', '_').replace(' ', '_'):
                # Parse record string "W-P-P-R" or percentage
                if isinstance(val, str) and '-' in val:
                    parts = val.split('-')
                    if len(parts) >= 4:
                        wins = int(parts[0])
                        runs = int(parts[3]) if int(parts[3]) > 0 else (sum(int(p) for p in parts))
                        if runs == 0:
                            continue
                        sr = wins / runs
                        if sr >= 0.30:
                            return 8  # proven on this going
                        elif sr >= 0.20:
                            return 7
                        elif sr >= 0.10:
                            return 5
                        elif runs >= 3 and wins == 0:
                            return 2  # many runs, no wins = dislikes this going
                        return 4
                elif isinstance(val, dict):
                    wins = val.get('wins', 0)
                    runs = val.get('runs', 0)
                    if runs > 0:
                        sr = wins / runs
                        if sr >= 0.30:
                            return 8
                        elif sr >= 0.20:
                            return 7
                        elif sr >= 0.10:
                            return 5
                        elif runs >= 3 and wins == 0:
                            return 2
                        return 4
                elif isinstance(val, (int, float)):
                    if val >= 30:
                        return 8
                    elif val >= 20:
                        return 7
                    elif val >= 10:
                        return 5
                    return 3

    return 4  # no record on this going — unknown


def score_course_form(runner_course_record):
    """Score horse's record at this specific course (0-6 points).

    Course specialists are real — some horses love certain tracks.
    Left-handed vs right-handed, tight vs galloping, undulations, etc.

    runner_course_record: dict with 'wins', 'places', 'runs' at this course,
    or a string like "2-1-0-5" (W-2nd-3rd-Runs).
    """
    if not runner_course_record:
        return 3  # no data

    wins = 0
    places = 0
    runs = 0

    if isinstance(runner_course_record, dict):
        wins = runner_course_record.get('wins', 0)
        places = runner_course_record.get('places', 0)
        runs = runner_course_record.get('runs', 0)
    elif isinstance(runner_course_record, str) and '-' in runner_course_record:
        parts = runner_course_record.split('-')
        if len(parts) >= 4:
            wins = int(parts[0])
            places = int(parts[1]) + int(parts[2])
            runs = int(parts[3]) if int(parts[3]) > 0 else sum(int(p) for p in parts)

    if runs == 0:
        return 3  # first time at course — neutral

    if wins >= 2 and runs <= 5:
        return 6  # course specialist
    elif wins >= 1:
        return 5  # course winner
    elif places >= 2:
        return 4  # placed multiple times
    elif places >= 1:
        return 3
    elif runs >= 3 and wins == 0 and places == 0:
        return 1  # proven to dislike this course
    return 2


def score_distance_suitability(runner_dist_record, race_distance_f):
    """Score whether horse is proven at this trip (0-6 points).

    Distance suitability is critical — a sprinter in a staying race will fade,
    a stayer in a sprint won't have the speed.

    runner_dist_record: dict with distance categories and records,
    or a string for wins at this distance.
    """
    if not race_distance_f:
        return 3

    if not runner_dist_record:
        return 3  # no data

    # Categorise race distance
    df = parse_distance_furlongs(race_distance_f)
    if df is None:
        return 3
    if df <= 6:
        dist_cat = 'sprint'
    elif df <= 8:
        dist_cat = 'sprint_mile'
    elif df <= 10:
        dist_cat = 'mile'
    elif df <= 14:
        dist_cat = 'middle'
    elif df <= 20:
        dist_cat = 'staying'
    else:
        dist_cat = 'extreme'

    if isinstance(runner_dist_record, dict):
        # Look for record at this distance category
        for key, val in runner_dist_record.items():
            if dist_cat in key.lower().replace(' ', '_'):
                if isinstance(val, str) and '-' in val:
                    parts = val.split('-')
                    if len(parts) >= 4:
                        wins = int(parts[0])
                        runs = int(parts[3]) if int(parts[3]) > 0 else sum(int(p) for p in parts)
                        if runs == 0:
                            continue
                        sr = wins / runs
                        if sr >= 0.25:
                            return 6
                        elif sr >= 0.15:
                            return 5
                        elif sr >= 0.05:
                            return 3
                        elif runs >= 3 and wins == 0:
                            return 1  # can't win at this trip
                        return 3
                elif isinstance(val, dict):
                    wins = val.get('wins', 0)
                    runs = val.get('runs', 0)
                    if runs > 0:
                        sr = wins / runs
                        if sr >= 0.25:
                            return 6
                        elif sr >= 0.15:
                            return 5
                        elif sr >= 0.05:
                            return 3
                        elif runs >= 3 and wins == 0:
                            return 1
                        return 3
                elif isinstance(val, (int, float)):
                    return 6 if val >= 1 else 3

    return 3  # no specific distance data


def calculate_composite_score(runner, race_data, all_runners, custom_weights=None):
    """Calculate composite score for a runner. If custom_weights provided, caps each
    factor at the custom weight instead of default max."""
    form_positions = parse_form(runner.get('form', ''))

    # Collect field ratings for comparison
    field_ratings = [r.get('rpr') or r.get('ofr') or 0 for r in all_runners if (r.get('rpr') or r.get('ofr'))]
    field_weights = [r.get('lbs') or 0 for r in all_runners if r.get('lbs')]

    scores = {
        'form': score_form(form_positions, race_data.get('field_size')),
        'rating': score_rating(runner.get('rpr'), runner.get('ofr'), runner.get('ts'), field_ratings),
        'trainer': score_trainer(runner.get('trainer', '')),
        'trainer_rtf': score_trainer_rtf(runner.get('trainer_rtf')),
        'jockey': score_jockey(runner.get('jockey', '')),
        'fitness': score_fitness(runner.get('last_run')),
        'class': score_class_change(race_data.get('race_class'), runner.get('ofr'), field_ratings),
        'going': score_going_preference(runner.get('going_record'), race_data.get('going', '')),
        'course': score_course_form(runner.get('course_record')),
        'distance': score_distance_suitability(runner.get('distance_record'), race_data.get('distance_f')),
        'age': score_age(runner.get('age'), race_data.get('race_type', ''), race_data.get('distance_f')),
        'weight': score_weight(runner.get('lbs'), field_weights, race_data.get('race_type', ''),
                               race_data.get('handicap', False), runner.get('age')),
        'draw': score_draw(runner.get('draw'), race_data.get('field_size'), race_data.get('course', '')),
        'headgear': score_headgear(runner.get('headgear'), runner.get('headgear_first')),
        'spotlight': score_spotlight(runner.get('spotlight', '')),
    }

    # Trainer RTF bonus (add to trainer score)
    trainer_cap = custom_weights.get('trainer', 12) if custom_weights else 12
    scores['trainer'] = min(scores['trainer'] + scores.pop('trainer_rtf'), trainer_cap)

    # Apply custom weights if provided (cap each factor at its calibrated weight)
    if custom_weights:
        for f in scores:
            scores[f] = min(scores[f], custom_weights.get(f, 99))
        max_possible = sum(custom_weights.get(f, 0) for f in scores)
    else:
        max_possible = 118

    total = sum(scores.values())

    return {
        'total': total,
        'breakdown': scores,
        'max_possible': max_possible
    }


def calculate_placement_probability(score, top_n, field_size, max_score=118):
    """Estimate probability of finishing in Top N based on score and field size.

    Uses a calibrated model with dampened skill factor to prevent inflated probs.
    Benchmarks (9-runner field):
    - TOP PICK (75%+): ~25-35% win, ~55-70% top 3
    - STRONG (60%):    ~18-22% win, ~45-55% top 3
    - SOLID (50%):     ~14-18% win, ~35-45% top 3
    """
    if not field_size or field_size == 0:
        field_size = 12

    norm = min(score / max_score, 1.0) if max_score > 0 else 0
    baseline = min(top_n / field_size, 1.0)
    skill = norm ** 2.0
    prob = baseline + skill * (1 - baseline) * 0.75

    return min(max(round(prob * 100), 5), 95)


def _top_n_list(field_size):
    """Generate appropriate Top N positions based on actual field size.
    E.g. 6-runner race → [1,2,3,4,5,6], 12-runner → [1,2,3,4,5,6,8,10,12]"""
    fs = field_size or 12
    positions = list(range(1, min(fs + 1, 7)))  # Always 1 through min(fs, 6)
    if fs > 6 and fs <= 10:
        positions.append(fs)
    elif fs > 10:
        positions.append(8)
        positions.append(10)
        if fs > 10:
            positions.append(fs)
    return sorted(set(positions))


def get_confidence_label(score, max_score=118):
    """Get confidence label based on composite score as percentage of max."""
    pct = (score / max_score) * 100 if max_score > 0 else 0
    if pct >= 64:
        return "TOP PICK"
    elif pct >= 55:
        return "STRONG"
    elif pct >= 47:
        return "SOLID"
    elif pct >= 38:
        return "MODERATE"
    elif pct >= 30:
        return "WEAK"
    return "AVOID"


def process_rpscrape_data(json_path, target_date):
    """Read rpscrape JSON output and process into our format."""
    with open(json_path, 'r') as f:
        data = json.load(f)

    output = {
        'date': target_date,
        'generated_at': datetime.datetime.now().isoformat(),
        'venues': {}
    }

    # rpscrape organizes by region > course > time
    for region, courses in data.items():
        for course_name, races in courses.items():
            venue_key = course_name.lower().replace(' ', '_')

            venue_races = []
            for time_str, race_data in sorted(races.items()):
                runners_data = race_data.get('runners', [])

                # Calculate scores for all runners
                field_size = race_data.get('field_size', len(runners_data))
                scored_runners = []
                for runner in runners_data:
                    if runner.get('non_runner', False):
                        continue

                    score_data = calculate_composite_score(runner, race_data, runners_data)

                    scored_runner = {
                        'name': runner.get('name', 'Unknown'),
                        'number': runner.get('number'),
                        'draw': runner.get('draw'),
                        'age': runner.get('age'),
                        'form': runner.get('form', ''),
                        'rpr': runner.get('rpr'),
                        'ts': runner.get('ts'),
                        'ofr': runner.get('ofr'),
                        'last_run': runner.get('last_run'),
                        'lbs': runner.get('lbs'),
                        'trainer': runner.get('trainer', ''),
                        'trainer_rtf': runner.get('trainer_rtf', ''),
                        'jockey': runner.get('jockey', ''),
                        'jockey_allowance': runner.get('jockey_allowance'),
                        'headgear': runner.get('headgear'),
                        'headgear_first': runner.get('headgear_first', False),
                        'spotlight': runner.get('spotlight', ''),
                        'comment': runner.get('comment', ''),
                        'silk_url': runner.get('silk_url', ''),
                        'owner': runner.get('owner', ''),
                        'score': score_data['total'],
                        'score_breakdown': score_data['breakdown'],
                        'confidence': get_confidence_label(score_data['total']),
                        'probs': {
                            f'top_{n}': calculate_placement_probability(
                                score_data['total'], n, field_size
                            )
                            for n in _top_n_list(field_size)
                        }
                    }
                    scored_runners.append(scored_runner)

                # Sort by score descending
                scored_runners.sort(key=lambda x: x['score'], reverse=True)

                race_info = {
                    'time': time_str,
                    'name': race_data.get('race_name', ''),
                    'course': course_name,
                    'distance': race_data.get('distance', ''),
                    'distance_f': race_data.get('distance_f'),
                    'going': race_data.get('going', ''),
                    'race_class': race_data.get('race_class'),
                    'race_type': race_data.get('race_type', ''),
                    'pattern': race_data.get('pattern', ''),
                    'handicap': race_data.get('handicap', False),
                    'field_size': race_data.get('field_size', len(scored_runners)),
                    'prize': race_data.get('prize', ''),
                    'age_band': race_data.get('age_band', ''),
                    'surface': race_data.get('surface', ''),
                    'runners': scored_runners,
                }
                venue_races.append(race_info)

            if venue_races:
                output['venues'][course_name] = {
                    'course': course_name,
                    'races': sorted(venue_races, key=lambda x: x['time']),
                    'race_count': len(venue_races),
                }

    return output


def run_rpscrape(target_date):
    """Run rpscrape to fetch racecards."""
    scripts_dir = os.path.join(RPSCRAPE_DIR, 'scripts')
    racecards_dir = os.path.join(RPSCRAPE_DIR, 'racecards')

    if not os.path.exists(scripts_dir):
        print(f"Error: rpscrape not found at {RPSCRAPE_DIR}")
        print("Please clone rpscrape: git clone https://github.com/joenano/rpscrape.git")
        sys.exit(1)

    # rpscrape uses --day 1 for today, --day 2 for tomorrow
    today = datetime.date.today()
    target = datetime.date.fromisoformat(target_date)
    day_offset = (target - today).days + 1

    if day_offset < 1 or day_offset > 2:
        print(f"Warning: rpscrape only supports today and tomorrow. Requested date {target_date} is {day_offset-1} days away.")
        print("Attempting to fetch anyway...")
        day_offset = max(1, min(day_offset, 2))

    print(f"Fetching racecards for {target_date} (day offset: {day_offset})...")

    try:
        result = subprocess.run(
            [sys.executable, 'racecards.py', '--day', str(day_offset)],
            cwd=scripts_dir,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode != 0:
            print(f"rpscrape stderr: {result.stderr}")
            # Don't exit - try to use existing data
    except subprocess.TimeoutExpired:
        print("rpscrape timed out after 5 minutes")
    except FileNotFoundError:
        print("Python not found or rpscrape not installed correctly")

    # Check for output
    json_path = os.path.join(racecards_dir, f'{target_date}.json')
    return json_path if os.path.exists(json_path) else None


def create_sample_data(target_date):
    """Create sample data structure for testing when rpscrape isn't available."""
    return {
        'date': target_date,
        'generated_at': datetime.datetime.now().isoformat(),
        'venues': {},
        'status': 'no_data',
        'message': f'No race data available for {target_date}. This could mean: (1) No racing scheduled, (2) rpscrape needs Racing Post auth tokens, or (3) network issue. You can manually add data via the dashboard.'
    }


def main():
    parser = argparse.ArgumentParser(description='Fetch and analyze daily horse racing data')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)', default=None)
    parser.add_argument('--tomorrow', action='store_true', help='Fetch tomorrow\'s races')
    parser.add_argument('--input', type=str, help='Use existing rpscrape JSON file instead of fetching')
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    elif args.tomorrow:
        target_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    else:
        target_date = datetime.date.today().isoformat()

    print(f"Target date: {target_date}")

    if args.input and os.path.exists(args.input):
        json_path = args.input
    else:
        json_path = run_rpscrape(target_date)

    if json_path and os.path.exists(json_path):
        print(f"Processing: {json_path}")
        output = process_rpscrape_data(json_path, target_date)

        venue_count = len(output['venues'])
        horse_count = sum(
            len(r['runners'])
            for v in output['venues'].values()
            for r in v['races']
        )
        print(f"Found {venue_count} venues, {horse_count} horses")
    else:
        print("No rpscrape data available, creating empty structure")
        output = create_sample_data(target_date)

    # Save output
    output_path = os.path.join(OUTPUT_DIR, 'daily_race_data.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Output saved to: {output_path}")

    # Also save dated copy into race_data subfolder
    race_data_dir = os.path.join(OUTPUT_DIR, 'race_data')
    os.makedirs(race_data_dir, exist_ok=True)
    dated_path = os.path.join(race_data_dir, f'race_data_{target_date}.json')
    with open(dated_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Dated copy: {dated_path}")
    return output


if __name__ == '__main__':
    main()
