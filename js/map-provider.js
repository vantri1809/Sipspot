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
      L.tileLayer(c.tilesUrl, {
        attribution: c.tilesAttribution,
        maxZoom: c.tilesMaxZoom || 19,
        subdomains: "abcd"
      }).addTo(map);

      const groups = Object.create(null);
      let userMarker = null;

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
          flags.push('<span class="pin-flag filtered" title="Filtered water">F</span>');
        }
        if (chilled) {
          flags.push('<span class="pin-flag chilled" title="Chilled">C</span>');
        }
        return flags.length ? '<span class="pin-flags">' + flags.join("") + "</span>" : "";
      }

      function markerIcon(kind, marker) {
        const deco = pinFlags(marker);
        const staleClass = marker && marker.stale ? " stale" : "";
        const staleNote = marker && marker.stale ? " — not updated in 3+ years" : "";
        if (kind === "partner") {
          return L.divIcon({
            className: "",
            html: '<div class="rm-marker partner" title="Cooler partner"><span>P</span>' + deco + "</div>",
            iconSize: [28, 28],
            iconAnchor: [14, 14],
            popupAnchor: [0, -14]
          });
        }
        if (kind === "cafe_refill") {
          return L.divIcon({
            className: "",
            html: '<div class="rm-marker cafe' + staleClass + '" title="Café or shop' + staleNote + '"><span>💧</span>' + deco + "</div>",
            iconSize: [28, 28],
            iconAnchor: [14, 28],
            popupAnchor: [0, -28]
          });
        }
        return L.divIcon({
          className: "",
          html: '<div class="rm-marker fountain' + staleClass + '" title="Public fountain' + staleNote + '"><span>💧</span>' + deco + "</div>",
          iconSize: [28, 28],
          iconAnchor: [14, 28],
          popupAnchor: [0, -28]
        });
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
            iconCreateFunction: clusterIcon(kind)
          });
          map.addLayer(layer);
          groups[id] = layer;
          return id;
        },
        addMarker: function (groupId, marker) {
          const layer = groups[groupId];
          if (!layer) return;
          L.marker([marker.lat, marker.lon], {
            icon: markerIcon(marker.kind, marker),
            title: marker.title || ""
          })
            .bindPopup(marker.popupHtml, { maxWidth: 280, autoPanPaddingTopLeft: [16, 72], autoPanPaddingBottomRight: [16, 16] })
            .addTo(layer);
        },
        clearGroup: function (groupId) {
          const layer = groups[groupId];
          if (layer) layer.clearLayers();
        },
        addUserMarker: function (lat, lon, popupHtml) {
          if (userMarker) map.removeLayer(userMarker);
          userMarker = L.circleMarker([lat, lon], {
            radius: 8,
            color: "#084f4a",
            fillColor: "#2EC4B6",
            fillOpacity: 0.9,
            weight: 2
          }).addTo(map);
          if (popupHtml) userMarker.bindPopup(popupHtml);
        },
        removeUserMarker: function () {
          if (userMarker) {
            map.removeLayer(userMarker);
            userMarker = null;
          }
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
