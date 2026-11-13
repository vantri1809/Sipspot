/* SipSpot — generated from config.json. Edit config.json, then run
 * python3 scripts/generate_pages.py to refresh this file and the HTML pages.
 * config.json is the source of truth for brand, domain and map settings.
 */
window.SIPSPOT_CONFIG = {
  brand: "SipSpot",
  shortBrand: "SipSpot",
  domain: "sipspot.co.uk",
  siteUrl: "https://sipspot.co.uk",
  locale: "en-GB",
  tagline: "Find it. Fill it. Go.",
  contactEmail: "hello@sipspot.co.uk",
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
  basemap: "carto-voyager",
  tilesApiKey: "cb1_56i5_1_6839c644a0509397bfd4be67",
  googleMapsApiKey: "",
  palette: "Fresh",
  colors: {"primary": "#1E88E5", "leaf": "#43A047", "background": "#E3F2FD", "partner": "#8E24AA"},
  posterLine: "Skip the plastic. Find a tap.",
  metaDescription: "Find it. Fill it. Go. Free drinking water and bottle-fill points across the UK. No app, no account.",
  staleAfterMonths: 36,
  feedback: {"enabled": true, "endpoint": null, "dataUrl": "/data/feedback.json"},
  apiBase: "https://api.sipspot.co.uk"
};
window.REFILLMAP_CONFIG = window.SIPSPOT_CONFIG;

(function (cfg) {
  if (!cfg) return;
  function detectBasePath() {
    var scripts = document.getElementsByTagName('script');
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].getAttribute('src') || '';
      if (!/(?:^|\/)js\/(?:config|app|form|map-provider|pwa)\.js(?:\?|$)/.test(src)) continue;
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
  var assetVersion = "b465456";
  function withVersion(url) {
    if (!url) return url;
    if (/^(https?:)?\/\//i.test(url) && url.indexOf(location.origin) !== 0) return url;
    if (/[?&]v=/.test(url)) return url;
    return url + (url.indexOf('?') >= 0 ? '&' : '?') + 'v=' + assetVersion;
  }
  cfg.basePath = detectBasePath();
  cfg.assetVersion = assetVersion;
  cfg.withBase = withBase;
  cfg.withVersion = withVersion;
  if (cfg.osmDataUrl) cfg.osmDataUrl = withVersion(withBase(cfg.osmDataUrl));
  if (cfg.partnerDataUrl) cfg.partnerDataUrl = withVersion(withBase(cfg.partnerDataUrl));
  if (cfg.feedback && cfg.feedback.dataUrl) cfg.feedback.dataUrl = withVersion(withBase(cfg.feedback.dataUrl));
})(window.SIPSPOT_CONFIG);
