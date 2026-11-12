// Integration tests against a running local Worker:
//   npm run dev   (in another shell; uses .dev.vars with TRUST_TEST_IP_HEADER=true)
//   API_BASE=http://127.0.0.1:8787 npm test
// Each run uses random test IPs so it can be re-run against the same local DB.
import { test } from "node:test";
import assert from "node:assert/strict";

const BASE = process.env.API_BASE || "http://127.0.0.1:8787";
const ORIGIN = "http://localhost:8000";
const LONDON = "osm:node:272018520";
const LONDON2 = "osm:node:280114917";
const rnd = () => "10." + [1, 2, 3].map(() => Math.floor(Math.random() * 250)).join(".");

async function post(path, body, ip, origin = ORIGIN) {
  const headers = { "Content-Type": "application/json", "X-Test-IP": ip };
  if (origin) headers.Origin = origin;
  const res = await fetch(BASE + path, { method: "POST", headers, body: JSON.stringify(body) });
  return { status: res.status, headers: res.headers, body: await res.json().catch(() => null) };
}
async function get(path, origin = ORIGIN) {
  const res = await fetch(BASE + path, { headers: origin ? { Origin: origin } : {} });
  return { status: res.status, headers: res.headers, body: await res.json().catch(() => null) };
}

test("refill increments point, city and UK totals", async () => {
  const before = await get("/api/stats?city=london");
  const p0 = await get("/api/point/" + encodeURIComponent(LONDON));
  const r = await post("/api/refill", { id: LONDON }, rnd());
  assert.equal(r.status, 200);
  assert.equal(r.body.point.refills, p0.body.refills + 1);
  const after = await get("/api/stats?city=london");
  assert.equal(after.body.uk.refills, before.body.uk.refills + 1);
  assert.equal(after.body.city.refills, before.body.city.refills + 1);
  assert.equal(r.headers.get("access-control-allow-origin"), ORIGIN);
});

test("same IP + point is throttled; another point is fine", async () => {
  const ip = rnd();
  assert.equal((await post("/api/refill", { id: LONDON }, ip)).status, 200);
  const again = await post("/api/refill", { id: LONDON }, ip);
  assert.equal(again.status, 200);
  assert.equal(again.body.ok, false);
  assert.equal(again.body.error, "too_soon");
  assert.ok(again.body.retry_after_s > 7000);
  assert.equal((await post("/api/refill", { id: LONDON2 }, ip)).status, 200);
});

test("votes persist and are throttled per point", async () => {
  const ip = rnd();
  const p0 = await get("/api/point/" + encodeURIComponent(LONDON2));
  const v = await post("/api/vote", { id: LONDON2, vote: "here" }, ip);
  assert.equal(v.status, 200);
  assert.equal(v.body.point.here, p0.body.here + 1);
  assert.match(v.body.point.last_here, /^\d{4}-\d{2}-\d{2}$/);
  assert.equal((await post("/api/vote", { id: LONDON2, vote: "gone" }, ip)).body.error, "too_soon");
  const g = await post("/api/vote", { id: LONDON2, vote: "gone" }, rnd());
  assert.equal(g.body.point.gone, p0.body.gone + 1);
  assert.equal((await post("/api/vote", { id: LONDON2, vote: "maybe" }, rnd())).status, 400);
});

test("rejects bad and unknown ids, unknown cities", async () => {
  assert.equal((await post("/api/refill", { id: "osm:node:abc" }, rnd())).status, 400);
  assert.equal((await post("/api/refill", { id: "<script>" }, rnd())).status, 400);
  assert.equal((await post("/api/refill", { id: "osm:node:1" }, rnd())).status, 404);
  assert.equal((await get("/api/point/osm%3Anode%3A1")).status, 404);
  assert.equal((await get("/api/stats?city=atlantis")).status, 404);
});

test("strict CORS: writes need an allowed Origin", async () => {
  assert.equal((await post("/api/refill", { id: LONDON }, rnd(), "https://evil.example")).status, 403);
  assert.equal((await post("/api/refill", { id: LONDON }, rnd(), null)).status, 403);
  const pre = await fetch(BASE + "/api/refill", { method: "OPTIONS", headers: { Origin: "https://evil.example", "Access-Control-Request-Method": "POST" } });
  assert.equal(pre.status, 403);
  const ok = await fetch(BASE + "/api/refill", { method: "OPTIONS", headers: { Origin: "https://sipspot.co.uk", "Access-Control-Request-Method": "POST" } });
  assert.equal(ok.status, 204);
  assert.equal(ok.headers.get("access-control-allow-origin"), "https://sipspot.co.uk");
  const g = await get("/api/stats", "https://evil.example");
  assert.equal(g.headers.get("access-control-allow-origin"), null);
});

test("daily cap per IP hash", async () => {
  const ip = rnd();
  const idx = await import("../generated/points-index.json", { with: { type: "json" } });
  const ids = Object.keys(idx.default.points).slice(100, 145);
  let last;
  let ok = 0;
  for (const id of ids) {
    last = await post("/api/refill", { id }, ip);
    if (last.body.ok) ok++;
    else break;
  }
  assert.equal(ok, 40);
  assert.equal(last.body.throttled, true);
  assert.equal(last.body.error, "daily_cap");
});

// "Not working" reports. LOCAL_REPORTS_KEY must match REPORTS_KEY in .dev.vars.
const LOCAL_KEY = process.env.LOCAL_REPORTS_KEY || "";
const REPORT_PT = "osm:node:697031987";

test("report: validated, throttled per point, shown until a later Still here", async () => {
  assert.equal((await post("/api/report", { id: REPORT_PT, reason: "flooded" }, rnd())).status, 400);
  assert.equal((await post("/api/report", { id: "osm:node:1", reason: "broken" }, rnd())).status, 404);
  assert.equal((await post("/api/report", { id: REPORT_PT, reason: "broken" }, rnd(), "https://evil.example")).status, 403);
  const ip = rnd();
  const r = await post("/api/report", { id: REPORT_PT, reason: "no_water" }, ip);
  assert.equal(r.status, 200);
  assert.equal(r.body.ok, true);
  assert.equal(r.body.point.reports[0].reason, "no_water");
  assert.equal(r.body.point.reports[0].label, "No water");
  assert.equal(JSON.stringify(r.body).includes(ip), false);
  const again = await post("/api/report", { id: REPORT_PT, reason: "broken" }, ip);
  assert.equal(again.body.error, "too_soon");
  const p = await get("/api/point/" + encodeURIComponent(REPORT_PT));
  assert.ok(p.body.reports.length >= 1);
  const open = await get("/api/open-reports");
  assert.equal(open.body.points[REPORT_PT].reason, "no_water");
  // A later "Still here" vote closes it (reports never remove the point).
  await new Promise((res) => setTimeout(res, 1100));
  assert.equal((await post("/api/vote", { id: REPORT_PT, vote: "here" }, rnd())).status, 200);
  const p2 = await get("/api/point/" + encodeURIComponent(REPORT_PT));
  assert.equal(p2.status, 200);
  assert.deepEqual(p2.body.reports, []);
  assert.equal((await get("/api/open-reports")).body.points[REPORT_PT], undefined);
});

test("reports count toward the daily cap", async () => {
  const ip = rnd();
  const idx = await import("../generated/points-index.json", { with: { type: "json" } });
  const ids = Object.keys(idx.default.points).slice(200, 239);
  for (const id of ids) assert.equal((await post("/api/refill", { id }, ip)).body.ok, true);
  assert.equal((await post("/api/report", { id: ids[0], reason: "dirty" }, ip)).body.ok, true);
  const capped = await post("/api/report", { id: ids[1], reason: "dirty" }, ip);
  assert.equal(capped.body.error, "daily_cap");
});

test("owner reports endpoint needs the bearer key", async () => {
  assert.equal((await get("/api/reports")).status, 401);
  const bad = await fetch(BASE + "/api/reports", { headers: { Authorization: "Bearer wrong" } });
  assert.equal(bad.status, 401);
  if (!LOCAL_KEY) return;
  const ok = await fetch(BASE + "/api/reports?days=7", { headers: { Authorization: "Bearer " + LOCAL_KEY } });
  assert.equal(ok.status, 200);
  assert.equal(ok.headers.get("access-control-allow-origin"), null);
  const body = await ok.json();
  const hit = body.reports.find((x) => x.point_id === REPORT_PT);
  assert.ok(hit && hit.name && hit.cities.length && typeof hit.lat === "number");
  assert.equal(hit.open, false);
  assert.ok(hit.still_here_since);
});

test("IPv6 is throttled per /64", async () => {
  const net = "2001:db8:" + Math.floor(Math.random() * 65535).toString(16) + ":" + Math.floor(Math.random() * 65535).toString(16);
  assert.equal((await post("/api/report", { id: LONDON, reason: "other" }, net + "::1")).body.ok, true);
  assert.equal((await post("/api/report", { id: LONDON, reason: "other" }, net + ":0:0:0:2")).body.error, "too_soon");
});
