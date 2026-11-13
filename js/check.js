/* SipSpot staff check-in. Opened from the QR code on a managed unit:
 *   https://sipspot.co.uk/check/#u=<point id>&k=<check key>
 * The fragment (after #) is never sent to any server, so the key only leaves
 * the phone inside the POST body to the SipSpot API. */
(function () {
  const cfg = window.SIPSPOT_CONFIG || {};
  const api = String(cfg.apiBase || "").trim().replace(/\/+$/, "");
  const $ = (id) => document.getElementById(id);
  const unitEl = $("check-unit");
  const metaEl = $("check-meta");
  const body = $("check-body");
  const result = $("check-result");
  const okBtn = $("check-ok");
  const probBtn = $("check-problem");
  const confirmBtn = $("check-problem-confirm");

  // A new QR scan in the same tab only changes the fragment: start again.
  window.addEventListener("hashchange", () => location.reload());

  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  const id = params.get("u") || "";
  const key = params.get("k") || "";

  function show(text, kind) {
    result.textContent = text;
    result.className = "check-result is-" + kind;
    result.hidden = false;
  }

  function when(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return "";
    return d.toLocaleString("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function describe(u) {
    unitEl.textContent = (u.label || "Refill unit") + (u.partner ? " · " + u.partner : "");
    const last = u.last_check ? "Last checked " + when(u.last_check) + "." : "Not checked yet.";
    let state = "";
    if (u.status === "hidden") state = " Off the map now" + (u.hidden_label ? ": " + u.hidden_label.toLowerCase() : "") + ".";
    else if (u.status === "overdue") state = " A check is overdue.";
    metaEl.textContent = last + state;
  }

  function post(path, payload) {
    return fetch(api + path, {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload)
    }).then((res) => res.json().catch(() => ({})).then((b) => ({ status: res.status, body: b })));
  }

  function fail(r) {
    if (r && r.status === 403) {
      unitEl.textContent = "This QR code isn’t valid any more.";
      metaEl.textContent = "Please contact SipSpot for a new sticker.";
      body.hidden = true;
      return;
    }
    show("That didn’t go through. Check your signal and try again.", "error");
    okBtn.disabled = probBtn.disabled = confirmBtn.disabled = false;
  }

  function send(outcome) {
    okBtn.disabled = probBtn.disabled = confirmBtn.disabled = true;
    post("/api/check", { id: id, key: key, outcome: outcome }).then((r) => {
      if (r.status !== 200 || !r.body || r.body.ok !== true) return fail(r);
      describe(r.body.unit);
      body.hidden = true;
      if (outcome === "ok") {
        show("Thank you. Check logged at " + when(r.body.unit.last_check) + ". The unit is showing on the map.", "ok");
      } else {
        show("The unit is off the map and the owner has been told. Keep it out of use until it has been cleaned or repaired, then scan again and tap “Checked, all fine”.", "problem");
      }
    }).catch(() => fail(null));
  }

  if (!api) {
    unitEl.textContent = "Checks aren’t switched on yet.";
    return;
  }
  if (!/^(osm:(node|way|relation):\d{1,12}|partner:[A-Za-z0-9][A-Za-z0-9._-]{0,99})$/.test(id) || !/^[0-9a-f]{32}$/.test(key)) {
    unitEl.textContent = "Scan the QR code on the unit to start a check.";
    return;
  }

  post("/api/check-info", { id: id, key: key }).then((r) => {
    if (r.status !== 200 || !r.body || r.body.ok !== true) return fail(r);
    describe(r.body.unit);
    body.hidden = false;
  }).catch(() => {
    unitEl.textContent = "Couldn’t reach SipSpot.";
    metaEl.textContent = "Check your signal and reload the page.";
  });

  okBtn.addEventListener("click", () => send("ok"));
  probBtn.addEventListener("click", () => {
    probBtn.hidden = true;
    confirmBtn.hidden = false;
    confirmBtn.focus();
  });
  confirmBtn.addEventListener("click", () => send("problem"));
})();
