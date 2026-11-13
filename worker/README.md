# SipSpot API (refill counter, Still here / Gone votes, Not working reports)

A Cloudflare Worker with a D1 database, served at `https://api.sipspot.co.uk`
(Worker custom domain, so the apex can stay DNS-only to GitHub Pages).

| Method | Path | Body / query | Returns |
| --- | --- | --- | --- |
| GET | `/api/stats` | `?city=<slug>` optional | `{ uk: { refills }, city: { slug, refills } }` |
| GET | `/api/point/:id` | id e.g. `osm:node:123`, `partner:<id>` | `{ refills, here, gone, last_here, last_gone }` |
| POST | `/api/refill` | `{ "id": "<point id>" }` | updated point + UK and city totals |
| POST | `/api/vote` | `{ "id": "<point id>", "vote": "here" \| "gone" }` | updated point |
| POST | `/api/report` | `{ "id": "<point id>", "reason": "no_water" \| "broken" \| "dirty" \| "locked" \| "other" }` | updated point with open `reports` |
| GET | `/api/open-reports` | | `{ points: { "<id>": { reason, label, at } } }` (list markers) |
| GET | `/api/reports` | `Authorization: Bearer <REPORTS_KEY>`, `?days=1..365` (30), `?open=1` | owner only: reports with point name, cities, lat/lon |
| GET | `/api/units` | | `{ units: { "<id>": { status: "ok" \| "overdue" \| "hidden", last_check, every_hours } } }` |
| POST | `/api/check` | `{ "id", "key", "outcome": "ok" \| "problem" }` | staff check-in from a unit's QR code |
| POST | `/api/check-info` | `{ "id", "key" }` | unit name and status for the staff page |
| POST | `/api/admin/unit` | owner bearer key; `{ id, partner_id, partner_name?, alert_email?, label?, check_every_hours?, rotate_key? }` | registers a unit; returns its `check_key` once |
| POST | `/api/admin/unit-status` | owner bearer key; `{ id, hidden: true \| false }` | hide or restore a unit |
| GET | `/api/admin/units` | owner bearer key | every unit with partner, status and checks in the last 30 days |

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
* Votes and reports never remove points from the map, except that urgent
  reports ("Looks tampered with", "Tastes or smells odd") hide a *managed unit*
  until its staff check it (see below).
* IPv6 callers are throttled per /64 (devices rotate the rest of the address).

## Not working reports

* Stored in the `reports` table: point id, reason, unix time. No IP and no hash.
  Same throttle as votes (one per point per IP hash per 2 hours, counts toward
  the daily cap). Deleted after a year by the cron.
* A report is *open* for 7 days unless a "Still here" vote arrives after it
  (`point_stats.last_here_at`). Open reports show on the popup in amber
  ("Reported not working: No water, 12 November 2026") and as a list badge.
* Owner view: `python3 scripts/view_reports.py [--days 7] [--open] [--csv]`.
  It reads the key from `/workspace/sipspot-secrets/reports-key.txt` (chmod 600,
  never committed) and sends it only as a bearer header. The key was made with
  `openssl rand -hex 32` and set with `wrangler secret put REPORTS_KEY`.

## Managed units and staff checks

A managed unit is a refill point whose owner's staff check it by scanning a
QR code on the unit. SipSpot never checks units itself.

* Register a unit and print its sticker with `python3 scripts/units.py add ...`
  (see the script's help). The QR code opens `https://sipspot.co.uk/check/#u=<id>&k=<key>`.
  The key is in the URL fragment, which browsers never send to a server, and
  only its SHA-256 is stored. Lost or copied sticker: `units.py sticker --id ...`
  makes a new key and the old QR stops working.
* Status: `ok` within the interval (default 24 hours), `overdue` after it
  (shown as "Not checked recently"), and hidden after twice the interval, after
  an urgent report, or when staff tap "Problem". A staff "Checked, all fine"
  puts it back and closes open reports.
* Alerts: the partner's `alert_email` (and `OWNER_ALERT_EMAIL`) get an email when
  a unit is hidden, and the hourly cron sends "check overdue" at most once a day
  per unit. Email goes through Resend once `RESEND_API_KEY` (secret) and
  `ALERT_FROM` (var, an address on a domain verified in Resend) are set; until
  then alerts are only logged.
* The `checks` table keeps unit, outcome and time for two years, so a partner
  can show checks happened. No visitor data is involved.
* Anyone can trigger an urgent report, so a unit can be hidden by mistake or
  mischief. That is deliberate: the cost is a unit off the map until staff
  scan it, which is the safe way round. Reports are throttled as before.

## Local development

```sh
cd worker
npm install
printf 'IP_SALT=local-dev-salt\nALLOW_LOCALHOST=true\nTRUST_TEST_IP_HEADER=true\nREPORTS_KEY=local-test-key-at-least-32-characters\n' > .dev.vars
npm run db:init:local               # new local DB (existing: apply migrations/)
npm run dev                         # http://127.0.0.1:8787
API_BASE=http://127.0.0.1:8787 LOCAL_REPORTS_KEY=local-test-key-at-least-32-characters npm test
# wrangler dev only watches ../data (custom build), so restart it after editing src/
```

## First deploy

1. `npx wrangler d1 create sipspot-api` and paste the `database_id` into `wrangler.toml`.
2. `npm run db:init:remote`
3. `openssl rand -hex 32 | npx wrangler secret put IP_SALT`
4. `npm run deploy` (creates the Worker, the `api.sipspot.co.uk` custom domain and the cron).
5. Set `"apiBase": "https://api.sipspot.co.uk"` in `config.json`, run
   `python3 scripts/generate_pages.py`, commit and push.

Migrations for an existing database, in order:
`npx wrangler d1 execute sipspot-api --remote --file=./migrations/0002_reports.sql` (applied 12 Nov 2026), then
`npx wrangler d1 execute sipspot-api --remote --file=./migrations/0003_managed_units.sql` (managed units; not yet applied).

Deployed 11 Nov 2026: D1 `sipspot-api` (WEUR), custom domain `api.sipspot.co.uk`,
hourly cron. `workers_dev = false` (not served on workers.dev), but the account
needs a workers.dev subdomain registered for cron triggers to deploy.

Until `apiBase` is set the site hides the refill button and counters, and
Still here / Gone keep working in the browser only.

The API token needs: **Account** → Workers Scripts: Edit, D1: Edit;
**Zone** (sipspot.co.uk) → Workers Routes: Edit, DNS: Edit, Zone: Read.
Set `CLOUDFLARE_ACCOUNT_ID` so Wrangler does not need user/membership read.
