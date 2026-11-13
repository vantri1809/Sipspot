#!/usr/bin/env python3
"""Manage SipSpot managed units and print their staff-check QR stickers (owner only).

A managed unit is a refill point whose owner's staff check it by scanning a QR
code on the unit. SipSpot never checks units itself: the API records checks,
flags overdue units, hides units that are reported or not checked, and emails
the partner.

Usage:
  # Register a unit (the map point must already exist) and make its sticker:
  python3 scripts/units.py add --id partner:three-spires-1 \\
      --partner-id three-spires --partner-name "Three Spires" \\
      --email facilities@example.com --label "Unit 1, Market St entrance"

  python3 scripts/units.py list                  # every unit and its status
  python3 scripts/units.py sticker --id ID       # new key + new sticker (old QR stops working)
  python3 scripts/units.py hide --id ID          # take a unit off the map
  python3 scripts/units.py show --id ID          # put it back

Stickers are written to stickers/ (git-ignored). Each QR code contains that
unit's secret check key, so treat sticker files like keys: print them, fix
them inside the unit's service panel or another staff-only place, and do not
share the files. Lost or copied sticker? Run `sticker` to replace the key.

The owner bearer key is read from $SIPSPOT_REPORTS_KEY_FILE (default
/workspace/sipspot-secrets/reports-key.txt), the same key as view_reports.py.
Needs: pip install qrcode
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("SIPSPOT_API", "https://api.sipspot.co.uk").rstrip("/")
SITE = os.environ.get("SIPSPOT_SITE", "https://sipspot.co.uk").rstrip("/")
KEY_FILE = os.environ.get("SIPSPOT_REPORTS_KEY_FILE", "/workspace/sipspot-secrets/reports-key.txt")
STICKER_DIR = ROOT / "stickers"


def owner_key() -> str:
    try:
        return Path(KEY_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        sys.exit(f"Cannot read the owner key file ({KEY_FILE}). Set SIPSPOT_REPORTS_KEY_FILE.")


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={
            "Authorization": "Bearer " + owner_key(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "sipspot-owner-units/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return json.load(res)
    except urllib.error.HTTPError as err:
        try:
            detail = json.load(err).get("error")
        except Exception:  # noqa: BLE001
            detail = None
        sys.exit(f"API answered {err.code}" + (f" ({detail})" if detail else "") + ".")


def check_url(point_id: str, key: str) -> str:
    # Fragment, not query string: browsers never send it to a server.
    return f"{SITE}/check/#u={point_id}&k={key}"


def sticker_svg(point_id: str, key: str, label: str, partner: str) -> str:
    import qrcode
    import qrcode.image.svg

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, box_size=10)
    qr.add_data(check_url(point_id, key))
    qr.make(fit=True)
    modules = qr.modules_count
    # Draw the QR as one path in a 0..modules box, scaled into the sticker.
    path = []
    for y, row in enumerate(qr.get_matrix()):
        for x, on in enumerate(row):
            if on:
                path.append(f"M{x} {y}h1v1h-1z")
    size = 50.0  # mm
    scale = size / modules
    lines = [
        "Scan, then: look for damage or tampering,",
        "wipe the spout, run the water for a few",
        "seconds, and tap “Checked, all fine”.",
    ]
    text = "".join(
        f'<text x="35" y="{78 + i * 4.2:.1f}" font-size="3.2" text-anchor="middle">{escape(t)}</text>'
        for i, t in enumerate(lines)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="70mm" height="95mm" viewBox="0 0 70 95" font-family="Source Sans 3, Arial, sans-serif" fill="#0d2137">
  <rect x="0.5" y="0.5" width="69" height="94" rx="4" fill="#fff" stroke="#1E88E5" stroke-width="1"/>
  <text x="35" y="9" font-size="5" font-weight="700" text-anchor="middle" fill="#1565C0">SipSpot daily check</text>
  <text x="35" y="14.5" font-size="3.4" text-anchor="middle">Staff only · {escape(partner)}</text>
  <g transform="translate(10 18) scale({scale:.5f})"><path d="{''.join(path)}" fill="#000"/></g>
  <text x="35" y="73" font-size="3.6" font-weight="700" text-anchor="middle">{escape(label)}</text>
  {text}
</svg>
"""


def write_sticker(unit: dict, key: str, partner: str) -> Path:
    STICKER_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", f"{unit.get('partner_id', '')}-{unit.get('label') or unit['id']}".lower()).strip("-")
    out = STICKER_DIR / f"{slug[:80]}.svg"
    out.write_text(sticker_svg(unit["id"], key, unit.get("label") or "Refill unit", partner), encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    return out


def find_unit(point_id: str) -> dict:
    for u in call("GET", "/api/admin/units").get("units", []):
        if u["id"] == point_id:
            return u
    sys.exit(f"No managed unit with id {point_id}. Use `add` first.")


def cmd_add(a) -> int:
    body = {"id": a.id, "partner_id": a.partner_id, "check_every_hours": a.every}
    if a.partner_name:
        body["partner_name"] = a.partner_name
    if a.email:
        body["alert_email"] = a.email
    if a.label:
        body["label"] = a.label
    res = call("POST", "/api/admin/unit", body)
    unit = res["unit"]
    print(("Registered" if res.get("created") else "Updated") + f" {unit['id']} for {a.partner_id}: {unit['status']}.")
    if res.get("check_key"):
        partner = a.partner_name or unit.get("partner_id")
        path = write_sticker(unit, res["check_key"], partner)
        print(f"Sticker: {path.relative_to(ROOT)} (contains the unit's secret key; keep it private).")
    else:
        print("Existing unit: its key was not changed. Use `sticker` for a new key and sticker.")
    return 0


def cmd_sticker(a) -> int:
    u = find_unit(a.id)
    res = call("POST", "/api/admin/unit", {"id": a.id, "partner_id": u["partner_id"], "rotate_key": True,
                                           "check_every_hours": u.get("every_hours", 24)})
    path = write_sticker(res["unit"], res["check_key"], u.get("partner") or u["partner_id"])
    print(f"New key made; the old QR code no longer works. Sticker: {path.relative_to(ROOT)}")
    return 0


def cmd_list(_a) -> int:
    units = call("GET", "/api/admin/units").get("units", [])
    if not units:
        print("No managed units yet.")
        return 0
    for u in units:
        status = u["status"] + (f" ({u['hidden_label']})" if u.get("hidden_label") else "")
        last = u.get("last_check") or "never"
        print(f"{u['partner']:<22} {str(u.get('label') or u['id'])[:34]:<34} {status:<34} last check {last}  "
              f"checks/30d {u.get('checks_last_30_days', 0)}")
    return 0


def cmd_hide(a, hidden: bool) -> int:
    res = call("POST", "/api/admin/unit-status", {"id": a.id, "hidden": hidden})
    print(f"{a.id}: {res['unit']['status']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add", help="register or update a unit")
    p.add_argument("--id", required=True, help="map point id, e.g. partner:three-spires-1 or osm:node:123")
    p.add_argument("--partner-id", required=True, help="short id, e.g. three-spires")
    p.add_argument("--partner-name", help="needed the first time a partner is used")
    p.add_argument("--email", help="where alerts go")
    p.add_argument("--label", help='staff-facing name, e.g. "Unit 1, Market St entrance"')
    p.add_argument("--every", type=int, default=24, help="hours between checks (default 24)")
    p = sub.add_parser("sticker", help="new key and sticker for a unit")
    p.add_argument("--id", required=True)
    sub.add_parser("list", help="list units")
    for name in ("hide", "show"):
        p = sub.add_parser(name, help=f"{name} a unit")
        p.add_argument("--id", required=True)
    a = ap.parse_args()
    if a.cmd == "add":
        return cmd_add(a)
    if a.cmd == "sticker":
        return cmd_sticker(a)
    if a.cmd == "list":
        return cmd_list(a)
    return cmd_hide(a, a.cmd == "hide")


if __name__ == "__main__":
    raise SystemExit(main())
