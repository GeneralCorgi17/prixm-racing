#!/usr/bin/env python3
"""
One-time migration: results_history.json → race_data.db

Run once:
    python scripts/migrate_to_sqlite.py

Safe to re-run — uses INSERT OR REPLACE so existing rows are overwritten with
the current JSON values. Does not delete races that exist in DB but not in JSON.
"""

import json
import os
import sys

OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH  = os.path.join(OUTPUT_DIR, 'results_history.json')
DB_PATH    = os.path.join(OUTPUT_DIR, 'race_data.db')

# Re-use server helpers — importing doesn't start the server (guarded by __main__)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_server import get_conn, init_db, upsert_race


def migrate():
    if not os.path.exists(JSON_PATH):
        print(f'ERROR: {JSON_PATH} not found.')
        sys.exit(1)

    print(f'Reading  {JSON_PATH} ...')
    with open(JSON_PATH, encoding='utf-8') as f:
        history = json.load(f)

    races = history.get('races', [])
    print(f'Found {len(races)} races in JSON.')

    conn = get_conn()
    init_db(conn)

    before = conn.execute('SELECT COUNT(*) FROM races').fetchone()[0]
    print(f'DB currently has {before} races.')

    ok = err = 0
    for i, race in enumerate(races, 1):
        try:
            upsert_race(conn, race)
            ok += 1
        except Exception as e:
            print(f'  WARN race {i} ({race.get("date")} {race.get("venue")} {race.get("time")}): {e}')
            err += 1
        if i % 100 == 0:
            print(f'  ... {i}/{len(races)}')

    after = conn.execute('SELECT COUNT(*) FROM races').fetchone()[0]
    conn.close()

    print(f'\nDone. {ok} upserted, {err} errors.')
    print(f'DB now has {after} races.')
    print(f'Database: {DB_PATH}')


if __name__ == '__main__':
    migrate()
