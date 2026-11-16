#!/usr/bin/env python3
"""
🔭 Model — eye-catchers + soft blend (display only, both engines). Added 2026-11-16.

A gradient-boosted model trained on every logged runner (pre-race data only: archived racecards +
results history strictly BEFORE each race) gives each runner a "data chance" (normalised per race).
It never changes the engine: scores, gaps, segments, picks and the Ledger are untouched.

  runner['eye'] = {pm, pr, flag, pos:[[label, lift, n]], neg:[...]}   pm = data chance %, pr = engine-rank chance %
  race['eye_top'] = name of the model's top pick (soft blend — logged next to the engine's top pick)

Eye-catcher (flag) = not the engine's top pick, pm ≥ 15 and pm ≥ 2 × pr.
Walk-forward back-test (2026-11-16, Jun–Nov): 157 flags, 29.9% won, +17.9% ROI at SP but unstable by
month — hit rate proven, profit NOT proven. Model top pick 26.5% vs engine 25.1% (ROI −13.3% vs −15.0%).
No market prices are used as inputs.

CLI:
  python engine/eye_model.py              annotate today's card (daily_race_data.json/.js + dated archive)
  python engine/eye_model.py --log        rebuild eye_log.json/.js (live log from archived cards + results)
  python engine/eye_model.py --backtest   recompute the walk-forward back-test stored in eye_log.json
Needs scikit-learn + numpy; without them everything is skipped quietly.
"""
import collections
import glob
import json
import os
import pickle
import re
import sys
from datetime import date as _date

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
MODEL_CACHE = os.path.join(_HERE, 'eye_model.pkl')          # gitignored
LOG_JSON = os.path.join(_ROOT, 'eye_log.json')
LOG_JS = os.path.join(_ROOT, 'eye_log.js')
FLAG_MIN, FLAG_RATIO = 0.15, 2.0

LABEL = {'class_drop': 'Drops in class', 'quick_7': 'Ran within 7 days', 'trainer_hot': 'Trainer in form (RTF 40%+)', 'won_lto': 'Won last time',
         'placed_lto': 'Placed last time', 'or_up': 'Rating raised 3+', 'course_winner': 'Course winner', 'course_placed2': 'Placed 2+ times here',
         'dist_winner': 'Distance winner', 'going_winner': 'Won on this going', 'top_rpr': 'Top RPR in field', 'top_ts': 'Top Topspeed in field',
         'trainer_course_20': 'Trainer 20%+ at course', 'jockey_course_20': 'Jockey 20%+ at course', 'draw_good': 'Good draw here',
         'lone_speed': 'Lone front-runner', 'fit_suits': 'Track suits', 'hg_first': 'First-time headgear', 'fresh_60p': 'Fresh (60+ days)',
         'close_top': 'Within 3 pts of top score', 'holdup_fast_pace': 'Hold-up horse, strong pace'}
NEGL = {'or_down': 'Rating dropped 3+', 'class_rise': 'Up in class', 'trainer_cold': 'Trainer cold (<15%)', 'draw_bad': 'Poor draw here',
        'fit_unsuited': 'Track unsuited'}


# ── helpers ──────────────────────────────────────────────────────────────────
def _n(s): return re.sub(r'[^a-z0-9]', '', (s or '').lower())
def _vk(v): return re.sub(r'\s*\(.*?\)', '', (v or '')).strip().lower()
def _band(f):
    if not f: return None
    return '5f' if f <= 5.5 else '6f' if f <= 6.5 else '7f' if f <= 7.5 else '1m' if f <= 8.5 else '1m2f+'
def _pl(fs): return 1 if fs <= 4 else 2 if fs <= 7 else 3 if fs <= 15 else 4
def _gcat(g):
    g = (g or '').lower()
    if not g: return None
    if 'standard' in g or 'slow' in g or 'fast' in g: return 'aw'
    if 'heavy' in g: return 'heavy'
    if 'soft' in g and 'good' not in g: return 'soft'
    if 'good to soft' in g or 'yielding' in g: return 'gs'
    if 'firm' in g: return 'gf'
    return 'good'
def _isnh(t): return any(x in (t or '').lower() for x in ('hurdle', 'chase', 'nh flat', 'bumper'))
def _cls(c):
    try: return int(str(c).strip()[0])
    except Exception: return None
def _uk_ire(course):
    """UK/IRE only (no country code, '(AW)' or '(IRE)'); France/abroad are display-only elsewhere."""
    codes = re.findall(r'\(([A-Z]+)\)', course or '')
    return all(c in ('AW', 'IRE') for c in codes)


# ── history index ────────────────────────────────────────────────────────────
class Index:
    def __init__(self, hist):
        self.res = {}
        self.runs = collections.defaultdict(list)
        self.trn = collections.defaultdict(list)
        self.jky = collections.defaultdict(list)
        self.draw = collections.defaultdict(list)
        for r in hist:
            d, tk = r['date'], _vk(r['venue'])
            fs = r.get('field_size') or len([x for x in r.get('results', []) if not x.get('non_runner')])
            self.res[(d, tk, r['time'])] = r
            for x in r.get('results', []):
                if x.get('non_runner'): continue
                pos = x.get('finish_pos')
                self.runs[_n(x['name'])].append(dict(date=d, track=tk, won=pos == 1, placed=bool(pos and pos <= _pl(fs)),
                                                     df=r.get('distance_f'), going=_gcat(r.get('going')), cls=_cls(r.get('race_class')),
                                                     style=x.get('run_style')))
                if x.get('trainer'): self.trn[(_n(x['trainer']), tk)].append((d, pos == 1))
                jk = x.get('jockey') or x.get('jockey_result')
                if jk: self.jky[(_n(jk), tk)].append((d, pos == 1))
                if x.get('draw') and fs >= 6 and _band(r.get('distance_f')):
                    self.draw[(tk, _band(r['distance_f']), min(x['draw'], 16))].append((d, bool(pos and pos <= _pl(fs)), _pl(fs) / fs))
        for v in self.runs.values(): v.sort(key=lambda z: z['date'])

    @staticmethod
    def sr(rows, before, min_n):
        a = [w for dd, w in rows if dd < before]
        return sum(a) / len(a) if len(a) >= min_n else None


def race_rows(d, rc, course, I, or_at, results=None):
    """Feature rows for one race (runners with a score). results = {norm name: result row} or None (today)."""
    tk = _vk(course)
    rs = [x for x in rc.get('runners', []) if not x.get('non_runner') and x.get('score') is not None
          and (results is None or _n(x.get('name')) in results)]
    if len(rs) < 4: return []
    rs = sorted(rs, key=lambda x: -x['score'])
    fs, top = len(rs), rs[0]['score']
    rprs = sorted([x['rpr'] for x in rs if x.get('rpr')], reverse=True)
    tss = sorted([x['ts'] for x in rs if x.get('ts')], reverse=True)
    g, df, cl = _gcat(rc.get('going')), rc.get('distance_f'), _cls(rc.get('race_class'))
    styles = {}
    for x in rs:
        st = [z['style'] for z in I.runs.get(_n(x['name']), []) if z['date'] < d and z.get('style')][-4:]
        styles[_n(x['name'])] = max(set(st), key=st.count) if st else None
    n_fr = sum(1 for s in styles.values() if s == 'FR')
    out = []
    for i, x in enumerate(rs):
        nm = _n(x['name'])
        prior = [z for z in I.runs.get(nm, []) if z['date'] < d]
        last = prior[-1] if prior else None
        F = {'rank2_4': 2 <= i + 1 <= 4, 'rank5p': i + 1 >= 5, 'close_top': i > 0 and top - x['score'] <= 3}
        if x.get('rpr') and rprs: F['top_rpr'] = x['rpr'] == rprs[0]
        if x.get('ts') and tss: F['top_ts'] = x['ts'] == tss[0]
        if x.get('ofr') and last:
            po = or_at.get((last['date'], nm))
            if po: F['or_up'] = x['ofr'] - po >= 3; F['or_down'] = x['ofr'] - po <= -3
        if last:
            F['won_lto'] = last['won']; F['placed_lto'] = last['placed']
            if cl and last['cls']: F['class_drop'] = cl > last['cls']; F['class_rise'] = cl < last['cls']
        F['course_winner'] = any(z['track'] == tk and z['won'] for z in prior)
        F['course_placed2'] = sum(1 for z in prior if z['track'] == tk and z['placed']) >= 2
        if df: F['dist_winner'] = any(z['df'] and abs(z['df'] - df) <= 1 and z['won'] for z in prior)
        if g: F['going_winner'] = any(z['going'] == g and z['won'] for z in prior)
        F['debut_logged'] = not prior
        lr = x.get('last_run')
        if lr is not None: F['fresh_60p'] = lr >= 60; F['quick_7'] = lr <= 7
        try: rtf = float(x.get('trainer_rtf'))
        except Exception: rtf = None
        if rtf is not None: F['trainer_hot'] = rtf >= 40; F['trainer_cold'] = rtf < 15
        if x.get('trainer'):
            s = I.sr(I.trn[(_n(x['trainer']), tk)], d, 10)
            if s is not None: F['trainer_course_20'] = s >= .2
        if x.get('jockey'):
            s = I.sr(I.jky[(_n(x['jockey']), tk)], d, 10)
            if s is not None: F['jockey_course_20'] = s >= .2
        F['hg_first'] = bool(x.get('headgear_first'))
        if x.get('draw') and df and fs >= 6:
            a = [(p, e) for dd, p, e in I.draw[(tk, _band(df), min(x['draw'], 16))] if dd < d]
            if len(a) >= 15:
                diff = (sum(p for p, e in a) - sum(e for p, e in a)) / len(a) * 100
                F['draw_good'] = diff >= 5; F['draw_bad'] = diff <= -5
        st = styles.get(nm)
        if st: F['lone_speed'] = st == 'FR' and n_fr == 1; F['holdup_fast_pace'] = st == 'HU' and n_fr >= 3
        tf = x.get('track_fit')
        if tf: F['fit_suits'] = tf.get('verdict') == 's'; F['fit_unsuited'] = tf.get('verdict') == 'u'
        rr = results.get(nm) if results else None
        out.append(dict(date=d, track=tk, time=rc.get('time'), name=x['name'], rank=i + 1, fs=fs, hcap=bool(rc.get('handicap')),
                        nh=_isnh(rc.get('race_type')), score=x['score'], gap=top - x['score'], F=F, runner=x,
                        won=(rr.get('finish_pos') == 1) if rr else None, sp=rr.get('sp') if rr else None))
    return out


def load_all():
    hist = json.load(open(os.path.join(_ROOT, 'results_history.json'), encoding='utf-8')).get('races', [])
    hist = [r for r in hist if r.get('engine') != 'vanta']   # Vanta (France) stays out of the UK/IRE model
    cards = {}
    for f in sorted(glob.glob(os.path.join(_ROOT, 'race_data', 'race_data_*.json'))):
        try: cards[f[-15:-5]] = json.load(open(f, encoding='utf-8'))
        except Exception: pass
    or_at = {}
    for d, c in cards.items():
        for v in (c.get('venues') or {}).values():
            for rc in v.get('races', []):
                for ru in rc.get('runners', []):
                    if ru.get('ofr'): or_at[(d, _n(ru.get('name')))] = ru['ofr']
    return hist, cards, or_at


def training_rows(I, cards, or_at, before=None):
    rows = []
    for d, c in cards.items():
        if before and d >= before: continue
        for v in (c.get('venues') or {}).values():
            course = v.get('course', '')
            if not _uk_ire(course): continue
            for rc in v.get('races', []):
                res = I.res.get((d, _vk(course), rc.get('time')))
                if not res: continue
                rr = {_n(x['name']): x for x in res.get('results', []) if not x.get('non_runner')}
                rows += race_rows(d, rc, course, I, or_at, rr)
    return rows


# ── model ────────────────────────────────────────────────────────────────────
def _feats(rows): return sorted({f for r in rows for f in r['F']})
def _X(r, feats):
    import numpy as np
    v = [min(r['rank'], 10) == k for k in range(1, 11)] + [r['gap'], np.log(r['fs']), r['hcap'], r['nh'], r['score']]
    for f in feats:
        x = r['F'].get(f); v += [x is True, x is None]
    return v
def _B(r):
    import numpy as np
    return [min(r['rank'], 10) == k for k in range(1, 11)] + [r['gap'], np.log(r['fs']), r['hcap']]


def train(rows):
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    feats = _feats(rows)
    y = [bool(r['won']) for r in rows]
    m1 = HistGradientBoostingClassifier(max_iter=250, learning_rate=.05, max_leaf_nodes=15, min_samples_leaf=80,
                                        l2_regularization=1.0, early_stopping=False, random_state=0).fit(np.array([_X(r, feats) for r in rows], float), y)
    m0 = LogisticRegression(max_iter=2000).fit(np.array([_B(r) for r in rows], float), y)
    # single-signal lift vs engine-rank expectation → "reasons"
    def fb(k): return 0 if k <= 7 else 1 if k <= 11 else 2
    n, w = collections.Counter(), collections.Counter()
    for r in rows: k = (min(r['rank'], 10), fb(r['fs']), r['hcap']); n[k] += 1; w[k] += bool(r['won'])
    lift = {}
    for f in list(LABEL) + list(NEGL):
        s = [r for r in rows if r['F'].get(f) is True]
        if len(s) < 100: continue
        e = sum(w[(min(r['rank'], 10), fb(r['fs']), r['hcap'])] / n[(min(r['rank'], 10), fb(r['fs']), r['hcap'])] for r in s)
        lift[f] = (round(sum(bool(r['won']) for r in s) / e, 2), len(s))
    return {'m1': m1, 'm0': m0, 'feats': feats, 'lift': lift, 'n': len(rows)}


def predict(M, rows):
    """Sets r['pm'], r['pr'] (0–1, normalised within each race)."""
    import numpy as np
    if not rows: return
    p1 = M['m1'].predict_proba(np.array([_X(r, M['feats']) for r in rows], float))[:, 1]
    p0 = M['m0'].predict_proba(np.array([_B(r) for r in rows], float))[:, 1]
    g = collections.defaultdict(list)
    for i, r in enumerate(rows): g[(r['date'], r['track'], r['time'])].append(i)
    for ix in g.values():
        a1, a0 = p1[ix] / p1[ix].sum(), p0[ix] / p0[ix].sum()
        for j, i in enumerate(ix): rows[i]['pm'], rows[i]['pr'] = float(a1[j]), float(a0[j])


def is_flag(r): return r['rank'] > 1 and r['pm'] >= FLAG_MIN and r['pm'] >= FLAG_RATIO * r['pr']


def get_model(hist, cards, or_at, I, today=None):
    """Cached model, retrained only when new results / archived cards appear."""
    key = (len(hist), max((r['date'] for r in hist), default=''), len([d for d in cards if d != today]))
    try:
        with open(MODEL_CACHE, 'rb') as f:
            c = pickle.load(f)
        if c.get('key') == key: return c['M']
    except Exception:
        pass
    M = train(training_rows(I, {d: c for d, c in cards.items() if d != today}, or_at))
    try:
        with open(MODEL_CACHE, 'wb') as f: pickle.dump({'key': key, 'M': M}, f)
    except Exception:
        pass
    return M


def annotate_card(card, date=None, quiet=False):
    """Add runner['eye'] / race['eye_top'] to a racecard dict in place. Never touches scores."""
    try:
        import numpy  # noqa: F401
        import sklearn  # noqa: F401
    except Exception:
        if not quiet: print('  [🔭 Model] skipped: needs scikit-learn (pip install scikit-learn)')
        return card
    date = date or card.get('date')
    hist, cards, or_at = load_all()
    I = Index(hist)
    M = get_model(hist, cards, or_at, I, today=date)
    lift = M['lift']; flags = 0
    for v in (card.get('venues') or {}).values():
        course = v.get('course', '')
        for rc in v.get('races', []):
            for x in rc.get('runners', []): x.pop('eye', None)
            rc.pop('eye_top', None)
            if not _uk_ire(course): continue
            rows = race_rows(date, rc, course, I, or_at)
            if not rows: continue
            predict(M, rows)
            top = max(rows, key=lambda r: r['pm'])
            rc['eye_top'] = top['name']
            for r in rows:
                pos = sorted([(lift[f][0], f) for f, val in r['F'].items() if val is True and f in LABEL and f in lift and lift[f][0] >= 1.12], reverse=True)[:4]
                neg = sorted([(lift[f][0], f) for f, val in r['F'].items() if val is True and f in NEGL and f in lift and lift[f][0] <= .9])[:2]
                fl = is_flag(r); flags += fl
                r['runner']['eye'] = {'pm': round(r['pm'] * 100, 1), 'pr': round(r['pr'] * 100, 1), 'flag': fl,
                                      'pos': [[LABEL[f], l, lift[f][1]] for l, f in pos], 'neg': [[NEGL[f], l, lift[f][1]] for l, f in neg]}
    card['eye_model'] = {'trained_on': M['n'], 'flag_min': FLAG_MIN * 100, 'flag_ratio': FLAG_RATIO}
    if not quiet: print(f'🔭 Model: {flags} eye-catcher(s) (trained on {M["n"]} logged runners)')
    return card


# ── log (live since launch + walk-forward back-test) ─────────────────────────
def _write_log(data):
    with open(LOG_JSON, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)
    with open(LOG_JS, 'w', encoding='utf-8') as f:
        f.write('window._eyeLogFile='); json.dump(data, f, ensure_ascii=False); f.write(';')


def _read_log():
    try: return json.load(open(LOG_JSON, encoding='utf-8'))
    except Exception: return {}


def build_log(quiet=False):
    """Live log: every archived card that carries runner.eye, joined with its results."""
    hist = json.load(open(os.path.join(_ROOT, 'results_history.json'), encoding='utf-8')).get('races', [])
    res = {(r['date'], _vk(r['venue']), r['time']): r for r in hist}
    eyes, tops = [], []
    for f in sorted(glob.glob(os.path.join(_ROOT, 'race_data', 'race_data_*.json'))):
        d = f[-15:-5]
        try: c = json.load(open(f, encoding='utf-8'))
        except Exception: continue
        for v in (c.get('venues') or {}).values():
            course = v.get('course', '')
            for rc in v.get('races', []):
                if not rc.get('eye_top'): continue
                r = res.get((d, _vk(course), rc.get('time')))
                if not r: continue
                rr = {_n(x['name']): x for x in r.get('results', [])}
                rs = sorted([x for x in rc.get('runners', []) if x.get('score') is not None and not x.get('non_runner')], key=lambda x: -x['score'])
                if not rs: continue
                eng = rs[0]
                def outcome(name):
                    x = rr.get(_n(name)) or {}
                    if x.get('non_runner'): return None, None
                    return x.get('finish_pos') == 1, x.get('sp')
                ew, es = outcome(eng['name']); mw, ms = outcome(rc['eye_top'])
                if ew is None or mw is None: continue
                tops.append({'date': d, 'course': course, 'time': rc.get('time'), 'eng': eng['name'], 'mod': rc['eye_top'],
                             'eng_won': ew, 'eng_sp': es, 'mod_won': mw, 'mod_sp': ms, 'differ': _n(eng['name']) != _n(rc['eye_top'])})
                for i, x in enumerate(rs):
                    e = x.get('eye') or {}
                    if not e.get('flag'): continue
                    w, sp = outcome(x['name'])
                    if w is None: continue
                    eyes.append({'date': d, 'course': course, 'time': rc.get('time'), 'name': x['name'], 'rank': i + 1, 'fs': len(rs),
                                 'pm': e.get('pm'), 'pr': e.get('pr'), 'won': w, 'sp': sp})
    data = _read_log()
    data['live'] = {'eye': eyes, 'top': tops, 'since': min([t['date'] for t in tops], default=None)}
    _write_log(data)
    if not quiet: print(f'🔭 Model log: {len(eyes)} live eye-catcher result(s), {len(tops)} races compared')
    return data


def backtest(quiet=False):
    """Walk-forward: each month predicted by a model trained only on earlier months."""
    hist, cards, or_at = load_all()
    I = Index(hist)
    rows = training_rows(I, cards, or_at)
    months = sorted({r['date'][:7] for r in rows})
    eyes, tops = [], []
    for m in months:
        tr = [r for r in rows if r['date'] < m + '-01']; te = [r for r in rows if r['date'][:7] == m]
        if not te or len(tr) < 15000: continue          # ~2.5 months of logged runners minimum
        M = train(tr); predict(M, te)
        g = collections.defaultdict(list)
        for r in te: g[(r['date'], r['track'], r['time'])].append(r)
        for rs in g.values():
            eng = max(rs, key=lambda r: r['score']); mod = max(rs, key=lambda r: r['pm'])
            tops.append({'date': eng['date'], 'eng_won': eng['won'], 'eng_sp': eng['sp'], 'mod_won': mod['won'], 'mod_sp': mod['sp'], 'differ': mod is not eng})
            for r in rs:
                if is_flag(r): eyes.append({'date': r['date'], 'name': r['name'], 'rank': r['rank'], 'fs': r['fs'], 'pm': round(r['pm'] * 100, 1),
                                            'pr': round(r['pr'] * 100, 1), 'won': r['won'], 'sp': r['sp']})
        if not quiet: print(f'  backtest {m}: {sum(1 for e in eyes if e["date"][:7] == m)} flags')
    data = _read_log()
    data['backtest'] = {'eye': eyes, 'top': tops, 'built': _date.today().isoformat(), 'from': min((e['date'] for e in tops), default=None)}
    _write_log(data)
    return data


if __name__ == '__main__':
    if '--backtest' in sys.argv:
        backtest(); build_log()
    elif '--log' in sys.argv:
        build_log()
    else:
        path = os.path.join(_ROOT, 'daily_race_data.json')
        card = json.load(open(path, encoding='utf-8'))
        annotate_card(card)
        with open(path, 'w', encoding='utf-8') as f: json.dump(card, f, indent=2, default=str)
        with open(os.path.join(_ROOT, 'daily_race_data.js'), 'w', encoding='utf-8') as f:
            f.write('window._raceDataFile='); json.dump(card, f, indent=2, default=str); f.write(';')
        dated = os.path.join(_ROOT, 'race_data', f"race_data_{card.get('date')}.json")
        if card.get('date') and os.path.exists(dated):
            with open(dated, 'w', encoding='utf-8') as f: json.dump(card, f, indent=2, default=str)
        print('🔭 Model applied to', path)
