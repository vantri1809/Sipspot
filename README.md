# SipSpot

Find it. Fill it. Go.

A static, mobile-first map of free drinking water and bottle-fill points in the UK. Free for anyone, no purchase needed. Public fountains, taps and café fill points come from OpenStreetMap. Businesses that offer a fill at a water cooler are a **separate partner layer**. There is no login and no app.

The placeholder domain is **sipspot.uk**. Change it in one file: `config.json`.

Partner poster / sticker line: **Skip the plastic. Find a tap.**

## Quick start

```bash
python3 scripts/fetch_points.py
python3 scripts/generate_pages.py
python3 -m http.server 8080 --directory .
```

Open <http://localhost:8080/>. The site is plain HTML, CSS and JavaScript in this folder. It can be deployed as-is to Cloudflare Pages, Netlify or GitHub Pages.

## Changing the brand or domain

Edit `config.json` only, then run:

```bash
python3 scripts/generate_pages.py
```

That refreshes `js/config.js`, every HTML page, `sitemap.xml` and `robots.txt`. Fields you will usually change:

- `brand`, `domain`, `siteUrl`, `contactEmail`
- `tagline` (header, homepage hero and meta description) — default `Find it. Fill it. Go.`
- `posterLine` (partner posters and stickers) — default `Skip the plastic. Find a tap.`
- `partnerFormEndpoint` (optional form backend; leave empty to use `mailto:`)
- `mapProvider` (see Map providers below)
- `staleAfterMonths` (how old an OSM last-edit date must be before a pin is faded; default `36`)
- `feedback.enabled`, `feedback.endpoint`, `feedback.dataUrl` (see Visitor feedback below)

## Deploy

Point the host at the repository root (this folder), not a subfolder. Set the production domain to whatever you put in `siteUrl`.

### Cloudflare Pages

1. New project → connect the GitHub repo (or upload the folder).
2. Build command: leave empty, or `python3 scripts/generate_pages.py` if you want pages rebuilt on each deploy.
3. Output directory: `/` (the project root).
4. Add a custom domain, for example `sipspot.uk`.

### Netlify

1. New site from Git, or drag this folder onto the Netlify drop zone.
2. Build command empty (or `python3 scripts/generate_pages.py`).
3. Publish directory: `.`
4. Add the custom domain.

### GitHub Pages

1. Settings → Pages → Deploy from a branch (usually `main`, `/` root).
2. Project sites such as `https://user.github.io/repo/` work: page links and assets use relative paths, and the map data URLs are resolved from the location of `js/config.js`. A custom domain (`sipspot.uk`) is still the production target.
3. The weekly workflow needs permission to push commits (`contents: write` is set in the workflow file).

## Data

Published OSM points live in `data/points.geojson`. Rebuild them with these three scripts, in this order if you are starting from scratch:

1. `scripts/fetch_points.py` — downloads four UK Overpass tiles into `data/overpass-cache/` (`south-west`, `south-east`, `north-west`, `north-east`). It then calls `build_points.py`. Use `--cache-only` to skip Overpass and only merge existing caches. Public Overpass instances are often busy; a failed tile is skipped and is **not** written as an empty cache.
2. `scripts/extract_from_pbf.py` — if an Overpass tile fails, extract the same OSM tags from a [Geofabrik](https://download.geofabrik.de/europe/united-kingdom.html) PBF. Needs pyosmium in `.venv`:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install osmium
   .venv/bin/python scripts/extract_from_pbf.py data/pbf/scotland-latest.osm.pbf
   .venv/bin/python scripts/extract_from_pbf.py data/pbf/ireland-and-northern-ireland-latest.osm.pbf
   ```

   Each run writes `data/overpass-cache/pbf-<name>.json`. Republic of Ireland points from the Ireland extract are dropped later by a UK geographic filter.
3. `scripts/build_points.py` — the only script that should write `data/points.geojson`. It merges every JSON file in `data/overpass-cache/`, drops `fee=yes` and `access=customers|private|no`, and deduplicates by OSM type and id.

   ```bash
   python3 scripts/fetch_points.py --cache-only
   # or:
   python3 scripts/build_points.py
   python3 scripts/generate_pages.py
   ```

`data/overpass-cache/` and `data/pbf/` are local working files (gitignored). Keep `data/points.geojson` in the repo so the static site can be deployed without re-fetching.

This build's caches cover England and Wales mainly from Overpass (south-west, south-east, north-east), Scotland from the Geofabrik Scotland PBF, and Northern Ireland from the Geofabrik Ireland and Northern Ireland PBF. The Overpass **north-west** tile (north of 54.5°N, west of 2°W) did not come back from Overpass, and no England PBF was extracted for that tile, so Cumbria north of 54.5°N is effectively uncovered (Carlisle and Whitehaven have 0 points). Lancashire, Greater Manchester, Merseyside, Cheshire and southern Cumbria sit in the south-west tile and are present. To fill the gap, download a Geofabrik England or north-west extract and run `extract_from_pbf.py`, then `build_points.py`.

### OpenStreetMap points (`data/points.geojson`)

The extract uses only these OSM tags:

- `amenity=drinking_water`
- `drinking_water:refill=yes`
- `man_made=water_tap` with `drinking_water=yes`
- `amenity=water_point`

Each feature keeps the OSM type and id, name, opening hours, access, fee, bottle tag, water type, chilled flag, and the last-edit timestamp from `out meta`. Points tagged `fee=yes` or `access=customers`/`private`/`no` are dropped. The file is purely OSM-derived. Do not merge it with any other database.

The script is scheduled weekly by `.github/workflows/refresh-data.yml` (Mondays at 03:00 UTC) and can be run by hand from the Actions tab.

Licence of this file: [ODbL 1.0](https://opendatacommons.org/licenses/odbl/), © OpenStreetMap contributors. Attribution must remain visible ([copyright](https://www.openstreetmap.org/copyright)).

### Partner points (`data/partners.geojson`) — keep this separate

Cooler partner businesses (for example venues with a water cooler) live in a **second file**. The site loads the two files independently, draws them as two layers, and never writes a joined dataset. That is deliberate: mixing OSM data with another database and publishing the result can trigger ODbL share-alike on the other source.

The copy in this repo is **example data only** (three fictional listings, clearly labelled). Remove it before launch and import a real list:

```bash
python3 scripts/import_partners.py path/to/partners.csv -o data/partners.geojson
```

CSV columns: `name,address,postcode,lat,lon,partner,hours,verified_date,walk_in_free`. `walk_in_free` must be `yes`. Optional: `logo_url`, `refill_offered`, `id`, `is_example`, `water_type`, `chilled`. If `lat`/`lon` are missing, the script geocodes the postcode with [postcodes.io](https://postcodes.io/) (ONS-derived). It does not use OpenStreetMap or Google for geocoding.

The weekly OSM workflow does **not** commit `data/partners.geojson`.

### City pages

`scripts/generate_pages.py` builds a page for each of the 30 most populous places in `scripts/uk_places.json`, plus any other place in that gazetteer with 10 or more OSM points. Pages live at `/london/`, `/manchester/` and so on, with the title “Free water refill points in &lt;City&gt;”, a count, a list, an embedded map, FAQ JSON-LD, and an optional “Sponsored by …” slot when partners are present in that city.

## Map providers

The default map is **Leaflet** with the [CARTO Voyager](https://carto.com/basemaps) vector style, loaded through MapLibre GL Leaflet. All pin, filter, cluster and partner-layer code talks to a small adapter in `js/map-provider.js`. Attribution on the map is “© OpenStreetMap contributors, © CARTO”, with both names linked.

CARTO raster tiles have required a key since 25 September 2026. With no `tilesApiKey` set, the adapter uses CARTO's keyless vector style (`https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json`) so the default works without a key. If you later add a CARTO key, it will switch to the Voyager raster tiles automatically.

To switch the basemap, change one line in `config.json` and rebuild `js/config.js` (or run `python3 scripts/generate_pages.py`):

```json
"basemap": "carto-voyager"
```

Built-in catalog keys (defined in `js/map-provider.js`): `carto-voyager` (default), `carto-positron`, `osm`, `stadia-alidade-smooth`, `stadia-osm-bright`, `maptiler-streets`, `maptiler-dataviz`, `openfreemap-liberty`, `openfreemap-positron`, `openfreemap-bright`. Raster styles that need a key also accept `tilesApiKey`. MapTiler always needs a key and falls back to OSM if none is set. Stadia works without a key on `localhost`; a production site needs domain authentication or an API key. OpenFreeMap is vector-only and is loaded through MapLibre GL Leaflet.

You can preview another style locally with `?basemap=osm` without editing the file.

The OSMF [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) asks heavy or production sites not to use `tile.openstreetmap.org` as a default, which is why the live site no longer uses those tiles. If you switch `basemap` back to `osm`, use your own tiles or another host for a public launch.

To switch later to the **Google Maps JavaScript API**, set in `config.json`:

```json
"mapProvider": "google",
"googleMapsApiKey": "YOUR_KEY"
```

Then implement the Google branch in `js/map-provider.js` behind the same methods (`setView`, `addClusterGroup`, `addMarker`, and so on). Pins, filters and the partner layer should not need to change.

Notes if you do that:

- You need a Google Cloud API key with the Maps JavaScript API enabled.
- Google’s monthly free tier is commonly quoted as 10,000 map loads; after that, map loads are billed. Check current [Maps JavaScript API pricing](https://developers.google.com/maps/documentation/javascript/usage-and-billing) before going live.
- Do not use Google Places or Google Geocoding data with the non-Google (Leaflet / OSM) map, and do not write Google Places/Geocoding results into `data/points.geojson` or `data/partners.geojson`. Directions links that only open Google or Apple Maps in a new tab via a plain URL are fine.

## Design

Palette name: Fresh.

- Primary water blue `#1E88E5` — public fountain pins
- Leaf green `#43A047` — café or shop pins
- Partner purple `#8E24AA` — cooler partner pins
- Light aqua background `#E3F2FD`

## Walk-in free policy

SipSpot lists **only free walk-in fills** — free for anyone, no purchase needed.

- OpenStreetMap points tagged `fee=yes` are excluded, as are points tagged `access=customers`, `access=private` or `access=no`. Untagged access is kept.
- Partner CSV rows must include `walk_in_free=yes`. Other values are skipped by `scripts/import_partners.py`.
- There is no “Free” filter: every point on the map is already free to walk in and fill a bottle.

## Water type, chilled water and opening hours

Each point has a water type of **Tap water**, **Filtered water**, or **Unknown** (partners may also be **Chilled filtered water**).

- For OSM points, **Filtered** is set only from a real tag such as `drinking_water:filtered` or `water_filter`, or from a `description`/`note` that actually mentions a filter. Plain public fountains and taps default to Tap water. Café and shop fill points default to Unknown. The script never guesses Filtered.
- **Chilled** is a yes/no flag. For OSM points it is set only when a real tag says so (`drinking_water:chilled`, `chilled`, `drinking_water:cooled` or `cooled`). Partner CSV columns are `water_type` (`tap`, `filtered`, `chilled filtered`) and `chilled` (`yes`/`no`).
- The map has **Filtered only** and **Chilled only** filters, plus a small F/C mark on pins and badges in popups and city lists.
- Opening hours are shown prominently on every point (OSM `opening_hours`, partner `hours`). If they are missing the site says **Hours not listed**. An **Open now** filter includes only points whose hours can be parsed and that are open at the moment (using [opening_hours.js](https://github.com/opening-hours/opening_hours.js) with a simple fallback).

## Older OpenStreetMap points

Each OSM point keeps the last-edit timestamp from OpenStreetMap (`properties.timestamp`). The browser compares that date with today and, if the edit is older than `staleAfterMonths` (default 36 months, or 3 years), the pin is faded on the map and the popup adds a note such as “Last updated on OpenStreetMap over 3 years ago, so it may have changed.” Every OSM popup also shows `Last updated: Mon YYYY`. Partner points are never faded.

An old edit date does not mean the tap has gone — most fountains are mapped once and rarely edited again — so these points stay on the map. A filter, **Hide points not updated in 3+ years**, is off by default.

## Visitor feedback (Still here / Gone)

Each OSM popup has **Still here** and **Gone** buttons. A click is always stored in the browser’s `localStorage`, so the same browser cannot vote twice on a point, and the popup then shows a thank-you message. Choosing **Gone** also offers a link to [open a note on OpenStreetMap](https://www.openstreetmap.org/note/new) at that location. Votes must never automatically remove a point from the map.

`feedback.endpoint` is `null` by default, so **votes are not collected on a server until you set an endpoint**. The buttons and thank-you state still work locally. Set `feedback.enabled` to `false` to hide the buttons. When an endpoint is set, the site POSTs JSON:

```json
{
  "osm_type": "node",
  "osm_id": 123,
  "vote": "here",
  "ts": "2026-11-10T16:00:00.000Z",
  "page": "/bath/"
}
```

`vote` is `"here"` or `"gone"`. Two simple, cheap ways to collect those POSTs:

1. **A Cloudflare Worker with a KV namespace.** A minimal example is in `scripts/feedback-worker.js` (not deployed). Create a Worker, bind KV as `FEEDBACK`, deploy that script, and set `feedback.endpoint` to the Worker URL. If the Worker is on a different origin, keep the CORS headers and tighten `Access-Control-Allow-Origin` before launch.
2. **A form service that accepts JSON POSTs**, such as Formspark or Basin. Point `feedback.endpoint` at the form’s endpoint.

After `config.json` is changed, run `python3 scripts/generate_pages.py` so `js/config.js` is refreshed.

### Optional confirmation overlay

You can later summarise collected votes into `data/feedback.json` (see `data/feedback.example.json` for the format). If that file is present, the front end loads it and, for a matching OSM point with `status: "here"` and a `confirmed_on` date, shows “Confirmed by visitors on &lt;date&gt;”. The data scripts (`fetch_points.py`, `extract_from_pbf.py`, `build_points.py`) do not read or write this file yet. Confirmations are an overlay only — they do not add, edit or remove points in `data/points.geojson`.

```json
{
  "points": [
    {
      "osm_type": "node",
      "osm_id": 123,
      "status": "here",
      "confirmed_on": "2026-10-15"
    }
  ]
}
```

Change `feedback.dataUrl` if you host the overlay at a different path.

## Ads and affiliates

Advertisement slots are marked “Advertisement” and sit below the map, never on top of it. The reusable-bottle box is an affiliate placeholder. **Add a cookie consent banner before AdSense or similar ads go live** — this is also stated on the privacy page.

## Licence

- Code in this repository: you may treat it as CC0 / public domain unless a later licence file says otherwise.
- `data/points.geojson`: ODbL 1.0, © OpenStreetMap contributors.
- `data/partners.geojson`: not an OSM derivative. Example rows in the shipped file are fictional.
