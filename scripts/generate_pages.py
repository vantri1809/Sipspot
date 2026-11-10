#!/usr/bin/env python3
"""Generate static HTML pages, sitemap.xml and robots.txt.

Brand, domain and taglines come from config.json. OSM points and partner
points are counted and listed separately; this script never writes a
merged dataset.
"""

from __future__ import annotations

import json
import math
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACES_PATH = ROOT / "scripts" / "uk_places.json"
OSM_PATH = ROOT / "data" / "points.geojson"
PARTNER_PATH = ROOT / "data" / "partners.geojson"
CONFIG_PATH = ROOT / "config.json"

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
    lines.append(r"      if (!/(?:^|\/)js\/(?:config|app|form|map-provider)\.js(?:\?|$)/.test(src)) continue;")
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
    lines.append("  cfg.basePath = detectBasePath();")
    lines.append("  cfg.withBase = withBase;")
    lines.append("  if (cfg.osmDataUrl) cfg.osmDataUrl = withBase(cfg.osmDataUrl);")
    lines.append("  if (cfg.partnerDataUrl) cfg.partnerDataUrl = withBase(cfg.partnerDataUrl);")
    lines.append("  if (cfg.feedback && cfg.feedback.dataUrl) cfg.feedback.dataUrl = withBase(cfg.feedback.dataUrl);")
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
        (site_href("list-your-business/", depth), "List your business", "list"),
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
      <a href="{site_href("list-your-business/", depth)}">List your business</a> ·
      <a href="{site_href("privacy/", depth)}">Privacy</a>
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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&amp;family=Source+Sans+3:wght@400;600;700&amp;display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{site_href('css/style.css', depth)}">{map_css}
  {extra}
</head>"""


def map_scripts(depth: int = 0) -> str:
    return f"""
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/opening_hours@3.8.0/opening_hours+deps.min.js"></script>
  <script src="{site_href("js/config.js", depth)}"></script>
  <script src="{site_href("js/map-provider.js", depth)}"></script>
  <script src="{site_href("js/app.js", depth)}"></script>"""


def ad_slot(placement: str, depth: int = 0) -> str:
    return f"""<aside class="ad-slot" data-ad-placement="{escape(placement)}" aria-label="Advertisement">
  <p class="label">Advertisement</p>
  <p>AdSense slot — {escape(placement)}. Not shown over the map. A cookie consent banner must be added before ads go live. See the <a href="{site_href("privacy/", depth)}">privacy page</a>.</p>
</aside>"""


def affiliate_slot() -> str:
    return """<aside class="affiliate-slot" aria-label="Recommended reusable bottles">
  <p class="label">Affiliate</p>
  <h2>Recommended reusable bottles</h2>
  <p>Placeholder for affiliate links to reusable bottles. Replace with your chosen programme (for example Amazon Associates) before launch. Disclose affiliate relationships on the privacy page.</p>
  <div class="affiliate-items">
    <div class="affiliate-item">Bottle 1 — placeholder</div>
    <div class="affiliate-item">Bottle 2 — placeholder</div>
    <div class="affiliate-item">Bottle 3 — placeholder</div>
  </div>
</aside>"""


def legend() -> str:
    return """<div class="legend" aria-label="Map key">
  <span><span class="legend-swatch fountain"></span>Public fountain</span>
  <span><span class="legend-swatch cafe"></span>Café or shop</span>
  <span><span class="legend-swatch partner"></span>Cooler partner</span>
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
  <button type="button" class="filter-chip partner" data-filter="partner" aria-pressed="false">Cooler partner</button>
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
        <p class="lede">Free drinking water and bottle-fill points across the UK. No app, no account. Free for anyone, no purchase needed. Public fountains and café taps come from OpenStreetMap; cooler partners are listed separately.</p>
        <div class="hero-actions">
          <button type="button" class="btn btn-primary js-locate" id="locate-btn">Find water near me</button>
          <a class="btn btn-ghost" href="{site_href("list-your-business/", depth)}">List your business</a>
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
      <div class="slots">
        {ad_slot("homepage-below-map", depth)}
        {affiliate_slot()}
      </div>
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
            f"Yes. Every point on SipSpot is free for anyone, with no purchase needed. OpenStreetMap points tagged as charging a fee, or as customers-only, private or no public access, are left off the map. Cooler partners must be marked walk-in free.",
        ),
        (
            f"Where does the {city_name} map data come from?",
            "Public fountains, taps and café fill points come from OpenStreetMap and are updated from the official OSM database. Cooler partner businesses are a separate list maintained by SipSpot and are never merged with the OSM data.",
        ),
        (
            "How often is the map updated?",
            "OpenStreetMap points are refreshed weekly from the Overpass API. Each popup shows the date the point was last edited on OpenStreetMap. Partner listings show the date they were last verified.",
        ),
        (
            "What if a point is wrong?",
            "For an OpenStreetMap point, use the “Is this wrong? Fix on OpenStreetMap” link in the popup. For a cooler partner listing, use the List your business page to get in touch.",
        ),
        (
            "When is a point open?",
            "Opening hours are shown on every point. If hours are missing we say “Hours not listed”. The Open now filter only includes points whose hours we can parse and that are open at the moment, using your device clock.",
        ),
        (
            "How do I add a business?",
            "Use the List your business page. There is no account, password or payment. A short form sends your details by email or a form endpoint.",
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


def sponsor_slot(city, partners, depth: int = 0) -> str:
    real = [p for p in partners if not (p.get("properties") or {}).get("is_example")]
    examples = [p for p in partners if (p.get("properties") or {}).get("is_example")]
    companies = []
    for p in (real or examples):
        name = (p.get("properties") or {}).get("partner")
        if name and name not in companies:
            companies.append(name)
    note = ""
    if not real and examples:
        note = '<p class="example-note">This sponsorship line is driven by example partner data and must be removed or replaced before launch.</p>'
    if companies:
        label = " and ".join(escape(c) for c in companies)
        return f"""<aside class="sponsor-slot">
  <p class="label">Sponsorship</p>
  {note}
  <h2>Sponsored by {label}</h2>
  <p>Cooler partners in {escape(city["name"])} help people fill a bottle for free.</p>
</aside>"""
    return f"""<aside class="sponsor-slot">
  <p class="label">Sponsorship</p>
  <h2>Sponsorship available for {escape(city["name"])}</h2>
  <p>Water cooler companies and local businesses can be listed as cooler partners. <a href="{site_href("list-your-business/", depth)}">List your business</a>.</p>
</aside>"""


def page_city(cfg, city, osm_feats, partner_feats) -> str:
    brand = cfg["brand"]
    name = city["name"]
    title = f"Free water refill points in {name} — {brand}"
    desc = (
        f"{cfg.get('tagline') or 'Find it. Fill it. Go.'} "
        f"{city['osm_count']} OpenStreetMap drinking-water points in {name}."
    )
    url = cfg["siteUrl"].rstrip("/") + f"/{city['slug']}/"
    depth = 1
    faq = faq_jsonld(name, city["osm_count"])
    extra = f'<script type="application/ld+json">{faq}</script>'
    city_payload = {
        "slug": city["slug"],
        "name": city["name"],
        "lat": city["lat"],
        "lon": city["lon"],
        "radius_km": city["radius_km"],
        "zoom": city.get("zoom", 12),
    }
    partner_note = ""
    if city.get("partner_count"):
        n = city["partner_count"]
        partner_note = f" There {'is' if n == 1 else 'are'} also {n} cooler partner listing{'s' if n != 1 else ''} in this area, shown separately."
        if any((p.get("properties") or {}).get("is_example") for p in partner_feats):
            partner_note += " Some partner pins are example data only."
    return f"""{head(cfg, title, desc, url, extra=extra, include_map=True, depth=depth)}
<body class="city-page">
  <a class="skip-link" href="#map">Skip to map</a>
  {header(cfg, "cities", depth)}
  <main class="page-body">
    <div class="wrap city-intro">
      <h1>Free water refill points in {escape(name)}</h1>
      <p class="lede">{city['osm_count']} OpenStreetMap point{"s" if city["osm_count"] != 1 else ""} in and around {escape(name)}.{partner_note}</p>
      <div class="hero-actions">
        <button type="button" class="btn btn-primary js-locate" id="locate-btn">Find water near me</button>
      </div>
      <p class="status" id="status" role="status"></p>
    </div>
    <div class="wrap city-sponsor">
      {sponsor_slot(city, partner_feats, depth)}
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
      <div class="slots">
        {ad_slot(f"city-{city['slug']}-below-map", depth)}
        {affiliate_slot()}
      </div>
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
          <p>Public fountains, taps and café fill points come from OpenStreetMap. Cooler partner businesses are a separate list and are never merged with OSM data.</p>
        </details>
        <details>
          <summary>What if a point is wrong?</summary>
          <p>Use “Is this wrong? Fix on OpenStreetMap” in the popup, or <a href="{site_href("list-your-business/", depth)}">contact us</a> about a partner listing.</p>
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
      <p class="lede">Static pages for major UK cities and any place in our gazetteer with 10 or more OpenStreetMap points.</p>
      {city_grid(cities, "All city pages", depth=depth)}
    </div>
  </main>
  {footer(cfg, depth)}
  <script src="{site_href("js/config.js", depth)}"></script>
</body>
</html>"""


def page_privacy(cfg) -> str:
    brand = cfg["brand"]
    tagline = cfg.get("tagline") or "Find it. Fill it. Go."
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
      <p>{escape(tagline)} {escape(brand)} is a static website. You do not need an account, and we do not ask for a password.</p>
      <h2>Location</h2>
      <p>If you use “Find water near me”, your browser may share your location with this page so the map can sort points by an approximate walking distance. That location is used only in your browser. It is not sent to our server (the site is static files) and it is not used to build the map data.</p>
      <h2>Map data</h2>
      <p>Public fountain and café fill-point data comes from OpenStreetMap and is licensed under the ODbL. Partner business listings are a separate file and are not combined with OSM data. SipSpot lists only free walk-in fills: OSM points tagged fee=yes or access=customers, access=private or access=no are excluded, and partner listings must have walk_in_free=yes.</p>
      <h2>Advertising and cookies</h2>
      <p><strong>A cookie consent banner must be added before ads go live.</strong> The advertisement slots on this site are placeholders only. Once Google AdSense or a similar network is connected, a consent banner is required before non-essential cookies or advertising identifiers are set, in line with UK GDPR and the Privacy and Electronic Communications Regulations.</p>
      <h2>Affiliate links</h2>
      <p>The “Recommended reusable bottles” box is a placeholder. If affiliate links are added later, this page will say so and name the programme.</p>
      <h2>List your business</h2>
      <p>The business listing form sends the details you type, such as a name, email address and address, by email to {email} or to a form endpoint configured in the site settings. Do not send passwords or payment details. We will use the information only to follow up about a listing.</p>
      <h2>Contact</h2>
      <p><a href="mailto:{email}">{email}</a></p>
    </div>
  </main>
  {footer(cfg, depth)}
  <script src="{site_href("js/config.js", depth)}"></script>
</body>
</html>"""


def page_list_business(cfg) -> str:
    brand = cfg["brand"]
    tagline = cfg.get("tagline") or "Find it. Fill it. Go."
    poster = cfg.get("posterLine") or "Skip the plastic. Find a tap."
    desc = f"List your business as a {brand} cooler partner. {poster}"
    url = cfg["siteUrl"].rstrip("/") + "/list-your-business/"
    email = escape(cfg.get("contactEmail") or "")
    depth = 1
    return f"""{head(cfg, f"List your business — {brand}", desc, url, depth=depth)}
<body>
  {header(cfg, "list", depth)}
  <main class="page-body">
    <div class="wrap">
      <h1>List your business</h1>
      <p class="lede">Offer a free walk-in bottle fill — free for anyone, no purchase needed — and appear on {escape(brand)} as a cooler partner. There is no account, no password and no payment at this stage. {escape(tagline)}</p>
      <div class="poster-card" aria-label="Partner poster wording">
        <p class="poster-brand">{escape(brand)}</p>
        <p class="poster-line">{escape(poster)}</p>
        <p class="poster-caption">Suggested line for partner posters and window stickers.</p>
      </div>
      <form class="form" id="partner-form" novalidate>
        <label>Business name
          <input type="text" name="business" required autocomplete="organization">
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
          <textarea name="notes" placeholder="Where the cooler is, any access notes"></textarea>
        </label>
        <p class="hint">This form does not collect a password or take payment. It opens an email to {email}, or posts to a form endpoint if one is set in config.json.</p>
        <button type="submit" class="btn btn-primary">Send listing request</button>
        <p class="status" id="form-status" role="status"></p>
      </form>
    </div>
  </main>
  {footer(cfg, depth)}
  <script src="{site_href("js/config.js", depth)}"></script>
  <script src="{site_href("js/form.js", depth)}"></script>
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
        (base + "/privacy/", "0.3"),
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


def main() -> int:
    cfg = load_json(CONFIG_PATH, {})
    if not cfg.get("brand"):
        raise SystemExit("config.json missing or incomplete")
    sync_config_js(cfg)

    places = load_json(PLACES_PATH, [])
    osm = load_json(OSM_PATH, {}).get("features") or []
    partners = load_json(PARTNER_PATH, {}).get("features") or []

    cities = choose_cities(places, osm, partners)
    public_cities = [{k: v for k, v in c.items() if not k.startswith("_")} for c in cities]
    write(ROOT / "data" / "cities.json", json.dumps(public_cities, ensure_ascii=False, indent=2))

    write(ROOT / "index.html", page_index(cfg, public_cities))
    write(ROOT / "cities" / "index.html", page_cities(cfg, public_cities))
    write(ROOT / "privacy" / "index.html", page_privacy(cfg))
    write(ROOT / "list-your-business" / "index.html", page_list_business(cfg))

    # Remove stale city folders only if they look like generated pages? Safer: just write/overwrite.
    for city in cities:
        write(ROOT / city["slug"] / "index.html", page_city(cfg, city, city["_osm"], city["_partners"]))

    write_sitemap(cfg, public_cities)
    write_robots(cfg)

    print(f"Generated {len(cities)} city pages from {len(osm)} OSM points and {len(partners)} partner points")
    print("Top 30 by population are always included; additional places need 10+ OSM points.")
    for c in sorted(public_cities, key=lambda x: (-x["osm_count"], x["name"]))[:15]:
        print(f"  {c['name']}: {c['osm_count']} OSM, {c['partner_count']} partners")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
