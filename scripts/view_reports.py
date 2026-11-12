#!/usr/bin/env python3
"""Show recent "Not working" reports from the SipSpot API (owner only).

Usage:
  python3 scripts/view_reports.py            # last 30 days
  python3 scripts/view_reports.py --days 7 --open
  python3 scripts/view_reports.py --csv > reports.csv

The bearer key is read from $SIPSPOT_REPORTS_KEY_FILE (default
/workspace/sipspot-secrets/reports-key.txt) and is never printed. It is sent
only in the Authorization header, so it does not show up in the process list.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = os.environ.get("SIPSPOT_API", "https://api.sipspot.co.uk")
KEY_FILE = os.environ.get("SIPSPOT_REPORTS_KEY_FILE", "/workspace/sipspot-secrets/reports-key.txt")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=30, help="look back this many days (1-365)")
    ap.add_argument("--open", action="store_true", help="only reports still showing on the map")
    ap.add_argument("--csv", action="store_true", help="CSV output (for forwarding to partners)")
    args = ap.parse_args()

    try:
        key = open(KEY_FILE, encoding="utf-8").read().strip()
    except OSError:
        print(f"Cannot read the reports key file ({KEY_FILE}).", file=sys.stderr)
        return 2
    url = f"{API}/api/reports?days={max(1, min(365, args.days))}" + ("&open=1" if args.open else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "Accept": "application/json", "User-Agent": "sipspot-owner-reports/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            data = json.load(res)
    except urllib.error.HTTPError as err:
        print(f"API answered {err.code}. Check the key file matches the REPORTS_KEY Worker secret.", file=sys.stderr)
        return 1

    rows = data.get("reports") or []
    if args.csv:
        w = csv.writer(sys.stdout)
        w.writerow(["reported_at_utc", "reason", "name", "cities", "lat", "lon", "point_id", "open", "still_here_since"])
        for r in rows:
            w.writerow([r["reported_at"], r["reason_label"], r.get("name") or "", " ".join(r.get("cities") or []),
                        r.get("lat"), r.get("lon"), r["point_id"], "yes" if r.get("open") else "no",
                        r.get("still_here_since") or ""])
        return 0
    scope = "open reports" if args.open else "reports"
    print(f"{len(rows)} {scope} in the last {data.get('days')} days")
    for r in rows:
        when = datetime.fromisoformat(r["reported_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
        where = ", ".join(c.replace("-", " ").title() for c in (r.get("cities") or [])) or "outside a city page"
        status = "OPEN" if r.get("open") else "closed"
        map_link = f"https://www.openstreetmap.org/?mlat={r['lat']}&mlon={r['lon']}#map=19/{r['lat']}/{r['lon']}" if r.get("lat") is not None else ""
        print(f"- {when:%d %b %Y %H:%M} UTC  [{status}]  {r['reason_label']}: {r.get('name') or r['point_id']} ({where})")
        print(f"    {r['point_id']}  {map_link}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
