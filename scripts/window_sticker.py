#!/usr/bin/env python3
"""Make a public window or unit sticker for a SipSpot refill point.

  python3 scripts/window_sticker.py --venue "Melbourne in Lichfield" --city lichfield
  python3 scripts/window_sticker.py --venue "Alpha Running" --city lichfield \\
      --sponsor "South Staffs Water" --sponsor-logo path/to/logo.svg -o alpha.svg

Writes a 100 x 140 mm SVG that print shops take as it is. The QR code opens the
city's SipSpot page. --sponsor adds "Free refills sponsored by <name>" at the
foot, with the sponsor's logo if one is given (SVG or PNG, embedded in the file).

Only print a sponsor's name or logo once they have agreed in writing, and use
the logo files and colours their brand team sends you.
Needs: pip install qrcode
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import re
from html import escape
from pathlib import Path

SITE = "https://sipspot.co.uk"
DROP = (
    '<circle cx="18" cy="18" r="18" fill="#1E88E5"/>'
    '<path d="M18 7.5c-5.2 6.2-7.2 9.4-7.2 12.2a7.2 7.2 0 0 0 14.4 0c0-2.8-2-6-7.2-12.2z" fill="#fff"/>'
    '<path d="M25 11c2.2 1.1 3.4 2.8 3 4.4-1.5-.2-2.8-1-3.6-2.2-.4-1.2-.3-2.2.6-2.2z" fill="#43A047"/>'
)


def qr_path(url: str) -> tuple[str, int]:
    import qrcode

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
    qr.add_data(url)
    qr.make(fit=True)
    d = "".join(
        f"M{x} {y}h1v1h-1z"
        for y, row in enumerate(qr.get_matrix())
        for x, on in enumerate(row)
        if on
    )
    return d, qr.modules_count


def logo_href(path: str) -> str:
    raw = Path(path).read_bytes()
    mime = mimetypes.guess_type(path)[0] or "image/png"
    if mime not in {"image/svg+xml", "image/png", "image/jpeg"}:
        raise SystemExit("Sponsor logo must be SVG, PNG or JPEG.")
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def sticker(venue: str, city: str, sponsor: str | None, sponsor_logo: str | None) -> str:
    url = f"{SITE}/{city}/" if city else f"{SITE}/"
    d, n = qr_path(url)
    qr_size = 34.0
    foot = ""
    if sponsor:
        logo = ""
        if sponsor_logo:
            logo = (f'<image href="{logo_href(sponsor_logo)}" x="30" y="117.5" width="40" height="12" '
                    'preserveAspectRatio="xMidYMid meet"/>')
        else:
            logo = (f'<text x="50" y="124" font-size="5.2" font-weight="700" text-anchor="middle" '
                    f'fill="#0D47A1">{escape(sponsor)}</text>')
        foot = (
            '<line x1="12" y1="109" x2="88" y2="109" stroke="#BBDEFB" stroke-width="0.5"/>'
            '<text x="50" y="115.5" font-size="3.6" text-anchor="middle" fill="#2c4a63">'
            "Free refills here sponsored by</text>" + logo
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="140mm" viewBox="0 0 100 140"
     font-family="Source Sans 3, Arial, sans-serif" fill="#0d2137">
  <rect width="100" height="140" rx="6" fill="#ffffff"/>
  <rect x="0" y="0" width="100" height="48" rx="6" fill="#E3F2FD"/>
  <rect x="0" y="40" width="100" height="8" fill="#E3F2FD"/>
  <g transform="translate(9 8) scale(0.33)">{DROP}</g>
  <text x="23" y="17" font-family="Fraunces, Georgia, serif" font-size="8.5" font-weight="700" fill="#0D47A1">SipSpot</text>
  <text x="9" y="36" font-size="8.6" font-weight="700" fill="#0d2137">Free water refills here</text>
  <text x="9" y="43.5" font-size="4.4" fill="#2c4a63">Bring your bottle. No purchase needed.</text>
  <text x="50" y="57" font-size="4.6" font-weight="700" text-anchor="middle">{escape(venue)}</text>
  <g transform="translate({50 - qr_size / 2} 61) scale({qr_size / n:.5f})"><path d="{d}" fill="#0d2137"/></g>
  <text x="50" y="101" font-size="3.8" text-anchor="middle" fill="#2c4a63">Scan for more free refills nearby</text>
  <text x="50" y="105.5" font-size="3.4" text-anchor="middle" fill="#1565C0">{escape(url.replace("https://", ""))}</text>
  {foot}
  <text x="50" y="{134 if sponsor else 128}" font-size="4" font-weight="700" text-anchor="middle" fill="#2E7D32">Find it. Fill it. Go.</text>
</svg>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venue", required=True)
    ap.add_argument("--city", default="", help="city page slug, e.g. lichfield")
    ap.add_argument("--sponsor", help="sponsor name, only with their written agreement")
    ap.add_argument("--sponsor-logo", help="sponsor logo file (SVG, PNG or JPEG) from their brand team")
    ap.add_argument("-o", "--out", help="output .svg (default: stickers/window-<venue>.svg)")
    a = ap.parse_args()
    if a.city and not re.fullmatch(r"[a-z0-9-]+", a.city):
        raise SystemExit("--city must be a page slug such as lichfield")
    out = Path(a.out) if a.out else Path(__file__).resolve().parents[1] / "stickers" / (
        "window-" + re.sub(r"[^a-z0-9]+", "-", a.venue.lower()).strip("-") + ".svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sticker(a.venue, a.city, a.sponsor, a.sponsor_logo), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
