#!/usr/bin/env python3
"""
Racecard fetcher using The Racing API (theracingapi.com).
Requires a subscription — set credentials in config below or via environment variables.
Falls back to Racing Post scraper if API is unavailable.

Usage:
  python racecard_fetcher_api.py              # Today's races
  python racecard_fetcher_api.py --date 2026-04-20
  python racecard_fetcher_api.py --tomorrow
  python racecard_fetcher_api.py --probe      # Check availability only
"""

import datetime
import json
import os
import sys
import urllib.request
import urllib.error
import base64

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== CONFIG ====================
# Option 1: Set credentials here
API_USERNAME = ''
API_PASSWORD = ''
# Option 2: Or use environment variables THE_RACING_API_USER / THE_RACING_API_PASS

API_BASE = 'https://api.theracingapi.com/v1'
# ================================================


def get_credentials():
    user = API_USERNAME or os.environ.get('THE_RACING_API_USER', '')
    pwd = API_PASSWORD or os.environ.get('THE_RACING_API_PASS', '')
    return user, pwd


def api_request(endpoint, params=None):
    """Make authenticated request to The Racing API."""
    user, pwd = get_credentials()
    if not user or not pwd:
        return None, 'NO_CREDENTIALS'

    url = f'{API_BASE}{endpoint}'
    if params:
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'{url}?{query}'

    # HTTP Basic Auth
    auth_str = base64.b64encode(f'{user}:{pwd}'.encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_str}',
        'Accept': 'application/json',
        'User-Agent': 'PrixmAnalyzer/1.0',
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data, 'OK'
    except urllib.error.HTTPError as e:
        return None, f'HTTP_{e.code}'
    except Exception as e:
        return None, str(e)


def fetch_racecards_api(date_str):
    """Fetch racecards from The Racing API."""
    print(f"  Fetching from The Racing API...")

    # Get racecards for the date — UK & Ireland
    data, status = api_request('/racecards', {
        'day': date_str,
        'region': 'gb,ire',
    })

    if status == 'NO_CREDENTIALS':
        print("  No API credentials configured.")
        print("  Set THE_RACING_API_USER and THE_RACING_API_PASS environment variables,")
        print("  or edit racecard_fetcher_api.py and fill in API_USERNAME/API_PASSWORD.")
        return None

    if status != 'OK' or not data:
        print(f"  API returned: {status}")
        return None

    # Parse API response into our standard format
    racecards = data if isinstance(data, list) else data.get('racecards', [])
    if not racecards:
        print("  API returned no racecards.")
        return None

    print(f"  Received {len(racecards)} races from API.")
    return racecards


def transform_api_to_standard(racecards, date_str):
    """Transform The Racing API response to our standard JSON format."""
    # Import scoring engine
    sys.path.insert(0, os.path.join(OUTPUT_DIR, 'engine'))
    from fetch_daily_races import (
        calculate_composite_score, calculate_placement_probability,
        get_confidence_label
    )

    output = {
        'date': date_str,
        'generated_at': datetime.datetime.now().isoformat(),
        'source': 'theracingapi',
        'venues': {}
    }

    for race in racecards:
        course = race.get('course', '') or race.get('course_name', '')
        if not course:
            continue

        time_str = race.get('off_time', '') or race.get('time', '') or '00:00'
        # Normalize time to HH:MM
        if len(time_str) > 5:
            time_str = time_str[:5]

        runners_data = race.get('runners', [])
        if not runners_data:
            continue

        # Build race info
        race_info = {
            'time': time_str,
            'course': course,
            'name': race.get('race_name', '') or race.get('name', ''),
            'distance': race.get('distance', ''),
            'going': race.get('going', ''),
            'race_class': race.get('race_class', ''),
            'field_size': len(runners_data),
            'runners': [],
        }

        # Process runners
        scored_runners = []
        for r in runners_data:
            runner = {
                'name': r.get('horse', '') or r.get('horse_name', ''),
                'number': r.get('number', '') or r.get('cloth_number', ''),
                'draw': r.get('draw', r.get('stall_draw', '')),
                'age': r.get('age', ''),
                'form': r.get('form', ''),
                'rpr': r.get('rpr', r.get('official_rating', '')),
                'ts': r.get('ts', r.get('topspeed', '')),
                'ofr': r.get('ofr', r.get('official_rating', '')),
                'last_run': r.get('last_run', r.get('days_since_ran', '')),
                'lbs': r.get('lbs', r.get('weight_lbs', '')),
                'trainer': r.get('trainer', '') or r.get('trainer_name', ''),
                'trainer_rtf': r.get('trainer_rtf', ''),
                'jockey': r.get('jockey', '') or r.get('jockey_name', ''),
                'jockey_allowance': r.get('jockey_allowance', 0),
                'headgear': r.get('headgear', ''),
                'headgear_first': r.get('headgear_first', False),
                'spotlight': r.get('spotlight', r.get('comment', '')),
                'comment': r.get('comment', r.get('spotlight', '')),
                'silk_url': r.get('silk_url', ''),
                'owner': r.get('owner', '') or r.get('owner_name', ''),
                'non_runner': r.get('non_runner', False),
            }

            # Skip non-runners
            if runner.get('non_runner'):
                continue

            # Score runner using existing engine
            try:
                race_context = {
                    'going': race.get('going', ''),
                    'distance': race.get('distance', ''),
                    'race_class': race.get('race_class', ''),
                    'course': course,
                }
                score_data = calculate_composite_score(runner, race_context, runners_data)
                runner['score'] = score_data['total']
                runner['score_breakdown'] = score_data['breakdown']
                runner['confidence'] = get_confidence_label(score_data['total'])
                probs = calculate_placement_probability(score_data['total'], len(runners_data))
                runner['probs'] = probs
            except Exception as e:
                runner['score'] = 0
                runner['score_breakdown'] = {}
                runner['confidence'] = 'LOW'
                runner['probs'] = {}

            scored_runners.append(runner)

        race_info['runners'] = sorted(scored_runners, key=lambda x: x.get('score', 0), reverse=True)
        race_info['field_size'] = len(scored_runners)

        if course not in output['venues']:
            output['venues'][course] = {
                'course': course,
                'races': [],
                'race_count': 0,
            }
        output['venues'][course]['races'].append(race_info)
        output['venues'][course]['race_count'] = len(output['venues'][course]['races'])

    # Sort races by time within each venue
    for v in output['venues'].values():
        v['races'].sort(key=lambda x: x.get('time', ''))

    return output


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fetch racecards via The Racing API')
    parser.add_argument('--date', type=str, default=None)
    parser.add_argument('--tomorrow', action='store_true')
    parser.add_argument('--probe', action='store_true', help='Check availability only')
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    elif args.tomorrow:
        target_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    else:
        target_date = datetime.date.today().isoformat()

    print(f"=== Prixm Racecard Fetcher (API) — {target_date} ===")

    user, pwd = get_credentials()
    if not user or not pwd:
        print()
        print("  No API credentials found.")
        print("  To use The Racing API, sign up at https://www.theracingapi.com")
        print("  Then either:")
        print("    1. Set environment variables: THE_RACING_API_USER / THE_RACING_API_PASS")
        print("    2. Edit racecard_fetcher_api.py and fill in API_USERNAME / API_PASSWORD")
        print()
        print("  Falling back to Racing Post scraper...")
        print()
        # Fall back to Racing Post scraper
        os.system(f'python "{os.path.join(OUTPUT_DIR, "racecard_fetcher.py")}" --date {target_date}')
        return

    if args.probe:
        print("  Checking API availability...")
        racecards = fetch_racecards_api(target_date)
        if racecards:
            # Count unique courses
            courses = set()
            for r in racecards:
                c = r.get('course', '') or r.get('course_name', '')
                if c:
                    courses.add(c)
            print(f"  Date: {target_date}")
            print(f"  Status: AVAILABLE - {len(racecards)} races, {len(courses)} venues")
            for c in sorted(courses):
                print(f"    {c}")
        else:
            print(f"  Date: {target_date}")
            print(f"  Status: NOT READY - no races returned")
        return

    # Full fetch
    racecards = fetch_racecards_api(target_date)

    if not racecards:
        print("\n  API fetch failed. Falling back to Racing Post scraper...")
        os.system(f'python "{os.path.join(OUTPUT_DIR, "racecard_fetcher.py")}" --date {target_date}')
        return

    output = transform_api_to_standard(racecards, target_date)

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
    venue_count = len(output.get('venues', {}))
    print(f"\n  Done! {venue_count} venues, {total_horses} horses scored.")
    print(f"  Output: {out_path}")


if __name__ == '__main__':
    main()
