#!/usr/bin/env python3
"""
Prixm local SQLite server.
Serves results_history over HTTP on localhost:7432.
All stdlib — no pip dependencies.

Endpoints:
  GET  /api/health          → {"status":"ok","races":N}
  GET  /api/results         → results_history-format JSON
  POST /api/results         → upsert one race record
  DELETE /api/results/{date}/{venue}/{time}  → remove race
"""

import json
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT       = 7432
_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH    = os.path.join(_ROOT, 'race_data.db')
CALIB_PATH = os.path.join(_ROOT, 'calibrations.json')
_lock      = threading.Lock()


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS races (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            date             TEXT NOT NULL,
            venue            TEXT NOT NULL,
            time             TEXT NOT NULL,
            race_name        TEXT,
            field_size       INTEGER,
            going            TEXT,
            surface          TEXT,
            race_type        TEXT,
            profile          TEXT,
            handicap         INTEGER DEFAULT 0,
            segment          TEXT,
            winner_price     REAL,
            winner_price_raw TEXT,
            UNIQUE(date, venue, time)
        );
        CREATE TABLE IF NOT EXISTS runners (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id              INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
            name                 TEXT,
            finish_pos           INTEGER,
            non_runner           INTEGER DEFAULT 0,
            pull_out             INTEGER DEFAULT 0,
            jockey               TEXT,
            trainer              TEXT,
            predicted_score      REAL,
            predicted_confidence TEXT,
            score_breakdown      TEXT,
            sp                   REAL,
            sp_raw               TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_races_date       ON races(date);
        CREATE INDEX IF NOT EXISTS idx_runners_race_id  ON runners(race_id);
    ''')
    conn.commit()


def races_to_history(conn):
    """Return results_history-compatible dict from SQLite."""
    rows  = conn.execute('SELECT * FROM races ORDER BY date, time').fetchall()
    races = []
    for row in rows:
        race = dict(row)
        race['handicap'] = bool(race['handicap'])
        runners_rows = conn.execute(
            'SELECT * FROM runners WHERE race_id=? ORDER BY predicted_score DESC',
            (race['id'],)
        ).fetchall()
        results = []
        for r in runners_rows:
            rd = dict(r)
            rd['non_runner'] = bool(rd['non_runner'])
            rd['pull_out']   = bool(rd['pull_out'])
            try:
                rd['score_breakdown'] = json.loads(rd['score_breakdown'] or '{}')
            except Exception:
                rd['score_breakdown'] = {}
            del rd['id']
            del rd['race_id']
            results.append(rd)
        race['results'] = results
        del race['id']
        races.append(race)
    return {'version': 1, 'races': races}


def upsert_race(conn, race_data):
    """Insert or replace a race and its runners. Thread-safe."""
    with _lock:
        cur = conn.execute('''
            INSERT INTO races
                (date, venue, time, race_name, field_size, going, surface,
                 race_type, profile, handicap, segment, winner_price, winner_price_raw)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(date, venue, time) DO UPDATE SET
                race_name        = excluded.race_name,
                field_size       = excluded.field_size,
                going            = excluded.going,
                surface          = excluded.surface,
                race_type        = excluded.race_type,
                profile          = excluded.profile,
                handicap         = excluded.handicap,
                segment          = excluded.segment,
                winner_price     = excluded.winner_price,
                winner_price_raw = excluded.winner_price_raw
        ''', (
            race_data.get('date'),  race_data.get('venue'), race_data.get('time'),
            race_data.get('race_name', ''), race_data.get('field_size', 0),
            race_data.get('going', ''),     race_data.get('surface', ''),
            race_data.get('race_type', ''), race_data.get('profile', ''),
            int(bool(race_data.get('handicap', False))),
            race_data.get('segment', ''),
            race_data.get('winner_price'),  race_data.get('winner_price_raw'),
        ))
        # lastrowid is 0 on UPDATE — fetch the real id
        race_id = cur.lastrowid or conn.execute(
            'SELECT id FROM races WHERE date=? AND venue=? AND time=?',
            (race_data['date'], race_data['venue'], race_data['time'])
        ).fetchone()['id']

        conn.execute('DELETE FROM runners WHERE race_id=?', (race_id,))
        for r in race_data.get('results', []):
            conn.execute('''
                INSERT INTO runners
                    (race_id, name, finish_pos, non_runner, pull_out,
                     jockey, trainer, predicted_score, predicted_confidence,
                     score_breakdown, sp, sp_raw)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                race_id,
                r.get('name', ''),          r.get('finish_pos'),
                int(bool(r.get('non_runner', False))),
                int(bool(r.get('pull_out', False))),
                r.get('jockey', ''),         r.get('trainer', ''),
                r.get('predicted_score'),    r.get('predicted_confidence', ''),
                json.dumps(r.get('score_breakdown') or {}),
                r.get('sp'),                 r.get('sp_raw', ''),
            ))
        conn.commit()


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silence default access log
        pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin',  '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _send(self, code, data):
        body = json.dumps(data, separators=(',', ':')).encode()
        self.send_response(code)
        self.send_header('Content-Type',   'application/json')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/health':
            conn  = get_conn()
            count = conn.execute('SELECT COUNT(*) FROM races').fetchone()[0]
            conn.close()
            self._send(200, {'status': 'ok', 'races': count})

        elif self.path.startswith('/api/results'):
            conn = get_conn()
            data = races_to_history(conn)
            conn.close()
            self._send(200, data)

        elif self.path == '/api/calibrations':
            if os.path.exists(CALIB_PATH):
                with open(CALIB_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = []
            self._send(200, data)

        else:
            self._send(404, {'error': 'not found'})

    def do_POST(self):
        if self.path == '/api/results':
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            try:
                race_data = json.loads(body)
                conn = get_conn()
                upsert_race(conn, race_data)
                conn.close()
                self._send(200, {'ok': True})
            except Exception as e:
                self._send(400, {'error': str(e)})

        elif self.path == '/api/calibrations':
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            try:
                calib_data = json.loads(body)
                with _lock:
                    with open(CALIB_PATH, 'w', encoding='utf-8') as f:
                        json.dump(calib_data, f, separators=(',', ':'))
                self._send(200, {'ok': True})
            except Exception as e:
                self._send(400, {'error': str(e)})

        else:
            self._send(404, {'error': 'not found'})

    def do_DELETE(self):
        # /api/results/{date}/{venue}/{time}
        parts = [p for p in self.path.split('/') if p]
        if len(parts) >= 4 and parts[0] == 'api' and parts[1] == 'results':
            date, venue, time_val = parts[2], parts[3], parts[4] if len(parts) > 4 else ''
            conn = get_conn()
            with _lock:
                conn.execute(
                    'DELETE FROM races WHERE date=? AND venue=? AND time=?',
                    (date, venue, time_val)
                )
                conn.commit()
            conn.close()
            self._send(200, {'ok': True})
        else:
            self._send(404, {'error': 'not found'})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    conn = get_conn()
    init_db(conn)
    count = conn.execute('SELECT COUNT(*) FROM races').fetchone()[0]
    conn.close()

    print(f'Prixm DB server  →  http://localhost:{PORT}')
    print(f'Database         →  {DB_PATH}')
    print(f'Races loaded     →  {count}')
    print('Press Ctrl+C to stop.\n')

    server = HTTPServer(('localhost', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Server stopped.')
