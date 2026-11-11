#!/usr/bin/env python3
"""Infer water type and chilled flags from OSM tags, conservatively.

Filtered is only set from an explicit tag (or a description that actually
mentions a filter). Chilled is only set from an explicit chilled/cooled tag.
Plain public fountains and taps default to tap water; café and shop refill
points default to unknown. This module never guesses Filtered or Chilled.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

YES = {"yes", "true", "1"}
NO = {"no", "false", "0"}

WATER_TYPE_LABELS = {
    "tap": "Tap water",
    "filtered": "Filtered water",
    "chilled_filtered": "Chilled filtered water",
    "unknown": "Unknown",
}

# Partner CSV / form values mapped to the stored water_type key.
WATER_TYPE_ALIASES = {
    "tap": "tap",
    "tap water": "tap",
    "mains": "tap",
    "mains water": "tap",
    "filtered": "filtered",
    "filtered water": "filtered",
    "filter": "filtered",
    "chilled filtered": "chilled_filtered",
    "chilled_filtered": "chilled_filtered",
    "chilled-filtered": "chilled_filtered",
    "chilled filtered water": "chilled_filtered",
    "unknown": "unknown",
    "": "unknown",
}

FILTER_TAG_KEYS = ("drinking_water:filtered", "water_filter")
CHILL_TAG_KEYS = ("drinking_water:chilled", "chilled", "drinking_water:cooled", "cooled")
FILTER_YES_VALUES = YES | {"filtered", "ro", "reverse_osmosis", "carbon", "uv"}
CHILL_YES_VALUES = YES | {"chilled", "cooled", "cold"}

FILTER_MENTION = re.compile(
    r"\b(filtered|filtration|water filter|reverse osmosis|reverse-osmosis)\b",
    re.I,
)
FILTER_NEGATION = re.compile(
    r"\b(unfiltered|not filtered|no filter|without (a )?filter)\b",
    re.I,
)
PAID_VALUES = YES | {"paid"}


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def is_paid(tags: dict | None) -> bool:
    """fee=yes (and obvious equivalents) are excluded."""
    return _norm((tags or {}).get("fee")) in PAID_VALUES

RESTRICTED_ACCESS = {"customers", "private", "no"}


def is_restricted_access(tags: dict | None) -> bool:
    """Walk-in only: customers, private and no access are excluded."""
    return _norm((tags or {}).get("access")) in RESTRICTED_ACCESS


def is_excluded_osm(tags: dict | None) -> bool:
    """SipSpot lists only free walk-in fills."""
    return is_paid(tags) or is_restricted_access(tags)


def is_walk_in_free(value) -> bool:
    if isinstance(value, bool):
        return value is True
    return _norm(str(value) if value is not None else "") in YES


def tag_truth(tags: dict, keys: tuple[str, ...], yes_values: set[str]) -> bool | None:
    """Return True/False if an explicit tag is present, else None. Never guess."""
    seen_no = False
    for key in keys:
        if key not in (tags or {}):
            continue
        val = _norm(tags.get(key))
        if val in yes_values:
            return True
        if val in NO:
            seen_no = True
    if seen_no:
        return False
    return None


def infer_osm_chilled(tags: dict | None) -> bool | None:
    """Only set chilled when a real OSM tag says so."""
    return tag_truth(tags or {}, CHILL_TAG_KEYS, CHILL_YES_VALUES)


def infer_osm_water_type(tags: dict | None, category: str | None) -> str:
    tags = tags or {}
    filtered = tag_truth(tags, FILTER_TAG_KEYS, FILTER_YES_VALUES)
    if filtered is True:
        return "filtered"

    text = " ".join(t for t in (tags.get("description"), tags.get("note")) if t)
    if text and not FILTER_NEGATION.search(text) and FILTER_MENTION.search(text):
        return "filtered"

    if category == "public_fountain":
        return "tap"
    return "unknown"


def water_type_label(key: str | None) -> str:
    return WATER_TYPE_LABELS.get(key or "unknown", "Unknown")


def parse_partner_water_type(raw: str | None) -> str:
    return WATER_TYPE_ALIASES.get(_norm(raw), "unknown")


def parse_partner_chilled(raw: str | None, water_type: str | None) -> bool | None:
    if water_type == "chilled_filtered":
        return True
    val = _norm(raw)
    if val in YES or val in {"chilled", "cooled"}:
        return True
    if val in NO:
        return False
    return None


def osm_tags_from_props(props: dict) -> dict:
    """Rebuild a tag-like dict from stored feature properties (for post-processing)."""
    tags = {}
    for key in (
        "description",
        "note",
        "fee",
        "amenity",
        "man_made",
        "drinking_water",
        "drinking_water:refill",
        "drinking_water:filtered",
        "water_filter",
        "drinking_water:chilled",
        "chilled",
        "drinking_water:cooled",
        "cooled",
        "opening_hours",
    ):
        if props.get(key) not in (None, ""):
            tags[key] = props[key]
    return tags


def apply_osm_attributes(props: dict, tags: dict | None = None) -> dict:
    source_tags = dict(osm_tags_from_props(props))
    if tags:
        source_tags.update({k: v for k, v in tags.items() if v not in (None, "")})
    category = props.get("category")
    water_type = infer_osm_water_type(source_tags, category)
    chilled = infer_osm_chilled(source_tags)
    props["water_type"] = water_type
    props["water_type_label"] = water_type_label(water_type)
    props["chilled"] = chilled
    for key in ("drinking_water:filtered", "water_filter", "drinking_water:chilled", "chilled", "note"):
        if key in source_tags and key not in ("chilled",) or (
            key in source_tags and key != "chilled"
        ):
            if key in ("drinking_water:filtered", "water_filter", "drinking_water:chilled", "note"):
                props[key] = source_tags[key]
    # Store OSM chilled tag separately if present so it is not confused with the bool.
    if "chilled" in source_tags and props.get("chilled") is not None:
        props["chilled_tag"] = source_tags["chilled"]
    return props


# OSM nodes hidden by hand: mapping duplicates (e.g. 15 unnamed fountains at
# Sayer Court, Peterborough; only 5831980249 is kept). Hidden 11 Nov 2026.
HIDDEN_OSM_IDS = {5831980250, 5832597972, 5832597973, 5832597974, 5832597975, 5832597976, 5832597977, 5832597978, 5832597979, 5832597980, 5832597981, 5832597982, 5832597983, 5832597984}


def postprocess_osm_geojson(path: Path) -> dict:
    """Drop paid points and attach water_type / chilled on an existing OSM file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = []
    skipped_fee = 0
    for feat in data.get("features") or []:
        props = feat.get("properties") or {}
        if props.get("osm_id") in HIDDEN_OSM_IDS:
            continue
        if is_excluded_osm(props) or is_excluded_osm(osm_tags_from_props(props)):
            skipped_fee += 1
            continue
        feat["properties"] = apply_osm_attributes(props)
        kept.append(feat)
    data["features"] = kept
    counts = data.get("counts") or {}
    counts["total"] = len(kept)
    counts["skipped_fee_or_restricted"] = counts.get("skipped_fee_or_restricted", 0) + skipped_fee
    counts["water_tap"] = sum(1 for f in kept if f["properties"].get("water_type") == "tap")
    counts["water_filtered"] = sum(1 for f in kept if f["properties"].get("water_type") == "filtered")
    counts["water_unknown"] = sum(1 for f in kept if f["properties"].get("water_type") == "unknown")
    counts["chilled_yes"] = sum(1 for f in kept if f["properties"].get("chilled") is True)
    data["counts"] = counts
    data["policy"] = "SipSpot lists only free walk-in fills. Points tagged fee=yes or access=customers/private/no are excluded."
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return counts


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data" / "points.geojson"
    print(json.dumps(postprocess_osm_geojson(target), indent=2))
