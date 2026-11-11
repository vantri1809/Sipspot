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
