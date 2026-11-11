/* SipSpot service worker. CACHE_VERSION is kept in sync with the
 * site's ?v= stamp by scripts/generate_pages.py. */
const CACHE_VERSION = "cdcf7a4";
const SHELL_CACHE = "sipspot-shell-" + CACHE_VERSION;
const DATA_CACHE = "sipspot-data-" + CACHE_VERSION;
const CDN_CACHE = "sipspot-cdn-" + CACHE_VERSION;

const SHELL = [
  "./",
  "./index.html",
  "./offline.html",
  "./config.json",
  "./manifest.webmanifest",
  "./favicon.ico",
  "./css/style.css?v=" + CACHE_VERSION,
  "./js/config.js?v=" + CACHE_VERSION,
  "./js/app.js?v=" + CACHE_VERSION,
  "./js/map-provider.js?v=" + CACHE_VERSION,
  "./js/form.js?v=" + CACHE_VERSION,
  "./js/pwa.js?v=" + CACHE_VERSION,
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-512-maskable.png",
  "./icons/apple-touch-icon.png",
  "./icons/logo.svg"
];

const DATA_URLS = [
  "./data/points.geojson?v=" + CACHE_VERSION,
  "./data/partners.geojson?v=" + CACHE_VERSION
];

function isMapTile(url) {
  const host = url.hostname;
  return (
    host === "basemaps.cartocdn.com" ||
    host.endsWith(".basemaps.cartocdn.com") ||
    host.endsWith("cartocdn.com") ||
    host === "tile.openstreetmap.org" ||
    host.endsWith(".tile.openstreetmap.org") ||
    host.endsWith("stadiamaps.com") ||
    host.endsWith("maptiler.com") ||
    host.endsWith("openfreemap.org")
  );
}

function isMapLibrary(url) {
  const href = url.href;
  return (
    /unpkg\.com\/(leaflet|leaflet\.markercluster|maplibre-gl|@maplibre)\b/.test(href) ||
    /cdn\.jsdelivr\.net\/npm\/opening_hours/.test(href)
  );
}

/* Live counters must never be cached: skip the API host and any /api/ path. */
function isApiRequest(url) {
  return /^api\./.test(url.hostname) || /^\/api(?:\/|$)/.test(url.pathname);
}

function isHtmlRequest(request, url) {
  if (request.mode === "navigate") return true;
  const accept = request.headers.get("accept") || "";
  if (accept.includes("text/html")) return true;
  return url.origin === self.location.origin && /\.html(?:$|\?)/.test(url.pathname);
}

function isGeojson(url) {
  return url.origin === self.location.origin && /\/data\/[^/]+\.geojson(?:$|\?)/.test(url.pathname + url.search);
}

async function putIfOk(cache, request, response) {
  if (response && response.ok) {
    try {
      await cache.put(request, response.clone());
    } catch (err) {
      // Ignore quota / opaque failures; the response is still returned.
    }
  }
  return response;
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  await putIfOk(cache, request, response);
  return response;
}

async function networkFirst(request, cacheName, fallbackUrl) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    await putIfOk(cache, request, response);
    if (response && response.ok) return response;
    const cached = await cache.match(request);
    if (cached) return cached;
    if (response) return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (request.mode === "navigate" || (request.headers.get("accept") || "").includes("text/html")) {
      const offline = await cache.match(fallbackUrl || "./offline.html") ||
        await caches.match("./offline.html", { ignoreSearch: true });
      if (offline) return offline;
    }
    throw err;
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    for (const url of SHELL) {
      try {
        await cache.add(url);
      } catch (err) {
        console.warn("SipSpot SW: failed to precache", url);
      }
    }
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL_CACHE, DATA_CACHE, CDN_CACHE]);
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((key) => key.startsWith("sipspot-") && !keep.has(key))
        .map((key) => caches.delete(key))
    );
    await self.clients.claim();
    // Warm the last-seen map data so a first visit can go offline after this.
    const dataCache = await caches.open(DATA_CACHE);
    for (const url of DATA_URLS) {
      try {
        const response = await fetch(url, { credentials: "same-origin" });
        await putIfOk(dataCache, url, response);
      } catch (err) {
        // Offline during activate is fine; runtime caching will fill this later.
      }
    }
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  if (isApiRequest(url)) return;

  // Do not cache map tiles (licence and volume). Let the browser handle them.
  if (isMapTile(url)) return;

  if (isMapLibrary(url)) {
    event.respondWith(cacheFirst(request, CDN_CACHE));
    return;
  }

  if (isGeojson(url)) {
    event.respondWith(networkFirst(request, DATA_CACHE));
    return;
  }

  if (isHtmlRequest(request, url)) {
    event.respondWith(networkFirst(request, SHELL_CACHE, "./offline.html"));
    return;
  }

  if (url.origin === self.location.origin) {
    // Versioned CSS/JS use a new URL when ?v= changes, so cache-first is safe.
    event.respondWith(cacheFirst(request, SHELL_CACHE));
  }
});
