/* Basemap adapter.
 *
 * The rest of the app (pins, filters, OSM layer, partner layer, popups,
 * clustering, geolocation) talks only to the object returned by
 * RefillMap.createMap(). Swap the basemap by setting
 * REFILLMAP_CONFIG.mapProvider to "leaflet-osm" (default) or "google".
 *
 * The Google provider is a hook for later. It is not wired up to a live
 * key in this build. Do not use Google Places or Google Geocoding data
 * on the Leaflet/OSM map, and do not mix those results into OSM or
 * partner files.
 */
(function (root) {
  const DEFAULT_PROVIDER = "leaflet-osm";

  function cfg() {
    return root.REFILLMAP_CONFIG || {};
  }

  function almostEqual(a, b) {
    return Math.abs(a - b) < 1e-6;
  }

  /* ---------- Leaflet + OSM-based tiles (default, free) ---------- */
  const leafletOsm = {
    id: "leaflet-osm",
    create: function (container, options) {
      if (typeof L === "undefined") {
        throw new Error("Leaflet failed to load");
      }
      const c = cfg();
      const map = L.map(container, { scrollWheelZoom: true, attributionControl: true });
      map.setView(options.center, options.zoom);
      // Back-reference for tests (not a public API).
      if (container) container._sipspotLeafletMap = map;
      map.on("popupopen", function (e) {
        protectPopupFromGhostClick(map, e.popup);
      });
      L.tileLayer(c.tilesUrl, {
        attribution: c.tilesAttribution,
        maxZoom: c.tilesMaxZoom || 19,
        subdomains: "abcd"
      }).addTo(map);

      const groups = Object.create(null);
      let userMarker = null;
      let userAccuracy = null;
      let locateButton = null;

      function clusterIcon(kind) {
        return function (cluster) {
          const count = cluster.getChildCount();
          const size = count < 10 ? "small" : count < 50 ? "medium" : "large";
          let extra = " marker-cluster-" + size;
          if (kind === "partner") extra = " marker-cluster-partner";
          else if (kind === "cafe_refill") extra = " marker-cluster-cafe";
          return L.divIcon({
            html: "<div><span>" + count + "</span></div>",
            className: "marker-cluster" + extra,
            iconSize: L.point(40, 40)
          });
        };
      }

      function pinFlags(marker) {
        const flags = [];
        const type = marker && marker.water_type;
        const chilled = marker && (marker.chilled === true || type === "chilled_filtered");
        if (type === "filtered" || type === "chilled_filtered") {
          flags.push('<span class="pin-flag filtered" aria-label="Filtered water">F</span>');
        }
        if (chilled) {
          flags.push('<span class="pin-flag chilled" aria-label="Chilled">C</span>');
        }
        return flags.length ? '<span class="pin-flags">' + flags.join("") + "</span>" : "";
      }

      function attrEscape(str) {
        return String(str)
          .replace(/&/g, "&amp;")
          .replace(/"/g, "&quot;")
          .replace(/</g, "&lt;");
      }

      function markerIcon(kind, marker) {
        const deco = pinFlags(marker);
        const staleClass = marker && marker.stale ? " stale" : "";
        const staleNote = marker && marker.stale ? " — not updated in 3+ years" : "";
        /* Use aria-label, never the HTML title attribute. On iOS Safari a
         * title is shown as a tooltip on tap, which looks like a tiny popup
         * of just the name and can interfere with opening the real popup. */
        if (kind === "partner") {
          return L.divIcon({
            className: "",
            html: '<div class="rm-marker partner" role="img" aria-label="Cooler partner"><span>P</span>' + deco + "</div>",
            iconSize: [28, 28],
            iconAnchor: [14, 14],
            popupAnchor: [0, -14]
          });
        }
        if (kind === "cafe_refill") {
          return L.divIcon({
            className: "",
            html: '<div class="rm-marker cafe' + staleClass + '" role="img" aria-label="' + attrEscape("Café or shop" + staleNote) + '"><span>💧</span>' + deco + "</div>",
            iconSize: [28, 28],
            iconAnchor: [14, 28],
            popupAnchor: [0, -28]
          });
        }
        return L.divIcon({
          className: "",
          html: '<div class="rm-marker fountain' + staleClass + '" role="img" aria-label="' + attrEscape("Public fountain" + staleNote) + '"><span>💧</span>' + deco + "</div>",
          iconSize: [28, 28],
          iconAnchor: [14, 28],
          popupAnchor: [0, -28]
        });
      }

      function popupOptions() {
        const size = map.getSize();
        const maxHeight = Math.max(160, Math.min(280, size.y - 120));
        return {
          maxWidth: 280,
          maxHeight: maxHeight,
          autoPan: true,
          /* Keep the popup clear of the sticky 64px header and the map edge. */
          autoPanPaddingTopLeft: [20, 88],
          autoPanPaddingBottomRight: [20, 24]
        };
      }

      /* Leaflet binds map "preclick" to close an open popup. On iOS, opening
       * a popup near the edge auto-pans the map, then a delayed/ghost click
       * lands on the map and immediately closes it. Hold off that binding
       * until the pan and the ghost click window have passed. */
      function protectPopupFromGhostClick(leafletMap, popup) {
        if (!popup || typeof popup.close !== "function") return;
        /* Leaflet 1.9 binds map preclick to popup.close via getEvents(). */
        leafletMap.off("preclick", popup.close, popup);
        let released = false;
        let releaseTimer = null;
        function release() {
          if (released) return;
          released = true;
          if (releaseTimer) clearTimeout(releaseTimer);
          leafletMap.off("moveend", scheduleRelease);
          if (popup._map === leafletMap) {
            leafletMap.on("preclick", popup.close, popup);
          }
        }
        function scheduleRelease() {
          if (released) return;
          if (releaseTimer) clearTimeout(releaseTimer);
          releaseTimer = setTimeout(release, 500);
        }
        scheduleRelease();
        leafletMap.on("moveend", scheduleRelease);
      }

      return {
        provider: "leaflet-osm",
        setView: function (lat, lon, zoom) {
          map.setView([lat, lon], zoom);
        },
        getZoom: function () {
          return map.getZoom();
        },
        addClusterGroup: function (id, groupOptions) {
          const kind = (groupOptions && groupOptions.kind) || id;
          const layer = L.markerClusterGroup({
            chunkedLoading: true,
            maxClusterRadius: kind === "partner" ? 40 : 50,
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true,
            disableClusteringAtZoom: c.clusterDisableZoom || 16,
            /* Default is true, and on mobile the plugin uses the exact
             * viewport with no padding. Opening a popup auto-pans so the
             * pin can sit just off the map, the plugin then removes that
             * marker, and the popup closes immediately. */
            removeOutsideVisibleBounds: false, // sipspot-popup-stay-open
            iconCreateFunction: clusterIcon(kind)
          });
          map.addLayer(layer);
          groups[id] = layer;
          return id;
        },
        addMarker: function (groupId, marker) {
          const layer = groups[groupId];
          if (!layer) return;
          const m = L.marker([marker.lat, marker.lon], {
            icon: markerIcon(marker.kind, marker),
            alt: marker.title || "Water refill point",
            keyboard: true
          });
          m._sipspotId = marker.id || (String(marker.lat) + "," + String(marker.lon));
          m.bindPopup(marker.popupHtml, popupOptions());
          m.addTo(layer);
          return m;
        },
        clearGroup: function (groupId) {
          const layer = groups[groupId];
          if (layer) layer.clearLayers();
        },
        getOpenPopupId: function () {
          const popup = map._popup;
          if (!popup || !map.hasLayer(popup)) return null;
          const src = popup._source;
          return (src && src._sipspotId) || null;
        },
        openPopupById: function (id) {
          if (!id) return false;
          let found = null;
          let foundLayer = null;
          Object.keys(groups).forEach(function (gid) {
            if (found) return;
            const layer = groups[gid];
            if (!layer || typeof layer.eachLayer !== "function") return;
            layer.eachLayer(function (m) {
              if (found) return;
              if (m && m._sipspotId === id) {
                found = m;
                foundLayer = layer;
              }
            });
          });
          if (!found) return false;
          function open() {
            if (found && found.openPopup) found.openPopup();
          }
          if (foundLayer && typeof foundLayer.zoomToShowLayer === "function") {
            foundLayer.zoomToShowLayer(found, open);
          } else {
            open();
          }
          return true;
        },
        addUserMarker: function (lat, lon, popupHtml, accuracy) {
          const latlng = L.latLng(lat, lon);
          const accRaw = Number(accuracy);
          const acc = Number.isFinite(accRaw) && accRaw > 0 ? accRaw : 30;
          if (userAccuracy) {
            userAccuracy.setLatLng(latlng);
            userAccuracy.setRadius(acc);
          } else {
            userAccuracy = L.circle(latlng, {
              radius: acc,
              color: "#1E88E5",
              weight: 1,
              opacity: 0.35,
              fillColor: "#1E88E5",
              fillOpacity: 0.15,
              interactive: false,
              className: "sipspot-accuracy",
              pane: "overlayPane"
            }).addTo(map);
          }
          if (userMarker) {
            userMarker.setLatLng(latlng);
          } else {
            userMarker = L.marker(latlng, {
              icon: L.divIcon({
                className: "sipspot-you-are-here",
                html: '<div class="sipspot-user-dot" role="img" aria-label="You are here"></div>',
                iconSize: [22, 22],
                iconAnchor: [11, 11]
              }),
              interactive: false,
              keyboard: false,
              zIndexOffset: 1000,
              alt: "You are here"
            }).addTo(map);
          }
          if (popupHtml && userMarker.bindPopup && !userMarker.getPopup()) {
            userMarker.bindPopup(popupHtml);
          }
        },
        removeUserMarker: function () {
          if (userAccuracy) {
            map.removeLayer(userAccuracy);
            userAccuracy = null;
          }
          if (userMarker) {
            map.removeLayer(userMarker);
            userMarker = null;
          }
        },
        addLocateControl: function (options) {
          const onClick = options && options.onClick;
          const LocateControl = L.Control.extend({
            options: { position: "bottomright" },
            onAdd: function () {
              const wrap = L.DomUtil.create("div", "sipspot-locate-control leaflet-control");
              const btn = L.DomUtil.create("button", "sipspot-locate-btn", wrap);
              btn.type = "button";
              btn.setAttribute("aria-label", "Use my location");
              btn.setAttribute("title", "Use my location");
              btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3A8.994 8.994 0 0 0 13 3.06V1h-2v2.06A8.994 8.994 0 0 0 3.06 11H1v2h2.06A8.994 8.994 0 0 0 11 20.94V23h2v-2.06A8.994 8.994 0 0 0 20.94 13H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/></svg>';
              L.DomEvent.disableClickPropagation(wrap);
              L.DomEvent.disableScrollPropagation(wrap);
              L.DomEvent.on(btn, "click", function (e) {
                L.DomEvent.stop(e);
                if (typeof onClick === "function") onClick();
              });
              this._button = btn;
              return wrap;
            }
          });
          const control = new LocateControl();
          control.addTo(map);
          locateButton = control._button;
          return control;
        },
        setLocateState: function (mode) {
          const btn = locateButton;
          if (!btn) return;
          const locating = mode === "locating";
          const active = mode === "active";
          btn.classList.toggle("is-locating", locating);
          btn.classList.toggle("is-active", active);
          btn.setAttribute("aria-busy", locating ? "true" : "false");
          btn.setAttribute("aria-label", locating ? "Finding your location" : "Use my location");
          btn.disabled = locating;
        },
        onDragStart: function (fn) {
          map.on("dragstart", fn);
        },
        openPopupAt: function (groupId, lat, lon, zoom) {
          const z = Math.max(map.getZoom(), zoom || 16);
          map.setView([lat, lon], z);
          const layer = groups[groupId];
          if (!layer) return;
          layer.eachLayer(function (m) {
            const ll = m.getLatLng && m.getLatLng();
            if (ll && almostEqual(ll.lat, lat) && almostEqual(ll.lng, lon)) {
              if (typeof layer.zoomToShowLayer === "function") {
                layer.zoomToShowLayer(m, function () { m.openPopup(); });
              } else {
                m.openPopup();
              }
            }
          });
        }
      };
    }
  };

  /* ---------- Google Maps JS API (optional, not the default) ---------- */
  const googleMaps = {
    id: "google",
    create: function (container, options) {
      const key = cfg().googleMapsApiKey;
      if (!key || typeof google === "undefined" || !google.maps) {
        console.warn(
          "RefillMap: mapProvider is 'google' but the Google Maps JavaScript API " +
          "is not available (API key missing or script not loaded). " +
          "Falling back to leaflet-osm. See the README."
        );
        return leafletOsm.create(container, options);
      }
      /* Intentionally not implemented in this build. When you add it:
       *  - load the Maps JavaScript API with the key from config
       *  - put pins, clusters and InfoWindows behind the same methods
       *    as the Leaflet adapter (setView, addClusterGroup, addMarker, …)
       *  - do not import Google Places or Geocoding results into
       *    data/points.geojson or data/partners.geojson, and do not use
       *    those Google services to feed the Leaflet/OSM basemap
       */
      throw new Error(
        "The Google Maps provider is reserved for a later swap. " +
        "Use mapProvider: \"leaflet-osm\" for this release."
      );
    }
  };

  const providers = {
    "leaflet-osm": leafletOsm,
    leaflet: leafletOsm,
    osm: leafletOsm,
    google: googleMaps,
    "google-maps": googleMaps
  };

  root.RefillMap = {
    providers: providers,
    createMap: function (container, options) {
      const name = (cfg().mapProvider || DEFAULT_PROVIDER).toLowerCase();
      const provider = providers[name] || providers[DEFAULT_PROVIDER];
      if (!providers[name]) {
        console.warn("RefillMap: unknown mapProvider '" + name + "', using leaflet-osm");
      }
      return provider.create(container, options || {});
    }
  };
})(window);
