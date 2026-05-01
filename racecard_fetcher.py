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
import urllib.request
import urllib.error
from html.parser import HTMLParser

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


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
                # Try with minimal headers on retry
                fallback_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    'Accept': '*/*',
                    'Accept-Language': 'en-GB,en;q=0.9',
                }
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


def get_race_urls(date_str):
    """Get all race URLs for a given date."""
    url = f'https://www.racingpost.com/racecards/{date_str}'
    content, status = fetch_url(url)

    if not content or status != 200:
        print(f"Failed to fetch racecard index for {date_str} (status: {status})")
        return []

    parser = RacecardLinkParser()
    parser.feed(content)
    return parser.race_links


def parse_runners_json(json_data):
    """Parse runners JSON from Racing Post API."""
    runners = []
    try:
        data = json.loads(json_data)
        runners_map = data.get('runners', {})
        for uid, runner in runners_map.items():
            r = {
                'name': clean_string(runner.get('horseName', '')),
                'horse_id': runner.get('horseUid'),
                'number': runner.get('startNumber'),
                'draw': runner.get('draw'),
                'age': runner.get('horseAge'),
                'form': ''.join(
                    f.get('formFigure', '') for f in (runner.get('figuresCalculated') or [])
                )[::-1] if runner.get('figuresCalculated') else '',
                'rpr': runner.get('rpPostmark') or None,
                'ts': runner.get('rpTopspeed') or None,
                'ofr': runner.get('officialRatingToday') or None,
                'last_run': runner.get('daysSinceLastRun'),
                'jockey': clean_string(runner.get('jockeyName', '')),
                'jockey_id': runner.get('jockeyUid'),
                'jockey_allowance': runner.get('weightAllowanceLbs'),
                'trainer': clean_string(runner.get('trainerStylename', '')),
                'trainer_id': runner.get('trainerId'),
                'trainer_rtf': runner.get('trainerRtf', ''),
                'lbs': runner.get('weightCarriedLbs'),
                'headgear': runner.get('rpHorseHeadGearCode'),
                'headgear_first': runner.get('firstTime', False),
                'non_runner': runner.get('nonRunner', False),
                'spotlight': runner.get('spotlight', ''),
                'comment': runner.get('diomed', ''),
                'silk_url': f'https://www.rp-assets.com/svg/{runner.get("silkImagePath", "")}.svg' if runner.get('silkImagePath') else '',
                'owner': clean_string(runner.get('ownerName', '')),
                'sex_code': runner.get('horseSexCode', ''),
                'colour': runner.get('horseColourCode', ''),
                'race_datetime': runner.get('raceDatetime', ''),
            }
            runners.append(r)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error parsing runners: {e}")

    return runners


def clean_string(s):
    """Clean up string."""
    if not s:
        return ''
    return re.sub(r'\s+', ' ', s).strip()


def extract_race_info(html_content, runners_data):
    """Extract race metadata from HTML."""
    info = {}

    # Race name
    m = re.search(r'RC-header__raceInstanceTitle[^>]*>([^<]+)', html_content)
    info['race_name'] = m.group(1).strip() if m else ''

    # Distance
    m = re.search(r'RC-header__raceDistance[^>]*>([^<]+)', html_content)
    info['distance'] = m.group(1).strip().strip('()') if m else ''
    m = re.search(r'RC-header__raceDistanceRound[^>]*>([^<]+)', html_content)
    info['distance_round'] = m.group(1).strip() if m else info['distance']

    # Going
    m = re.search(r'Going:\s*([^<]+)', html_content, re.IGNORECASE)
    info['going'] = m.group(1).strip().title() if m else ''

    # Runners count
    m = re.search(r'Runners:\s*(\d+)', html_content, re.IGNORECASE)
    info['field_size'] = int(m.group(1)) if m else 0

    # Prize
    m = re.search(r'Winner:\s*([^<]+)', html_content, re.IGNORECASE)
    info['prize'] = m.group(1).strip() if m else ''

    # Class
    m = re.search(r'Class\s*(\d)', html_content)
    info['race_class'] = int(m.group(1)) if m else None

    # Pattern/Grade
    race_name_lower = info['race_name'].lower()
    grade_m = re.search(r'(grade|group)\s*(\d|[a-c]|I*)', race_name_lower, re.IGNORECASE)
    if grade_m:
        info['pattern'] = f'{grade_m.group(1).title()} {grade_m.group(2)}'
    elif 'listed' in race_name_lower:
        info['pattern'] = 'Listed'
    else:
        info['pattern'] = ''

    # Race type from first runner
    if runners_data:
        first = runners_data[0] if isinstance(runners_data, list) else list(runners_data.values())[0]
        rtc = first.get('raceTypeCode', '')
        info['race_type'] = {'F': 'Flat', 'X': 'Flat', 'C': 'Chase', 'U': 'Chase',
                             'H': 'Hurdle', 'B': 'NH Flat', 'W': 'NH Flat'}.get(rtc, '')
    else:
        info['race_type'] = ''

    # Handicap
    info['handicap'] = bool(re.search(r'handicap', race_name_lower)) or info.get('rating_band') is not None

    # Age band
    m = re.search(r'RC-header__rpAges[^>]*>\(([^)]+)\)', html_content)
    info['age_band'] = m.group(1).split()[0] if m else ''

    # Distance in furlongs
    m = re.search(r'"distanceFurlongRounded":\s*([\d.]+)', html_content)
    info['distance_f'] = float(m.group(1)) if m else None

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

        # Fetch racecard page
        rc_url = f'https://www.racingpost.com{href}'
        rc_content, rc_status = fetch_url(rc_url)

        # Fetch runners JSON
        runners_url = f'https://www.racingpost.com/profile/horse/data/cardrunners/{race_id}.json'
        runners_content, runners_status = fetch_url(runners_url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Referer': rc_url,
        })

        if not rc_content or rc_status != 200:
            print(f"    Failed racecard page (status: {rc_status})")
            continue

        if not runners_content or runners_status != 200:
            print(f"    Failed runners JSON (status: {runners_status})")
            continue

        # Parse
        try:
            runners_json = json.loads(runners_content)
        except json.JSONDecodeError:
            print(f"    Invalid JSON for runners")
            continue

        runners = parse_runners_json(runners_content)
        race_info = extract_race_info(rc_content, runners_json.get('runners', {}))

        # Extract time
        time_str = ''
        for r in runners:
            if r.get('race_datetime'):
                try:
                    dt = datetime.datetime.fromisoformat(r['race_datetime'].replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M')
                except (ValueError, TypeError):
                    pass
                break

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

    return results


def probe_availability(date_str):
    """Quick check — probe racecard page and return (race_count, venues_list)."""
    url = f'https://www.racingpost.com/racecards/{date_str}'
    content, status = fetch_url(url)
    if content and status == 200:
        parser = RacecardLinkParser()
        parser.feed(content)
        courses = sorted(set(r['course'] for r in parser.race_links if r['course']))
        return len(parser.race_links), courses
    return 0, []


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, default=None)
    parser.add_argument('--tomorrow', action='store_true')
    parser.add_argument('--probe', action='store_true', help='Check availability only, no fetch')
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

    print(f"=== Prixm Racecard Fetcher — {target_date} ===")

    raw_data = fetch_racecards(target_date)

    if not raw_data:
        print("No race data found. Check if there's racing today.")
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

    # Save
    out_path = os.path.join(OUTPUT_DIR, 'daily_race_data.json')
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    race_data_dir = os.path.join(OUTPUT_DIR, 'race_data')
    os.makedirs(race_data_dir, exist_ok=True)
    dated_path = os.path.join(race_data_dir, f'race_data_{target_date}.json')
    with open(dated_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    total_horses = sum(len(r['runners']) for v in output.get('venues', {}).values() for r in v['races'])
    print(f"\nDone! {len(output.get('venues', {}))} venues, {total_horses} horses scored.")
    print(f"Output: {out_path}")


if __name__ == '__main__':
    main()
