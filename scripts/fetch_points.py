#!/usr/bin/env python3
"""Fetch UK drinking-water and bottle-fill points from the OSM Overpass API.

The output (data/points.geojson) is purely OpenStreetMap-derived.
Do not merge, join, or cross-reference it with data/partners.geojson.
Licence of this output: ODbL 1.0, (c) OpenStreetMap contributors
https://www.openstreetmap.org/copyright

Refresh Overpass tiles into data/overpass-cache/, then run build_points.py
to publish data/points.geojson (including any pbf-*.json extracts).
Use --cache-only to skip the network and only rebuild from caches.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from water_attributes import apply_osm_attributes, is_excluded_osm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT_PATH = ROOT / "data" / "points.geojson"
CACHE_DIR = ROOT / "data" / "overpass-cache"
PBF_DIR = ROOT / "data" / "pbf"

# English land in the north-west Overpass tile (north of 54.5°N, west of 2°W)
# is Cumbria plus a sliver of western Northumberland. Geofabrik has no single
# "north-west England" extract; these two county files are the smallest that
# cover that gap. Scotland and Northern Ireland in the same tile have their
# own PBF caches.
NORTH_WEST_PBF = [
    ("cumbria", "https://download.geofabrik.de/europe/united-kingdom/england/cumbria-latest.osm.pbf"),
    ("northumberland", "https://download.geofabrik.de/europe/united-kingdom/england/northumberland-latest.osm.pbf"),
]

USER_AGENT = (
    "SipSpot/1.0 (static UK drinking-water map; OSM Overpass extract; "
    "https://sipspot.co.uk)"
)

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.openstreetmap.fr/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

# UK bounding boxes (includes Northern Ireland, Shetland, Scilly). Split so
# public Overpass instances are less likely to drop a single huge query.
BBOXES = [
    ("south-west", "49.80,-8.90,54.50,-2.00"),
    ("south-east", "49.80,-2.00,54.50,2.00"),
    ("north-west", "54.50,-8.90,60.90,-2.00"),
    ("north-east", "54.50,-2.00,60.90,2.00"),
]


def _filters(bbox: str) -> str:
    # Built with concatenation so Overpass filter syntax is not parsed as Python.
    parts = [
        'node["amenity"="drinking_water"](' + bbox + ');',
        'way["amenity"="drinking_water"](' + bbox + ');',
        'relation["amenity"="drinking_water"](' + bbox + ');',
        'node["drinking_water:refill"="yes"](' + bbox + ');',
        'way["drinking_water:refill"="yes"](' + bbox + ');',
        'relation["drinking_water:refill"="yes"](' + bbox + ');',
        'node["man_made"="water_tap"]["drinking_water"="yes"](' + bbox + ');',
        'way["man_made"="water_tap"]["drinking_water"="yes"](' + bbox + ');',
        'relation["man_made"="water_tap"]["drinking_water"="yes"](' + bbox + ');',
        'node["amenity"="water_point"](' + bbox + ');',
        'way["amenity"="water_point"](' + bbox + ');',
        'relation["amenity"="water_point"](' + bbox + ');',
    ]
    return "(\n  " + "\n  ".join(parts) + "\n);"


def query_for(bbox: str) -> str:
    return "[out:json][timeout:180];\n" + _filters(bbox) + "\nout meta center;"


def classify(tags: dict) -> str:
    """Return a display category used only for OSM points."""
    refill = tags.get("drinking_water:refill") == "yes"
    amenity = tags.get("amenity", "")
    man_made = tags.get("man_made", "")
    shop_like = amenity in {
        "cafe",
        "restaurant",
        "fast_food",
        "pub",
        "bar",
        "biergarten",
        "food_court",
        "ice_cream",
        "marketplace",
        "community_centre",
        "library",
        "fuel",
        "pharmacy",
        "bank",
        "townhall",
        "arts_centre",
        "theatre",
        "cinema",
        "museum",
        "gallery",
        "place_of_worship",
        "shop",
    } or "shop" in tags or tags.get("tourism") in {"hotel", "hostel", "museum", "gallery", "attraction"}

    if refill or shop_like:
        return "cafe_refill"
    if amenity == "drinking_water" or man_made == "water_tap" or amenity == "water_point":
        return "public_fountain"
    return "public_fountain"


def kind_label(tags: dict, category: str) -> str:
    if category == "cafe_refill":
        amenity = tags.get("amenity") or tags.get("shop") or tags.get("tourism")
        if amenity:
            return f"Café or shop refill ({amenity.replace('_', ' ')})"
        return "Café or shop refill"
    amenity = tags.get("amenity", "")
    man_made = tags.get("man_made", "")
    if amenity == "water_point":
        return "Water point"
    if man_made == "water_tap":
        return "Water tap"
    if amenity == "drinking_water":
        fountain = tags.get("fountain") or tags.get("drinking_water:type")
        if fountain:
            return f"Public fountain ({fountain.replace('_', ' ')})"
        return "Public fountain"
    return "Drinking water"


def bottle_value(tags: dict) -> str | None:
    for key in ("bottle", "drinking_water:bottle"):
        if key in tags:
            return tags[key]
    return None



def in_uk(lat: float, lon: float) -> bool:
    """Coarse geographic filter used because split bounding boxes also cover
    a little of the Republic of Ireland and the French coast. Not a legal
    boundary file — it only drops obvious non-UK points."""
    # Northern Ireland
    if 54.0 <= lat <= 55.45 and -8.25 <= lon <= -5.25:
        return True
    # Shetland and Fair Isle
    if 58.7 <= lat <= 61.05 and -2.8 <= lon <= 0.3:
        return True
    # Great Britain and nearby islands (Orkney, Hebrides, Scilly, Anglesey, Wight)
    if 49.80 <= lat <= 58.7 and -7.05 <= lon <= 1.95:
        # Drop the Republic of Ireland south of the land border
        if lon < -5.90 and lat < 54.0:
            return False
        return True
    return False


def element_coords(el: dict) -> tuple[float, float] | None:
    if "lat" in el and "lon" in el:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center")
    if center and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def to_feature(el: dict) -> dict | None:
    coords = element_coords(el)
    if not coords:
        return None
    lat, lon = coords
    if not in_uk(lat, lon):
        return None
    tags = el.get("tags") or {}
    if is_excluded_osm(tags):
        return None
    category = classify(tags)
    bottle = bottle_value(tags)
    props = {
        "osm_type": el.get("type"),
        "osm_id": el.get("id"),
        "name": tags.get("name") or None,
        "opening_hours": tags.get("opening_hours") or None,
        "access": tags.get("access") or None,
        "fee": tags.get("fee") or None,
        "bottle": bottle,
        "amenity": tags.get("amenity") or None,
        "man_made": tags.get("man_made") or None,
        "drinking_water": tags.get("drinking_water") or None,
        "drinking_water:refill": tags.get("drinking_water:refill") or None,
        "operator": tags.get("operator") or None,
        "brand": tags.get("brand") or None,
        "description": tags.get("description") or None,
        "wheelchair": tags.get("wheelchair") or None,
        "timestamp": el.get("timestamp") or None,
        "version": el.get("version") or None,
        "changeset": el.get("changeset") or None,
        "category": category,
        "kind": kind_label(tags, category),
        "source": "openstreetmap",
        "note": tags.get("note") or None,
        "drinking_water:filtered": tags.get("drinking_water:filtered") or None,
        "water_filter": tags.get("water_filter") or None,
        "drinking_water:chilled": tags.get("drinking_water:chilled") or None,
        "cooled": tags.get("cooled") or None,
        "chilled_tag": tags.get("chilled") or None,
    }
    apply_osm_attributes(props, tags)
    # Drop nulls to keep the file lean, but keep the required fields even if null
    required = {
        "osm_type",
        "osm_id",
        "name",
        "opening_hours",
        "access",
        "fee",
        "bottle",
        "timestamp",
        "category",
        "kind",
        "source",
        "water_type",
        "water_type_label",
        "chilled",
    }
    props = {k: v for k, v in props.items() if v is not None or k in required}
    return {
        "type": "Feature",
        "id": f"{el.get('type')}/{el.get('id')}",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
    }



def post_overpass(url: str, query: str, timeout: int = 90) -> dict:
    import urllib.parse
    import http.client

    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    print(f"Requesting {url} ...", flush=True)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        print(f"  HTTP {resp.status}, {len(raw):,} bytes", flush=True)
        return json.loads(raw)


def post_overpass_curl(url: str, query: str, timeout: int = 120) -> dict:
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(prefix="overpass-", suffix=".json", delete=False) as tmp:
        out = tmp.name
    try:
        cmd = [
            "curl", "-sS", "--fail", "--compressed",
            "-A", USER_AGENT,
            "--max-time", str(min(timeout, 120)),
            "--connect-timeout", "25",
            "--retry", "0",
            "-X", "POST",
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "--data-urlencode", "data=" + query,
            "-o", out,
            url,
        ]
        print(f"curl {url} ...", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"curl exit {proc.returncode}")
        raw = Path(out).read_bytes()
        print(f"  curl ok, {len(raw):,} bytes", flush=True)
        return json.loads(raw)
    finally:
        Path(out).unlink(missing_ok=True)


NETWORK_ERRORS = (
    urllib.error.URLError,
    urllib.error.HTTPError,
    TimeoutError,
    json.JSONDecodeError,
    ConnectionError,
    OSError,
    RuntimeError,
)



def valid_payload(payload: dict, label: str) -> str | None:
    """Return an error string if the Overpass JSON should not be trusted."""
    if not isinstance(payload, dict) or "elements" not in payload:
        return "JSON missing elements"
    if payload.get("remark"):
        return f"Overpass remark: {payload.get('remark')}"
    ts = str((payload.get("osm3s") or {}).get("timestamp_osm_base") or "")
    if ts and "T" not in ts and not ts.startswith("20"):
        return f"implausible osm timestamp {ts!r}"
    n = len(payload.get("elements") or [])
    # A full UK quadrant with no points is almost certainly a failed response.
    if label in {"south-west", "south-east", "north-west", "north-east"} and n == 0:
        return f"{label} returned 0 elements"
    return None


def fetch_one(query: str, label: str) -> dict:
    last_error = None
    attempts = []
    for url in ENDPOINTS:
        attempts.append((url, post_overpass_curl))
        attempts.append((url, post_overpass))
    for attempt, (url, fn) in enumerate(attempts, start=1):
        try:
            payload = fn(url, query)
            elements = payload.get("elements")
            if elements is None:
                raise RuntimeError("Overpass JSON missing elements")
            problem = valid_payload(payload, label)
            if problem:
                raise RuntimeError(problem)
            print(f"  {label}: {len(elements)} elements", flush=True)
            return payload
        except NETWORK_ERRORS as exc:
            last_error = exc
            wait = min(20, 4 * ((attempt - 1) // 2 + 1))
            print(f"  Failed {fn.__name__} ({type(exc).__name__}: {exc}). Waiting {wait}s...", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"All Overpass attempts failed for {label}: {last_error}")


def split_bbox(bbox: str) -> list[str]:
    south, west, north, east = (float(x) for x in bbox.split(","))
    mid_lat = round((south + north) / 2, 4)
    mid_lon = round((west + east) / 2, 4)
    return [
        f"{south},{west},{mid_lat},{mid_lon}",
        f"{south},{mid_lon},{mid_lat},{east}",
        f"{mid_lat},{west},{north},{mid_lon}",
        f"{mid_lat},{mid_lon},{north},{east}",
    ]


def fetch_bbox(label: str, bbox: str, depth: int = 0) -> dict:
    cache_path = CACHE_DIR / (label + ".json")
    if cache_path.is_file() and cache_path.stat().st_size > 100:
        print(f"Using cached {cache_path.name}", flush=True)
        return json.loads(cache_path.read_text(encoding="utf-8"))
    try:
        payload = fetch_one(query_for(bbox), label)
    except RuntimeError as exc:
        if depth >= 2:
            print(f"  Giving up on {label}: {exc}", flush=True)
            return {"elements": [], "failed": True}
        print(f"  Splitting {label} into 4 smaller boxes after failure ({exc})", flush=True)
        merged = []
        osm_ts = None
        for i, sub in enumerate(split_bbox(bbox)):
            part = fetch_bbox(f"{label}-{i}", sub, depth + 1)
            merged.extend(part.get("elements") or [])
            osm_ts = osm_ts or (part.get("osm3s") or {}).get("timestamp_osm_base")
        payload = {"elements": merged, "osm3s": {"timestamp_osm_base": osm_ts}}
        if not merged:
            print(f"  {label} still empty after splitting; not writing a zero cache file", flush=True)
            return {"elements": [], "failed": True}
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    print(f"  cached {cache_path.name} ({len(payload.get('elements') or []):,} elements)", flush=True)
    return payload


def download_file(url: str, dest: Path) -> None:
    """Download a file with curl (follows Geofabrik's dated-file redirect)."""
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    cmd = [
        "curl",
        "-L",
        "--fail",
        "--retry",
        "3",
        "--retry-delay",
        "5",
        "-A",
        USER_AGENT,
        "-o",
        str(tmp),
        url,
    ]
    print(f"Downloading {url} -> {dest} ...", flush=True)
    proc = subprocess.run(cmd)
    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 1000:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"download failed: {url} (exit {proc.returncode})")
    tmp.replace(dest)
    print(f"  saved {dest.name} ({dest.stat().st_size:,} bytes)", flush=True)


def ensure_northwest_pbf() -> None:
    """Fill a missing north-west Overpass tile from Geofabrik county PBFs.

    Writes data/overpass-cache/pbf-cumbria.json and pbf-northumberland.json
    (downloading the PBFs into data/pbf/ if needed). Existing cache JSON is
    left as-is. build_points.py merges those files with the other tiles.
    """
    from extract_from_pbf import main as extract_main

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for stem, url in NORTH_WEST_PBF:
        cache = CACHE_DIR / f"pbf-{stem}.json"
        if cache.is_file() and cache.stat().st_size > 100:
            print(f"Using existing {cache.name} as north-west PBF fallback", flush=True)
            continue
        pbf = PBF_DIR / f"{stem}-latest.osm.pbf"
        if not pbf.is_file() or pbf.stat().st_size < 1000:
            try:
                download_file(url, pbf)
            except Exception as exc:
                print(f"WARNING: could not download {stem} PBF ({exc})", flush=True)
                continue
        print(f"Extracting north-west fallback from {pbf.name} ...", flush=True)
        if extract_main([str(pbf)]) != 0:
            print(f"WARNING: extract_from_pbf failed for {pbf.name}", flush=True)


def fetch() -> dict:
    all_elements = []
    osm_ts = None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for label, bbox in BBOXES:
        try:
            payload = fetch_bbox(label, bbox)
        except Exception as exc:
            print(f"WARNING: {label} could not be fetched ({exc}). Continuing with other tiles and any PBF caches.", flush=True)
            payload = {"elements": []}
        all_elements.extend(payload.get("elements") or [])
        osm_ts = osm_ts or (payload.get("osm3s") or {}).get("timestamp_osm_base")
        if payload.get("failed"):
            print(f"WARNING: {label} has no Overpass data. build_points.py will still include any PBF extracts.", flush=True)
    if not (CACHE_DIR / "north-west.json").is_file():
        print("North-west Overpass tile is missing; using Geofabrik PBF fallback.", flush=True)
        ensure_northwest_pbf()
    return {"elements": all_elements, "osm3s": {"timestamp_osm_base": osm_ts}}



def main() -> int:
    """Refresh Overpass caches, then publish data/points.geojson via build_points.py.

    That merge step also includes any Geofabrik PBF extracts in
    data/overpass-cache/pbf-*.json, so a failed Overpass tile cannot
    wipe Scotland or Northern Ireland out of the published file.

    Pass --cache-only to skip Overpass and only rebuild from caches.
    """
    import urllib.parse  # noqa: F401
    from build_points import main as build_main

    if "--cache-only" in sys.argv:
        print("Skipping Overpass (--cache-only); building from caches.", flush=True)
        if not (CACHE_DIR / "north-west.json").is_file():
            ensure_northwest_pbf()
        return build_main()

    try:
        payload = fetch()
        print(f"Overpass pass collected {len(payload.get('elements') or [])} raw elements (plus any PBF caches).", flush=True)
    except Exception as exc:
        print(f"Overpass fetch did not finish cleanly ({exc}). Building from existing caches.", flush=True)
    return build_main()


if __name__ == "__main__":
    # Ensure urllib.parse is visible to post_overpass without circular issues
    import urllib.parse  # noqa: F401

    # Bind parse into the function's global scope used above
    sys.exit(main())
