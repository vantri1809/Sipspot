/**
 * SipSpot API — "I filled up here" refill counter and Still here / Gone votes.
 *
 * Cloudflare Worker + D1. Endpoints (all JSON):
 *   GET  /api/stats            -> { uk: { refills } }
 *   GET  /api/stats?city=slug  -> { uk: { refills }, city: { slug, refills } }
 *   GET  /api/point/:id        -> { id, refills, here, gone, last_here, last_gone }
 *   POST /api/refill  { id }           -> logs one refill
 *   POST /api/vote    { id, vote }     -> vote is "here" or "gone"
 *   Throttled writes return 200 { ok: false, throttled: true, error, retry_after_s }.
 *
 * Privacy: no cookies, no accounts, nothing personal is stored. The caller's
 * IP address is only used in memory to build an HMAC hash (secret salt + IP +
 * UTC day). That hash is used for short-lived throttle keys that expire after
 * a few hours (or at the end of the day for the daily cap) and are deleted by
 * the hourly cron. Counts never remove points from the map.
 */
import INDEX from "../generated/points-index.json";

const ID_RE = /^(?:osm:(?:node|way|relation):\d{1,12}|partner:[A-Za-z0-9][A-Za-z0-9._-]{0,99})$/;
const CITY_RE = /^[a-z0-9-]{1,60}$/;
const MAX_BODY_BYTES = 1024;

const KNOWN = (INDEX && INDEX.points) || null;
const CITY_SLUGS = (INDEX && Array.isArray(INDEX.cities)) ? INDEX.cities : [];
const CITY_SET = new Set(CITY_SLUGS);

export function isValidId(id) {
  return typeof id === "string" && ID_RE.test(id);
}

export function isKnownId(id) {
  if (!isValidId(id)) return false;
  if (!KNOWN) return true; // index not built: fall back to the format check
  return Object.prototype.hasOwnProperty.call(KNOWN, id);
}

function citiesFor(id) {
  const idx = KNOWN && KNOWN[id];
  if (!Array.isArray(idx)) return [];
  return idx.map((i) => CITY_SLUGS[i]).filter(Boolean);
}

function intVar(env, name, fallback) {
  const n = Number(env && env[name]);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

function allowedOrigin(request, env) {
  const origin = request.headers.get("Origin");
  if (!origin) return null;
  const list = String((env && env.ALLOWED_ORIGINS) || "")
    .split(",").map((s) => s.trim()).filter(Boolean);
  if (list.includes(origin)) return origin;
  if (String(env && env.ALLOW_LOCALHOST) === "true" &&
      /^http:\/\/(localhost|127\.0\.0\.1)(:\d{1,5})?$/.test(origin)) {
    return origin;
  }
  return null;
}

function corsHeaders(origin) {
  const h = {
    "Vary": "Origin",
    "X-Content-Type-Options": "nosniff"
  };
  if (origin) {
    h["Access-Control-Allow-Origin"] = origin;
    h["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS";
    h["Access-Control-Allow-Headers"] = "Content-Type";
    h["Access-Control-Max-Age"] = "86400";
  }
  return h;
}

function json(body, status, origin, extra) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...corsHeaders(origin),
      ...(extra || {})
    }
  });
}

function utcDay(nowMs) {
  return new Date(nowMs).toISOString().slice(0, 10);
}

async function ipHash(request, env, day) {
  let ip = request.headers.get("CF-Connecting-IP") || "";
  if (String(env.TRUST_TEST_IP_HEADER) === "true") {
    ip = request.headers.get("X-Test-IP") || ip; // local tests only (set in .dev.vars)
  }
  if (!ip) ip = "unknown";
  const salt = env.IP_SALT;
  if (!salt) throw new Error("IP_SALT secret is not set");
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(salt), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(ip + "|" + day));
  return Array.from(new Uint8Array(sig).slice(0, 16)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function readBody(request) {
  const len = Number(request.headers.get("Content-Length") || 0);
  if (len > MAX_BODY_BYTES) return null;
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return null;
  try {
    const body = JSON.parse(text);
    return body && typeof body === "object" ? body : null;
  } catch (err) {
    return null;
  }
}

/* Takes a per-point throttle slot and one unit of the daily cap.
 * Returns null when allowed, or an error object when throttled.
 * Throttled taps answer 200 with ok:false (plus Retry-After) rather than 429,
 * so an ordinary "already counted" tap does not log a browser console error. */
async function takeThrottle(env, hash, kind, id, nowS, nowMs) {
  const cooldown = intVar(env, "POINT_COOLDOWN_SECONDS", 7200);
  const cap = intVar(env, "DAILY_CAP", 40);
  const pointKey = kind + ":" + hash + ":" + id;
  const claim = await env.DB.prepare(
    "INSERT INTO throttle (key, hits, expires_at) VALUES (?1, 1, ?2) " +
    "ON CONFLICT(key) DO UPDATE SET hits = 1, expires_at = excluded.expires_at " +
    "WHERE throttle.expires_at <= ?3"
  ).bind(pointKey, nowS + cooldown, nowS).run();
  if (!claim.meta || claim.meta.changes === 0) {
    const row = await env.DB.prepare("SELECT expires_at FROM throttle WHERE key = ?1").bind(pointKey).first();
    const retry = row ? Math.max(1, row.expires_at - nowS) : cooldown;
    return { status: 200, body: { ok: false, throttled: true, error: "too_soon", retry_after_s: retry } };
  }
  const endOfDay = Math.floor(Date.parse(utcDay(nowMs) + "T00:00:00Z") / 1000) + 86400;
  const dayKey = "d:" + hash;
  const daily = await env.DB.prepare(
    "INSERT INTO throttle (key, hits, expires_at) VALUES (?1, 1, ?2) " +
    "ON CONFLICT(key) DO UPDATE SET " +
    "hits = CASE WHEN throttle.expires_at <= ?3 THEN 1 ELSE throttle.hits + 1 END, " +
    "expires_at = CASE WHEN throttle.expires_at <= ?3 THEN excluded.expires_at ELSE throttle.expires_at END " +
    "WHERE throttle.expires_at <= ?3 OR throttle.hits < ?4 RETURNING hits"
  ).bind(dayKey, endOfDay, nowS, cap).first();
  if (!daily) {
    // Over the daily cap: release the point slot so it is not wasted.
    await env.DB.prepare("DELETE FROM throttle WHERE key = ?1").bind(pointKey).run();
    return { status: 200, body: { ok: false, throttled: true, error: "daily_cap", retry_after_s: Math.max(1, endOfDay - nowS) } };
  }
  return null;
}

async function readPoint(env, id) {
  const row = await env.DB.prepare(
    "SELECT refills, here, gone, last_here, last_gone FROM point_stats WHERE point_id = ?1"
  ).bind(id).first();
  return {
    id: id,
    refills: row ? row.refills : 0,
    here: row ? row.here : 0,
    gone: row ? row.gone : 0,
    last_here: row ? row.last_here : null,
    last_gone: row ? row.last_gone : null
  };
}

async function readTotals(env, scopes) {
  if (!scopes.length) return {};
  const placeholders = scopes.map((_, i) => "?" + (i + 1)).join(", ");
  const res = await env.DB.prepare(
    "SELECT scope, refills FROM totals WHERE scope IN (" + placeholders + ")"
  ).bind(...scopes).all();
  const out = {};
  scopes.forEach((s) => { out[s] = 0; });
  (res.results || []).forEach((r) => { out[r.scope] = r.refills; });
  return out;
}

async function handleStats(url, env, origin) {
  const city = url.searchParams.get("city");
  const scopes = ["uk"];
  if (city != null) {
    if (!CITY_RE.test(city) || (CITY_SET.size && !CITY_SET.has(city))) {
      return json({ ok: false, error: "unknown_city" }, 404, origin);
    }
    scopes.push("city:" + city);
  }
  const t = await readTotals(env, scopes);
  const body = { ok: true, uk: { refills: t.uk } };
  if (city != null) body.city = { slug: city, refills: t["city:" + city] };
  return json(body, 200, origin, { "Cache-Control": "public, max-age=15" });
}

async function handlePoint(id, env, origin) {
  if (!isValidId(id)) return json({ ok: false, error: "bad_id" }, 400, origin);
  if (!isKnownId(id)) return json({ ok: false, error: "unknown_point" }, 404, origin);
  const p = await readPoint(env, id);
  return json({ ok: true, ...p }, 200, origin, { "Cache-Control": "public, max-age=10" });
}

async function handleRefill(request, env, origin) {
  const body = await readBody(request);
  const id = body && body.id;
  if (!isValidId(id)) return json({ ok: false, error: "bad_id" }, 400, origin);
  if (!isKnownId(id)) return json({ ok: false, error: "unknown_point" }, 404, origin);
  const nowMs = Date.now();
  const nowS = Math.floor(nowMs / 1000);
  const hash = await ipHash(request, env, utcDay(nowMs));
  const blocked = await takeThrottle(env, hash, "r", id, nowS, nowMs);
  if (blocked) return json(blocked.body, blocked.status, origin, { "Retry-After": String(blocked.body.retry_after_s) });

  const cities = citiesFor(id);
  const scopes = ["uk"].concat(cities.map((c) => "city:" + c));
  const stmts = [
    env.DB.prepare(
      "INSERT INTO point_stats (point_id, refills) VALUES (?1, 1) " +
      "ON CONFLICT(point_id) DO UPDATE SET refills = point_stats.refills + 1"
    ).bind(id)
  ];
  scopes.forEach((s) => {
    stmts.push(env.DB.prepare(
      "INSERT INTO totals (scope, refills) VALUES (?1, 1) " +
      "ON CONFLICT(scope) DO UPDATE SET refills = totals.refills + 1"
    ).bind(s));
  });
  await env.DB.batch(stmts);
  const point = await readPoint(env, id);
  const t = await readTotals(env, scopes);
  return json({
    ok: true,
    point: point,
    uk: { refills: t.uk },
    cities: cities.map((c) => ({ slug: c, refills: t["city:" + c] }))
  }, 200, origin);
}

async function handleVote(request, env, origin) {
  const body = await readBody(request);
  const id = body && body.id;
  const vote = body && body.vote;
  if (!isValidId(id)) return json({ ok: false, error: "bad_id" }, 400, origin);
  if (vote !== "here" && vote !== "gone") return json({ ok: false, error: "bad_vote" }, 400, origin);
  if (!isKnownId(id)) return json({ ok: false, error: "unknown_point" }, 404, origin);
  const nowMs = Date.now();
  const nowS = Math.floor(nowMs / 1000);
  const day = utcDay(nowMs);
  const hash = await ipHash(request, env, day);
  const blocked = await takeThrottle(env, hash, "v", id, nowS, nowMs);
  if (blocked) return json(blocked.body, blocked.status, origin, { "Retry-After": String(blocked.body.retry_after_s) });
  const sql = vote === "here"
    ? "INSERT INTO point_stats (point_id, here, last_here) VALUES (?1, 1, ?2) " +
      "ON CONFLICT(point_id) DO UPDATE SET here = point_stats.here + 1, last_here = ?2"
    : "INSERT INTO point_stats (point_id, gone, last_gone) VALUES (?1, 1, ?2) " +
      "ON CONFLICT(point_id) DO UPDATE SET gone = point_stats.gone + 1, last_gone = ?2";
  await env.DB.prepare(sql).bind(id, day).run();
  const point = await readPoint(env, id);
  return json({ ok: true, point: point }, 200, origin);
}

export async function cleanup(env) {
  const nowS = Math.floor(Date.now() / 1000);
  await env.DB.prepare("DELETE FROM throttle WHERE expires_at <= ?1").bind(nowS).run();
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const origin = allowedOrigin(request, env);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    if (!path.startsWith("/api/")) {
      return json({ ok: false, error: "not_found" }, 404, origin);
    }
    if (request.method === "OPTIONS") {
      if (!origin) return new Response(null, { status: 403, headers: { "Vary": "Origin" } });
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (!env.DB) return json({ ok: false, error: "not_configured" }, 503, origin);

    try {
      if (request.method === "GET") {
        if (path === "/api/stats") return await handleStats(url, env, origin);
        if (path === "/api/health") return json({ ok: true, points: KNOWN ? Object.keys(KNOWN).length : null }, 200, origin);
        const m = path.match(/^\/api\/point\/([^/]+)$/);
        if (m) {
          let id;
          try { id = decodeURIComponent(m[1]); } catch (e) { id = ""; }
          return await handlePoint(id, env, origin);
        }
        return json({ ok: false, error: "not_found" }, 404, origin);
      }
      if (request.method === "POST") {
        // Writes are only accepted from the SipSpot site itself.
        if (!origin) return json({ ok: false, error: "forbidden_origin" }, 403, null);
        const type = request.headers.get("Content-Type") || "";
        if (!/^application\/json\b/i.test(type) && !/^text\/plain\b/i.test(type)) {
          return json({ ok: false, error: "bad_content_type" }, 415, origin);
        }
        if (path === "/api/refill") return await handleRefill(request, env, origin);
        if (path === "/api/vote") return await handleVote(request, env, origin);
        return json({ ok: false, error: "not_found" }, 404, origin);
      }
      return json({ ok: false, error: "method_not_allowed" }, 405, origin);
    } catch (err) {
      console.error("sipspot-api error", err && err.message);
      return json({ ok: false, error: "server_error" }, 500, origin);
    } finally {
      // Opportunistic tidy-up on a small share of writes, in addition to the cron.
      if (request.method === "POST" && env.DB && ctx && Math.random() < 0.02) {
        ctx.waitUntil(cleanup(env).catch(() => {}));
      }
    }
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(cleanup(env));
  }
};
