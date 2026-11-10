/* SipSpot — generated from config.json. Edit config.json, then run
 * python3 scripts/generate_pages.py to refresh this file and the HTML pages.
 * config.json is the source of truth for brand, domain and map settings.
 */
window.SIPSPOT_CONFIG = {
  brand: "SipSpot",
  shortBrand: "SipSpot",
  domain: "sipspot.uk",
  siteUrl: "https://sipspot.uk",
  locale: "en-GB",
  tagline: "Find it. Fill it. Go.",
  contactEmail: "hello@sipspot.uk",
  partnerFormEndpoint: "",
  osmAttributionText: "© OpenStreetMap contributors",
  osmAttributionUrl: "https://www.openstreetmap.org/copyright",
  tilesUrl: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  tilesAttribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors",
  tilesMaxZoom: 19,
  defaultCenter: [54.5, -2.8],
  defaultZoom: 6,
  clusterDisableZoom: 16,
  walkingDetour: 1.25,
  walkingKmh: 5,
  osmDataUrl: "/data/points.geojson",
  partnerDataUrl: "/data/partners.geojson",
  mapProvider: "leaflet-osm",
  googleMapsApiKey: "",
  palette: "Fresh",
  colors: {"primary": "#1E88E5", "leaf": "#43A047", "background": "#E3F2FD", "partner": "#8E24AA"},
  posterLine: "Skip the plastic. Find a tap.",
  metaDescription: "Find it. Fill it. Go. Free drinking water and bottle-fill points across the UK. No app, no account.",
  staleAfterMonths: 36,
  feedback: {"enabled": true, "endpoint": null, "dataUrl": "/data/feedback.json"}
};
window.REFILLMAP_CONFIG = window.SIPSPOT_CONFIG;

(function (cfg) {
  if (!cfg) return;
  function detectBasePath() {
    var scripts = document.getElementsByTagName('script');
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].getAttribute('src') || '';
      if (!/(?:^|\/)js\/(?:config|app|form|map-provider)\.js(?:\?|$)/.test(src)) continue;
      var url = new URL(src, document.baseURI);
      return url.pathname.replace(/\/js\/[^/]+$/, '/');
    }
    return '/';
  }
  function withBase(path) {
    if (!path) return path;
    if (/^(https?:)?\/\//i.test(path) || path.indexOf('data:') === 0 || path.indexOf('mailto:') === 0) return path;
    var base = cfg.basePath || '/';
    return base.replace(/\/+$/, '') + '/' + String(path).replace(/^\/+/, '');
  }
  cfg.basePath = detectBasePath();
  cfg.withBase = withBase;
  if (cfg.osmDataUrl) cfg.osmDataUrl = withBase(cfg.osmDataUrl);
  if (cfg.partnerDataUrl) cfg.partnerDataUrl = withBase(cfg.partnerDataUrl);
  if (cfg.feedback && cfg.feedback.dataUrl) cfg.feedback.dataUrl = withBase(cfg.feedback.dataUrl);
})(window.SIPSPOT_CONFIG);
