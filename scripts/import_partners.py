#!/usr/bin/env python3
"""Convert a partner business CSV into data/partners.geojson.

This script does not read, write, or join OpenStreetMap data.
If latitude or longitude is missing, the UK postcode is geocoded with
the postcodes.io API (ONS-derived), not with OSM.

Expected columns (header row):
  name, address, postcode, lat, lon, partner, hours, verified_date
The partner (supplier / sponsor) column is accepted but never written to the
public GeoJSON: listings show the venue only, never a supplier or cooler company.
Optional columns:
  logo_url, refill_offered, id, is_example, water_type, chilled, walk_in_free
walk_in_free must be yes — SipSpot only lists free walk-in fills.
water_type values: tap, filtered, chilled filtered, unknown
chilled values: yes, no

Usage:
  python3 scripts/import_partners.py data/partners.example.csv
  python3 scripts/import_partners.py partners.csv -o data/partners.geojson
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from water_attributes import is_walk_in_free, parse_partner_chilled, parse_partner_water_type, water_type_label

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "partners.geojson"
POSTCODES_URL = "https://api.postcodes.io/postcodes"
USER_AGENT = "SipSpot/1.0 (partner import; postcodes.io geocoding)"


def norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (key or "").strip().lower())


HEADER_MAP = {
    "name": "name",
    "businessname": "name",
    "business": "name",
    "address": "address",
    "postcode": "postcode",
    "postcodes": "postcode",
    "lat": "lat",
    "latitude": "lat",
    "lon": "lon",
    "lng": "lon",
    "long": "lon",
    "longitude": "lon",
    "partner": "partner",
    "partnercompany": "partner",
    "sponsor": "partner",
    "hours": "hours",
    "openinghours": "hours",
    "verifieddate": "verified_date",
    "verified": "verified_date",
    "logourl": "logo_url",
    "logo": "logo_url",
    "refilloffered": "refill_offered",
    "refill": "refill_offered",
    "id": "id",
    "isexample": "is_example",
    "example": "is_example",
    "watertype": "water_type",
    "water": "water_type",
    "chilled": "chilled",
    "walkinfree": "walk_in_free",
    "walkinfreetag": "walk_in_free",
}


def map_row(raw: dict) -> dict:
    mapped = {}
    for k, v in raw.items():
        nk = HEADER_MAP.get(norm_key(k))
        if nk:
            mapped[nk] = (v or "").strip()
    return mapped


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def geocode_postcodes(postcodes: list[str]) -> dict[str, tuple[float, float]]:
    """Bulk-lookup unique postcodes via postcodes.io. Returns postcode -> (lat, lon)."""
    found: dict[str, tuple[float, float]] = {}
    unique = []
    seen = set()
    for pc in postcodes:
        key = re.sub(r"\s+", "", pc.upper())
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(pc)
    if not unique:
        return found

    for group in chunked(unique, 100):
        payload = json.dumps({"postcodes": group}).encode("utf-8")
        req = urllib.request.Request(
            POSTCODES_URL,
            data=payload,
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"postcodes.io request failed: {exc}", file=sys.stderr)
            continue
        for item in body.get("result") or []:
            query = (item or {}).get("query") or ""
            result = (item or {}).get("result")
            if not result:
                print(f"  No match for postcode {query!r}", file=sys.stderr)
                continue
            lat, lon = result.get("latitude"), result.get("longitude")
            if lat is None or lon is None:
                continue
            found[re.sub(r"\s+", "", query.upper())] = (float(lat), float(lon))
    return found


def parse_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def parse_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def slug_id(name: str, postcode: str, index: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "partner").lower()).strip("-") or "partner"
    pc = re.sub(r"\s+", "", (postcode or "").lower())
    tail = pc or f"{index:03d}"
    return f"partner-{base}-{tail}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Partner CSV to import")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.csv_path.is_file():
        print(f"CSV not found: {args.csv_path}", file=sys.stderr)
        return 1

    with args.csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = [map_row(r) for r in reader]

    need_geo = []
    for row in rows:
        if parse_float(row.get("lat")) is None or parse_float(row.get("lon")) is None:
            if row.get("postcode"):
                need_geo.append(row["postcode"])
            else:
                print(f"Skipping '{row.get('name') or '(unnamed)'}': no lat/lon or postcode", file=sys.stderr)

    lookup = geocode_postcodes(need_geo) if need_geo else {}

    features = []
    skipped = 0
    geocoded = 0
    for i, row in enumerate(rows, start=1):
        lat = parse_float(row.get("lat"))
        lon = parse_float(row.get("lon"))
        if lat is None or lon is None:
            pc_key = re.sub(r"\s+", "", (row.get("postcode") or "").upper())
            if pc_key in lookup:
                lat, lon = lookup[pc_key]
                geocoded += 1
            else:
                skipped += 1
                continue
        name = row.get("name") or f"Partner {i}"
        fid = row.get("id") or slug_id(name, row.get("postcode") or "", i)
        offered = (row.get("refill_offered") or "free").strip().lower() or "free"
        if offered not in {"free", "yes", "y"}:
            print(f"Skipping '{name}': SipSpot lists only free fills (refill_offered={offered!r})", file=sys.stderr)
            skipped += 1
            continue
        if not is_walk_in_free(row.get("walk_in_free")):
            print(f"Skipping '{name}': walk_in_free must be yes (free for anyone, no purchase needed)", file=sys.stderr)
            skipped += 1
            continue
        water_type = parse_partner_water_type(row.get("water_type"))
        chilled = parse_partner_chilled(row.get("chilled"), water_type)
        props = {
            "name": name,
            "address": row.get("address") or None,
            "postcode": row.get("postcode") or None,
            "hours": row.get("hours") or None,
            "refill_offered": "free",
            "verified_date": row.get("verified_date") or None,
            "logo_url": row.get("logo_url") or "",
            "is_example": parse_bool(row.get("is_example")),
            "source": "partner",
            "water_type": water_type,
            "water_type_label": water_type_label(water_type),
            "chilled": chilled,
            "walk_in_free": True,
        }
        features.append({
            "type": "Feature",
            "id": fid,
            "properties": props,
            "geometry": {
                "type": "Point",
                "coordinates": [round(lon, 6), round(lat, 6)],
            },
        })

    geojson = {
        "type": "FeatureCollection",
        "name": "SipSpot partner businesses",
        "source": "partners",
        "licence": "Not an OSM derivative. Do not merge with data/points.geojson.",
        "note": (
            "This layer is kept strictly separate from OpenStreetMap data to avoid "
            "ODbL share-alike applying to the partner list."
        ),
        "counts": {
            "total": len(features),
            "geocoded_from_postcode": geocoded,
            "skipped": skipped,
            "examples": sum(1 for f in features if f["properties"].get("is_example")),
        },
        "features": features,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(geojson, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(features)} partner points to {args.output} ({geocoded} geocoded, {skipped} skipped)")
    return 0 if features else 2


if __name__ == "__main__":
    sys.exit(main())
