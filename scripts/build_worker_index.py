#!/usr/bin/env python3
"""Build worker/generated/points-index.json for the SipSpot API Worker.

The Worker only accepts refill taps and votes for point ids it knows about,
and keeps per-city refill totals up to date on write. This script bakes:

  cities: list of public city slugs (same pages as generate_pages.py)
  points: { "<api id>": [city index, ...] } for every OSM and partner point

API ids:  osm:<node|way|relation>:<id>   and   partner:<partner id>

The output is generated at deploy time (wrangler [build] command) and is not
committed, because it can include partner listings. OSM and partner points
are read from their separate files and are only listed together here as ids.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_pages as gp  # noqa: E402

OUT = gp.ROOT / "worker" / "generated" / "points-index.json"
PARTNER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def api_id(feat, source: str):
    p = feat.get("properties") or {}
    if source == "osm":
        t, i = p.get("osm_type"), p.get("osm_id")
        if t in ("node", "way", "relation") and i is not None and re.fullmatch(r"\d{1,12}", str(i)):
            return f"osm:{t}:{i}"
        return None
    pid = p.get("id")
    if pid and PARTNER_ID_RE.match(str(pid)):
        return f"partner:{pid}"
    return None


def main() -> int:
    places = gp.load_json(gp.PLACES_PATH, [])
    osm = gp.load_json(gp.OSM_PATH, {}).get("features") or []
    # SIPSPOT_PARTNERS_PATH lets local tests use a fixture instead of the real file.
    partner_path = Path(os.environ.get("SIPSPOT_PARTNERS_PATH") or gp.PARTNER_PATH)
    partners = gp.load_json(partner_path, {}).get("features") or []
    cities = gp.choose_cities(places, osm, partners)
    cities, _redirects = gp.apply_city_merges(cities)
    slugs = [c["slug"] for c in cities]
    slug_index = {s: i for i, s in enumerate(slugs)}

    points: dict[str, list[int]] = {}
    for feat in osm:
        pid = api_id(feat, "osm")
        if pid:
            points.setdefault(pid, [])
    for feat in partners:
        pid = api_id(feat, "partner")
        if pid:
            points.setdefault(pid, [])
    for city in cities:
        idx = slug_index[city["slug"]]
        for source, feats in (("osm", city.get("_osm") or []), ("partner", city.get("_partners") or [])):
            for feat in feats:
                pid = api_id(feat, source)
                if pid and idx not in points[pid]:
                    points[pid].append(idx)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"cities": slugs, "points": points}, separators=(",", ":")), encoding="utf-8")
    in_city = sum(1 for v in points.values() if v)
    print(f"Worker index: {len(points)} points ({in_city} in a city page), {len(slugs)} cities -> {OUT.relative_to(gp.ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
