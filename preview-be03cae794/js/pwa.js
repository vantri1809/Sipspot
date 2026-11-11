/* SipSpot installable web app: register the service worker and show a
 * small, dismissible install hint. No tracking. */
(function () {
  var STORAGE_KEY = "sipspot-install-hint-dismissed";
  var deferredPrompt = null;

  function getBase() {
    var cfg = window.SIPSPOT_CONFIG;
    if (cfg && cfg.basePath) {
      var base = cfg.basePath;
      return base.charAt(base.length - 1) === "/" ? base : base + "/";
    }
    var scripts = document.getElementsByTagName("script");
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].getAttribute("src") || "";
      if (!/(?:^|\/)js\/pwa\.js(?:\?|$)/.test(src)) continue;
      return new URL(src, document.baseURI).pathname.replace(/\/js\/[^/]+$/, "/");
    }
    return "./";
  }

  function isStandalone() {
    return (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
      window.navigator.standalone === true;
  }

  function isIosSafari() {
    var ua = window.navigator.userAgent || "";
    var isIos = /iPad|iPhone|iPod/.test(ua) ||
      (window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1);
    var isSafari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|Chrome|Android/.test(ua);
    return isIos && isSafari;
  }

  function hintDismissed() {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === "1";
    } catch (err) {
      return false;
    }
  }

  function dismissHint() {
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch (err) {}
    var el = document.getElementById("pwa-install");
    if (el) el.setAttribute("hidden", "");
  }

  function ensureBanner() {
    var existing = document.getElementById("pwa-install");
    if (existing) return existing;
    var banner = document.createElement("div");
    banner.id = "pwa-install";
    banner.className = "pwa-install";
    banner.setAttribute("hidden", "");
    banner.setAttribute("role", "region");
    banner.setAttribute("aria-label", "Install SipSpot");
    banner.innerHTML =
      '<div class="pwa-install-copy">' +
        '<strong>Install SipSpot</strong>' +
        '<p class="pwa-install-text"></p>' +
      "</div>" +
      '<div class="pwa-install-actions">' +
        '<button type="button" class="btn btn-primary pwa-install-btn" hidden>Install app</button>' +
        '<button type="button" class="pwa-install-dismiss" aria-label="Dismiss">Not now</button>' +
      "</div>";
    document.body.appendChild(banner);
    banner.querySelector(".pwa-install-dismiss").addEventListener("click", dismissHint);
    banner.querySelector(".pwa-install-btn").addEventListener("click", function () {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () {
        deferredPrompt = null;
        dismissHint();
      });
    });
    return banner;
  }

  function showIosHint() {
    if (isStandalone() || hintDismissed() || !isIosSafari()) return;
    var banner = ensureBanner();
    banner.querySelector(".pwa-install-text").textContent =
      "Tap Share, then Add to Home Screen";
    banner.querySelector(".pwa-install-btn").hidden = true;
    banner.removeAttribute("hidden");
  }

  function showInstallButton() {
    if (isStandalone() || hintDismissed()) return;
    var banner = ensureBanner();
    banner.querySelector(".pwa-install-text").textContent =
      "Add the free water refill map to your home screen.";
    banner.querySelector(".pwa-install-btn").hidden = false;
    banner.removeAttribute("hidden");
  }

  if ("serviceWorker" in navigator) {
    var swUrl = getBase() + "sw.js";
    navigator.serviceWorker.register(swUrl, { scope: getBase() }).catch(function () {
      // Registration can fail on insecure origins other than localhost; ignore.
    });
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredPrompt = event;
    showInstallButton();
  });

  window.addEventListener("appinstalled", function () {
    deferredPrompt = null;
    dismissHint();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", showIosHint);
  } else {
    showIosHint();
  }
})();
