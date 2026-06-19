#!/usr/bin/env python3
"""Startup check: report today's qualifying picks from Excel."""

import datetime
import os
import sys

today = datetime.date.today().isoformat()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
xl_path = os.path.join(BASE, 'output', 'qualifying_picks.xlsx')

if not os.path.exists(xl_path):
    print(f"[{today}]  NO EXCEL FILE FOUND — run fetcher first")
    sys.exit(0)

try:
    import openpyxl
    wb = openpyxl.load_workbook(xl_path, data_only=True)
    ws = wb.active
except Exception as e:
    print(f"[{today}]  ERROR reading Excel: {e}")
    sys.exit(0)

picks = []
for row in ws.iter_rows(min_row=5, values_only=True):
    if not row[0]:
        continue
    date_val = str(row[0])[:10]
    if date_val == today:
        picks.append({
            'venue': row[1],
            'time':  row[2],
            'horse': row[3],
            'score': row[4],
            'gap':   row[5],
        })

SEP = "=" * 52
print(SEP)
if picks:
    print(f"  PRIXM  |  {today}  |  {len(picks)} QUALIFIER{'S' if len(picks) > 1 else ''}")
    print(SEP)
    for p in picks:
        print(f"  {p['time']}  {p['venue']:20}  {p['horse']}")
        print(f"           Score: {p['score']}  Gap: {p['gap']}")
else:
    print(f"  PRIXM  |  {today}  |  NO QUALIFIER TODAY")
print(SEP)
