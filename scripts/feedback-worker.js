/**
 * Example Cloudflare Worker for SipSpot "Still here" / "Gone" votes.
 *
 * This file is not deployed. To use it:
 *   1. Create a Worker and a KV namespace in the Cloudflare dashboard.
 *   2. Bind the KV namespace to the Worker as FEEDBACK.
 *   3. Deploy this script as the Worker.
 *   4. Set feedback.endpoint in config.json to the Worker URL, then run
 *      python3 scripts/generate_pages.py.
 *
 * Votes are stored only. They must never be used to automatically remove
 * points from the map. CORS is open so the static site can POST from a
 * different origin; tighten Allowed-Origin before a public launch.
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Accept",
  "Access-Control-Max-Age": "86400"
};

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS }
  });
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }
    if (request.method !== "POST") {
      return json({ error: "Method not allowed" }, 405);
    }
    if (!env || !env.FEEDBACK) {
      return json({ error: "FEEDBACK KV binding is not configured" }, 500);
    }

    let body;
    try {
      body = await request.json();
    } catch (err) {
      return json({ error: "Invalid JSON" }, 400);
    }

    const vote = body && body.vote;
    const osmType = body && body.osm_type;
    const osmId = body && body.osm_id;
    if ((vote !== "here" && vote !== "gone") || !osmType || osmId == null || osmId === "") {
      return json({ error: "Need osm_type, osm_id and vote (here or gone)" }, 400);
    }

    const rec = {
      osm_type: String(osmType),
      osm_id: String(osmId),
      vote: vote,
      ts: typeof body.ts === "string" && body.ts ? body.ts : new Date().toISOString(),
      page: typeof body.page === "string" ? body.page : null
    };
    const key = "vote:" + rec.osm_type + ":" + rec.osm_id + ":" + rec.ts + ":" + crypto.randomUUID();
    await env.FEEDBACK.put(key, JSON.stringify(rec));
    return json({ ok: true });
  }
};
