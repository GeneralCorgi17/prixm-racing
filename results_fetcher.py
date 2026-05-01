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

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG = False

EXCLUDED_VENUES = [
    'happy valley', 'rosehill', 'flemington', 'oaklawn park',
    'gulfstream park', 'meydan', 'sha tin', 'chukyo', 'saint-cloud',
    'bahrain', 'keeneland', 'randwick', 'aqueduct', 'santa anita',
    'turffontein', 'palermo', 'abu dhabi', 'hanshin', 'longchamp',
    'deauville', 'free to air', 'scoop', 'morphettville', 'worldwide stakes', 'dusseldorf', 'chantilly', 'fukushima', 'nakayama',
    'krefeld', 'world pool', 'churchill downs', 'san siro', 'munich'
]


def is_excluded(venue_name):
    v = venue_name.lower().strip()
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
        path = os.path.join(OUTPUT_DIR, filename)
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

        # Convert slug to name: "kempton-aw" -> "Kempton Aw"
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

    # Strategy 2: Broader regex — any /results/ link with a numeric final segment
    for m in re.finditer(r'href="(/results/[^"]*?/(\d{4,}))"', html):
        href = m.group(1)
        race_id = m.group(2)
        # Skip if race_id looks like a year (2024-2030)
        if 2020 <= int(race_id) <= 2030:
            continue
        if race_id in seen_ids:
            continue
        seen_ids.add(race_id)

        # Try to extract course from URL segments
        parts = href.strip('/').split('/')
        course_name = ''
        for p in parts[1:]:  # skip 'results'
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
    Extract finishing positions from an RP race result page.
    Uses data-test-selector attributes which are reliable across RP pages.

    RP structure (multiline, whitespace-heavy):
      <tr class="rp-horseTable__mainRow" data-test-selector="table-row">
        <span class="rp-horseTable__pos__number" data-test-selector="text-horsePosition">
          1<!-- comment --><sup ...>(2)</sup>
        </span>
        ...
        <a class="rp-horseTable__horse__name ..." data-test-selector="link-horseName">
          Golden Prosperity  <svg ...>
        </a>
      </tr>
    """
    results = []

    # Extract all positions via data-test-selector="text-horsePosition"
    positions = []
    for m in re.finditer(
        r'data-test-selector="text-horsePosition"[^>]*>\s*(\w+)',
        html, re.DOTALL
    ):
        positions.append(m.group(1).strip())

    # Extract all horse names via data-test-selector="link-horseName"
    names = []
    for m in re.finditer(
        r'data-test-selector="link-horseName"[^>]*>\s*(.+?)(?:\s*<)',
        html, re.DOTALL
    ):
        name = m.group(1).strip()
        if name:
            names.append(name)

    # Pair them up (positions and names should be in same order)
    if positions and names and len(positions) == len(names):
        for pos_text, name in zip(positions, names):
            is_pu = pos_text.upper() in ('PU', 'P')
            is_f = pos_text.upper() in ('F', 'UR', 'BD', 'SU', 'RR', 'CO', 'RFT')
            results.append({
                'name': clean_name(name),
                'finish_pos': parse_pos_text(pos_text),
                'non_runner': False,
                'pull_out': is_pu
            })
        if results:
            return results

    # Fallback: if counts don't match, try mainRow-based extraction
    for m in re.finditer(
        r'rp-horseTable__mainRow.*?</tr>',
        html, re.DOTALL
    ):
        row = m.group(0)
        pos_m = re.search(r'text-horsePosition"[^>]*>\s*(\w+)', row)
        name_m = re.search(r'link-horseName"[^>]*>\s*(.+?)(?:\s*<)', row, re.DOTALL)
        if pos_m and name_m:
            pos_text = pos_m.group(1).strip()
            name = name_m.group(1).strip()
            is_pu = pos_text.upper() in ('PU', 'P')
            results.append({
                'name': clean_name(name),
                'finish_pos': parse_pos_text(pos_text),
                'non_runner': False,
                'pull_out': is_pu
            })

    # Non-runners: look for nonRunners section
    nr_section = re.search(r'(?:rp-horseTable__nonRunners|nonRunner)(.*?)(?:</div>|</section>)', html, re.DOTALL | re.IGNORECASE)
    if nr_section:
        for nm in re.finditer(r'link-horseName"[^>]*>\s*(.+?)(?:\s*<)', nr_section.group(1), re.DOTALL):
            name = nm.group(1).strip()
            if name:
                results.append({
                    'name': clean_name(name),
                    'finish_pos': None,
                    'non_runner': True,
                    'pull_out': False
                })

    return results


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


def classify_profile(surface, race_type):
    rt = (race_type or '').lower()
    s = (surface or '').lower()
    if s in ('aw', 'all-weather'):
        return 'aw'
    if any(x in rt for x in ['hurdle', 'chase', 'nh flat', 'bumper']):
        return 'nh'
    return 'turf_flat'


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

        matched.append({
            'name': entry['name'],
            'finish_pos': entry['finish_pos'],
            'non_runner': entry.get('non_runner', False),
            'pull_out': entry.get('pull_out', False),
            'jockey': pred.get('jockey', ''),
            'trainer': pred.get('trainer', ''),
            'predicted_score': pred.get('score', 0),
            'predicted_confidence': pred.get('confidence', ''),
            'score_breakdown': pred.get('score_breakdown', {})
        })
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

def main():
    global DEBUG
    import argparse
    parser = argparse.ArgumentParser(description='Fetch race results from Racing Post')
    parser.add_argument('--date', type=str, default=None)
    parser.add_argument('--yesterday', action='store_true')
    parser.add_argument('--debug', action='store_true', help='Save raw HTML for debugging')
    args = parser.parse_args()

    DEBUG = args.debug

    if args.date:
        target_date = args.date
    elif args.yesterday:
        target_date = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    else:
        # Auto-detect: read date from loaded racecard JSON
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

    # Load race JSON
    race_json = load_race_json(target_date)
    if race_json:
        venue_list = [v for v in race_json.get('venues', {}).keys() if not is_excluded(v)]
        print(f"Loaded race data: {len(venue_list)} venues (excl. excluded)")
        for v in venue_list:
            rc = len(race_json['venues'][v].get('races', []))
            print(f"  {v}: {rc} races")
    else:
        print("Warning: No race JSON found. Results saved without predicted scores.")

    # Load history
    history = load_results_history()
    existing_count = len(history['races'])
    print(f"Existing history: {existing_count} races\n")

    # Fetch results index
    index_url = f'https://www.racingpost.com/results/{target_date}'
    print(f"Fetching results index: {index_url}")
    index_html, status = fetch_url(index_url)

    if not index_html or status != 200:
        print(f"Failed to fetch index (status: {status})")
        return

    debug_save('debug_index.html', index_html)

    # Parse index for race links
    race_links = parse_results_index(index_html, target_date)

    if not race_links:
        print("No race links found! Try --debug to save HTML for analysis.")
        return

    # Filter excluded venues
    before = len(race_links)
    race_links = [l for l in race_links if not is_excluded(l.get('course', ''))]
    if before != len(race_links):
        print(f"  Filtered: {before} -> {len(race_links)} (excluded {before - len(race_links)} foreign venues)")

    # Group by course for cleaner output
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

        # Match to JSON venue
        json_venue = None
        json_race = None
        if race_json:
            json_venue = match_venue(course, [v for v in race_json['venues'].keys()
                                               if not is_excluded(v)])

        label = f"[{i+1}/{len(race_links)}] {course}"
        print(f"  {label}... ", end='', flush=True)

        # Fetch individual race result page
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

        # Extract race time from the page
        race_time = extract_race_time_from_html(page_html)

        # Extract results
        result_entries = extract_results_from_page(page_html)

        if not result_entries:
            print(f"no results parsed (time={race_time})")
            no_results += 1
            debug_save(f'debug_no_results_{race_id}.html', page_html)
            continue

        # If no time from page, try matching to JSON by horse names
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

        # If we have time but no json_race yet, try matching
        if not json_race and json_venue and race_json:
            venue_data = race_json['venues'].get(json_venue, {})
            # Try exact time match
            for race in venue_data.get('races', []):
                if race['time'] == race_time:
                    json_race = race
                    break
            # Try horse name overlap if time didn't match
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
                    # Use JSON time for consistency with existing entries
                    race_time = best_match['time']

        venue_key = json_venue or course
        dup_key = target_date + venue_key + race_time
        already = any((r['date'] + r['venue'] + r['time']) == dup_key for r in history['races'])
        if already:
            skipped += 1
            print(f"already logged ({race_time})")
            continue

        # Match results to JSON for predicted scores
        if json_race:
            matched = match_result_to_race(result_entries, json_race)
        else:
            matched = [{
                'name': r['name'], 'finish_pos': r['finish_pos'],
                'non_runner': r.get('non_runner', False),
                'pull_out': r.get('pull_out', False),
                'jockey': '', 'trainer': '', 'predicted_score': 0,
                'predicted_confidence': '', 'score_breakdown': {}
            } for r in result_entries]

        profile = classify_profile(
            json_race.get('surface') if json_race else '',
            json_race.get('race_type') if json_race else ''
        )

        entry = {
            'date': target_date,
            'venue': venue_key,
            'time': race_time,
            'race_name': (json_race or {}).get('name', (json_race or {}).get('race_name', '')),
            'field_size': (json_race or {}).get('field_size', len(result_entries)),
            'going': (json_race or {}).get('going', ''),
            'surface': (json_race or {}).get('surface', ''),
            'race_type': (json_race or {}).get('race_type', ''),
            'profile': profile,
            'results': matched
        }

        # Dedup and add
        history['races'] = [r for r in history['races']
                            if (r['date'] + r['venue'] + r['time']) != dup_key]
        history['races'].append(entry)
        logged += 1
        finishers = len([m for m in matched if m.get('finish_pos')])
        matched_tag = '✓ matched' if json_race else '○ no JSON match'
        print(f"OK {race_time} ({finishers} finishers, {matched_tag})")
        time.sleep(0.3)

    # Summary
    print(f"\n{'='*50}")
    print(f"Logged: {logged} | Already existed: {skipped} | "
          f"Failed: {failed} | No results parsed: {no_results}")
    new_count = len(history['races']) - existing_count
    print(f"Total history: {len(history['races'])} races ({new_count} new)")

    if logged > 0 or existing_count > 0:
        save_results_history(history)
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
