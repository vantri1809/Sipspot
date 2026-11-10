/* SipSpot map + list. OSM and partner data are loaded and filtered
 * as two separate collections and are never merged into one dataset.
 * Map rendering goes through js/map-provider.js so the basemap can be
 * swapped without changing pins, filters, or the partner layer.
 * SipSpot lists only free fills. Points tagged fee=yes are excluded.
 */
(function () {
  const cfg = window.SIPSPOT_CONFIG || window.REFILLMAP_CONFIG;
  const state = {
    osmFeatures: [],
    partnerFeatures: [],
    userLat: null,
    userLon: null,
    filters: {
      public_fountain: false,
      cafe_refill: false,
      bottle: false,
      partner: false,
      filtered: false,
      chilled: false,
      open_now: false,
      hide_stale: false
    },
    city: null,
    map: null,
    feedbackByKey: {}
  };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function formatDate(iso) {
    if (!iso) return "unknown";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return new Intl.DateTimeFormat("en-GB", {
      day: "numeric",
      month: "long",
      year: "numeric"
    }).format(d);
  }

  function formatMonthYear(iso) {
    if (!iso) return "unknown";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "unknown";
    return new Intl.DateTimeFormat("en-GB", {
      month: "short",
      year: "numeric"
    }).format(d);
  }

  function staleThresholdMonths() {
    const n = Number(cfg.staleAfterMonths);
    return Number.isFinite(n) && n > 0 ? n : 36;
  }

  function staleThresholdPhrase() {
    const months = staleThresholdMonths();
    if (months % 12 === 0) {
      const years = months / 12;
      return years === 1 ? "1+ year" : years + "+ years";
    }
    return months + "+ months";
  }

  function subtractMonths(from, months) {
    const d = new Date(from.getTime());
    const day = d.getDate();
    d.setDate(1);
    d.setMonth(d.getMonth() - months);
    const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
    d.setDate(Math.min(day, last));
    return d;
  }

  function osmEditDate(props) {
    if (!props || !props.timestamp) return null;
    const d = new Date(props.timestamp);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  /* Partner points are never treated as stale. Missing timestamps are not guessed. */
  function isOsmStale(props) {
    const edited = osmEditDate(props);
    if (!edited) return false;
    return edited <= subtractMonths(new Date(), staleThresholdMonths());
  }

  function staleNoteText() {
    return "Last updated on OpenStreetMap over " + staleThresholdPhrase().replace("+", "") + " ago, so it may have changed.";
  }

  function applyStaleLabels() {
    const phrase = staleThresholdPhrase();
    $all("[data-stale-legend]").forEach((el) => {
      el.textContent = "Not updated in " + phrase;
    });
    $all('[data-filter="hide_stale"]').forEach((el) => {
      el.textContent = "Hide points not updated in " + phrase;
    });
  }

  const FEEDBACK_STORE = "sipspot-feedback-v1";

  function feedbackConfig() {
    return cfg.feedback || {};
  }

  function feedbackEnabled() {
    const fb = feedbackConfig();
    return fb.enabled !== false;
  }

  function feedbackKey(osmType, osmId) {
    return String(osmType) + ":" + String(osmId);
  }

  function readStoredVotes() {
    try {
      const raw = localStorage.getItem(FEEDBACK_STORE);
      const data = raw ? JSON.parse(raw) : {};
      return data && typeof data === "object" ? data : {};
    } catch (err) {
      return {};
    }
  }

  function getStoredVote(osmType, osmId) {
    return readStoredVotes()[feedbackKey(osmType, osmId)] || null;
  }

  function saveStoredVote(osmType, osmId, vote) {
    const all = readStoredVotes();
    all[feedbackKey(osmType, osmId)] = {
      vote: vote,
      ts: new Date().toISOString()
    };
    try {
      localStorage.setItem(FEEDBACK_STORE, JSON.stringify(all));
    } catch (err) {
      /* private mode or quota — still show the thank-you state for this visit */
    }
  }

  function visitorConfirmation(osmType, osmId) {
    return state.feedbackByKey[feedbackKey(osmType, osmId)] || null;
  }

  function osmNoteUrl(lat, lon) {
    return "https://www.openstreetmap.org/note/new#map=19/" + lat + "/" + lon;
  }

  function confirmDateLabel(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    if (/^\d{4}-\d{2}$/.test(String(iso))) {
      return new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" }).format(d);
    }
    return formatDate(iso);
  }

  function feedbackThanksHtml(vote, lat, lon) {
    let html = '<p class="feedback-thanks" role="status">Thank you. We have noted this.</p>';
    if (vote === "gone" && lat != null && lon != null) {
      html +=
        '<p class="feedback-osm-note">If you can, report it on OpenStreetMap so the map can be updated.</p>' +
        '<a class="feedback-osm-link" href="' + osmNoteUrl(lat, lon) + '" target="_blank" rel="noopener">Report it on OpenStreetMap</a>';
    }
    return html;
  }

  function feedbackBlock(feature) {
    if (!feedbackEnabled()) return "";
    const p = feature.properties || {};
    if (!p.osm_type || p.osm_id == null) return "";
    const ll = featureLatLon(feature) || {};
    const stored = getStoredVote(p.osm_type, p.osm_id);
    let inner;
    if (stored && (stored.vote === "here" || stored.vote === "gone")) {
      inner = feedbackThanksHtml(stored.vote, ll.lat, ll.lon);
    } else {
      inner =
        '<p class="feedback-prompt">Is this still here?</p>' +
        '<div class="feedback-actions">' +
          '<button type="button" class="feedback-btn feedback-here" data-vote="here">Still here</button>' +
          '<button type="button" class="feedback-btn feedback-gone" data-vote="gone">Gone</button>' +
        "</div>";
    }
    return (
      '<div class="point-feedback" data-osm-type="' + escapeHtml(p.osm_type) +
      '" data-osm-id="' + escapeHtml(p.osm_id) +
      '" data-lat="' + ll.lat +
      '" data-lon="' + ll.lon +
      '">' + inner + "</div>"
    );
  }

  function postFeedbackVote(payload) {
    const endpoint = feedbackConfig().endpoint;
    if (!endpoint) return;
    fetch(String(endpoint), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload)
    }).catch(function () {
      /* votes are still kept in this browser; nothing to show until an endpoint is set */
    });
  }

  function submitFeedback(box, vote) {
    if (!box || (vote !== "here" && vote !== "gone")) return;
    const osmType = box.getAttribute("data-osm-type");
    const osmIdRaw = box.getAttribute("data-osm-id");
    if (!osmType || osmIdRaw == null) return;
    if (getStoredVote(osmType, osmIdRaw)) {
      const existing = getStoredVote(osmType, osmIdRaw);
      box.innerHTML = feedbackThanksHtml(existing.vote, box.getAttribute("data-lat"), box.getAttribute("data-lon"));
      return;
    }
    const osmId = /^-?\d+$/.test(osmIdRaw) ? Number(osmIdRaw) : osmIdRaw;
    const ts = new Date().toISOString();
    saveStoredVote(osmType, osmIdRaw, vote);
    postFeedbackVote({
      osm_type: osmType,
      osm_id: osmId,
      vote: vote,
      ts: ts,
      page: window.location.pathname || "/"
    });
    box.innerHTML = feedbackThanksHtml(vote, box.getAttribute("data-lat"), box.getAttribute("data-lon"));
  }

  function indexFeedbackOverlay(data) {
    const byKey = {};
    const rows = Array.isArray(data)
      ? data
      : (data && (data.points || data.confirmations || data.features)) || [];
    rows.forEach(function (row) {
      if (!row) return;
      const props = row.properties || row;
      const osmType = props.osm_type;
      const osmId = props.osm_id;
      if (!osmType || osmId == null) return;
      const status = String(props.status || props.vote || "here").toLowerCase();
      const confirmedOn = props.confirmed_on || props.confirmedOn || props.date || null;
      byKey[feedbackKey(osmType, osmId)] = {
        status: status,
        confirmed_on: confirmedOn
      };
    });
    state.feedbackByKey = byKey;
  }

  function loadFeedbackOverlay() {
    const url = feedbackConfig().dataUrl || (cfg.withBase ? cfg.withBase("/data/feedback.json") : "data/feedback.json");
    return loadJson(url).then(indexFeedbackOverlay).catch(function () {
      state.feedbackByKey = {};
    });
  }

  function haversineMetres(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = (d) => d * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  function walkingLabel(metresStraight) {
    const walk = metresStraight * (cfg.walkingDetour || 1.25);
    const minutes = Math.max(1, Math.round((walk / 1000) / (cfg.walkingKmh || 5) * 60));
    let dist;
    if (walk < 1000) dist = Math.round(walk / 10) * 10 + " m";
    else dist = (walk / 1000).toFixed(walk >= 10000 ? 0 : 1).replace(/\.0$/, "") + " km";
    return "Approx. " + dist + " walk (" + minutes + " min)";
  }

  function pointInCity(lat, lon, city) {
    if (!city) return true;
    const km = haversineMetres(lat, lon, city.lat, city.lon) / 1000;
    return km <= city.radius_km;
  }

  function isPaid(props) {
    const fee = String(props.fee || "").toLowerCase();
    return fee === "yes" || fee === "true" || fee === "paid";
  }

  function isRestrictedAccess(props) {
    const access = String(props.access || "").toLowerCase();
    return access === "customers" || access === "private" || access === "no";
  }

  function isWalkInFreeOsm(props) {
    return !isPaid(props) && !isRestrictedAccess(props);
  }

  function isPartnerWalkInFree(props) {
    const offered = String(props.refill_offered || "free").toLowerCase();
    const offeredOk = offered === "free" || offered === "yes" || offered === "y" || offered === "";
    const walkIn = props.walk_in_free;
    const walkOk = walkIn === true || String(walkIn).toLowerCase() === "yes" || String(walkIn).toLowerCase() === "y";
    return offeredOk && walkOk;
  }

  function hoursString(props) {
    const raw = props.opening_hours || props.hours;
    if (raw && String(raw).trim()) return String(raw).trim();
    return null;
  }

  function fallbackIsOpen(raw, now) {
    const s = raw.trim();
    if (/^24\/7$/i.test(s)) return true;
    // Simple "Mo-Fr 08:00-17:00" / "Mo-Su 07:00-19:00" / several "; "-separated rules
    const days = ["su", "mo", "tu", "we", "th", "fr", "sa"];
    const day = days[now.getDay()];
    const mins = now.getHours() * 60 + now.getMinutes();
    const dayAliases = {
      mo: 1, tu: 2, we: 3, th: 4, fr: 5, sa: 6, su: 0,
      monday: 1, tuesday: 2, wednesday: 3, thursday: 4, friday: 5, saturday: 6, sunday: 0
    };
    function parseDayToken(tok) {
      return dayAliases[tok.toLowerCase()];
    }
    function inDayRange(spec) {
      const m = spec.trim().toLowerCase().match(/^([a-z]{2})(?:-([a-z]{2}))?$/);
      if (!m) return false;
      const a = parseDayToken(m[1]);
      const b = m[2] ? parseDayToken(m[2]) : a;
      if (a == null || b == null) return false;
      const today = now.getDay();
      if (a <= b) return today >= a && today <= b;
      return today >= a || today <= b;
    }
    function inTimeRange(spec) {
      const m = spec.trim().match(/^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$/);
      if (!m) return false;
      const start = Number(m[1]) * 60 + Number(m[2]);
      const end = Number(m[3]) * 60 + Number(m[4]);
      if (end <= start) return mins >= start || mins < end;
      return mins >= start && mins < end;
    }
    // Reject strings we cannot reasonably parse
    if (/PH|off|sunrise|sunset|\|\||months/i.test(s) && !/^24\/7$/i.test(s)) {
      const simple = /^(?:Mo|Tu|We|Th|Fr|Sa|Su)/i.test(s) && /^\S/.test(s);
      if (!simple) return null;
    }
    const rules = s.split(";").map((r) => r.trim()).filter(Boolean);
    let matched = false;
    let open = false;
    for (const rule of rules) {
      if (/^off$/i.test(rule)) continue;
      const parts = rule.split(/\s+/);
      if (parts.length < 2) return null;
      const dayPart = parts[0];
      const timePart = parts.slice(1).join(" ");
      if (!inDayRange(dayPart)) continue;
      matched = true;
      if (inTimeRange(timePart)) open = true;
    }
    if (!matched) {
      // Might be a format we didn't understand
      if (!/^(Mo|Tu|We|Th|Fr|Sa|Su)/i.test(s)) return null;
      return false;
    }
    return open;
  }

  function parseOpenState(raw) {
    if (!raw) return { parsed: false, open: null };
    const now = new Date();
    if (typeof opening_hours === "function") {
      try {
        const oh = new opening_hours(raw, { address: { country_code: "gb" } });
        return { parsed: true, open: !!oh.getState(now) };
      } catch (err) {
        /* fall through to the simple parser */
      }
    }
    const fb = fallbackIsOpen(raw, now);
    if (fb == null) return { parsed: false, open: null };
    return { parsed: true, open: fb };
  }

  function hoursInfo(props) {
    const raw = hoursString(props);
    if (!raw) {
      return { raw: null, text: "Hours not listed", state: "unknown", parsed: false, open: null };
    }
    const parsed = parseOpenState(raw);
    let state = "listed";
    if (parsed.parsed && parsed.open === true) state = "open";
    else if (parsed.parsed && parsed.open === false) state = "closed";
    else state = "unparsed";
    return { raw: raw, text: raw, state: state, parsed: parsed.parsed, open: parsed.open };
  }

  function isFilteredType(props) {
    const t = props.water_type;
    return t === "filtered" || t === "chilled_filtered";
  }

  function isChilled(props) {
    return props.chilled === true || props.water_type === "chilled_filtered";
  }

  function waterTypeLabel(props) {
    if (props.water_type_label) return props.water_type_label;
    const t = props.water_type;
    if (t === "tap") return "Tap water";
    if (t === "filtered") return "Filtered water";
    if (t === "chilled_filtered") return "Chilled filtered water";
    return "Unknown";
  }

  function osmPassesFilters(props) {
    if (!isWalkInFreeOsm(props)) return false;
    const f = state.filters;
    const typeWanted = f.public_fountain || f.cafe_refill;
    if (typeWanted) {
      if (f.public_fountain && props.category === "public_fountain") { /* ok */ }
      else if (f.cafe_refill && props.category === "cafe_refill") { /* ok */ }
      else return false;
    }
    if (f.bottle && props.bottle !== "yes") return false;
    if (f.filtered && !isFilteredType(props)) return false;
    if (f.chilled && !isChilled(props)) return false;
    if (f.open_now) {
      const info = hoursInfo(props);
      if (!(info.parsed && info.open)) return false;
    }
    if (f.hide_stale && isOsmStale(props)) return false;
    return true;
  }

  function partnerPassesFilters(props) {
    if (!isPartnerWalkInFree(props)) return false;
    const f = state.filters;
    const typeWanted = f.public_fountain || f.cafe_refill || f.partner;
    if (typeWanted && !f.partner) return false;
    if (f.bottle) return false;
    if (f.filtered && !isFilteredType(props)) return false;
    if (f.chilled && !isChilled(props)) return false;
    if (f.open_now) {
      const info = hoursInfo(props);
      if (!(info.parsed && info.open)) return false;
    }
    return true;
  }

  function featureLatLon(feature) {
    const c = feature.geometry && feature.geometry.coordinates;
    if (!c) return null;
    return { lon: c[0], lat: c[1] };
  }

  function displayName(props, fallbackKind) {
    return props.name || fallbackKind || "Water refill point";
  }

  function accessLabel(access) {
    if (!access) return "Access not recorded";
    const map = {
      yes: "Public access",
      public: "Public access",
      permissive: "Permissive access",
      customers: "Customers only",
      private: "Private",
      no: "No public access"
    };
    return map[access] || ("Access: " + access);
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function hoursBlock(props) {
    const info = hoursInfo(props);
    let badge = "";
    if (info.state === "open") badge = '<span class="badge open">Open now</span>';
    else if (info.state === "closed") badge = '<span class="badge closed">Closed now</span>';
    return (
      '<p class="hours-prominent"><strong>Hours:</strong> ' +
      escapeHtml(info.text) + " " + badge + "</p>"
    );
  }

  function waterBadges(props) {
    const badges = [];
    const typeKey = props.water_type || "unknown";
    const typeClass = typeKey === "chilled_filtered" ? "filtered" : typeKey;
    badges.push('<span class="badge water-' + typeClass + '">' + escapeHtml(waterTypeLabel(props)) + "</span>");
    if (isChilled(props) && typeKey !== "chilled_filtered") {
      badges.push('<span class="badge chilled">Chilled</span>');
    }
    return badges;
  }

  let directMeSeq = 0;

  function isApplePlatform() {
    const ua = navigator.userAgent || "";
    const plat = navigator.platform || "";
    return /iPad|iPhone|iPod|Macintosh|Mac OS X/i.test(ua) || /Mac|iPhone|iPad|iPod/i.test(plat);
  }

  function directionsBlock(lat, lon) {
    const gmaps = "https://www.google.com/maps/dir/?api=1&destination=" + lat + "," + lon;
    const amaps = "https://maps.apple.com/?daddr=" + lat + "," + lon;
    const appleFirst = isApplePlatform();
    const first = appleFirst
      ? { href: amaps, label: "Apple Maps" }
      : { href: gmaps, label: "Google Maps" };
    const second = appleFirst
      ? { href: gmaps, label: "Google Maps" }
      : { href: amaps, label: "Apple Maps" };
    const id = "direct-choices-" + (++directMeSeq);
    return (
      '<div class="direct-me">' +
        '<button type="button" class="direct-me-btn" aria-expanded="false" aria-controls="' + id + '" aria-haspopup="true">' +
          "Direct me there" +
        "</button>" +
        '<div class="direct-me-choices" id="' + id + '" hidden>' +
          '<a class="direct-choice" href="' + first.href + '" target="_blank" rel="noopener">' + escapeHtml(first.label) + "</a>" +
          '<a class="direct-choice" href="' + second.href + '" target="_blank" rel="noopener">' + escapeHtml(second.label) + "</a>" +
        "</div>" +
      "</div>"
    );
  }

  function toggleDirectMe(btn) {
    const expanded = btn.getAttribute("aria-expanded") === "true";
    const next = !expanded;
    btn.setAttribute("aria-expanded", next ? "true" : "false");
    const id = btn.getAttribute("aria-controls");
    const panel = id ? document.getElementById(id) : (btn.parentElement && btn.parentElement.querySelector(".direct-me-choices"));
    if (panel) {
      if (next) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
    }
  }

  function isPopupControl(target) {
    return !!(target && target.closest && target.closest(".direct-me, .point-feedback"));
  }

  function stopPopupControlMapEvent(e) {
    if (isPopupControl(e.target)) {
      e.stopPropagation();
    }
  }

  function initDirections() {
    document.addEventListener("click", function (e) {
      const btn = e.target && e.target.closest && e.target.closest(".direct-me-btn");
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      toggleDirectMe(btn);
    }, true);
    document.addEventListener("click", function (e) {
      const btn = e.target && e.target.closest && e.target.closest(".point-feedback .feedback-btn");
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      const box = btn.closest(".point-feedback");
      submitFeedback(box, btn.getAttribute("data-vote"));
    }, true);
    ["pointerdown", "mousedown", "touchstart", "dblclick"].forEach(function (type) {
      document.addEventListener(type, stopPopupControlMapEvent, true);
    });
  }

  function osmPopup(feature) {
    const p = feature.properties;
    const { lat, lon } = featureLatLon(feature);
    const osmUrl = "https://www.openstreetmap.org/" + p.osm_type + "/" + p.osm_id;
    const editUrl = "https://www.openstreetmap.org/edit?" + p.osm_type + "=" + p.osm_id;
    const name = displayName(p, p.kind);
    const bottle = p.bottle === "yes" ? "Bottle-friendly" : (p.bottle === "no" ? "Not bottle-friendly" : null);
    return (
      '<div class="popup">' +
        "<h3>" + escapeHtml(name) + "</h3>" +
        "<p>" + escapeHtml(p.kind || "Drinking water") + " · " + waterBadges(p).join(" ") + "</p>" +
        hoursBlock(p) +
        "<p>" + escapeHtml(accessLabel(p.access)) + "</p>" +
        (bottle ? "<p>" + escapeHtml(bottle) + "</p>" : "") +
        "<p class=\"popup-updated\">Last updated: " + escapeHtml(formatMonthYear(p.timestamp)) + "</p>" +
        visitorConfirmedBlock(p) +
        (isOsmStale(p) ? '<p class="stale-note">' + escapeHtml(staleNoteText()) + "</p>" : "") +
        directionsBlock(lat, lon) +
        feedbackBlock(feature) +
        '<div class="popup-links">' +
          '<a href="' + editUrl + '" target="_blank" rel="noopener">Is this wrong? Fix on OpenStreetMap</a>' +
          '<a href="' + osmUrl + '" target="_blank" rel="noopener">View on OpenStreetMap</a>' +
        "</div>" +
      "</div>"
    );
  }

  function visitorConfirmedBlock(props) {
    const rec = visitorConfirmation(props.osm_type, props.osm_id);
    if (!rec) return "";
    const status = rec.status || "here";
    if (status !== "here" && status !== "confirmed") return "";
    const when = confirmDateLabel(rec.confirmed_on);
    if (!when) return "";
    return '<p class="visitor-confirmed">Confirmed by visitors on ' + escapeHtml(when) + "</p>";
  }

  function partnerPopup(feature) {
    const p = feature.properties;
    const { lat, lon } = featureLatLon(feature);
    const example = p.is_example
      ? '<div class="example-banner">Example listing — not a real refill point</div>'
      : "";
    const sponsor = p.partner ? "<p>Sponsored by " + escapeHtml(p.partner) + "</p>" : "";
    const verified = p.verified_date ? "Verified: " + formatDate(p.verified_date) : "Not yet verified";
    const logo = p.logo_url
      ? '<p><img src="' + escapeHtml(p.logo_url) + '" alt="" style="max-height:36px"></p>'
      : "";
    return (
      '<div class="popup">' +
        example +
        "<h3>" + escapeHtml(p.name || "Cooler partner") + "</h3>" +
        '<p><span class="badge partner">Cooler partner</span> ' + waterBadges(p).join(" ") + "</p>" +
        hoursBlock(p) +
        (p.address ? "<p>" + escapeHtml(p.address) + "</p>" : "") +
        sponsor + logo +
        "<p>" + escapeHtml(verified) + "</p>" +
        directionsBlock(lat, lon) +
      "</div>"
    );
  }

  function visibleOsm() {
    return state.osmFeatures.filter((f) => {
      const ll = featureLatLon(f);
      if (!ll) return false;
      if (!pointInCity(ll.lat, ll.lon, state.city)) return false;
      return osmPassesFilters(f.properties);
    });
  }

  function visiblePartners() {
    return state.partnerFeatures.filter((f) => {
      const ll = featureLatLon(f);
      if (!ll) return false;
      if (!pointInCity(ll.lat, ll.lon, state.city)) return false;
      return partnerPassesFilters(f.properties);
    });
  }

  function withDistance(features, source) {
    return features.map((f) => {
      const ll = featureLatLon(f);
      let metres = null;
      if (state.userLat != null && ll) {
        metres = haversineMetres(state.userLat, state.userLon, ll.lat, ll.lon);
      }
      return { feature: f, source: source, metres: metres, lat: ll.lat, lon: ll.lon };
    });
  }

  function renderMarkers() {
    const map = state.map;
    if (!map) return;
    map.clearGroup("osm");
    map.clearGroup("partner");

    visibleOsm().forEach((f) => {
      const ll = featureLatLon(f);
      const p = f.properties;
      map.addMarker("osm", {
        lat: ll.lat,
        lon: ll.lon,
        kind: p.category || "public_fountain",
        title: displayName(p, p.kind),
        popupHtml: osmPopup(f),
        water_type: p.water_type,
        chilled: p.chilled,
        stale: isOsmStale(p)
      });
    });

    visiblePartners().forEach((f) => {
      const ll = featureLatLon(f);
      const p = f.properties;
      map.addMarker("partner", {
        lat: ll.lat,
        lon: ll.lon,
        kind: "partner",
        title: p.name || "Cooler partner",
        popupHtml: partnerPopup(f),
        water_type: p.water_type,
        chilled: p.chilled
      });
    });
  }

  function renderList() {
    const list = $("#result-list");
    const meta = $("#results-meta");
    if (!list) return;
    const osmItems = withDistance(visibleOsm(), "osm");
    const partnerItems = withDistance(visiblePartners(), "partner");
    const items = osmItems.concat(partnerItems);
    items.sort((a, b) => {
      if (a.metres == null && b.metres == null) {
        const an = (a.feature.properties.name || a.feature.properties.kind || "").toLowerCase();
        const bn = (b.feature.properties.name || b.feature.properties.kind || "").toLowerCase();
        return an.localeCompare(bn, "en-GB");
      }
      if (a.metres == null) return 1;
      if (b.metres == null) return -1;
      return a.metres - b.metres;
    });

    const osmCount = osmItems.length;
    const partnerCount = partnerItems.length;
    let summary = osmCount + " OpenStreetMap point" + (osmCount === 1 ? "" : "s");
    if (partnerCount) {
      summary += " and " + partnerCount + " cooler partner" + (partnerCount === 1 ? "" : "s");
    }
    if (state.userLat != null) summary += ", nearest first";
    if (meta) meta.textContent = summary;

    const limit = state.city ? 80 : 40;
    const shown = items.slice(0, limit);
    list.innerHTML = "";
    if (!shown.length) {
      list.innerHTML = "<li><p class=\"results-meta\">No points match these filters.</p></li>";
      return;
    }
    shown.forEach((item) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "result-card " + (item.source === "partner" ? "is-partner" : "is-osm");
      const p = item.feature.properties;
      const title = item.source === "partner" ? (p.name || "Cooler partner") : displayName(p, p.kind);
      const badges = [];
      if (item.source === "partner") badges.push('<span class="badge partner">Cooler partner</span>');
      if (p.is_example) badges.push('<span class="badge example">Example data</span>');
      if (p.kind && item.source === "osm") badges.push('<span class="badge">' + escapeHtml(p.kind) + "</span>");
      badges.push.apply(badges, waterBadges(p));
      if (p.bottle === "yes") badges.push('<span class="badge">Bottle-friendly</span>');
      if (item.source === "osm" && isOsmStale(p)) {
        badges.push('<span class="badge stale">May have changed</span>');
        btn.classList.add("is-stale");
      }
      const hours = hoursInfo(p);
      if (hours.state === "open") badges.push('<span class="badge open">Open now</span>');
      else if (hours.state === "closed") badges.push('<span class="badge closed">Closed now</span>');
      const bits = [];
      bits.push(hours.raw ? hours.text : "Hours not listed");
      if (item.metres != null) bits.push(walkingLabel(item.metres));
      if (item.source === "osm") bits.push("Last updated: " + formatMonthYear(p.timestamp));
      if (item.source === "partner" && p.address) bits.push(p.address);
      if (item.source === "partner" && p.partner) bits.push("Sponsored by " + p.partner);
      btn.innerHTML =
        "<h3>" + escapeHtml(title) + "</h3>" +
        '<p class="hours-prominent"><strong>Hours:</strong> ' + escapeHtml(hours.text) + "</p>" +
        "<div>" + badges.join(" ") + "</div>" +
        '<div class="meta">' + escapeHtml(bits.filter((b) => b !== hours.text && b !== "Hours not listed").join(" · ")) + "</div>";
      btn.addEventListener("click", () => {
        state.map.openPopupAt(item.source === "partner" ? "partner" : "osm", item.lat, item.lon, 16);
      });
      li.appendChild(btn);
      list.appendChild(li);
    });
    if (items.length > limit) {
      const more = document.createElement("li");
      more.innerHTML = '<p class="results-meta">Showing the first ' + limit + " of " + items.length + ". Zoom the map or use Find water near me to narrow the list.</p>";
      list.appendChild(more);
    }
  }

  function refresh() {
    renderMarkers();
    renderList();
  }

  function setStatus(msg, isError) {
    const el = $("#status");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.toggle("error", !!isError);
  }

  function locate() {
    const btn = $("#locate-btn");
    if (!navigator.geolocation) {
      setStatus("Geolocation is not supported in this browser.", true);
      return;
    }
    if (btn) btn.disabled = true;
    setStatus("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        state.userLat = pos.coords.latitude;
        state.userLon = pos.coords.longitude;
        state.map.addUserMarker(state.userLat, state.userLon, "You are here");
        state.map.setView(state.userLat, state.userLon, 14);
        if (btn) btn.disabled = false;
        setStatus("Showing points nearest to you. Distances are an approximate walking estimate, not a turn-by-turn route.");
        refresh();
      },
      (err) => {
        if (btn) btn.disabled = false;
        const msg = err && err.code === 1
          ? "Location permission was denied. You can still browse the map."
          : "Could not get your location. You can still browse the map.";
        setStatus(msg, true);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
    );
  }

  function initFilters() {
    $all("[data-filter]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const key = chip.getAttribute("data-filter");
        const next = chip.getAttribute("aria-pressed") !== "true";
        chip.setAttribute("aria-pressed", next ? "true" : "false");
        state.filters[key] = next;
        refresh();
      });
    });
  }

  function initMap() {
    const city = state.city;
    const center = city ? [city.lat, city.lon] : cfg.defaultCenter;
    const zoom = city ? city.zoom || 12 : cfg.defaultZoom;
    const map = window.RefillMap.createMap($("#map"), { center: center, zoom: zoom });
    map.addClusterGroup("osm", { kind: "osm" });
    map.addClusterGroup("partner", { kind: "partner" });
    state.map = map;
  }

  function loadJson(url) {
    return fetch(url, { credentials: "same-origin" }).then((res) => {
      if (!res.ok) throw new Error("Failed to load " + url + " (" + res.status + ")");
      return res.json();
    });
  }

  function applyBrand() {
    $all("[data-brand]").forEach((el) => { el.textContent = cfg.brand; });
    $all("[data-tagline]").forEach((el) => { el.textContent = cfg.tagline; });
  }

  function boot() {
    applyBrand();
    const cityEl = document.getElementById("city-data");
    if (cityEl) {
      try { state.city = JSON.parse(cityEl.textContent); } catch (e) { state.city = null; }
    }
    if (!$("#map")) return;
    initMap();
    initFilters();
    initDirections();
    applyStaleLabels();
    const locateBtn = $("#locate-btn");
    if (locateBtn) locateBtn.addEventListener("click", locate);

    setStatus("Loading map data…");
    Promise.all([
      loadJson(cfg.osmDataUrl).catch((err) => { console.error(err); return { features: [] }; }),
      loadJson(cfg.partnerDataUrl).catch((err) => { console.error(err); return { features: [] }; }),
      loadFeedbackOverlay()
    ]).then(([osm, partners]) => {
      state.osmFeatures = (Array.isArray(osm.features) ? osm.features : []).filter((f) => isWalkInFreeOsm(f.properties || {}));
      state.partnerFeatures = (Array.isArray(partners.features) ? partners.features : []).filter((f) => isPartnerWalkInFree(f.properties || {}));
      refresh();
      const o = state.city ? visibleOsm().length : state.osmFeatures.length;
      const p = state.city ? visiblePartners().length : state.partnerFeatures.length;
      setStatus("Loaded " + o + " OpenStreetMap points" + (p ? " and " + p + " partner listings." : ".") + " Free for anyone, no purchase needed.");
    }).catch((err) => {
      setStatus("Could not load map data. " + err.message, true);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
