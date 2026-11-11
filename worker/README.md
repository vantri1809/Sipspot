# SipSpot API (refill counter + Still here / Gone votes)

A Cloudflare Worker with a D1 database, served at `https://api.sipspot.co.uk`
(Worker custom domain, so the apex can stay DNS-only to GitHub Pages).

| Method | Path | Body / query | Returns |
| --- | --- | --- | --- |
| GET | `/api/stats` | `?city=<slug>` optional | `{ uk: { refills }, city: { slug, refills } }` |
| GET | `/api/point/:id` | id e.g. `osm:node:123`, `partner:<id>` | `{ refills, here, gone, last_here, last_gone }` |
| POST | `/api/refill` | `{ "id": "<point id>" }` | updated point + UK and city totals |
| POST | `/api/vote` | `{ "id": "<point id>", "vote": "here" \| "gone" }` | updated point |

Throttled writes return `200 { ok: false, throttled: true, error: "too_soon" | "daily_cap", retry_after_s }`.

## Anti-spam and privacy

* One refill and one vote per point per IP hash every 2 hours (`POINT_COOLDOWN_SECONDS`),
  plus a daily cap per IP hash (`DAILY_CAP`, default 40 writes). The site also
  limits one refill per point per device every 2 hours in local storage.
* The IP is only used in memory: `HMAC-SHA256(IP_SALT, ip + "|" + UTC day)`.
  The hash rotates daily and is only used in throttle keys that expire
  (2 hours, or the end of the UTC day) and are deleted by the hourly cron.
* Writes must come from an allowed `Origin` (`ALLOWED_ORIGINS`); localhost is
  only allowed when `ALLOW_LOCALHOST=true` (local dev).
* Point ids are format-checked and must be in `generated/points-index.json`,
  which `scripts/build_worker_index.py` bakes at deploy time from
  `data/points.geojson` and `data/partners.geojson` (with the point → city map
  used to keep city totals up to date on write). It is not committed.
  Re-deploy after the map data changes so new points are accepted.
* Votes never remove points from the map.

## Local development

```sh
cd worker
npm install
printf 'IP_SALT=local-dev-salt\nALLOW_LOCALHOST=true\nTRUST_TEST_IP_HEADER=true\n' > .dev.vars
npm run db:init:local
npm run dev                         # http://127.0.0.1:8787
API_BASE=http://127.0.0.1:8787 npm test
```

## First deploy

1. `npx wrangler d1 create sipspot-api` and paste the `database_id` into `wrangler.toml`.
2. `npm run db:init:remote`
3. `openssl rand -hex 32 | npx wrangler secret put IP_SALT`
4. `npm run deploy` (creates the Worker, the `api.sipspot.co.uk` custom domain and the cron).
5. Set `"apiBase": "https://api.sipspot.co.uk"` in `config.json`, run
   `python3 scripts/generate_pages.py`, commit and push.

Deployed 11 Nov 2026: D1 `sipspot-api` (WEUR), custom domain `api.sipspot.co.uk`,
hourly cron. `workers_dev = false` (not served on workers.dev), but the account
needs a workers.dev subdomain registered for cron triggers to deploy.

Until `apiBase` is set the site hides the refill button and counters, and
Still here / Gone keep working in the browser only.

The API token needs: **Account** → Workers Scripts: Edit, D1: Edit;
**Zone** (sipspot.co.uk) → Workers Routes: Edit, DNS: Edit, Zone: Read.
Set `CLOUDFLARE_ACCOUNT_ID` so Wrangler does not need user/membership read.
