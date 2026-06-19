#!/usr/bin/env python3
"""
Racing Post results fetcher.
Scrapes finishing positions from RP results pages and writes them
into results_history.json in the same format the HTML interface uses.

Usage:
    python results_fetcher.py              # fetch results for today
    python results_fetcher.py --date 2026-04-07
    python results_fetcher.py --yesterday
    python results_fetcher.py --debug      # save raw HTML for debugging
"""

import datetime
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from html.parser import HTMLParser

OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEBUG = False

EXCLUDED_VENUES = [
    # Asia / HK / Middle East
    'happy valley', 'sha tin', 'meydan', 'abu dhabi', 'bahrain',
    'hanshin', 'chukyo', 'fukushima', 'nakayama', 'tokyo', 'niigata', 'kyoto',
    # Australasia
    'rosehill', 'flemington', 'morphettville', 'eagle farm', 'doomben',
    'hawkesbury', 'ascot aus', 'gold coast', 'northam', 'scone',
    # South Africa
    'turffontein', 'scottsville', 'greyville',
    # USA / Canada
    'oaklawn park', 'gulfstream park', 'keeneland', 'aqueduct', 'santa anita',
    'belmont park', 'belmont at the big a', 'churchill downs', 'laurel park',
    'lone star park', 'percy warner', 'middleburg', 'great meadow', 'woodbine', 'saratoga',
    'hipodromo',
    # South America
    'cidade jardim', 'monterrico', 'gavea', 'palermo',
    # France
    'saint cloud', 'longchamp', 'deauville', 'chantilly', 'auteuil',
    'compiegne', 'toulouse', 'bordeaux', 'les landes', 'nantes', 'vichy', 'le lion',
    # Germany / Italy
    'san siro', 'munich', 'dusseldorf', 'krefeld', 'hoppegarten', 'dortmund', 'baden baden',
    'cologne', 'koln', 'firenze', 'randwick',
    # Ireland (all)
    'punchestown', 'leopardstown', 'curragh', 'naas', 'cork',
    'killarney', 'gowran park', 'roscommon', 'navan', 'limerick',
    'clonmel', 'wexford', 'tramore', 'kilbeggan', 'ballinrobe', 'sligo',
    'down royal', 'bellewstown', 'downpatrick', 'dundalk', 'tipperary',
    'fairyhouse', 'galway', 'laytown',
    # Meta
    'free to air', 'scoop', 'worldwide stakes', 'world pool',
    # Sweden
    'bro park',
]


def is_excluded(venue_name):
    v = venue_name.lower().strip().replace('-', ' ')
    return any(ex in v for ex in EXCLUDED_VENUES)


def fetch_url(url, headers=None):
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                      'image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Cache-Control': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode('utf-8', errors='replace'), resp.status
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if attempt == 2:
                print(f"  FETCH FAILED {url}: {e}")
                return None, 0
            time.sleep(1)
    return None, 0


def debug_save(filename, content):
    if DEBUG:
        debug_dir = os.path.join(OUTPUT_DIR, 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        path = os.path.join(debug_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  [DEBUG] Saved {path} ({len(content)} chars)")


# ═══════════════════════════════════════════════════════════════
# STEP 1: Parse the results INDEX page to get race links
# ═══════════════════════════════════════════════════════════════

def parse_results_index(html, date_str):
    """
    Parse RP results index page. Extract race links with course names.
    RP URLs follow pattern: /results/{course_id}/{course-slug}/{date}/{race_id}
    """
    race_links = []
    seen_ids = set()

    # Strategy 1: Find all <a> tags linking to individual race results
    # Pattern: href="/results/NUMBER/COURSE-SLUG/DATE/RACE_ID"
    for m in re.finditer(
        r'href="(/results/(\d+)/([^/]+)/[^/]+/(\d+))"',
        html
    ):
        href = m.group(1)
        course_id = m.group(2)
        course_slug = m.group(3)
        race_id = m.group(4)

        if race_id in seen_ids:
            continue
        seen_ids.add(race_id)

        course_name = course_slug.replace('-', ' ').title()

        race_links.append({
            'race_id': race_id,
            'course_id': course_id,
            'href': href,
            'course': course_name,
            'course_slug': course_slug
        })

    if race_links:
        print(f"  Found {len(race_links)} race links (URL pattern)")
        return race_links

    # Strategy 2: Construct URLs from race panel data attributes.
    # RP index page has: data-diffusion-race-id="RACE_ID"
    #                    data-test-selector="race-panel-COURSE_ID-TIME"
    #                    data-diffusion-coursename="VENUE"
    # Winning-times links provide course_id -> slug mapping.
    slug_map = {}
    for m in re.finditer(
        r'href="/results/(\d+)/([^/]+)/' + re.escape(date_str) + r'/winning-times"',
        html
    ):
        slug_map[m.group(1)] = m.group(2)

    for m in re.finditer(
        r'<div[^>]*data-diffusion-coursename="([^"]+)"[^>]*'
        r'data-diffusion-race-id="(\d+)"[^>]*'
        r'data-test-selector="race-panel-(\d+)-[^"]*"',
        html
    ):
        course_name_raw = m.group(1)
        race_id = m.group(2)
        course_id = m.group(3)

        if race_id in seen_ids:
            continue
        seen_ids.add(race_id)

        slug = slug_map.get(course_id, course_name_raw.lower().replace(' ', '-'))
        href = f'/results/{course_id}/{slug}/{date_str}/{race_id}'
        course_name = course_name_raw.title()

        race_links.append({
            'race_id': race_id,
            'course_id': course_id,
            'href': href,
            'course': course_name,
            'course_slug': slug
        })

    if race_links:
        print(f"  Found {len(race_links)} race links (panel data)")
        return race_links

    # Strategy 3: Broader regex — any /results/ link with a numeric final segment
    for m in re.finditer(r'href="(/results/[^"]*?/(\d{4,}))"', html):
        href = m.group(1)
        race_id = m.group(2)
        if 2020 <= int(race_id) <= 2030:
            continue
        if race_id in seen_ids:
            continue
        seen_ids.add(race_id)

        parts = href.strip('/').split('/')
        course_name = ''
        for p in parts[1:]:
            if not p.isdigit() and not re.match(r'\d{4}-\d{2}-\d{2}', p):
                course_name = p.replace('-', ' ').title()
                break

        race_links.append({
            'race_id': race_id,
            'href': href,
            'course': course_name
        })

    print(f"  Found {len(race_links)} race links (broad pattern)")
    return race_links


# ═══════════════════════════════════════════════════════════════
# STEP 2: Parse individual race result pages
# ═══════════════════════════════════════════════════════════════

def extract_race_time_from_html(html):
    """Extract race time (HH:MM, 24-hour) from a result page."""
    # Best source: data-analytics-race-date-time="2026-04-08T13:38:00+01:00"
    m = re.search(r'data-analytics-race-date-time="[^"]*T(\d{2}):(\d{2})', html)
    if m:
        return f'{m.group(1)}:{m.group(2)}'

    # Fallback: data-directive-race-replay-datetime
    m = re.search(r'data-directive-race-replay-datetime="[^"]*T(\d{2}):(\d{2})', html)
    if m:
        return f'{m.group(1)}:{m.group(2)}'

    # Fallback: raceTime class (but this is 12-hour, so try to convert)
    m = re.search(r'raceTime">\s*(\d{1,2}):(\d{2})', html)
    if m:
        h, mn = int(m.group(1)), m.group(2)
        # RP 12-hour times: morning races (before noon) would be <12, afternoon >=1
        # If h <= 12 and it's likely afternoon (most UK racing), add 12
        if h < 10:
            h += 12  # 1:38 → 13:38
        return f'{h}:{mn}'

    return ''


def extract_results_from_page(html):
    """
    Extract finishing positions and extra fields from an RP race result page.
    Primary: per table-row extraction (captures distance_beaten, draw, age, lbs, jockey).
    Fallback: list-based pairing if row extraction yields nothing.
    """
    results = []

    # ── PRIMARY: per-row extraction ─────────────────────────────────────────
    table_rows = re.findall(
        r'data-test-selector="table-row".*?(?=data-test-selector="table-row"|</tbody>)',
        html, re.DOTALL
    )
    for row in table_rows:
        pos_m   = re.search(r'data-test-selector="text-horsePosition"[^>]*>\s*(\w+)', row)
        name_m  = re.search(r'data-test-selector="link-horseName"[^>]*>\s*(.+?)(?:\s*<)', row, re.DOTALL)
        if not pos_m or not name_m:
            continue

        sp_m    = re.search(r'(?:text-winnerOdds|text-horseSp|rp-horseTable__horse__price)"[^>]*>\s*([A-Z0-9]+(?:[./][0-9]+)?[A-Z]?)', row, re.IGNORECASE)
        btn_m   = re.search(r'rp-horseTable__pos__length[^>]*>\s*<span>([^<]+)</span>', row, re.DOTALL)
        draw_m  = re.search(r'pos__draw[^>]*>\s*[^(]*\((\d+)\)', row)
        age_m   = re.search(r'data-test-selector="horse-age"[^>]*>\s*(\d+)', row)
        wt_st_m = re.search(r'horse-weight-st[^>]*>\s*(\d+)', row)
        wt_lb_m = re.search(r'horse-weight-lb[^>]*>.*?(\d+)', row, re.DOTALL)
        jky_m   = re.search(r'data-test-selector="link-jockeyName"[^>]*>\s*(.+?)(?:\s*<)', row, re.DOTALL)

        pos_text = pos_m.group(1).strip()
        sp_raw   = sp_m.group(1).strip() if sp_m else None

        lbs = None
        if wt_st_m and wt_lb_m:
            try:
                lbs = int(wt_st_m.group(1)) * 14 + int(wt_lb_m.group(1))
            except ValueError:
                pass

        results.append({
            'name':             clean_name(name_m.group(1).strip()),
            'finish_pos':       parse_pos_text(pos_text),
            'non_runner':       False,
            'pull_out':         pos_text.upper() in ('PU', 'P'),
            'sp':               fractional_to_decimal(sp_raw),
            'sp_raw':           sp_raw,
            'distance_beaten':  btn_m.group(1).strip() if btn_m else None,
            'draw':             int(draw_m.group(1)) if draw_m else None,
            'age':              int(age_m.group(1)) if age_m else None,
            'lbs':              lbs,
            'jockey_result':    clean_name(jky_m.group(1).strip()) if jky_m else None,
        })
    if results:
        # Non-runners appended below, then return
        _append_non_runners(html, results)
        return results

    # ── FALLBACK: list-based extraction (no extra fields) ───────────────────
    positions = [m.group(1).strip() for m in re.finditer(
        r'data-test-selector="text-horsePosition"[^>]*>\s*(\w+)', html, re.DOTALL)]
    names = [m.group(1).strip() for m in re.finditer(
        r'data-test-selector="link-horseName"[^>]*>\s*(.+?)(?:\s*<)', html, re.DOTALL) if m.group(1).strip()]
    sps_raw = []
    for sp_pat in [
        r'data-test-selector="text-winnerOdds"[^>]*>\s*([A-Z0-9]+(?:[./][0-9]+)?[A-Z]?)',
        r'data-test-selector="text-horseSp"[^>]*>\s*([A-Z0-9]+(?:[./][0-9]+)?[A-Z]?)',
        r'class="[^"]*rp-horseTable__horse__price[^"]*"[^>]*>\s*([A-Z0-9]+(?:[./][0-9]+)?[A-Z]?)',
    ]:
        found = [m.group(1).strip() for m in re.finditer(sp_pat, html, re.DOTALL | re.IGNORECASE)]
        if found:
            sps_raw = found
            break

    if positions and names and len(positions) == len(names):
        for i, (pos_text, name) in enumerate(zip(positions, names)):
            results.append({
                'name':       clean_name(name),
                'finish_pos': parse_pos_text(pos_text),
                'non_runner': False,
                'pull_out':   pos_text.upper() in ('PU', 'P'),
                'sp':         fractional_to_decimal(sps_raw[i] if i < len(sps_raw) else None),
                'sp_raw':     sps_raw[i] if i < len(sps_raw) else None,
            })
    else:
        for m in re.finditer(r'rp-horseTable__mainRow.*?</tr>', html, re.DOTALL):
            row = m.group(0)
            pos_m  = re.search(r'text-horsePosition"[^>]*>\s*(\w+)', row)
            name_m = re.search(r'link-horseName"[^>]*>\s*(.+?)(?:\s*<)', row, re.DOTALL)
            sp_m   = re.search(r'(?:text-winnerOdds|text-horseSp|rp-horseTable__horse__price)"[^>]*>\s*([A-Z0-9]+(?:[./][0-9]+)?[A-Z]?)', row, re.IGNORECASE)
            if pos_m and name_m:
                pos_text = pos_m.group(1).strip()
                sp_raw = sp_m.group(1).strip() if sp_m else None
                results.append({
                    'name':       clean_name(name_m.group(1).strip()),
                    'finish_pos': parse_pos_text(pos_text),
                    'non_runner': False,
                    'pull_out':   pos_text.upper() in ('PU', 'P'),
                    'sp':         fractional_to_decimal(sp_raw),
                    'sp_raw':     sp_raw,
                })

    _append_non_runners(html, results)
    return results


def _append_non_runners(html, results):
    nr_section = re.search(r'(?:rp-horseTable__nonRunners|nonRunner)(.*?)(?:</div>|</section>)', html, re.DOTALL | re.IGNORECASE)
    if nr_section:
        for nm in re.finditer(r'link-horseName"[^>]*>\s*(.+?)(?:\s*<)', nr_section.group(1), re.DOTALL):
            name = nm.group(1).strip()
            if name:
                results.append({'name': clean_name(name), 'finish_pos': None, 'non_runner': True, 'pull_out': False})


# ═══════════════════════════════════════════════════════════════
# Utility functions
# ═══════════════════════════════════════════════════════════════

def clean_name(name):
    if not name:
        return ''
    name = re.sub(r'\s*\(\w+\)\s*$', '', name)  # Remove trailing (IRE), (FR) etc
    name = re.sub(r'\s*\d+\s*$', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def normalize_name(name):
    return re.sub(r'[^a-z]', '', name.lower())


def parse_pos_text(text):
    if not text:
        return None
    text = text.strip().lower()
    text = re.sub(r'(st|nd|rd|th)$', '', text)
    if any(x in text for x in ['pu', 'f', 'ur', 'bd', 'su', 'rr', 'co', 'rft', 'dsq']):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def classify_segment(is_hcap, gap, top_score, surface, going=''):
    """Classify race into betting segment. Called at log time — never recalculated."""
    if is_hcap:
        return 'handicap'
    if gap >= 18 and top_score >= 74:
        return 'golden'
    if 10 <= gap < 12 and top_score >= 72 and (surface or '').lower() == 'turf':
        return 'silver'
    if 12 <= gap < 18:
        return 'dead_zone'
    if 8 <= gap < 10 and top_score >= 74 and going in ('Good', 'Good To Firm'):
        return 'bronze'
    return 'other'


def classify_profile(surface, race_type):
    rt = (race_type or '').lower()
    s = (surface or '').lower()
    if s in ('aw', 'all-weather'):
        return 'aw'
    if any(x in rt for x in ['hurdle', 'chase', 'nh flat', 'bumper']):
        return 'nh'
    return 'turf_flat'


def fractional_to_decimal(price_str):
    """Convert '11/4' → 3.75, 'EVS' → 2.0, pass-through decimals."""
    if not price_str:
        return None
    s = price_str.strip().upper()
    s = re.sub(r'[FCJ]$', '', s)  # strip fav/co-fav/joint markers
    if s in ('EVS', 'EVENS', 'EV'):
        return 2.0
    if '/' in s:
        try:
            num, den = s.split('/', 1)
            return round(int(num) / int(den) + 1, 2)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        v = float(s)
        return round(v, 2) if v > 0 else None
    except ValueError:
        return None


_AW_SLUGS = {
    'kempton-aw', 'lingfield-aw', 'wolverhampton', 'wolverhampton-aw',
    'chelmsford-city', 'chelmsford-city-aw', 'newcastle-aw',
    'southwell', 'southwell-aw', 'dundalk'
}

_AW_GOING = {'standard', 'standard to slow', 'standard to fast', 'slow', 'fast'}


def detect_surface(html, course_slug='', course_name='', going='', json_race_surface=''):
    """Derive AW vs Turf from RP page HTML, course slug/name, or going string."""
    if json_race_surface:
        return json_race_surface

    # 1. RP page HTML — surface label or going description block
    for pat in [
        r'(?i)"surface"\s*:\s*"([^"]+)"',
        r'(?i)>([Aa]ll.?[Ww]eather|AW|Turf)<',
        r'(?i)surface[^>]*>\s*(All.?Weather|AW|Turf)\b',
    ]:
        m = re.search(pat, html)
        if m:
            val = m.group(1).strip().lower()
            if 'aw' in val or 'all' in val or 'weather' in val:
                return 'AW'
            if 'turf' in val:
                return 'Turf'

    # 2. Course slug contains -aw suffix
    slug = (course_slug or '').lower().strip('/')
    slug_base = slug.split('/')[-1]
    if slug_base in _AW_SLUGS or slug_base.endswith('-aw'):
        return 'AW'

    # 3. Course name contains (AW) or ends with " Aw"
    name = (course_name or '').lower()
    if '(aw)' in name or name.endswith(' aw') or ' aw ' in name:
        return 'AW'

    # 4. Known AW venue substrings in course name
    for aw in ('wolverhampton', 'southwell', 'dundalk', 'chelmsford'):
        if aw in name:
            return 'AW'

    # 5. AW-specific going values (Standard/Slow/Fast are AW-only)
    g = (going or '').lower().strip()
    if g in _AW_GOING:
        return 'AW'

    return 'Turf'


def normalize_venue(venue):
    v = venue.lower().strip()
    v = re.sub(r'\s*\(aw\)\s*', ' ', v)
    v = re.sub(r'[-]', ' ', v)           # treat hyphens as spaces
    v = re.sub(r'\s+', ' ', v).strip()
    return v


def match_venue(rp_course, json_venues):
    """Match RP course name to JSON venue key."""
    rp_norm = normalize_venue(rp_course)
    if not rp_norm:
        return None

    # Exact
    for vk in json_venues:
        if normalize_venue(vk) == rp_norm:
            return vk

    # Substring
    for vk in json_venues:
        vk_norm = normalize_venue(vk)
        if rp_norm in vk_norm or vk_norm in rp_norm:
            return vk

    # Word overlap (need >50% match)
    rp_words = set(rp_norm.split())
    best, best_score = None, 0
    for vk in json_venues:
        vk_words = set(normalize_venue(vk).split())
        overlap = len(rp_words & vk_words)
        if overlap > best_score and overlap >= max(1, len(rp_words) // 2):
            best_score = overlap
            best = vk
    return best


def match_result_to_race(result_entries, race):
    """Match scraped results to race runners, attaching predicted scores."""
    runner_lookup = {}
    for r in race.get('runners', []):
        runner_lookup[normalize_name(r['name'])] = r

    matched = []
    for entry in result_entries:
        norm = normalize_name(entry['name'])
        pred = runner_lookup.get(norm, {})
        if not pred:
            for rn, rv in runner_lookup.items():
                if norm in rn or rn in norm:
                    pred = rv
                    break

        result = {
            'name': entry['name'],
            'finish_pos': entry['finish_pos'],
            'non_runner': entry.get('non_runner', False),
            'pull_out': entry.get('pull_out', False),
            'jockey': pred.get('jockey', '') or entry.get('jockey_result', ''),
            'trainer': pred.get('trainer', ''),
            'predicted_score': pred.get('score', 0),
            'predicted_confidence': pred.get('confidence', ''),
            'score_breakdown': pred.get('score_breakdown', {}),
            'sp': entry.get('sp'),
            'sp_raw': entry.get('sp_raw'),
        }
        if entry.get('distance_beaten') is not None:
            result['distance_beaten'] = entry['distance_beaten']
        if entry.get('draw') is not None:
            result['draw'] = entry['draw']
        if entry.get('age') is not None:
            result['age'] = entry['age']
        if entry.get('lbs') is not None:
            result['lbs'] = entry['lbs']
        matched.append(result)
    return matched


# ═══════════════════════════════════════════════════════════════
# File I/O
# ═══════════════════════════════════════════════════════════════

def load_race_json(date_str):
    dated_path = os.path.join(OUTPUT_DIR, 'race_data', f'race_data_{date_str}.json')
    if os.path.exists(dated_path):
        with open(dated_path, encoding='utf-8') as f:
            return json.load(f)
    daily_path = os.path.join(OUTPUT_DIR, 'daily_race_data.json')
    if os.path.exists(daily_path):
        with open(daily_path, encoding='utf-8') as f:
            data = json.load(f)
            if data.get('date') == date_str:
                return data
    return None


def load_results_history():
    path = os.path.join(OUTPUT_DIR, 'results_history.json')
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if data.get('races') is not None:
                return data
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"Warning: results_history.json corrupt ({e}), starting fresh.")
            backup = path + '.corrupt'
            try:
                os.replace(path, backup)
                print(f"  Backed up to {backup}")
            except Exception:
                pass
    return {
        'version': 1, 'races': [], 'calibrations': [],
        'weight_profiles': {
            'aw': {'form':20,'rating':15,'trainer':12,'jockey':10,'fitness':8,
                   'class':8,'going':8,'course':6,'distance':6,'age':7,
                   'weight':8,'draw':5,'headgear':3,'spotlight':2},
            'turf_flat': {'form':20,'rating':15,'trainer':12,'jockey':10,'fitness':8,
                          'class':8,'going':8,'course':6,'distance':6,'age':7,
                          'weight':8,'draw':5,'headgear':3,'spotlight':2},
            'nh': {'form':20,'rating':15,'trainer':12,'jockey':10,'fitness':8,
                   'class':8,'going':8,'course':6,'distance':6,'age':7,
                   'weight':8,'draw':5,'headgear':3,'spotlight':2}
        }
    }


def _write_to_sqlite(entry):
    """Upsert a single race entry into race_data.db. Non-fatal if DB not available."""
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from db_server import get_conn, init_db, upsert_race
        conn = get_conn()
        init_db(conn)
        upsert_race(conn, entry)
        conn.close()
    except Exception as e:
        print(f'  [SQLite] write skipped: {e}')


def save_results_history(history):
    path = os.path.join(OUTPUT_DIR, 'results_history.json')
    js_path = os.path.join(OUTPUT_DIR, 'results_history.js')
    tmp_path = path + '.tmp'
    tmp_js = js_path + '.tmp'
    try:
        data = json.dumps(history, indent=2, default=str)
        # Write JSON (for fetch-based loading)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        # Write JS file (works on file:// protocol via <script> tag)
        with open(tmp_js, 'w', encoding='utf-8') as f:
            f.write('window._resultsHistoryFile=' + data + ';')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_js, js_path)
        print(f"\nSaved to {path} ({len(history['races'])} races, {len(data)} bytes)")
        print(f"Also saved {js_path} for file:// loading")
    except Exception as e:
        print(f"\nERROR saving: {e}")
        for p in (tmp_path, tmp_js):
            if os.path.exists(p):
                os.remove(p)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def find_dates_missing_sp(history):
    """Return sorted list of dates >= 2026-04-08 where any non-NR runner lacks sp."""
    dates = set()
    today = datetime.date.today().isoformat()
    for race in history.get('races', []):
        d = race.get('date', '')
        if d < '2026-04-08' or d >= today:
            continue
        for r in race.get('results', []):
            if not r.get('non_runner') and 'sp' not in r:
                dates.add(d)
                break
    return sorted(dates)


def _fetch_and_log(target_date, history, force_reprocess=False):
    """Fetch RP results for target_date, log into history (mutated in place).

    force_reprocess=True bypasses the already-logged skip guard so SP data
    can be backfilled for races that were logged before SP scraping existed.
    Returns (logged, skipped, failed, no_results).
    """
    # Load race JSON for predicted score matching
    race_json = load_race_json(target_date)
    if race_json:
        venue_list = [v for v in race_json.get('venues', {}).keys() if not is_excluded(v)]
        print(f"Loaded race data: {len(venue_list)} venues (excl. excluded)")
        for v in venue_list:
            rc = len(race_json['venues'][v].get('races', []))
            print(f"  {v}: {rc} races")
    else:
        print("Warning: No race JSON found. Results saved without predicted scores.")

    # Fetch results index
    index_url = f'https://www.racingpost.com/results/{target_date}'
    print(f"Fetching results index: {index_url}")
    index_html, status = fetch_url(index_url)

    if not index_html or status != 200:
        print(f"Failed to fetch index (status: {status})")
        return 0, 0, 0, 0

    debug_save('debug_index.html', index_html)

    race_links = parse_results_index(index_html, target_date)
    if not race_links:
        print("No race links found! Try --debug to save HTML for analysis.")
        return 0, 0, 0, 0

    before = len(race_links)
    race_links = [l for l in race_links if not is_excluded(l.get('course', ''))]
    if before != len(race_links):
        print(f"  Filtered: {before} -> {len(race_links)} (excluded {before - len(race_links)} foreign venues)")

    by_course = {}
    for l in race_links:
        c = l['course'] or 'Unknown'
        by_course.setdefault(c, []).append(l)
    print(f"\nCourses found: {', '.join(sorted(by_course.keys()))}\n")

    logged = 0
    skipped = 0
    failed = 0
    no_results = 0

    for i, link in enumerate(race_links):
        course = link['course']
        race_id = link.get('race_id', '')

        json_venue = None
        json_race = None
        if race_json:
            json_venue = match_venue(course, [v for v in race_json['venues'].keys()
                                               if not is_excluded(v)])

        label = f"[{i+1}/{len(race_links)}] {course}"
        print(f"  {label}... ", end='', flush=True)

        href = link['href']
        if not href.startswith('http'):
            href = f'https://www.racingpost.com{href}'

        page_html, page_status = fetch_url(href)
        if not page_html or page_status != 200:
            print(f"FETCH FAILED ({page_status})")
            failed += 1
            continue

        if i == 0:
            debug_save('debug_race_result.html', page_html)

        race_time = extract_race_time_from_html(page_html)
        result_entries = extract_results_from_page(page_html)

        if not result_entries:
            print(f"no results parsed (time={race_time})")
            no_results += 1
            debug_save(f'debug_no_results_{race_id}.html', page_html)
            continue

        if not race_time and json_venue and race_json:
            venue_data = race_json['venues'].get(json_venue, {})
            result_names = {normalize_name(r['name']) for r in result_entries if r.get('name')}
            best_match, best_overlap = None, 0
            for race in venue_data.get('races', []):
                race_names = {normalize_name(r['name']) for r in race.get('runners', [])}
                overlap = len(result_names & race_names)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = race
            if best_match and best_overlap >= 2:
                json_race = best_match
                race_time = best_match['time']

        if not race_time:
            print(f"no time found, {len(result_entries)} results parsed but can't match")
            failed += 1
            continue

        if not json_race and json_venue and race_json:
            venue_data = race_json['venues'].get(json_venue, {})
            for race in venue_data.get('races', []):
                if race['time'] == race_time:
                    json_race = race
                    break
            if not json_race:
                result_names = {normalize_name(r['name']) for r in result_entries if r.get('name')}
                best_match, best_overlap = None, 0
                for race in venue_data.get('races', []):
                    race_names = {normalize_name(r['name']) for r in race.get('runners', [])}
                    overlap = len(result_names & race_names)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_match = race
                if best_match and best_overlap >= 2:
                    json_race = best_match
                    race_time = best_match['time']

        venue_key = json_venue or course
        dup_key = target_date + venue_key + race_time
        already = any((r['date'] + r['venue'] + r['time']) == dup_key for r in history['races'])
        if already and not force_reprocess:
            skipped += 1
            print(f"already logged ({race_time})")
            continue

        if json_race:
            matched = match_result_to_race(result_entries, json_race)
        else:
            matched = [{
                'name': r['name'], 'finish_pos': r['finish_pos'],
                'non_runner': r.get('non_runner', False),
                'pull_out': r.get('pull_out', False),
                'jockey': '', 'trainer': '', 'predicted_score': 0,
                'predicted_confidence': '', 'score_breakdown': {},
                'sp': r.get('sp'), 'sp_raw': r.get('sp_raw'),
            } for r in result_entries]

        going_str = (json_race or {}).get('going', '')
        surface = detect_surface(
            page_html,
            course_slug=link.get('course_slug', ''),
            course_name=course,
            going=going_str,
            json_race_surface=(json_race or {}).get('surface', ''),
        )
        profile = classify_profile(surface, (json_race or {}).get('race_type', ''))

        winner = next((m for m in matched if m.get('finish_pos') == 1), None)
        is_hcap = bool((json_race or {}).get('handicap', False))
        scored = sorted(
            [m.get('predicted_score', 0) for m in matched if m.get('predicted_score')],
            reverse=True
        )
        top_score = scored[0] if scored else 0
        gap_val = round(scored[0] - scored[1], 1) if len(scored) >= 2 else 0
        entry = {
            'date': target_date,
            'venue': venue_key,
            'time': race_time,
            'race_name': (json_race or {}).get('name', (json_race or {}).get('race_name', '')),
            'field_size': (json_race or {}).get('field_size', len(result_entries)),
            'going': going_str,
            'surface': surface,
            'race_type': (json_race or {}).get('race_type', ''),
            'profile': profile,
            'handicap': is_hcap,
            'segment': classify_segment(is_hcap, gap_val, top_score, surface, going_str),
            'winner_price': winner.get('sp') if winner else None,
            'winner_price_raw': winner.get('sp_raw') if winner else None,
            'results': matched
        }

        history['races'] = [r for r in history['races']
                            if (r['date'] + r['venue'] + r['time']) != dup_key]
        history['races'].append(entry)
        _write_to_sqlite(entry)
        logged += 1
        finishers = len([m for m in matched if m.get('finish_pos')])
        matched_tag = 'matched' if json_race else 'no JSON match'
        winner_info = ''
        if winner:
            price_str = f" @ {winner['sp']}SP" if winner.get('sp') else ''
            winner_info = f" — {winner['name']}{price_str}"
        print(f"OK {race_time} ({finishers} finishers, {matched_tag}){winner_info}")
        time.sleep(0.3)

    return logged, skipped, failed, no_results


def main():
    global DEBUG
    import sys as _sys
    if hasattr(_sys.stdout, 'reconfigure'):
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    import argparse
    parser = argparse.ArgumentParser(description='Fetch race results from Racing Post')
    parser.add_argument('--date', type=str, default=None)
    parser.add_argument('--yesterday', action='store_true')
    parser.add_argument('--debug', action='store_true', help='Save raw HTML for debugging')
    parser.add_argument('--backfill-sp', action='store_true',
                        help='Re-fetch SP prices for all May 2026+ races missing SP data')
    parser.add_argument('--backfill-surface', action='store_true',
                        help='Patch surface field on all existing records using course name + going (no re-fetch)')
    parser.add_argument('--purge-excluded', action='store_true',
                        help='Remove all races from results_history that match current EXCLUDED_VENUES list')
    args = parser.parse_args()

    DEBUG = args.debug

    # ── Purge excluded venues from history ────────────────────
    if args.purge_excluded:
        history = load_results_history()
        before = len(history['races'])
        history['races'] = [r for r in history['races'] if not is_excluded(r.get('venue', ''))]
        removed = before - len(history['races'])
        print(f"Purge excluded: removed {removed} races ({before} → {len(history['races'])}).")
        save_results_history(history)
        return

    # ── Surface backfill (no network) ─────────────────────────
    if args.backfill_surface:
        history = load_results_history()
        patched = 0
        for race in history.get('races', []):
            old = race.get('surface', '')
            new = detect_surface(
                '',
                course_slug='',
                course_name=race.get('venue', ''),
                going=race.get('going', ''),
                json_race_surface='',
            )
            if old != new:
                race['surface'] = new
                race['profile'] = classify_profile(new, race.get('race_type', ''))
                patched += 1
        print(f"Surface backfill: {patched} races patched.")
        save_results_history(history)
        return

    # ── Backfill mode ──────────────────────────────────────────
    if args.backfill_sp:
        history = load_results_history()
        dates = find_dates_missing_sp(history)
        if not dates:
            print("No dates need SP backfill. All May 2026+ races have SP data.")
            return
        print(f"=== SP Price Backfill — {len(dates)} date(s) ===\n")
        print(f"Dates: {', '.join(dates)}\n")
        total_logged = 0
        for date_str in dates:
            print(f"\n{'='*50}")
            print(f"  {date_str}")
            print(f"{'='*50}")
            logged, skipped, failed, no_results = _fetch_and_log(date_str, history, force_reprocess=True)
            total_logged += logged
            print(f"  -> {logged} updated | {failed} failed")
        save_results_history(history)
        print(f"\n{'='*50}")
        print(f"SP backfill complete. {total_logged} races updated across {len(dates)} date(s).")
        try:
            from qualifying_exporter import rebuild_qualifying_excel
            xl_path, total, resolved = rebuild_qualifying_excel(OUTPUT_DIR)
            print(f"Qualifying picks updated: {resolved}/{total} results resolved -> {xl_path}")
        except Exception as e:
            print(f"Warning: could not update qualifying Excel: {e}")
        return

    # ── Normal mode ────────────────────────────────────────────
    if args.date:
        target_date = args.date
    elif args.yesterday:
        target_date = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    else:
        target_date = None
        daily_path = os.path.join(OUTPUT_DIR, 'daily_race_data.json')
        if os.path.exists(daily_path):
            try:
                with open(daily_path, encoding='utf-8') as f:
                    data = json.load(f)
                rc_date = data.get('date')
                if rc_date:
                    target_date = rc_date
                    print(f"Auto-detected racecard date: {target_date}")
            except Exception:
                pass
        if not target_date:
            target_date = datetime.date.today().isoformat()
            print(f"No racecard found, defaulting to today: {target_date}")

    print(f"=== Results Fetcher — {target_date} ===\n")

    history = load_results_history()
    existing_count = len(history['races'])
    print(f"Existing history: {existing_count} races\n")

    logged, skipped, failed, no_results = _fetch_and_log(target_date, history)

    print(f"\n{'='*50}")
    print(f"Logged: {logged} | Already existed: {skipped} | "
          f"Failed: {failed} | No results parsed: {no_results}")
    new_count = len(history['races']) - existing_count
    print(f"Total history: {len(history['races'])} races ({new_count} new)")

    if logged > 0 or existing_count > 0:
        save_results_history(history)
        try:
            from qualifying_exporter import rebuild_qualifying_excel
            xl_path, total, resolved = rebuild_qualifying_excel(OUTPUT_DIR)
            print(f"Qualifying picks updated: {resolved}/{total} results logged -> {xl_path}")
        except Exception as e:
            print(f"Warning: could not update qualifying Excel: {e}")
    else:
        print("\nNothing to save.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n!!! CRASH: {e}")
        import traceback
        traceback.print_exc()
    print()
    input("Press Enter to close...")
