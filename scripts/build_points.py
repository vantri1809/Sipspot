#!/usr/bin/env python3
"""Build data/points.geojson from Overpass bbox caches and optional PBF extracts.

Purely OSM-derived. Applies the walk-in-free policy. Does not touch partners.geojson.

Merge every JSON file in data/overpass-cache/ (Overpass tiles and PBF extracts)
into data/points.geojson. This is the only script that should write that file.
Applies the walk-in-free policy. Does not touch partners.geojson.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_points import OUT_PATH, ROOT, to_feature  # noqa: E402

CACHE = ROOT / "data" / "overpass-cache"


def load_elements(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("elements") or []


def main() -> int:
    files = sorted(CACHE.glob("*.json"))
    elements = []
    for path in files:
        # Skip merged quadrants that were rebuilt from children if children exist? Use all, dedupe later.
        els = load_elements(path)
        print(f"{path.name}: {len(els)} elements")
        elements.extend(els)

    features = []
    seen = set()
    skipped_no_coords = 0
    skipped_excluded = 0
    skipped_dup = 0
    for el in elements:
        key = (el.get("type"), el.get("id"))
        if key in seen:
            skipped_dup += 1
            continue
        seen.add(key)
        feat = to_feature(el)
        if feat is None:
            # paid/restricted already skipped inside to_feature as None, as is outside UK / no coords
            tags = el.get("tags") or {}
            from water_attributes import is_excluded_osm
            if is_excluded_osm(tags):
                skipped_excluded += 1
            else:
                skipped_no_coords += 1
            continue
        features.append(feat)

    counts = {
        "total": len(features),
        "nodes": sum(1 for f in features if f["properties"]["osm_type"] == "node"),
        "ways": sum(1 for f in features if f["properties"]["osm_type"] == "way"),
        "relations": sum(1 for f in features if f["properties"]["osm_type"] == "relation"),
        "public_fountain": sum(1 for f in features if f["properties"]["category"] == "public_fountain"),
        "cafe_refill": sum(1 for f in features if f["properties"]["category"] == "cafe_refill"),
        "bottle_yes": sum(1 for f in features if f["properties"].get("bottle") == "yes"),
        "fee_no": sum(1 for f in features if f["properties"].get("fee") == "no"),
        "skipped_excluded": skipped_excluded,
        "skipped_no_coords": skipped_no_coords,
        "skipped_duplicates": skipped_dup,
        "water_tap": sum(1 for f in features if f["properties"].get("water_type") == "tap"),
        "water_filtered": sum(1 for f in features if f["properties"].get("water_type") == "filtered"),
        "water_unknown": sum(1 for f in features if f["properties"].get("water_type") == "unknown"),
        "chilled_yes": sum(1 for f in features if f["properties"].get("chilled") is True),
        "sources": [p.name for p in files],
    }
    geojson = {
        "type": "FeatureCollection",
        "name": "UK drinking water and refill points",
        "licence": "ODbL-1.0",
        "attribution": "© OpenStreetMap contributors",
        "attribution_url": "https://www.openstreetmap.org/copyright",
        "source": "OpenStreetMap, via the Overpass API and Geofabrik OSM PBF extracts",
        "note": (
            "This file is purely OSM-derived. Do not merge it with partners.geojson "
            "or any other database. SipSpot lists only free walk-in fills: points tagged "
            "fee=yes or access=customers/private/no are excluded."
        ),
        "policy": "SipSpot lists only free walk-in fills. Points tagged fee=yes or access=customers/private/no are excluded.",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counts": counts,
        "features": features,
    }
    OUT_PATH.write_text(json.dumps(geojson, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(counts, indent=2))
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
