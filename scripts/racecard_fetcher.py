#!/usr/bin/env python3
"""
Direct Racing Post racecard fetcher (Python 3.8+ compatible).
Extracts the same data as rpscrape but without the 3.13 requirement.
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


class RacecardLinkParser(HTMLParser):
    """Parse racecard page for race links."""
    def __init__(self):
        super().__init__()
        self.race_links = []
        self.current_course = None
        self.in_course_name = False
        self._data_buf = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get('class', '')

        if 'RC-accordion__courseName' in cls:
            self.in_course_name = True
            self._data_buf = []

        if tag == 'a' and 'RC-meetingItem__link' in cls:
            href = attrs_dict.get('href', '')
            race_id = attrs_dict.get('data-race-id', '')
            if href and race_id:
                self.race_links.append({
                    'race_id': race_id,
                    'href': href,
                    'course': self.current_course or ''
                })

    def handle_data(self, data):
        if self.in_course_name:
            self._data_buf.append(data.strip())

    def handle_endtag(self, tag):
        if self.in_course_name and tag == 'span':
            self.current_course = ' '.join(self._data_buf).strip()
            self.in_course_name = False


def fetch_url(url, headers=None):
    """Fetch URL with retry."""
    if headers is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Cache-Control': 'no-cache',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }

    import time as _time
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode('utf-8', errors='replace'), resp.status
        except urllib.error.HTTPError as e:
            if e.code == 406:
                # Try with full browser-like headers on retry (keep original Referer/Accept if json-ish)
                fallback_headers = dict(headers)
                fallback_headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
                fallback_headers.setdefault('Accept-Language', 'en-GB,en-US;q=0.9,en;q=0.8')
                fallback_headers.setdefault('Accept-Encoding', 'identity')
                req = urllib.request.Request(url, headers=fallback_headers)
            if attempt == 2:
                print(f"Failed to fetch {url}: {e}")
                return None, 0
            _time.sleep(1)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                print(f"Failed to fetch {url}: {e}")
                return None, 0
            _time.sleep(1)
    return None, 0


def _french_from_day_index(data, date_str, seen_ids):
    """French meetings (display only) that RP leaves out of raceCards.meetings.

    raceCards.meetings only carries UK/IRE + the internationals RP chooses to feature
    (e.g. Longchamp on Arc weekend). Everyday French cards (Auteuil, Chantilly, ...) sit in
    initialState.meetings.byDate, which RP fills for the CURRENT day only — so this adds
    them when fetching today, and adds nothing for tomorrow/day-after fetches.
    Race URL = /racecards/{meetingId}/{courseKey}/{date}/{raceId} (meetingId is the course id).
    """
    try:
        by_id = data['props']['pageProps']['initialState']['meetings']['byDate'][date_str]['meetings']['byMeetingId']
    except (KeyError, TypeError):
        return []
    links = []
    for m in by_id.values():
        if m.get('countryCode') != 'FR' or m.get('isMeetingAbandoned'):
            continue
        course = f"{(m.get('name') or '').upper()} (FR)"
        for rid in m.get('raceIds') or []:
            if str(rid) in seen_ids:
                continue
            links.append({
                'race_id': str(rid),
                'href': f"/racecards/{m.get('meetingId')}/{m.get('courseKey')}/{date_str}/{rid}",
                'course': course,
            })
    if links:
        print(f"  + {len(links)} French races from RP's day index (display only)")
    return links


def get_race_urls(date_str):
    """Get all race URLs for a given date."""
    url = f'https://www.racingpost.com/racecards/{date_str}'
    content, status = fetch_url(url)

    if not content or status != 200:
        print(f"Failed to fetch racecard index for {date_str} (status: {status})")
        return []

    # Try Next.js __NEXT_DATA__ format (current)
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            meetings = data['props']['pageProps']['initialState']['raceCards']['meetings']
            race_links = []
            for meeting in meetings:
                course = meeting.get('courseName') or meeting.get('name', '')
                for race in meeting.get('races', []):
                    race_id = race.get('raceId')
                    race_url = race.get('raceUrl', '')
                    if race_id and race_url:
                        race_links.append({
                            'race_id': str(race_id),
                            'href': race_url,
                            'course': course,
                        })
            race_links += _french_from_day_index(data, date_str, {l['race_id'] for l in race_links})
            if race_links:
                return race_links
        except (KeyError, TypeError, json.JSONDecodeError):
            pass

    # Fallback: old HTML parser
    parser = RacecardLinkParser()
    parser.feed(content)
    return parser.race_links


def parse_racepage_runners(html_content):
    """Parse runners embedded in the racecard page's __NEXT_DATA__.

    Racing Post retired the standalone /profile/horse/data/cardrunners/{id}.json
    endpoint (now 404s) — runners are server-rendered directly into the page's
    initialState.racePage.data.runners instead.
    """
    runners = []
    nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_content, re.DOTALL)
    if not nd:
        return runners
    try:
        data = json.loads(nd.group(1))
        raw_runners = data['props']['pageProps']['initialState']['racePage']['data']['runners']
    except (KeyError, TypeError, json.JSONDecodeError):
        return runners

    def num_int(val):
        """Numeric fields come back as int, numeric string, or literal '-' placeholder."""
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    for runner in raw_runners:
        figures = runner.get('formFiguresData') or []
        form = ''.join(f.get('figure', '') for f in figures)[::-1]
        colour_sex = (runner.get('colorSex') or '').split()
        colour = colour_sex[0] if colour_sex else ''
        sex_code = colour_sex[1] if len(colour_sex) > 1 else ''
        r = {
            'name': clean_string(runner.get('horseName', '')),
            'horse_id': runner.get('horseId'),
            'number': runner.get('startNumber'),
            'draw': num_int(runner.get('draw')),
            'age': num_int(runner.get('age')),
            'form': form,
            'rpr': num_int(runner.get('rpPostmark')),
            'ts': num_int(runner.get('rpTopspeed')),
            'ofr': num_int(runner.get('officialRatingToday')),
            'last_run': num_int(runner.get('daysSinceLastRun')),
            'jockey': clean_string(runner.get('jockeyName', '')),
            'jockey_id': runner.get('jockeyId'),
            'jockey_allowance': num_int(runner.get('weightAllowanceLbs')),
            'trainer': clean_string(runner.get('trainerName', '')),
            'trainer_id': runner.get('trainerId'),
            'trainer_rtf': runner.get('trainerRtf', ''),
            'lbs': num_int(runner.get('weightCarried')),
            'headgear': runner.get('horseHeadGear'),
            'headgear_first': runner.get('horseHeadGearFirstTime', False),
            'non_runner': runner.get('nonRunner', False),
            'spotlight': runner.get('spotlight', ''),
            'comment': runner.get('diomed', ''),
            'silk_url': runner.get('silkImage', ''),
            'owner': clean_string(runner.get('ownerName', '')),
            'sex_code': sex_code,
            'colour': colour,
            'race_datetime': '',
        }
        runners.append(r)

    return runners


def clean_string(s):
    """Clean up string."""
    if not s:
        return ''
    return re.sub(r'\s+', ' ', s).strip()


def extract_forecast_prices(html_content):
    """Extract forecastOddsValue per horse from __NEXT_DATA__ racePage runners."""
    nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_content, re.DOTALL)
    if not nd:
        return {}
    try:
        data = json.loads(nd.group(1))
        runners = data['props']['pageProps']['initialState']['racePage']['data']['runners']
        prices = {}
        for r in runners:
            name = clean_string(r.get('horseName', ''))
            price = r.get('forecastOddsValue')
            if name and price and float(price) > 1.0:
                prices[name] = round(float(price), 2)
        return prices
    except (KeyError, TypeError, json.JSONDecodeError, ValueError):
        return {}


def extract_race_info(html_content, runners_data):
    """Extract race metadata from HTML."""
    # Try Next.js __NEXT_DATA__ format (current)
    nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_content, re.DOTALL)
    if nd:
        try:
            data = json.loads(nd.group(1))
            race = data['props']['pageProps']['initialState']['racePage']['data']['race']
            race_name = race.get('raceTitle', '') or ''
            race_name_lower = race_name.lower()
            dist_f = race.get('distanceFurlongs') or 0

            if dist_f:
                miles = int(dist_f) // 8
                rem_f = dist_f % 8
                if miles > 0 and rem_f:
                    dist_str = f'{miles}m{int(rem_f)}f'
                elif miles > 0:
                    dist_str = f'{miles}m'
                else:
                    dist_str = f'{int(dist_f)}f'
            else:
                dist_str = ''

            grade_m = re.search(r'(grade|group)\s*(\d|[a-c]|I*)', race_name_lower, re.IGNORECASE)
            if grade_m:
                pattern = f'{grade_m.group(1).title()} {grade_m.group(2)}'
            elif 'listed' in race_name_lower:
                pattern = 'Listed'
            else:
                pattern = ''

            rtc = race.get('raceType', '')
            race_type = {'F': 'Flat', 'X': 'Flat', 'C': 'Chase', 'U': 'Chase',
                         'H': 'Hurdle', 'B': 'NH Flat', 'W': 'NH Flat'}.get(rtc, race.get('raceTypeDesc', ''))

            return {
                'race_name': race_name,
                'distance': dist_str,
                'distance_round': dist_str,
                'going': race.get('going', ''),
                'field_size': race.get('numberOfRunners', 0) or race.get('declaredRunners', 0),
                'prize': '',
                'race_class': race.get('raceClass'),
                'pattern': pattern,
                'race_type': race_type,
                'handicap': race.get('raceHandicapUid') is not None,
                'age_band': race.get('agesAllowed', ''),
                'distance_f': dist_f or None,
                'race_time_iso': race.get('raceTime') or race.get('startDateTime') or '',
            }
        except (KeyError, TypeError, json.JSONDecodeError):
            pass

    # Fallback: old HTML regex approach
    info = {}
    m = re.search(r'RC-header__raceInstanceTitle[^>]*>([^<]+)', html_content)
    info['race_name'] = m.group(1).strip() if m else ''
    m = re.search(r'RC-header__raceDistance[^>]*>([^<]+)', html_content)
    info['distance'] = m.group(1).strip().strip('()') if m else ''
    m = re.search(r'RC-header__raceDistanceRound[^>]*>([^<]+)', html_content)
    info['distance_round'] = m.group(1).strip() if m else info['distance']
    m = re.search(r'Going:\s*([^<]+)', html_content, re.IGNORECASE)
    info['going'] = m.group(1).strip().title() if m else ''
    m = re.search(r'Runners:\s*(\d+)', html_content, re.IGNORECASE)
    info['field_size'] = int(m.group(1)) if m else 0
    m = re.search(r'Winner:\s*([^<]+)', html_content, re.IGNORECASE)
    info['prize'] = m.group(1).strip() if m else ''
    m = re.search(r'Class\s*(\d)', html_content)
    info['race_class'] = int(m.group(1)) if m else None
    race_name_lower = info['race_name'].lower()
    grade_m = re.search(r'(grade|group)\s*(\d|[a-c]|I*)', race_name_lower, re.IGNORECASE)
    if grade_m:
        info['pattern'] = f'{grade_m.group(1).title()} {grade_m.group(2)}'
    elif 'listed' in race_name_lower:
        info['pattern'] = 'Listed'
    else:
        info['pattern'] = ''
    if runners_data:
        first = runners_data[0] if isinstance(runners_data, list) else list(runners_data.values())[0]
        rtc = first.get('raceTypeCode', '')
        info['race_type'] = {'F': 'Flat', 'X': 'Flat', 'C': 'Chase', 'U': 'Chase',
                             'H': 'Hurdle', 'B': 'NH Flat', 'W': 'NH Flat'}.get(rtc, '')
    else:
        info['race_type'] = ''
    info['handicap'] = bool(re.search(r'handicap', race_name_lower))
    m = re.search(r'RC-header__rpAges[^>]*>\(([^)]+)\)', html_content)
    info['age_band'] = m.group(1).split()[0] if m else ''
    m = re.search(r'"distanceFurlongRounded":\s*([\d.]+)', html_content)
    info['distance_f'] = float(m.group(1)) if m else None
    info['race_time_iso'] = ''
    return info


def fetch_racecards(date_str):
    """Fetch all racecards for a given date."""
    print(f"Fetching race URLs for {date_str}...")
    race_links = get_race_urls(date_str)

    if not race_links:
        print("No races found.")
        return {}

    print(f"Found {len(race_links)} races. Fetching details...")

    results = {}  # course -> list of races

    for i, link in enumerate(race_links):
        race_id = link['race_id']
        href = link['href']
        course = link['course']

        print(f"  [{i+1}/{len(race_links)}] {course} - {href.split('/')[-1]}...")

        # Fetch racecard page (runners are embedded in its __NEXT_DATA__ —
        # the old standalone cardrunners.json API is retired/404s now)
        rc_url = f'https://www.racingpost.com{href}'
        rc_content, rc_status = fetch_url(rc_url)

        if not rc_content or rc_status != 200:
            print(f"    Failed racecard page (status: {rc_status})")
            continue

        runners = parse_racepage_runners(rc_content)
        if not runners:
            print(f"    Failed to parse runners from racecard page")
            continue

        race_info = extract_race_info(rc_content, runners)
        forecast_prices = extract_forecast_prices(rc_content)
        for r in runners:
            r['price'] = forecast_prices.get(r['name'])

        # Extract time
        time_str = ''
        race_time_iso = race_info.pop('race_time_iso', '')
        if race_time_iso:
            try:
                dt = datetime.datetime.fromisoformat(race_time_iso.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M')
            except (ValueError, TypeError):
                pass

        if not time_str:
            m = re.search(r'(\d{2}:\d{2})', href)
            time_str = m.group(1) if m else '00:00'

        race_data = {
            'time': time_str,
            'course': course,
            'race_id': race_id,
            **race_info,
            'runners': [r for r in runners if not r.get('non_runner', False)],
        }

        if course not in results:
            results[course] = []
        results[course].append(race_data)

    # 🇫🇷 French meetings RP doesn't carry (it only publishes everyday French cards on the
    # day itself) → PMU's programme, which is out a day ahead. Display only, never breaks the fetch.
    try:
        for course, races in fetch_pmu_french(date_str, results.keys()).items():
            results[course] = races
    except Exception as e:
        print(f"  [PMU] French fallback skipped: {e}")

    return results


# ==================== 🇫🇷 PMU FALLBACK (French cards RP doesn't have yet) ====================
# PMU's public programme feed (online.turfinfo.api.pmu.fr — unofficial, no key) lists French
# meetings a day ahead. Used ONLY for French gallop meetings missing from RP's list; trotting
# is skipped. Runners are mapped to the same fields parse_racepage_runners() returns, so they
# go through the normal scorer. No RPR/TS/OR/trainer RTF/forecast prices from this source, so
# scores lean on form, draw, weight and age — fine because France is display only.
PMU_BASE = 'https://online.turfinfo.api.pmu.fr/rest/client/1/programme'
PMU_GALLOP = {'PLAT': 'Flat', 'HAIE': 'Hurdle', 'STEEPLECHASE': 'Chase', 'CROSS': 'Chase'}
PMU_GOING = {'PSF': 'Standard', 'SEC': 'Firm', 'BON LEGER': 'Good To Firm', 'BON': 'Good',
             'BON SOUPLE': 'Good To Soft', 'SOUPLE': 'Soft', 'TRES SOUPLE': 'Soft',
             'COLLANT': 'Heavy', 'LOURD': 'Heavy', 'TRES LOURD': 'Heavy'}
PMU_COURSE_NAMES = {'PARISLONGCHAMP': 'LONGCHAMP'}


def _pmu_get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _course_key(name):
    """'LONGCHAMP (FR)' / 'PARISLONGCHAMP' / 'Saint-Cloud' → 'LONGCHAMP' / 'SAINTCLOUD' for matching."""
    n = re.sub(r'\(.*?\)', '', name or '').upper()
    n = re.sub(r'[^A-Z]', '', n)
    return PMU_COURSE_NAMES.get(n, n)


def _pmu_form(musique):
    """PMU 'musique' (newest first, '(25)' = season break) → RP-style form, oldest → newest."""
    out = []
    for tok in re.findall(r'\(\d+\)|[0-9A-Z][a-z]', musique or ''):
        if tok.startswith('('):
            out.append('-')
            continue
        c = tok[0]
        out.append(c if c.isdigit() else {'T': 'F', 'A': 'P', 'D': '0'}.get(c, 'U'))
    while out and out[0] == '-':
        out.pop(0)
    return ''.join(reversed(out[:7])).strip('-')


def _pmu_distance(metres):
    f = round((metres or 0) / 201.168 * 2) / 2   # nearest half furlong
    if not f:
        return '', None
    miles, rem = int(f // 8), f % 8
    rem_s = (str(int(rem)) if rem == int(rem) else f'{int(rem)}½') + 'f' if rem else ''
    return (f'{miles}m{rem_s}' if miles else rem_s), f


def _pmu_runner(p):
    age = p.get('age')
    sex = {'MALES': 'c' if (age or 9) <= 4 else 'h', 'FEMELLES': 'f' if (age or 9) <= 4 else 'm',
           'HONGRES': 'g'}.get(p.get('sexe'), '')
    kg = p.get('poidsConditionMonte') or p.get('handicapPoids')   # hectograms, after allowance when given
    blink = p.get('oeilleres') or ''
    return {
        'name': clean_string((p.get('nom') or '').title()),
        'number': p.get('numPmu'),
        'draw': p.get('placeCorde'),
        'age': age,
        'form': _pmu_form(p.get('musique')),
        'rpr': None, 'ts': None, 'ofr': None, 'last_run': None,
        'jockey': clean_string(p.get('driver') or ''),
        'jockey_allowance': None,
        'trainer': clean_string(re.sub(r'\s*\(S\)\s*$', '', p.get('entraineur') or '')),
        'trainer_rtf': '',
        'lbs': round(kg / 10 * 2.20462) if kg else None,
        'headgear': 'b' if blink and blink != 'SANS_OEILLERES' else None,
        'headgear_first': False,
        'non_runner': p.get('statut') != 'PARTANT',
        'spotlight': '', 'comment': '',
        'silk_url': p.get('urlCasaque') or '',
        'owner': clean_string(p.get('proprietaire') or ''),
        'sex_code': sex,
        'colour': {'BAI': 'b', 'BAI F.': 'br', 'ALEZAN': 'ch', 'GRIS': 'gr', 'NOIR': 'bl'}.get(
            ((p.get('robe') or {}).get('libelleCourt') or '').upper(), ''),
        'race_datetime': '',
        'price': None,
    }


def fetch_pmu_french(date_str, have_courses):
    """French gallop meetings from PMU that aren't already in the RP results → {course: [race,…]}."""
    have = {_course_key(c) for c in have_courses if c.upper().endswith('(FR)')}
    d = datetime.date.fromisoformat(date_str)
    prog = _pmu_get(f'{PMU_BASE}/{d:%d%m%Y}')
    out = {}
    for reunion in prog.get('programme', {}).get('reunions', []):
        if (reunion.get('pays') or {}).get('code') != 'FRA':
            continue
        name = (reunion.get('hippodrome') or {}).get('libelleCourt') or ''
        key = _course_key(name)
        if key in have:
            continue   # RP already has this meeting (featured day) — RP data is richer
        course = f"{PMU_COURSE_NAMES.get(key, name.upper())} (FR)"
        for c in reunion.get('courses', []):
            race_type = PMU_GALLOP.get(c.get('discipline'))
            if not race_type:
                continue   # trotting (ATTELE / MONTE) — not scored by Prixm
            r_no, c_no = reunion.get('numOfficiel'), c.get('numOrdre')
            try:
                parts = _pmu_get(f'{PMU_BASE}/{d:%d%m%Y}/R{r_no}/C{c_no}/participants').get('participants', [])
            except Exception as e:
                print(f"    [PMU] {course} C{c_no}: {e}")
                continue
            time.sleep(0.4)
            runners = [_pmu_runner(p) for p in parts]
            runners = [r for r in runners if r['name'] and not r['non_runner']]
            if not runners:
                continue
            dist_str, dist_f = _pmu_distance(c.get('distance'))
            going_raw = ((c.get('penetrometre') or {}).get('intitule') or '').upper()
            going_raw = going_raw.replace('É', 'E').replace('È', 'E')
            cat = c.get('categorieParticularite') or ''
            pattern = {'GROUPE_I': 'Group 1', 'GROUPE_II': 'Group 2', 'GROUPE_III': 'Group 3',
                       'LISTED': 'Listed'}.get(cat, '')
            start = c.get('heureDepart')
            out.setdefault(course, []).append({
                'time': datetime.datetime.fromtimestamp(start / 1000).strftime('%H:%M') if start else '00:00',
                'course': course,
                'race_id': f'pmu-{date_str}-R{r_no}C{c_no}',
                'race_name': (c.get('libelle') or '').title(),
                'distance': dist_str,
                'distance_round': dist_str,
                'going': PMU_GOING.get(going_raw, going_raw.title()),
                'field_size': len(runners),
                'prize': '',
                'race_class': None,
                'pattern': pattern,
                'race_type': race_type,
                'handicap': 'HANDICAP' in cat,
                'age_band': '',
                'distance_f': dist_f,
                'source': 'pmu',
                'runners': runners,
            })
        if course in out:
            print(f"  + {course}: {len(out[course])} races from PMU (RP doesn't have this meeting yet)")
    return out


def probe_availability(date_str):
    """Quick check — probe racecard page and return (race_count, venues_list)."""
    race_links = get_race_urls(date_str)
    courses = sorted(set(r['course'] for r in race_links if r['course']))
    return len(race_links), courses


def tag_one_off_segments(output):
    """Tag each race with region (uk/ire/foreign) + segment using the main engine's own
    rules (results_fetcher.classify_segment / is_ireland / is_excluded) — no copy of the logic."""
    from results_fetcher import classify_segment, is_ireland, is_excluded
    for vname, vdata in output.get('venues', {}).items():
        codes = re.findall(r'\(([A-Z]+)\)', vname)
        if is_ireland(vname):
            region = 'ire'
        elif is_excluded(vname) or any(c not in ('AW', 'GB') for c in codes):
            region = 'foreign'
        else:
            region = 'uk'
        for race in vdata.get('races', []):
            runners = sorted(race.get('runners', []), key=lambda x: x.get('score') or 0, reverse=True)
            top = runners[0].get('score') or 0 if runners else 0
            gap = top - (runners[1].get('score') or 0) if len(runners) > 1 else 0
            going = race.get('going') or ''
            surface = 'aw' if ('standard' in going.lower() or '(AW)' in vname) else 'turf'
            race['one_off_region'] = region
            race['one_off_gap'] = round(gap, 1)
            race['one_off_segment'] = (classify_segment(bool(race.get('handicap')), gap, top, surface, going)
                                       if region == 'uk' else None)


def save_one_off(output, target_date):
    """One-off pathway: write only one_off/race_data_DATE.json (for viewer_one_off.html)."""
    one_off_dir = os.path.join(OUTPUT_DIR, 'one_off')
    os.makedirs(one_off_dir, exist_ok=True)
    tag_one_off_segments(output)
    path = os.path.join(one_off_dir, f'race_data_{target_date}.json')
    with open(path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    # file:// copy for viewer_one_off.html (?date=YYYY-MM-DD) + latest.js (default load)
    for name in (f'race_data_{target_date}.js', 'latest.js'):
        with open(os.path.join(one_off_dir, name), 'w') as f:
            f.write('window._oneOffData=')
            json.dump(output, f, default=str)
            f.write(';')
    total_horses = sum(len(r['runners']) for v in output.get('venues', {}).values() for r in v['races'])
    print(f"\nDone! {len(output.get('venues', {}))} venues, {total_horses} horses scored.")
    print(f"One-off output: {path}")
    print("Main UI files, race_data/ and the qualifying Excel were NOT touched.")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, default=None)
    parser.add_argument('--tomorrow', action='store_true')
    parser.add_argument('--probe', action='store_true', help='Check availability only, no fetch')
    parser.add_argument('--one-off', action='store_true',
                        help='Write only one_off/race_data_DATE.json — never touches the main UI files, race_data/ or the Excel')
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    elif args.tomorrow:
        target_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    else:
        target_date = datetime.date.today().isoformat()

    if args.probe:
        race_count, courses = probe_availability(target_date)
        if race_count > 0:
            print(f"  Date: {target_date}")
            print(f"  Status: AVAILABLE - {race_count} races, {len(courses)} venues")
            for c in courses:
                print(f"    {c}")
        else:
            print(f"  Date: {target_date}")
            print(f"  Status: NOT READY - no races found yet")
            now = datetime.datetime.now()
            if now.hour < 6:
                print(f"  Racecards typically go live after 6 AM.")
        return

    print(f"=== Prixm Racecard Fetcher — {target_date}{' (ONE-OFF)' if args.one_off else ''} ===")

    raw_data = fetch_racecards(target_date)

    if not raw_data:
        print("No race data found. Check if there's racing today.")
        if args.one_off:
            print("One-off: nothing written.")
            return
        output = {
            'date': target_date,
            'generated_at': datetime.datetime.now().isoformat(),
            'venues': {},
            'status': 'no_data',
            'message': f'No races found for {target_date}. This could be a non-racing day or the data source may be unavailable.'
        }
    else:
        # Now import scoring from fetch_daily_races (in engine/ subfolder)
        sys.path.insert(0, os.path.join(OUTPUT_DIR, 'engine'))
        from fetch_daily_races import (
            calculate_composite_score, calculate_placement_probability,
            get_confidence_label
        )

        output = {
            'date': target_date,
            'generated_at': datetime.datetime.now().isoformat(),
            'venues': {}
        }

        for course_name, races in raw_data.items():
            venue_races = []
            for race_data in races:
                runners = race_data.get('runners', [])

                scored_runners = []
                for runner in runners:
                    score_data = calculate_composite_score(runner, race_data, runners)
                    scored_runner = {
                        **runner,
                        'score': score_data['total'],
                        'score_breakdown': score_data['breakdown'],
                        'confidence': get_confidence_label(score_data['total']),
                        'probs': {
                            f'top_{n}': calculate_placement_probability(
                                score_data['total'], n,
                                race_data.get('field_size') or len(runners)
                            )
                            for n in [1, 2, 3, 4, 5, 6, 8, 10]
                        }
                    }
                    # Remove internal fields
                    scored_runner.pop('race_datetime', None)
                    scored_runner.pop('horse_id', None)
                    scored_runner.pop('jockey_id', None)
                    scored_runner.pop('trainer_id', None)
                    scored_runner.pop('non_runner', None)
                    scored_runners.append(scored_runner)

                scored_runners.sort(key=lambda x: x['score'], reverse=True)
                race_data['runners'] = scored_runners
                venue_races.append(race_data)

            venue_races.sort(key=lambda x: x['time'])
            output['venues'][course_name] = {
                'course': course_name,
                'races': venue_races,
                'race_count': len(venue_races)
            }

        # ☘ Emerald: re-score Irish races (Prixm score kept as prixm_score) + Horse × Track
        # cross analysis / pace map on every race (display-only for Prixm races).
        try:
            from emerald_engine import process_card
            process_card(output, date=target_date)
            print("☘ Emerald scoring + 🧭 track-fit analysis applied")
        except Exception as e:
            print(f"  [Emerald] skipped: {e}")

    if args.one_off:
        save_one_off(output, target_date)
        return

    # Save
    out_path = os.path.join(OUTPUT_DIR, 'daily_race_data.json')
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    js_path = os.path.join(OUTPUT_DIR, 'daily_race_data.js')
    with open(js_path, 'w') as f:
        f.write('window._raceDataFile=')
        json.dump(output, f, indent=2, default=str)
        f.write(';')

    race_data_dir = os.path.join(OUTPUT_DIR, 'race_data')
    os.makedirs(race_data_dir, exist_ok=True)
    dated_path = os.path.join(race_data_dir, f'race_data_{target_date}.json')
    with open(dated_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    total_horses = sum(len(r['runners']) for v in output.get('venues', {}).values() for r in v['races'])
    print(f"\nDone! {len(output.get('venues', {}))} venues, {total_horses} horses scored.")
    print(f"Output: {out_path}")

    try:
        from qualifying_exporter import generate_qualifying_excel
        xl_path, n = generate_qualifying_excel(output, target_date, OUTPUT_DIR)
        print(f"Qualifying picks: {n} horse{'s' if n != 1 else ''} -> {xl_path}")
    except Exception as e:
        print(f"Warning: could not generate qualifying Excel: {e}")


if __name__ == '__main__':
    main()
