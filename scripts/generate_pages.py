#!/usr/bin/env python3
"""Generate static HTML pages, sitemap.xml and robots.txt.

Brand, domain and taglines come from config.json. OSM points and partner
points are counted and listed separately; this script never writes a
merged dataset.
"""

from __future__ import annotations

import json
import math
import subprocess
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACES_PATH = ROOT / "scripts" / "uk_places.json"
OSM_PATH = ROOT / "data" / "points.geojson"
PARTNER_PATH = ROOT / "data" / "partners.geojson"
CONFIG_PATH = ROOT / "config.json"

# Set in main() before pages are written, so every asset URL shares one stamp.
ASSET_VERSION = ""

def site_href(path: str = "", depth: int = 0) -> str:
    """Return a relative href that works at the domain root and under a subpath.

    depth is how many directories the page sits below the site root (0 for
    index.html, 1 for city and other section pages).
    """
    path = (path or "").lstrip("/")
    prefix = "../" * depth
    if not path:
        return prefix if prefix else "./"
    return prefix + path


def asset_version() -> str:
    """Short git hash, or a UTC timestamp if git is unavailable."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return out
    except (OSError, subprocess.CalledProcessError):
        pass
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def versioned_href(path: str, depth: int = 0) -> str:
    """Relative asset href with a ?v= cache-buster for GitHub Pages."""
    href = site_href(path, depth)
    ver = ASSET_VERSION
    sep = "&" if "?" in href else "?"
    return f"{href}{sep}v={ver}"


def load_json(path: Path, default):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(a)))


def feature_latlon(feat):
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates")
    if not coords or len(coords) < 2:
        return None
    return float(coords[1]), float(coords[0])


def features_in_city(features, city):
    out = []
    for feat in features:
        ll = feature_latlon(feat)
        if not ll:
            continue
        if haversine_km(ll[0], ll[1], city["lat"], city["lon"]) <= city["radius_km"]:
            out.append(feat)
    return out


def sync_config_js(cfg: dict) -> None:
    lines = [
        "/* SipSpot — generated from config.json. Edit config.json, then run",
        " * python3 scripts/generate_pages.py to refresh this file and the HTML pages.",
        " * config.json is the source of truth for brand, domain and map settings.",
        " */",
        "window.SIPSPOT_CONFIG = {",
    ]
    items = list(cfg.items())
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}{comma}")
    lines.append("};")
    lines.append("window.REFILLMAP_CONFIG = window.SIPSPOT_CONFIG;")
    lines.append("")
    lines.append("(function (cfg) {")
    lines.append("  if (!cfg) return;")
    lines.append("  function detectBasePath() {")
    lines.append("    var scripts = document.getElementsByTagName('script');")
    lines.append("    for (var i = 0; i < scripts.length; i++) {")
    lines.append("      var src = scripts[i].getAttribute('src') || '';")
    lines.append(r"      if (!/(?:^|\/)js\/(?:config|app|form|map-provider|pwa)\.js(?:\?|$)/.test(src)) continue;")
    lines.append("      var url = new URL(src, document.baseURI);")
    lines.append(r"      return url.pathname.replace(/\/js\/[^/]+$/, '/');")
    lines.append("    }")
    lines.append("    return '/';")
    lines.append("  }")
    lines.append("  function withBase(path) {")
    lines.append("    if (!path) return path;")
    lines.append(r"    if (/^(https?:)?\/\//i.test(path) || path.indexOf('data:') === 0 || path.indexOf('mailto:') === 0) return path;")
    lines.append("    var base = cfg.basePath || '/';")
    lines.append(r"    return base.replace(/\/+$/, '') + '/' + String(path).replace(/^\/+/, '');")
    lines.append("  }")
    lines.append(f"  var assetVersion = {json.dumps(ASSET_VERSION)};")
    lines.append("  function withVersion(url) {")
    lines.append("    if (!url) return url;")
    lines.append(r"    if (/^(https?:)?\/\//i.test(url) && url.indexOf(location.origin) !== 0) return url;")
    lines.append("    if (/[?&]v=/.test(url)) return url;")
    lines.append("    return url + (url.indexOf('?') >= 0 ? '&' : '?') + 'v=' + assetVersion;")
    lines.append("  }")
    lines.append("  cfg.basePath = detectBasePath();")
    lines.append("  cfg.assetVersion = assetVersion;")
    lines.append("  cfg.withBase = withBase;")
    lines.append("  cfg.withVersion = withVersion;")
    lines.append("  if (cfg.osmDataUrl) cfg.osmDataUrl = withVersion(withBase(cfg.osmDataUrl));")
    lines.append("  if (cfg.partnerDataUrl) cfg.partnerDataUrl = withVersion(withBase(cfg.partnerDataUrl));")
    lines.append("  if (cfg.feedback && cfg.feedback.dataUrl) cfg.feedback.dataUrl = withVersion(withBase(cfg.feedback.dataUrl));")
    lines.append("})(window.SIPSPOT_CONFIG);")
    lines.append("")
    (ROOT / "js" / "config.js").write_text("\n".join(lines), encoding="utf-8")


def brand_mark() -> str:
    return (
        '<svg class="brand-mark" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<circle cx="18" cy="18" r="18" fill="#1E88E5"/>'
        '<path d="M18 7.5c-5.2 6.2-7.2 9.4-7.2 12.2a7.2 7.2 0 0 0 14.4 0c0-2.8-2-6-7.2-12.2z" fill="#ffffff"/>'
        '<path d="M25 11c2.2 1.1 3.4 2.8 3 4.4-1.5-.2-2.8-1-3.6-2.2-.4-1.2-.3-2.2.6-2.2z" fill="#43A047"/>'
        "</svg>"
    )


def nav(cfg, current: str, depth: int = 0) -> str:
    links = [
        (site_href("", depth), "Map", "home"),
        (site_href("cities/", depth), "Cities", "cities"),
        (site_href("list-your-business/", depth), "List your venue", "list"),
        (site_href("privacy/", depth), "Privacy", "privacy"),
    ]
    parts = []
    for href, label, key in links:
        cur = ' aria-current="page"' if key == current else ""
        parts.append(f'<a href="{href}"{cur}>{escape(label)}</a>')
    return '<nav class="nav" id="site-nav" aria-label="Site">' + "".join(parts) + "</nav>"


def header(cfg, current: str, depth: int = 0) -> str:
    tagline = escape(cfg.get("tagline") or "Find it. Fill it. Go.")
    brand = escape(cfg.get("brand") or "SipSpot")
    home = site_href("", depth)
    return f"""<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="{home}" aria-label="{brand} home">
      {brand_mark()}
      <span class="brand-text">
        <span class="brand-name">{brand}</span>
        <span class="header-tagline">{tagline}</span>
      </span>
    </a>
    <button type="button" class="nav-toggle" id="nav-toggle" aria-expanded="false" aria-controls="site-nav" aria-label="Open menu">
      <span class="nav-toggle-icon" aria-hidden="true"></span>
    </button>
    {nav(cfg, current, depth)}
  </div>
</header>"""


def footer(cfg, depth: int = 0) -> str:
    brand = escape(cfg.get("brand") or "SipSpot")
    attr = escape(cfg.get("osmAttributionText") or "© OpenStreetMap contributors")
    attr_url = escape(cfg.get("osmAttributionUrl") or "https://www.openstreetmap.org/copyright")
    poster = escape(cfg.get("posterLine") or "Skip the plastic. Find a tap.")
    return f"""<footer class="site-footer">
  <div class="footer-inner">
    <p><strong>{brand}</strong> — {escape(cfg.get("tagline") or "")}</p>
    <p class="licence-note">Map points labelled as OpenStreetMap data are licensed under the <a href="https://opendatacommons.org/licenses/odbl/">ODbL 1.0</a>. {attr} — <a href="{attr_url}">{attr_url.replace("https://", "")}</a>. Partner listings are a separate dataset and are not combined with OSM data.</p>
    <p>For partner posters and window stickers: “{poster}”</p>
    <p>
      <a href="{site_href("cities/", depth)}">Cities</a> ·
      <a href="{site_href("list-your-business/", depth)}">List your venue</a> ·
      <a href="{site_href("privacy/", depth)}">Privacy</a> ·
      <a href="{site_href("terms/", depth)}">Terms</a>
    </p>
  </div>
</footer>"""


def head(cfg, title: str, description: str, canonical: str, extra: str = "", include_map: bool = False, depth: int = 0) -> str:
    brand = escape(cfg.get("brand") or "SipSpot")
    desc = escape(description)
    title_e = escape(title)
    canon = escape(canonical)
    map_css = ""
    if include_map:
        map_css = """
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">"""
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title_e}</title>
  <meta name="description" content="{desc}">
  <link rel="canonical" href="{canon}">
  <meta property="og:title" content="{title_e}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{canon}">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="en_GB">
  <meta name="theme-color" content="#1E88E5">
  <link rel="icon" href="{site_href("favicon.ico", depth)}" type="image/x-icon">
  <link rel="manifest" href="{site_href("manifest.webmanifest", depth)}">
  <link rel="apple-touch-icon" href="{site_href("icons/apple-touch-icon.png", depth)}">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="{brand}">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <meta name="mobile-web-app-capable" content="yes">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&amp;family=Source+Sans+3:wght@400;600;700&amp;display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{versioned_href('css/style.css', depth)}">{map_css}
  {extra}
</head>"""


def map_scripts(depth: int = 0) -> str:
    return f"""
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/opening_hours@3.8.0/opening_hours+deps.min.js"></script>
  <script src="{versioned_href("js/config.js", depth)}"></script>
  <script src="{versioned_href("js/map-provider.js", depth)}"></script>
  <script src="{versioned_href("js/app.js", depth)}"></script>
  <script src="{versioned_href("js/pwa.js", depth)}"></script>"""


def legend() -> str:
    return """<div class="legend" aria-label="Map key">
  <span><span class="legend-swatch fountain"></span>Public fountain</span>
  <span><span class="legend-swatch cafe"></span>Café or shop</span>
  <span><span class="legend-swatch partner"></span>Partner refill point</span>
  <span><span class="legend-swatch stale"></span><span data-stale-legend>Not updated in 3+ years</span></span>
</div>"""


def filter_chips() -> str:
    return """<div class="filters" role="group" aria-label="Filters">
  <button type="button" class="filter-chip fountain" data-filter="public_fountain" aria-pressed="false">Public fountain</button>
  <button type="button" class="filter-chip cafe" data-filter="cafe_refill" aria-pressed="false">Café or shop</button>
  <button type="button" class="filter-chip" data-filter="bottle" aria-pressed="false">Bottle-friendly</button>
  <button type="button" class="filter-chip" data-filter="filtered" aria-pressed="false">Filtered only</button>
  <button type="button" class="filter-chip" data-filter="chilled" aria-pressed="false">Chilled only</button>
  <button type="button" class="filter-chip" data-filter="open_now" aria-pressed="false">Open now</button>
  <button type="button" class="filter-chip partner" data-filter="partner" aria-pressed="false">Partner refill point</button>
  <button type="button" class="filter-chip" data-filter="hide_stale" aria-pressed="false">Hide points not updated in 3+ years</button>
</div>"""


def filters() -> str:
    """Filters sheet used on map pages. On desktop this is the chip row; on
    mobile it becomes a bottom sheet opened from the Filters button."""
    return f"""<div class="filters-sheet" id="filters-sheet">
  <div class="sheet-chrome">
    <div class="sheet-handle" aria-hidden="true"></div>
    <div class="sheet-head">
      <h2 id="filters-title">Filters</h2>
      <button type="button" class="sheet-close" id="filters-close" aria-label="Close filters"></button>
    </div>
  </div>
  <p class="policy-line">Free for anyone, no purchase needed.</p>
  {filter_chips()}
</div>"""


def legend_panel() -> str:
    return f"""<div class="legend-panel" id="legend-panel">
  <div class="legend-chrome">
    <h2 class="legend-title">Key</h2>
    <button type="button" class="sheet-close" id="legend-close" aria-label="Close key"></button>
  </div>
  {legend()}
</div>"""


def map_toolbar() -> str:
    return """<div class="map-toolbar" role="toolbar" aria-label="Map tools">
  <button type="button" class="map-tool-btn" id="filters-toggle" aria-expanded="false" aria-controls="filters-sheet">Filters</button>
  <button type="button" class="btn btn-primary js-locate" data-locate-btn>Find water near me</button>
  <button type="button" class="map-tool-btn" id="legend-toggle" aria-expanded="false" aria-controls="legend-panel">Key</button>
</div>"""


def sheet_backdrop() -> str:
    return """<div class="sheet-backdrop" id="sheet-backdrop" hidden></div>"""


def city_grid(cities, heading="Browse by city", depth: int = 0) -> str:
    items = []
    for c in cities:
        osm_n = c["osm_count"]
        label = f"{osm_n} OSM point" + ("" if osm_n == 1 else "s")
        if c.get("partner_count"):
            label += f", {c['partner_count']} partner" + ("" if c["partner_count"] == 1 else "s")
        items.append(
            f'<a href="{site_href(c["slug"] + "/", depth)}"><strong>{escape(c["name"])}</strong><span>{escape(label)}</span></a>'
        )
    return f"""<section class="cities-preview">
  <h2>{escape(heading)}</h2>
  <div class="city-grid">
    {"".join(items)}
  </div>
</section>"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")


def page_index(cfg, cities) -> str:
    brand = cfg["brand"]
    tagline = cfg.get("tagline") or "Find it. Fill it. Go."
    desc = cfg.get("metaDescription") or tagline
    url = cfg["siteUrl"].rstrip("/") + "/"
    depth = 0
    return f"""{head(cfg, f"{brand} — {tagline}", desc, url, include_map=True, depth=depth)}
<body class="home-page">
  <a class="skip-link" href="#map">Skip to map</a>
  {header(cfg, "home", depth)}
  <main>
    <section class="hero">
      <div class="wrap">
        <h1 class="tagline">{escape(tagline)}</h1>
        <p class="lede">Free drinking water and bottle-fill points across the UK. No app, no account. Free for anyone, no purchase needed. Public fountains and café taps come from OpenStreetMap; refill points listed by venues themselves are shown separately.</p>
        <p class="refill-total" data-refill-total="uk" hidden><span class="refill-total-icon" aria-hidden="true"></span><span><strong data-refill-number></strong><span data-refill-label></span></span></p>
        <div class="hero-actions">
          <button type="button" class="btn btn-primary js-locate" id="locate-btn">Find water near me</button>
          <a class="btn btn-ghost" href="{site_href("list-your-business/", depth)}">List your venue</a>
        </div>
      </div>
    </section>
    <div class="map-stage">
      <div class="wrap map-stage-inner">
        <p class="status" id="status" role="status"></p>
        {filters()}
        {legend_panel()}
        <div class="map-layout">
          <div class="map-pane">
            {map_toolbar()}
            <div id="map" role="application" aria-label="Map of drinking-water points"></div>
          </div>
          <div class="list-pane">
            <h2>Points</h2>
            <p class="results-meta" id="results-meta">Loading…</p>
            <ul class="result-list" id="result-list"></ul>
          </div>
        </div>
      </div>
    </div>
    <div class="wrap below-map">
      {city_grid(cities, "Free water refill points by city", depth=depth)}
    </div>
  </main>
  {sheet_backdrop()}
  {footer(cfg, depth)}
  {map_scripts(depth)}
</body>
</html>"""


def faq_jsonld(city_name: str, osm_count: int) -> str:
    faqs = [
        (
            f"Are these water refill points in {city_name} free?",
            f"Yes. Every point on SipSpot is free for anyone, with no purchase needed. OpenStreetMap points tagged as charging a fee, or as customers-only, private or no public access, are left off the map. Partner refill points, listed by the venue itself, must be free to walk in and use.",
        ),
        (
            f"Where does the {city_name} map data come from?",
            "Public fountains, taps and café fill points come from OpenStreetMap and are updated from the official OSM database. Partner refill points are taps and water coolers that venues list themselves. They are kept as a separate list and are never merged with the OSM data.",
        ),
        (
            "How often is the map updated?",
            "OpenStreetMap points are refreshed weekly from the Overpass API. Each popup shows the date the point was last edited on OpenStreetMap. Partner listings show the date they were last verified.",
        ),
        (
            "What if a point is wrong?",
            "For an OpenStreetMap point, use the “Is this wrong? Fix on OpenStreetMap” link in the popup. For a partner refill point, use the List your venue page to get in touch.",
        ),
        (
            "When is a point open?",
            "Opening hours are shown on every point. If hours are missing we say “Hours not listed”. The Open now filter only includes points whose hours we can parse and that are open at the moment, using your device clock.",
        ),
        (
            "How do I add my venue?",
            "Use the List your venue page. Shops, cafés, offices, councils, shopping centres, stations and chains can list their own free tap or water cooler. There is no account, password or payment. A short form sends your details by email or a form endpoint.",
        ),
    ]
    entities = []
    for q, a in faqs:
        entities.append({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a},
        })
    blob = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": entities,
    }
    return json.dumps(blob, ensure_ascii=False)


def feature_key(feat) -> tuple:
    props = feat.get("properties") or {}
    return (props.get("osm_type"), props.get("osm_id"), props.get("id"), id(feat) if not (props.get("osm_type") or props.get("osm_id") or props.get("id")) else None)


def union_features(*groups):
    seen = set()
    out = []
    for feats in groups:
        for feat in feats or []:
            key = feature_key(feat)
            if key in seen:
                continue
            seen.add(key)
            out.append(feat)
    return out


CITY_MERGES = {
    "manchester": {"absorb": ("salford",), "name": "Manchester and Salford"},
    "bournemouth": {"absorb": ("poole",), "name": "Bournemouth and Poole"},
}


def apply_city_merges(cities):
    """Merge neighbouring city pages and return (public_cities, redirects)."""
    by_slug = {c["slug"]: c for c in cities}
    redirects = {}
    for keep, spec in CITY_MERGES.items():
        host = by_slug.get(keep)
        if not host:
            continue
        centres = [{"lat": host["lat"], "lon": host["lon"], "radius_km": host["radius_km"]}]
        for slug in spec["absorb"]:
            other = by_slug.get(slug)
            if not other:
                continue
            host["_osm"] = union_features(host.get("_osm"), other.get("_osm"))
            host["_partners"] = union_features(host.get("_partners"), other.get("_partners"))
            centres.append({"lat": other["lat"], "lon": other["lon"], "radius_km": other["radius_km"]})
            redirects[slug] = keep
        host["name"] = spec["name"]
        host["centres"] = centres
        host["osm_count"] = len(host.get("_osm") or [])
        host["partner_count"] = len(host.get("_partners") or [])
        host["lat"] = sum(c["lat"] for c in centres) / len(centres)
        host["lon"] = sum(c["lon"] for c in centres) / len(centres)
    public = [c for c in cities if c["slug"] not in redirects]
    public.sort(key=lambda c: c["name"])
    return public, redirects


def category_counts(feats) -> dict:
    counts = {"public_fountain": 0, "cafe_refill": 0, "other": 0}
    for feat in feats or []:
        cat = (feat.get("properties") or {}).get("category") or "other"
        if cat not in counts:
            cat = "other"
        counts[cat] += 1
    return counts


def city_intro_paragraphs(city, all_cities) -> list[str]:
    """2–3 short sentences from our own counts only. No invented claims."""
    name = city["name"]
    n = city["osm_count"]
    pts = "point" if n == 1 else "points"
    cats = category_counts(city.get("_osm"))
    fountains = cats["public_fountain"]
    cafes = cats["cafe_refill"]
    if fountains and cafes:
        mix = (
            f"{fountains} are public fountains, taps or bottle-refill points, "
            f"and {cafes} {'is a' if cafes == 1 else 'are'} café or shop refill"
            f"{'' if cafes == 1 else 's'}."
        )
    elif fountains:
        mix = f"{fountains} are public fountains, taps or bottle-refill points."
    elif cafes:
        mix = f"{cafes} {'is a' if cafes == 1 else 'are'} café or shop refill{'' if cafes == 1 else 's'}."
    else:
        mix = ""

    slug = city["slug"]
    if slug == "london":
        largest = max((c["osm_count"] for c in all_cities), default=0)
        lead = f"London has {n} drinking {pts} on SipSpot"
        if n >= largest:
            lead += ", more than any other city in our gazetteer"
        lead += "."
        paras = [lead]
        if cafes:
            paras.append(
                f"Almost all are public fountains, taps or bottle-refill points; {cafes} are café or shop refills."
            )
        elif mix:
            paras.append(mix)
        r = city.get("radius_km")
        if r:
            rtxt = int(r) if float(r).is_integer() else r
            paras.append(f"The map covers points within {rtxt} km of the centre.")
        return paras
    if slug in ("manchester", "bournemouth"):
        paras = [f"{name} have {n} drinking {pts} on SipSpot."]
        if mix:
            paras.append(mix)
        if slug == "manchester":
            paras.append("This page covers both Manchester and Salford, and the old Salford address now brings you here.")
        else:
            paras.append("This page covers both Bournemouth and Poole, and the old Poole address now brings you here.")
        return paras
    if slug in ("bristol", "birmingham", "cardiff"):
        r = city.get("radius_km")
        rtxt = int(r) if r is not None and float(r).is_integer() else r
        paras = [f"{name} has {n} drinking {pts} on SipSpot, within {rtxt} km of the centre."]
        if mix:
            paras.append(mix)
        return paras
    return []


def breadcrumb_jsonld(cfg, city) -> str:
    base = cfg["siteUrl"].rstrip("/")
    blob = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": base + "/"},
            {"@type": "ListItem", "position": 2, "name": "Cities", "item": base + "/cities/"},
            {"@type": "ListItem", "position": 3, "name": city["name"], "item": base + f"/{city['slug']}/"},
        ],
    }
    return json.dumps(blob, ensure_ascii=False)


def page_redirect(cfg, from_slug: str, to_slug: str, to_name: str) -> str:
    dest = cfg["siteUrl"].rstrip("/") + f"/{to_slug}/"
    rel = site_href(f"{to_slug}/", 1)
    brand = escape(cfg.get("brand") or "SipSpot")
    title = f"Redirecting to {escape(to_name)} — {brand}"
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta http-equiv="refresh" content="0; url={escape(dest)}">
  <link rel="canonical" href="{escape(dest)}">
  <meta name="robots" content="noindex">
  <meta name="theme-color" content="#1E88E5">
  <link rel="icon" href="{site_href("favicon.ico", 1)}" type="image/x-icon">
</head>
<body>
  <p>This page has moved to <a href="{rel}">free water refill points in {escape(to_name)}</a>.</p>
</body>
</html>
"""


def page_city(cfg, city, osm_feats, partner_feats, all_cities=None) -> str:
    brand = cfg["brand"]
    name = city["name"]
    title = f"Free water refill points in {name} — {brand}"
    desc = (
        f"{cfg.get('tagline') or 'Find it. Fill it. Go.'} "
        f"{city['osm_count']} drinking points in {name}."
    )
    url = cfg["siteUrl"].rstrip("/") + f"/{city['slug']}/"
    depth = 1
    faq = faq_jsonld(name, city["osm_count"])
    crumbs = breadcrumb_jsonld(cfg, city)
    extra = (
        f'<script type="application/ld+json">{faq}</script>\n'
        f'  <script type="application/ld+json">{crumbs}</script>'
    )
    city_payload = {
        "slug": city["slug"],
        "name": city["name"],
        "lat": city["lat"],
        "lon": city["lon"],
        "radius_km": city["radius_km"],
        "zoom": city.get("zoom", 12),
    }
    if city.get("centres"):
        city_payload["centres"] = city["centres"]
    partner_note = ""
    if city.get("partner_count"):
        n = city["partner_count"]
        partner_note = f" There {'is' if n == 1 else 'are'} also {n} partner refill point{'s' if n != 1 else ''} in this area, listed by the venue{'s' if n != 1 else ''} and shown separately."
    intros = city_intro_paragraphs(city, all_cities or [])
    if intros:
        first, *rest = intros
        intro_html = f'<p class="lede">{escape(first)}</p>' + "".join(f"<p>{escape(p)}</p>" for p in rest)
        if partner_note:
            intro_html += f"<p>{escape(partner_note.strip())}</p>"
    else:
        intro_html = f'<p class="lede">{city["osm_count"]} drinking point{"s" if city["osm_count"] != 1 else ""} in and around {escape(name)}.{partner_note}</p>'
    # No sponsor strip: partner refill points never name a supplier or cooler company.
    return f"""{head(cfg, title, desc, url, extra=extra, include_map=True, depth=depth)}
<body class="city-page">
  <a class="skip-link" href="#map">Skip to map</a>
  {header(cfg, "cities", depth)}
  <main class="page-body">
    <div class="wrap city-intro">
      <h1>Free water refill points in {escape(name)}</h1>
      {intro_html}
      <p class="refill-total" data-refill-total="city" hidden><span class="refill-total-icon" aria-hidden="true"></span><span><strong data-refill-number></strong><span data-refill-label></span></span></p>
      <div class="hero-actions">
        <button type="button" class="btn btn-primary js-locate" id="locate-btn">Find water near me</button>
      </div>
      <p class="status" id="status" role="status"></p>
    </div>
    <div class="map-stage">
      <div class="wrap map-stage-inner">
        {filters()}
        {legend_panel()}
        <div class="map-layout">
          <div class="map-pane">
            {map_toolbar()}
            <div id="map" role="application" aria-label="Map of drinking-water points in {escape(name)}"></div>
          </div>
          <div class="list-pane">
            <h2>Points in {escape(name)}</h2>
            <p class="results-meta" id="results-meta">Loading…</p>
            <ul class="result-list" id="result-list"></ul>
          </div>
        </div>
      </div>
    </div>
    <div class="wrap below-map">
      <section class="faq">
        <h2>Frequently asked questions</h2>
        <details open>
          <summary>Are these points free?</summary>
          <p>Yes. Free for anyone, no purchase needed. Points tagged as charging a fee, or as customers-only, private or no public access, are not listed.</p>
        </details>
        <details>
          <summary>When is a point open?</summary>
          <p>Hours are shown on every point. If they are missing we say “Hours not listed”. The Open now filter only includes points whose hours we can parse and that are open at the moment.</p>
        </details>
        <details>
          <summary>Where does the data come from?</summary>
          <p>Public fountains, taps and café fill points come from OpenStreetMap. Partner refill points are listed by the venues themselves, kept as a separate list and never merged with OSM data.</p>
        </details>
        <details>
          <summary>What if a point is wrong?</summary>
          <p>Use “Is this wrong? Fix on OpenStreetMap” in the popup, or <a href="{site_href("list-your-business/", depth)}">contact us</a> about a partner refill point.</p>
        </details>
      </section>
    </div>
  </main>
  {sheet_backdrop()}
  <script type="application/json" id="city-data">{json.dumps(city_payload, ensure_ascii=False)}</script>
  {footer(cfg, depth)}
  {map_scripts(depth)}
</body>
</html>"""


def page_cities(cfg, cities) -> str:
    brand = cfg["brand"]
    tagline = cfg.get("tagline") or "Find it. Fill it. Go."
    desc = f"{tagline} Browse free drinking-water points in UK cities on {brand}."
    url = cfg["siteUrl"].rstrip("/") + "/cities/"
    depth = 1
    return f"""{head(cfg, f"Cities — {brand}", desc, url, depth=depth)}
<body>
  {header(cfg, "cities", depth)}
  <main class="page-body">
    <div class="wrap">
      <h1>Cities</h1>
      <p class="lede">Static pages for major UK cities and any place in our gazetteer with 10 or more drinking points.</p>
      {city_grid(cities, "All city pages", depth=depth)}
    </div>
  </main>
  {footer(cfg, depth)}
  <script src="{versioned_href("js/config.js", depth)}"></script>
  <script src="{versioned_href("js/pwa.js", depth)}"></script>
</body>
</html>"""


def page_privacy(cfg) -> str:
    brand = cfg["brand"]
    desc = f"Privacy information for {brand}."
    url = cfg["siteUrl"].rstrip("/") + "/privacy/"
    email = escape(cfg.get("contactEmail") or "")
    depth = 1
    return f"""{head(cfg, f"Privacy — {brand}", desc, url, depth=depth)}
<body>
  {header(cfg, "privacy", depth)}
  <main class="page-body">
    <div class="wrap prose">
      <h1>Privacy</h1>
      <p>{escape(brand)} is a free map of drinking-water and bottle-fill points in the UK. You do not need an account, and we do not ask you to sign in.</p>
      <h2>Who runs this site</h2>
      <p>{escape(brand)} is run by J Skelton, a sole trader in the United Kingdom. If you have a question about this site or about your information, email <a href="mailto:{email}">{email}</a>.</p>
      <h2>What we collect</h2>
      <p>The site is a set of static files. We do not run a user database, and we have not installed any analytics.</p>
      <p>If you use the “List your venue” form, it opens your own email app with the details you typed and addresses the message to {email}. We only see that information if you send the email. Please do not include a password or payment details. We will use what you send only to follow up about a listing.</p>
      <p>We do not set cookies. Taps on “I filled up here”, “Still here” and “Gone” are counted anonymously against that map point, so we can show totals such as “12 refills logged by SipSpot users”. We do not ask who you are. To stop spam, our counter briefly uses your IP address in hashed (scrambled) form to limit repeat taps. The IP address itself is not stored, and the hashed key is deleted within about a day. Your browser also keeps a note of your taps in local storage (not a cookie), so the same point does not ask again on this device.</p>
      <p>If you dismiss the “Install app” tip, that choice is also stored in your browser’s local storage, so we do not show it again on this device.</p>
      <h2>Location</h2>
      <p>If you tap “Find water near me”, your browser may share your location with this page so the map can centre on you and estimate a walking distance. That location stays in your browser. It is not sent to us.</p>
      <h2>Map tiles, directions and other services</h2>
      <p>The map background tiles are loaded from CARTO (basemaps.cartocdn.com). CARTO sees your IP address, as any website host would.</p>
      <p>The site also loads fonts from Google Fonts (fonts.googleapis.com and fonts.gstatic.com) and map scripts from unpkg.com and cdn.jsdelivr.net. Those providers may also see your IP address.</p>
      <p>The Directions buttons open Google Maps or Apple Maps, which have their own privacy policies. We do not receive the route you follow.</p>
      <h2>Hosting</h2>
      <p>The site is hosted on GitHub Pages. The sipspot.co.uk domain is set up with Cloudflare DNS. The tap counter runs on Cloudflare Workers.</p>
      <h2>Map data</h2>
      <p>Public fountain, tap and café fill-point data comes from OpenStreetMap and is licensed under the Open Database Licence (ODbL 1.0). © OpenStreetMap contributors — <a href="https://www.openstreetmap.org/copyright">www.openstreetmap.org/copyright</a>. Partner listings, when we add any, are a separate file and are not combined with the OpenStreetMap data.</p>
      <h2>Your rights</h2>
      <p>Because we are in the United Kingdom, UK GDPR applies to personal information we hold — for example an email you send us. You can ask to see that information, have it corrected or deleted, or ask us to restrict or object to how we use it. To do that, email <a href="mailto:{email}">{email}</a>.</p>
      <p>You also have the right to complain to the Information Commissioner’s Office (ICO) at <a href="https://www.ico.org.uk">ico.org.uk</a>.</p>
    </div>
  </main>
  {footer(cfg, depth)}
  <script src="{versioned_href("js/config.js", depth)}"></script>
  <script src="{versioned_href("js/pwa.js", depth)}"></script>
</body>
</html>"""


def page_terms(cfg) -> str:
    brand = cfg["brand"]
    desc = f"Terms of use for {brand}."
    url = cfg["siteUrl"].rstrip("/") + "/terms/"
    email = escape(cfg.get("contactEmail") or "")
    depth = 1
    return f"""{head(cfg, f"Terms of use — {brand}", desc, url, depth=depth)}
<body>
  {header(cfg, "", depth)}
  <main class="page-body">
    <div class="wrap prose">
      <h1>Terms of use</h1>
      <p>{escape(brand)} is an information service run by J Skelton, a sole trader in the United Kingdom. It helps you find drinking-water and bottle-fill points that have been mapped as free to use. If you have a question, email <a href="mailto:{email}">{email}</a>.</p>
      <p>The map is a starting point, not a guarantee. Always check a refill point yourself before you rely on it. A tap may be out of order, closed, or no longer there.</p>
      <p>Points come mainly from OpenStreetMap, which is updated by volunteers, and may also include partner refill points that venues list themselves, which we keep separately. Hours, access and water type can be wrong or out of date. We do not inspect every point, and we give no warranty that a point will be available, safe or suitable.</p>
      <p>Public fountain, tap and café fill-point data is © OpenStreetMap contributors and licensed under the Open Database Licence (ODbL 1.0). See <a href="https://www.openstreetmap.org/copyright">openstreetmap.org/copyright</a>.</p>
    </div>
  </main>
  {footer(cfg, depth)}
  <script src="{versioned_href("js/config.js", depth)}"></script>
  <script src="{versioned_href("js/pwa.js", depth)}"></script>
</body>
</html>"""


def page_list_business(cfg) -> str:
    brand = cfg["brand"]
    tagline = cfg.get("tagline") or "Find it. Fill it. Go."
    poster = cfg.get("posterLine") or "Skip the plastic. Find a tap."
    desc = f"List your venue’s free tap or water cooler on {brand}. Free for anyone, no purchase needed. {poster}"
    url = cfg["siteUrl"].rstrip("/") + "/list-your-business/"
    email = escape(cfg.get("contactEmail") or "")
    depth = 1
    return f"""{head(cfg, f"List your venue — {brand}", desc, url, depth=depth)}
<body>
  {header(cfg, "list", depth)}
  <main class="page-body">
    <div class="wrap">
      <h1>List your venue</h1>
      <p class="lede">Have a tap or water cooler where anyone can fill a bottle for free, with no purchase needed? List it yourself and it will appear on {escape(brand)} as a partner refill point. There is no account, no password and no payment at this stage. {escape(tagline)}</p>
      <p>Shops, cafés, offices, councils, shopping centres, stations and chains are all welcome. Your listing shows your venue’s name, address, hours and water type under a simple “Partner refill point” label. We never show the name of the company that supplies or services your tap or cooler.</p>
      <p>Looking after lots of sites, for example as a council, water company, shopping centre or station landlord, or a chain? Email <a href="mailto:{email}">{email}</a> and we can add your locations together.</p>
      <div class="poster-card" aria-label="Partner poster wording">
        <p class="poster-brand">{escape(brand)}</p>
        <p class="poster-line">{escape(poster)}</p>
        <p class="poster-caption">Suggested line for posters and window stickers at your refill point.</p>
      </div>
      <form class="form" id="partner-form" novalidate>
        <label>Venue or organisation name
          <input type="text" name="business" required autocomplete="organization">
        </label>
        <label>Type of venue
          <select name="venue_type">
            <option value="shop">Shop</option>
            <option value="cafe">Café, pub or restaurant</option>
            <option value="office">Office or workplace</option>
            <option value="council">Council or public building</option>
            <option value="shopping centre">Shopping centre</option>
            <option value="station">Station or transport hub</option>
            <option value="chain">Chain with several sites</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>What you offer
          <select name="refill_type">
            <option value="tap">Tap</option>
            <option value="water cooler">Water cooler</option>
            <option value="bottle-fill station">Bottle-fill station</option>
          </select>
        </label>
        <label>Your name
          <input type="text" name="contact_name" required autocomplete="name">
        </label>
        <label>Email
          <input type="email" name="email" required autocomplete="email">
        </label>
        <label>Address
          <input type="text" name="address" required autocomplete="street-address">
        </label>
        <label>Postcode
          <input type="text" name="postcode" required autocomplete="postal-code">
        </label>
        <label>Opening hours <span class="hint">(optional — shown as “Hours not listed” if left blank)</span>
          <input type="text" name="hours" placeholder="Mo-Fr 08:00-17:00">
        </label>
        <label>Water type
          <select name="water_type">
            <option value="tap">Tap water</option>
            <option value="filtered">Filtered water</option>
            <option value="chilled filtered">Chilled filtered water</option>
            <option value="unknown">Unknown</option>
          </select>
        </label>
        <label>Chilled
          <select name="chilled">
            <option value="no">No</option>
            <option value="yes">Yes</option>
          </select>
        </label>
        <label class="check">
          <input type="checkbox" name="walk_in_free" value="yes" required>
          Free for anyone, no purchase needed (required)
        </label>
        <label>Notes <span class="hint">(optional)</span>
          <textarea name="notes" placeholder="Where the tap or cooler is, any access notes"></textarea>
        </label>
        <p class="hint">This form does not collect a password or take payment. It opens an email to {email} with the details you typed.</p>
        <button type="submit" class="btn btn-primary">Send listing request</button>
        <p class="status" id="form-status" role="status"></p>
      </form>
    </div>
  </main>
  {footer(cfg, depth)}
  <script src="{versioned_href("js/config.js", depth)}"></script>
  <script src="{versioned_href("js/form.js", depth)}"></script>
  <script src="{versioned_href("js/pwa.js", depth)}"></script>
</body>
</html>"""


def choose_cities(places, osm_features, partner_features):
    ranked = []
    for place in places:
        osm = features_in_city(osm_features, place)
        partners = features_in_city(partner_features, place)
        row = dict(place)
        row["osm_count"] = len(osm)
        row["partner_count"] = len(partners)
        row["_osm"] = osm
        row["_partners"] = partners
        ranked.append(row)
    by_pop = sorted(ranked, key=lambda c: c.get("population") or 0, reverse=True)
    top30 = by_pop[:30]
    chosen_slugs = {c["slug"] for c in top30}
    extras = [c for c in ranked if c["slug"] not in chosen_slugs and c["osm_count"] >= 10]
    extras.sort(key=lambda c: (-c["osm_count"], c["name"]))
    chosen = top30 + extras
    chosen.sort(key=lambda c: c["name"])
    return chosen


def write_sitemap(cfg, cities) -> None:
    base = cfg["siteUrl"].rstrip("/")
    today = date.today().isoformat()
    urls = [
        (base + "/", "1.0"),
        (base + "/cities/", "0.8"),
        (base + "/list-your-business/", "0.6"),
        (base + "/privacy/", "0.5"),
        (base + "/terms/", "0.5"),
    ]
    for c in cities:
        urls.append((f"{base}/{c['slug']}/", "0.7"))
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, pri in urls:
        parts.append("  <url>")
        parts.append(f"    <loc>{escape(loc)}</loc>")
        parts.append(f"    <lastmod>{today}</lastmod>")
        parts.append(f"    <priority>{pri}</priority>")
        parts.append("  </url>")
    parts.append("</urlset>")
    write(ROOT / "sitemap.xml", "\n".join(parts))


def write_robots(cfg) -> None:
    sitemap = cfg["siteUrl"].rstrip("/") + "/sitemap.xml"
    write(ROOT / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {sitemap}\n")



def sync_service_worker_version() -> None:
    """Keep sw.js CACHE_VERSION in line with the site-wide ?v= stamp."""
    path = ROOT / "sw.js"
    if not path.is_file():
        raise SystemExit("sw.js is missing; cannot stamp the service worker cache")
    text = path.read_text(encoding="utf-8")
    needle = "const CACHE_VERSION = "
    start = text.find(needle)
    if start < 0:
        raise SystemExit("Could not update CACHE_VERSION in sw.js")
    end = text.find("\n", start)
    updated = text[:start] + f'{needle}"{ASSET_VERSION}";' + text[end:]
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def main() -> int:
    global ASSET_VERSION
    cfg = load_json(CONFIG_PATH, {})
    if not cfg.get("brand"):
        raise SystemExit("config.json missing or incomplete")
    ASSET_VERSION = asset_version()
    print(f"Asset version: {ASSET_VERSION}")
    sync_config_js(cfg)
    sync_service_worker_version()

    places = load_json(PLACES_PATH, [])
    osm = load_json(OSM_PATH, {}).get("features") or []
    partners = load_json(PARTNER_PATH, {}).get("features") or []

    cities = choose_cities(places, osm, partners)
    cities, redirects = apply_city_merges(cities)
    public_cities = [{k: v for k, v in c.items() if not k.startswith("_")} for c in cities]
    write(ROOT / "data" / "cities.json", json.dumps(public_cities, ensure_ascii=False, indent=2))

    write(ROOT / "index.html", page_index(cfg, public_cities))
    write(ROOT / "cities" / "index.html", page_cities(cfg, public_cities))
    write(ROOT / "privacy" / "index.html", page_privacy(cfg))
    write(ROOT / "terms" / "index.html", page_terms(cfg))
    write(ROOT / "list-your-business" / "index.html", page_list_business(cfg))

    by_slug = {c["slug"]: c for c in cities}
    for from_slug, to_slug in redirects.items():
        dest = by_slug[to_slug]
        write(ROOT / from_slug / "index.html", page_redirect(cfg, from_slug, to_slug, dest["name"]))

    for city in cities:
        write(ROOT / city["slug"] / "index.html", page_city(cfg, city, city["_osm"], city["_partners"], cities))

    write_sitemap(cfg, public_cities)
    write_robots(cfg)

    if redirects:
        print("Redirects: " + ", ".join(f"{a} → {b}" for a, b in sorted(redirects.items())))
    print(f"Generated {len(cities)} city pages from {len(osm)} OSM points and {len(partners)} partner points")
    print("Top 30 by population are always included; additional places need 10+ OSM points.")
    for c in sorted(public_cities, key=lambda x: (-x["osm_count"], x["name"]))[:15]:
        print(f"  {c['name']}: {c['osm_count']} OSM, {c['partner_count']} partners")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
