/**
 * Smart Ration System: Tamil Nadu Live Monitoring Dashboard Controller.
 * Manages 4-level drill-down: State > District > Godown > Fair Price Shop
 * Integrates Leaflet GeoJSON, real-time purchase feed, simulator control, and language toggle.
 */

const LiveDashboard = (function () {
  let map = null;
  let geojsonLayer = null;
  let markersLayer = null;
  let linesLayer = null;
  let stateHealthData = {};
  let currentLevel = "state"; // 'state', 'district', 'godown', 'shop'
  let currentDistrictId = null;
  let currentGodownId = null;
  let currentShopId = null;
  let liveFeedInterval = null;
  let currentLang = "en"; // 'en' or 'ta'
  let lastSeenTxnId = null;

  // Bilingual Dictionary
  const I18N = {
    en: {
      stateTitle: "Statewide Live Monitoring",
      stateSubtitle: "Tamil Nadu Civil Supplies & Consumer Protection Department",
      backToState: "← Back to State Overview",
      backToDistrict: "← Back to District View",
      backToGodown: "← Back to Godown Granary",
      totalStock: "Total Buffer Stock",
      distributedMonth: "Distributed (Month)",
      activeGodowns: "Active Granaries",
      activeShops: "Active FPS Shops",
      criticalAlerts: "Critical Alerts",
      warningAlerts: "Warning Alerts",
      shortageRank: "District Shortage Priority Ranking",
      liveFeedTitle: "Live Purchase Feed",
      godownListTitle: "Central Buffer Granaries",
      shopRiskTitle: "Fair Price Shop Stock Risk Ranking",
      daysLeft: "Days of Supply Left",
      stockoutDate: "Est. Stockout Date",
      reorderQty: "Recommended Reorder",
      confidence: "Prediction Confidence",
      rice: "Rice",
      wheat: "Wheat",
      sugar: "Sugar",
      toorDal: "Toor Dal",
      palmOil: "Palmolein Oil",
    },
    ta: {
      stateTitle: "மாநில நேரலை கண்காணிப்பு தளம்",
      stateSubtitle: "தமிழ்நாடு உணவுப் பொருள் வழங்கல் மற்றும் நுகர்வோர் பாதுகாப்புத் துறை",
      backToState: "← மாநில மேலோட்டத்திற்குத் திரும்பு",
      backToDistrict: "← மாவட்டப் பார்வைக்குத் திரும்பு",
      backToGodown: "← சேமிப்புக் கிடங்கிற்குத் திரும்பு",
      totalStock: "மொத்த இருப்பு அளவு",
      distributedMonth: "மாத விநியோகம்",
      activeGodowns: "செயல்பாட்டு கிடங்குகள்",
      activeShops: "நியாயவிலைக் கடைகள்",
      criticalAlerts: "அவசர எச்சரிக்கைகள்",
      warningAlerts: "கவனிக்கத்தக்கவை",
      shortageRank: "மாவட்ட பற்றாக்குறை முன்னுரிமைப் பட்டியல்",
      liveFeedTitle: "நேரலை விற்பனைப் பதிவு",
      godownListTitle: "மைய சேமிப்புக் கிடங்குகள்",
      shopRiskTitle: "கடை இருப்பு அபாய முன்னுரிமை",
      daysLeft: "இருப்பு நீடிக்கும் நாட்கள்",
      stockoutDate: "இருப்பு தீரும் உத்தேச நாள்",
      reorderQty: "பரிந்துரைக்கப்படும் கொள்முதல்",
      confidence: "கணிப்பு நம்பகத்தன்மை",
      rice: "அரிசி",
      wheat: "கோதுமை",
      sugar: "சர்க்கரை",
      toorDal: "துவரம் பருப்பு",
      palmOil: "பாமாயில்",
    }
  };

  function t(key) {
    return (I18N[currentLang] && I18N[currentLang][key]) || I18N["en"][key] || key;
  }

  // -------------------------------------------------------------
  // INITIALIZATION
  // -------------------------------------------------------------
  function init() {
    initLeafletMap();
    loadStateOverview();
    startLiveFeed();
    bindControls();
  }

  function initLeafletMap() {
    const mapElement = document.getElementById("tnMap");
    if (!mapElement) return;

    // Center of Tamil Nadu
    map = L.map("tnMap", {
      center: [11.1271, 78.6569],
      zoom: 7,
      minZoom: 6,
      maxZoom: 16,
      zoomControl: true,
    });

    // Clean, modern tile basemap (CartoDB Positron)
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; TNPDS',
      subdomains: "abcd",
      maxZoom: 19,
    }).addTo(map);

    markersLayer = L.layerGroup().addTo(map);
    linesLayer = L.layerGroup().addTo(map);

    // Fetch GeoJSON boundaries
    fetch("/api/districts/geojson")
      .then((res) => res.json())
      .then((data) => {
        renderDistrictGeoJSON(data);
      })
      .catch((err) => console.error("Error loading GeoJSON boundaries:", err));
  }

  function renderDistrictGeoJSON(geojsonData) {
    if (geojsonLayer) {
      map.removeLayer(geojsonLayer);
    }

    geojsonLayer = L.geoJSON(geojsonData, {
      style: function (feature) {
        const dId = feature.properties.id;
        const healthInfo = stateHealthData[dId];
        const fillColor = healthInfo ? healthInfo.color : "#10b981";

        return {
          fillColor: fillColor,
          weight: 1.5,
          opacity: 1,
          color: "#ffffff",
          dashArray: "2",
          fillOpacity: 0.65,
        };
      },
      onEachFeature: function (feature, layer) {
        const p = feature.properties;

        layer.on({
          mouseover: function (e) {
            const l = e.target;
            l.setStyle({
              weight: 3,
              color: "#1e3a8a",
              dashArray: "",
              fillOpacity: 0.85,
            });
            l.bringToFront();

            const h = stateHealthData[p.id] || {};
            const stockMt = h.total_stock_mt || "N/A";
            const crit = h.critical_shops || 0;
            const healthBadge = crit > 0 ? `<span style="color:#ef4444; font-weight:bold;">Critical Shortage (${crit} shops)</span>` : `<span style="color:#10b981;">Normal</span>`;

            l.bindTooltip(
              `<div style="font-family:sans-serif; padding:4px 6px;">
                <div style="font-weight:800; font-size:14px; color:#1e3a8a;">${p.name}</div>
                <div style="font-size:11px; color:#64748b;">${p.zone || 'District'} &bull; ${p.code}</div>
                <div style="margin-top:4px; font-size:12px;"><strong>Stock:</strong> ${stockMt} MT</div>
                <div style="font-size:12px;"><strong>Health:</strong> ${healthBadge}</div>
                <div style="font-size:11px; color:#2563eb; margin-top:3px;">&bull; Click to view Granaries & Shops</div>
              </div>`,
              { sticky: true }
            ).openTooltip();
          },
          mouseout: function (e) {
            geojsonLayer.resetStyle(e.target);
          },
          click: function () {
            drillDownToDistrict(p.id);
          },
        });
      },
    }).addTo(map);
  }

  // -------------------------------------------------------------
  // LEVEL 1: STATE OVERVIEW
  // -------------------------------------------------------------
  function loadStateOverview() {
    currentLevel = "state";
    currentDistrictId = null;
    currentGodownId = null;
    currentShopId = null;

    updateBreadcrumbs([
      { name: "Tamil Nadu", action: "LiveDashboard.loadStateOverview()" }
    ]);
    document.getElementById("levelBadge").innerText = "Level 1: State View";

    if (map) {
      map.setView([11.1271, 78.6569], 7);
      if (markersLayer) markersLayer.clearLayers();
      if (linesLayer) linesLayer.clearLayers();
    }

    fetch("/api/summary/live")
      .then((res) => res.json())
      .then((data) => {
        stateHealthData = data.district_health_map || {};
        if (geojsonLayer) {
          geojsonLayer.eachLayer(function (layer) {
            geojsonLayer.resetStyle(layer);
          });
        }
        renderStateRightPane(data);
      })
      .catch((err) => console.error("Error loading state overview:", err));
  }

  function renderStateRightPane(data) {
    const pane = document.getElementById("dashboardRightPane");
    if (!pane) return;

    const k = data.kpis;
    pane.innerHTML = `
      <!-- STATE HEADER -->
      <div class="drilldown-header">
        <div>
          <h2 style="font-size:1.3rem; font-weight:800; color:#0f172a;">${t("stateTitle")}</h2>
          <p style="font-size:0.85rem; color:#64748b;">${t("stateSubtitle")}</p>
        </div>
        <div style="display:flex; gap:8px;">
          <select id="quickDistrictSelect" class="select-input" onchange="LiveDashboard.drillDownToDistrict(this.value)" style="padding:6px 12px; font-size:0.85rem;">
            <option value="">-- Jump to District (38) --</option>
            ${data.top_shortage_districts.map(d => `<option value="${d.id}">${d.name} (${d.zone})</option>`).join("")}
          </select>
        </div>
      </div>

      <!-- 4 KPI CARDS -->
      <div class="mini-kpi-grid">
        <div class="mini-kpi-card" style="border-top:3px solid #1e3a8a;">
          <div class="mini-kpi-label">${t("totalStock")}</div>
          <div class="mini-kpi-val">${k.total_stock_mt.toLocaleString()} <span style="font-size:0.9rem; font-weight:600;">MT</span></div>
          <div class="mini-kpi-sub">${k.godown_stock_mt} MT Godown &bull; ${k.shop_stock_mt} MT Shop</div>
        </div>

        <div class="mini-kpi-card" style="border-top:3px solid #10b981;">
          <div class="mini-kpi-label">${t("distributedMonth")}</div>
          <div class="mini-kpi-val">${k.distributed_month_mt.toLocaleString()} <span style="font-size:0.9rem; font-weight:600;">MT</span></div>
          <div class="mini-kpi-sub">${k.total_households.toLocaleString()} Active Cardholders</div>
        </div>

        <div class="mini-kpi-card" style="border-top:3px solid #3b82f6;">
          <div class="mini-kpi-label">Logistics Network</div>
          <div class="mini-kpi-val">${k.active_shops} <span style="font-size:0.9rem; font-weight:600;">Shops</span></div>
          <div class="mini-kpi-sub">${k.active_godowns} Central Granaries (38 Dists)</div>
        </div>

        <div class="mini-kpi-card" style="border-top:3px solid #ef4444;">
          <div class="mini-kpi-label">${t("criticalAlerts")}</div>
          <div class="mini-kpi-val" style="color:#b91c1c;">${k.critical_alerts}</div>
          <div class="mini-kpi-sub">${k.warning_alerts} Warning Restock Flags</div>
        </div>
      </div>

      <!-- TOP SHORTAGE DISTRICTS TABLE -->
      <div class="ticker-card">
        <div class="ticker-header">
          <span style="font-weight:700; font-size:0.95rem; color:#0f172a;">${t("shortageRank")}</span>
          <span class="badge badge-critical">Action Recommended</span>
        </div>
        <table class="ticker-table">
          <thead>
            <tr>
              <th>District</th>
              <th>Zone</th>
              <th>Total Stock (MT)</th>
              <th>Critical Shops</th>
              <th>Health</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${data.top_shortage_districts.map(d => `
              <tr style="cursor:pointer;" onclick="LiveDashboard.drillDownToDistrict(${d.id})">
                <td><strong>${d.name}</strong></td>
                <td><span style="font-size:0.75rem; color:#64748b;">${d.zone}</span></td>
                <td>${d.total_stock_mt} MT</td>
                <td><span style="color:${d.critical_shops > 0 ? '#b91c1c' : '#15803d'}; font-weight:700;">${d.critical_shops}</span></td>
                <td>
                  <span class="badge ${d.health === 'critical' ? 'badge-critical' : (d.health === 'warning' ? 'badge-low' : 'badge-normal')}">
                    ${d.health.toUpperCase()}
                  </span>
                </td>
                <td><button class="btn-back" style="padding:2px 8px; font-size:0.75rem;">View Map &rarr;</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>

      <!-- LIVE PURCHASE TICKER PANEL -->
      <div class="ticker-card">
        <div class="ticker-header">
          <div style="display:flex; align-items:center; gap:8px;">
            <div class="live-dot"></div>
            <span style="font-weight:700; font-size:0.95rem; color:#0f172a;">${t("liveFeedTitle")}</span>
          </div>
          <span style="font-size:0.75rem; color:#64748b;" id="liveTickerCount">${data.live_transactions.length} recent events</span>
        </div>
        <table class="ticker-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Shop</th>
              <th>Cardholder</th>
              <th>Commodity</th>
              <th>Weight</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody id="liveTickerBody">
            ${data.live_transactions.map(t => renderTickerRow(t)).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  // -------------------------------------------------------------
  // LEVEL 2: DISTRICT VIEW
  // -------------------------------------------------------------
  function drillDownToDistrict(districtId) {
    currentLevel = "district";
    currentDistrictId = parseInt(districtId);
    currentGodownId = null;
    currentShopId = null;

    document.getElementById("levelBadge").innerText = "Level 2: District View";

    fetch(`/api/summary/district/${districtId}`)
      .then((res) => res.json())
      .then((data) => {
        const d = data.district;

        updateBreadcrumbs([
          { name: "Tamil Nadu", action: "LiveDashboard.loadStateOverview()" },
          { name: d.name, action: `LiveDashboard.drillDownToDistrict(${d.id})` }
        ]);

        // Smooth zoom to district
        if (map) {
          map.setView(d.centroid, 10);
          renderDistrictMarkers(data);
        }

        renderDistrictRightPane(data);
      })
      .catch((err) => console.error("Error loading district drill-down:", err));
  }

  function renderDistrictMarkers(data) {
    if (markersLayer) markersLayer.clearLayers();
    if (linesLayer) linesLayer.clearLayers();

    // 1. Render Godowns (Square Icons)
    data.godowns.forEach((g) => {
      const icon = L.divIcon({
        className: "custom-godown-icon",
        html: `<div class="marker-godown" title="${g.name}">🏬</div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
      });

      const marker = L.marker([g.lat, g.lng], { icon: icon }).addTo(markersLayer);
      marker.bindTooltip(
        `<strong>🏬 ${g.name}</strong><br/>Capacity: ${g.capacity_mt} MT<br/>Stock: ${g.current_stock_mt} MT (${g.utilization_pct}%)<br/><em>Click to inspect Granary & Dispatches</em>`
      );
      marker.on("click", () => drillDownToGodown(g.id));
    });

    // 2. Render Shops (Circle Icons)
    data.shops.forEach((s) => {
      const icon = L.divIcon({
        className: "custom-shop-icon",
        html: `<div class="marker-shop ${s.status}" title="${s.name}">${s.stock_kg < 300 ? '!' : '🏪'}</div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      });

      const marker = L.marker([s.lat, s.lng], { icon: icon }).addTo(markersLayer);
      marker.bindTooltip(
        `<strong>🏪 ${s.name}</strong><br/>Cards: ${s.card_count}<br/>Stock: ${s.stock_kg:,.1f} kg<br/>Days Left: ~${s.days_left}d<br/><em>Click to inspect Fair Price Shop</em>`
      );
      marker.on("click", () => drillDownToShop(s.id));
    });
  }

  function renderDistrictRightPane(data) {
    const pane = document.getElementById("dashboardRightPane");
    if (!pane) return;

    const d = data.district;
    const k = data.kpis;

    pane.innerHTML = `
      <div class="drilldown-header">
        <div>
          <button class="btn-back" onclick="LiveDashboard.loadStateOverview()">${t("backToState")}</button>
          <h2 style="font-size:1.3rem; font-weight:800; color:#0f172a; margin-top:8px;">${d.name} District Dashboard</h2>
          <p style="font-size:0.85rem; color:#64748b;">Zone: ${d.zone} &bull; HQ: ${d.headquarters}</p>
        </div>
        <div>
          <span class="badge ${k.critical_shops_count > 0 ? 'badge-critical' : 'badge-normal'}">
            ${k.critical_shops_count > 0 ? `${k.critical_shops_count} CRITICAL SHOPS` : 'HEALTHY'}
          </span>
        </div>
      </div>

      <!-- DISTRICT KPIS -->
      <div class="mini-kpi-grid">
        <div class="mini-kpi-card" style="border-top:3px solid #1e3a8a;">
          <div class="mini-kpi-label">District Buffer Stock</div>
          <div class="mini-kpi-val">${k.total_stock_mt.toLocaleString()} <span style="font-size:0.9rem; font-weight:600;">MT</span></div>
          <div class="mini-kpi-sub">Across Granaries & Shops</div>
        </div>

        <div class="mini-kpi-card" style="border-top:3px solid #3b82f6;">
          <div class="mini-kpi-label">${t("activeGodowns")}</div>
          <div class="mini-kpi-val">${k.godowns_count} <span style="font-size:0.9rem; font-weight:600;">Granaries</span></div>
          <div class="mini-kpi-sub">Buffer Supply Depots</div>
        </div>

        <div class="mini-kpi-card" style="border-top:3px solid #10b981;">
          <div class="mini-kpi-label">${t("activeShops")}</div>
          <div class="mini-kpi-val">${k.shops_count} <span style="font-size:0.9rem; font-weight:600;">FPS</span></div>
          <div class="mini-kpi-sub">Retail Distribution</div>
        </div>

        <div class="mini-kpi-card" style="border-top:3px solid #ef4444;">
          <div class="mini-kpi-label">Risk Flagged Shops</div>
          <div class="mini-kpi-val" style="color:#b91c1c;">${k.critical_shops_count}</div>
          <div class="mini-kpi-sub">${k.warning_shops_count} Warning Restock</div>
        </div>
      </div>

      <!-- GODOWNS LIST -->
      <div class="ticker-card">
        <div class="ticker-header">
          <span style="font-weight:700; font-size:0.95rem; color:#0f172a;">${t("godownListTitle")} (Select to view dispatches)</span>
        </div>
        <table class="ticker-table">
          <thead>
            <tr>
              <th>Granary Godown</th>
              <th>Stock (MT)</th>
              <th>Capacity</th>
              <th>Utilization</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${data.godowns.map(g => `
              <tr style="cursor:pointer;" onclick="LiveDashboard.drillDownToGodown('${g.id}')">
                <td><strong>🏬 ${g.name}</strong><br/><span style="font-size:0.75rem; color:#64748b;">${g.code}</span></td>
                <td><strong>${g.current_stock_mt} MT</strong></td>
                <td>${g.capacity_mt} MT</td>
                <td>
                  <div style="display:flex; align-items:center; gap:6px;">
                    <div style="flex:1; height:6px; background:#f1f5f9; border-radius:3px; overflow:hidden;">
                      <div style="height:100%; width:${Math.min(100, g.utilization_pct)}%; background:${g.utilization_pct < 25 ? '#f59e0b' : '#3b82f6'};"></div>
                    </div>
                    <span style="font-size:0.75rem;">${g.utilization_pct}%</span>
                  </div>
                </td>
                <td><button class="btn-back" style="padding:2px 8px; font-size:0.75rem;">Inspect &rarr;</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>

      <!-- SHOP RISK RANKING TABLE -->
      <div class="ticker-card">
        <div class="ticker-header">
          <span style="font-weight:700; font-size:0.95rem; color:#0f172a;">${t("shopRiskTitle")}</span>
          <span class="badge badge-low">Prioritized by Depletion</span>
        </div>
        <table class="ticker-table">
          <thead>
            <tr>
              <th>Shop Code</th>
              <th>Shop Name</th>
              <th>Card Count</th>
              <th>Rice Stock</th>
              <th>Est. Days Left</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${data.shop_risk_ranking.map(s => `
              <tr style="cursor:pointer;" onclick="LiveDashboard.drillDownToShop('${s.id}')">
                <td><span style="font-weight:700; color:#1e3a8a;">${s.code}</span></td>
                <td>${s.name}</td>
                <td>${s.card_count.toLocaleString()}</td>
                <td><span style="font-weight:700; color:${s.stock_kg < 300 ? '#b91c1c' : '#1e293b'};">${s.stock_kg.toLocaleString()} kg</span></td>
                <td>
                  <span class="badge ${s.status === 'critical' ? 'badge-critical' : (s.status === 'warning' ? 'badge-low' : 'badge-normal')}">
                    ~${s.days_left} Days
                  </span>
                </td>
                <td><button class="btn-back" style="padding:2px 8px; font-size:0.75rem;">Open Shop &rarr;</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  // -------------------------------------------------------------
  // LEVEL 3: GODOWN VIEW
  // -------------------------------------------------------------
  function drillDownToGodown(godownId) {
    currentLevel = "godown";
    currentGodownId = godownId;
    currentShopId = null;

    document.getElementById("levelBadge").innerText = "Level 3: Godown Granary";

    fetch(`/api/summary/godown/${godownId}`)
      .then((res) => res.json())
      .then((data) => {
        const g = data.godown;

        updateBreadcrumbs([
          { name: "Tamil Nadu", action: "LiveDashboard.loadStateOverview()" },
          { name: g.district_name, action: `LiveDashboard.drillDownToDistrict(${g.district_id})` },
          { name: g.name, action: `LiveDashboard.drillDownToGodown('${g.id}')` }
        ]);

        if (map) {
          map.setView([g.lat, g.lng], 11);
          renderGodownSupplyRoutes(data);
        }

        renderGodownRightPane(data);
      })
      .catch((err) => console.error("Error loading godown drill-down:", err));
  }

  function renderGodownSupplyRoutes(data) {
    if (markersLayer) markersLayer.clearLayers();
    if (linesLayer) linesLayer.clearLayers();

    const g = data.godown;

    // Highlighted Godown Marker
    const godownIcon = L.divIcon({
      className: "custom-godown-highlight",
      html: `<div class="marker-godown" style="width:42px; height:42px; font-size:20px; background:#1e3a8a; border:3px solid #60a5fa;">🏬</div>`,
      iconSize: [42, 42],
      iconAnchor: [21, 21],
    });
    L.marker([g.lat, g.lng], { icon: godownIcon }).addTo(markersLayer)
      .bindTooltip(`<strong>Central Granary: ${g.name}</strong><br/>Capacity: ${g.capacity_mt} MT`).openTooltip();

    // Linked Shops & Polyline Supply Routes
    data.linked_shops.forEach((s) => {
      // Draw supply route dashed line
      L.polyline([[g.lat, g.lng], [s.lat, s.lng]], {
        color: s.status === "critical" ? "#ef4444" : "#3b82f6",
        weight: 2,
        opacity: 0.75,
        dashArray: "4, 6",
      }).addTo(linesLayer);

      const shopIcon = L.divIcon({
        className: "custom-shop-icon",
        html: `<div class="marker-shop ${s.status}">${s.status === 'critical' ? '!' : '🏪'}</div>`,
        iconSize: [26, 26],
        iconAnchor: [13, 13],
      });

      const marker = L.marker([s.lat, s.lng], { icon: shopIcon }).addTo(markersLayer);
      marker.bindTooltip(`<strong>${s.name}</strong><br/>Stock: ${s.stock_kg} kg<br/><em>Click to inspect Shop</em>`);
      marker.on("click", () => drillDownToShop(s.id));
    });
  }

  function renderGodownRightPane(data) {
    const pane = document.getElementById("dashboardRightPane");
    if (!pane) return;

    const g = data.godown;

    pane.innerHTML = `
      <div class="drilldown-header">
        <div>
          <button class="btn-back" onclick="LiveDashboard.drillDownToDistrict(${g.district_id})">${t("backToDistrict")}</button>
          <h2 style="font-size:1.3rem; font-weight:800; color:#0f172a; margin-top:8px;">🏬 ${g.name}</h2>
          <p style="font-size:0.85rem; color:#64748b;">${g.code} &bull; ${g.district_name} &bull; Lat: ${g.lat}, Lng: ${g.lng}</p>
        </div>
        <div>
          <span class="badge ${g.utilization_pct < 25 ? 'badge-low' : 'badge-normal'}">
            ${g.utilization_pct}% Capacity Filled
          </span>
        </div>
      </div>

      <!-- MULTI-COMMODITY STOCK GAUGES -->
      <div class="ticker-card">
        <div class="ticker-header">
          <span style="font-weight:700; font-size:0.95rem; color:#0f172a;">Granary Stock by Commodity</span>
          <span style="font-size:0.75rem; color:#64748b;">Total: ${g.current_stock_mt} MT of ${g.capacity_mt} MT</span>
        </div>
        <div class="commodity-gauges-grid">
          ${data.commodities_stock.map(c => `
            <div class="commodity-card">
              <div class="commodity-card-header">
                <span class="commodity-title">${c.name}</span>
                <span style="font-size:0.75rem; color:#64748b;">${c.unit}</span>
              </div>
              <div style="font-size:1.3rem; font-weight:800; color:#1e3a8a;">
                ${c.qty_kg.toLocaleString()} <span style="font-size:0.8rem; font-weight:500;">${c.unit}</span>
              </div>
              <div style="font-size:0.75rem; color:#64748b;">(${c.qty_mt} MT stored)</div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- LINKED SHOPS WITH SUPPLY LINES -->
      <div class="ticker-card">
        <div class="ticker-header">
          <span style="font-weight:700; font-size:0.95rem; color:#0f172a;">Linked Fair Price Shops (${data.linked_shops.length})</span>
          <span style="font-size:0.75rem; color:#3b82f6;">Supply lines rendered on map</span>
        </div>
        <table class="ticker-table">
          <thead>
            <tr>
              <th>Shop</th>
              <th>Beneficiaries</th>
              <th>Current Stock</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${data.linked_shops.map(s => `
              <tr style="cursor:pointer;" onclick="LiveDashboard.drillDownToShop('${s.id}')">
                <td><strong>🏪 ${s.name}</strong><br/><span style="font-size:0.75rem; color:#64748b;">${s.code}</span></td>
                <td>${s.card_count} Cards</td>
                <td><strong>${s.stock_kg.toLocaleString()} kg</strong></td>
                <td>
                  <span class="badge ${s.status === 'critical' ? 'badge-critical' : (s.status === 'warning' ? 'badge-low' : 'badge-normal')}">
                    ${s.status.toUpperCase()}
                  </span>
                </td>
                <td><button class="btn-back" style="padding:2px 8px; font-size:0.75rem;">View Shop &rarr;</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>

      <!-- RECENT OUTBOUND DISPATCHES -->
      <div class="ticker-card">
        <div class="ticker-header">
          <span style="font-weight:700; font-size:0.95rem; color:#0f172a;">Recent Replenishment Dispatches to Shops</span>
        </div>
        <table class="ticker-table">
          <thead>
            <tr>
              <th>Consignment</th>
              <th>Target Shop</th>
              <th>Quantity</th>
              <th>Dispatched</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${data.recent_dispatches.map(d => `
              <tr>
                <td><code>${d.id}</code></td>
                <td><strong>${d.to_shop_id}</strong></td>
                <td>${d.qty_kg.toLocaleString()} kg</td>
                <td>${d.dispatched_date}</td>
                <td>
                  <span class="badge ${d.status === 'DELIVERED' ? 'badge-normal' : (d.status === 'DELAYED' ? 'badge-delayed' : 'badge-low')}">
                    ${d.status}
                  </span>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  // -------------------------------------------------------------
  // LEVEL 4: FAIR PRICE SHOP VIEW
  // -------------------------------------------------------------
  function drillDownToShop(shopId) {
    currentLevel = "shop";
    currentShopId = shopId;

    document.getElementById("levelBadge").innerText = "Level 4: Fair Price Shop";

    fetch(`/api/summary/shop/${shopId}`)
      .then((res) => res.json())
      .then((data) => {
        const s = data.shop;
        currentDistrictId = s.district_id;
        currentGodownId = s.godown_id;

        updateBreadcrumbs([
          { name: "Tamil Nadu", action: "LiveDashboard.loadStateOverview()" },
          { name: s.district_name, action: `LiveDashboard.drillDownToDistrict(${s.district_id})` },
          { name: s.godown_name, action: `LiveDashboard.drillDownToGodown('${s.godown_id}')` },
          { name: s.name, action: `LiveDashboard.drillDownToShop('${s.id}')` }
        ]);

        if (map) {
          map.setView([s.lat, s.lng], 14);
          renderShopLocationMarker(s);
        }

        renderShopRightPane(data);
      })
      .catch((err) => console.error("Error loading shop drill-down:", err));
  }

  function renderShopLocationMarker(shop) {
    if (markersLayer) markersLayer.clearLayers();
    if (linesLayer) linesLayer.clearLayers();

    const icon = L.divIcon({
      className: "custom-shop-radar",
      html: `<div class="marker-shop critical" style="width:36px; height:36px; font-size:18px;">🏪</div>`,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });

    L.marker([shop.lat, shop.lng], { icon: icon }).addTo(markersLayer)
      .bindTooltip(`<strong>${shop.name}</strong><br/>FPS ID: ${shop.id}<br/>Supplied by: ${shop.godown_name}`).openTooltip();
  }

  function renderShopRightPane(data) {
    const pane = document.getElementById("dashboardRightPane");
    if (!pane) return;

    const s = data.shop;
    const pred = data.prediction;

    pane.innerHTML = `
      <div class="drilldown-header">
        <div>
          <button class="btn-back" onclick="LiveDashboard.drillDownToGodown('${s.godown_id}')">${t("backToGodown")}</button>
          <h2 style="font-size:1.3rem; font-weight:800; color:#0f172a; margin-top:8px;">🏪 ${s.name}</h2>
          <p style="font-size:0.85rem; color:#64748b;">${s.code} &bull; ${s.district_name} &bull; Buffer: ${s.godown_name}</p>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="source-pill">📡 Source: Simulator Feed</span>
          <span class="badge ${pred.status === 'critical' ? 'badge-critical' : 'badge-normal'}">
            ${pred.status.toUpperCase()}
          </span>
        </div>
      </div>

      <!-- PREDICTION / INTELLIGENCE BOX -->
      <div class="prediction-box">
        <div class="prediction-header">
          <div>
            <div style="font-size:0.8rem; font-weight:700; text-transform:uppercase; color:#0369a1;">Stock-Out Horizon Intelligence</div>
            <div style="font-size:1.1rem; font-weight:800; color:#0f172a;">Demand & Replenishment Forecast</div>
          </div>
          <div class="days-left-badge ${pred.status}">
            ~${pred.days_left} Days Left
          </div>
        </div>

        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:10px; margin-top:4px;">
          <div style="background:#ffffff; padding:10px 14px; border-radius:8px; border:1px solid #bae6fd;">
            <div style="font-size:0.75rem; color:#64748b;">${t("stockoutDate")}</div>
            <div style="font-size:1rem; font-weight:800; color:#0f172a;">${pred.stockout_date}</div>
          </div>
          <div style="background:#ffffff; padding:10px 14px; border-radius:8px; border:1px solid #bae6fd;">
            <div style="font-size:0.75rem; color:#64748b;">${t("reorderQty")}</div>
            <div style="font-size:1rem; font-weight:800; color:#1e3a8a;">${pred.recommended_reorder_kg.toLocaleString()} kg</div>
          </div>
          <div style="background:#ffffff; padding:10px 14px; border-radius:8px; border:1px solid #bae6fd;">
            <div style="font-size:0.75rem; color:#64748b;">${t("confidence")}</div>
            <div style="font-size:1rem; font-weight:800; color:#15803d;">${pred.confidence}% (Prophet)</div>
          </div>
        </div>
        <div style="font-size:0.75rem; color:#64748b;">Model: ${pred.method} &bull; Includes 10% safety buffer. Planning recommendation, not official allocation.</div>
      </div>

      <!-- MULTI-COMMODITY STOCK GAUGES & ENTITLEMENT -->
      <div class="ticker-card">
        <div class="ticker-header">
          <span style="font-weight:700; font-size:0.95rem; color:#0f172a;">Cardholder Entitlements vs Current Stock (${s.card_count} Cards)</span>
          <span style="font-size:0.75rem; color:#64748b;">5 Essential Commodities</span>
        </div>
        <div class="commodity-gauges-grid">
          ${data.commodities.map(c => `
            <div class="commodity-card">
              <div class="commodity-card-header">
                <span class="commodity-title">${c.name}</span>
                <span class="badge ${c.status === 'critical' ? 'badge-critical' : (c.status === 'warning' ? 'badge-low' : 'badge-normal')}">${c.status}</span>
              </div>
              <div style="font-size:1.2rem; font-weight:800; color:#0f172a;">
                ${c.current_stock.toLocaleString()} <span style="font-size:0.75rem; font-weight:500;">${c.unit}</span>
              </div>
              <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width:${c.quota_pct}%; background:${c.status === 'critical' ? '#ef4444' : (c.status === 'warning' ? '#f59e0b' : '#10b981')};"></div>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:0.72rem; color:#64748b;">
                <span>Quota: ${c.total_monthly_quota} ${c.unit}</span>
                <span>~${c.days_left}d left</span>
              </div>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- SHOP ALERTS & NOTICES -->
      ${data.active_alerts.length > 0 ? `
        <div class="ticker-card" style="border-left:4px solid #ef4444;">
          <div class="ticker-header">
            <span style="font-weight:700; font-size:0.95rem; color:#b91c1c;">Active Attention Flags & Alerts (${data.active_alerts.length})</span>
          </div>
          ${data.active_alerts.map(a => `
            <div style="background:#fef2f2; padding:10px 14px; border-radius:6px; margin-bottom:8px;">
              <div style="display:flex; justify-content:space-between;">
                <strong>${a.type}</strong>
                <span class="badge badge-critical">${a.severity}</span>
              </div>
              <div style="font-size:0.82rem; color:#7f1d1d; margin-top:4px;">${a.explanation}</div>
              <div style="font-size:0.75rem; color:#991b1b; margin-top:2px;">Assigned: ${a.assigned_role} &bull; ${a.timestamp}</div>
            </div>
          `).join("")}
        </div>
      ` : ''}

      <!-- SHOP RECENT TRANSACTIONS -->
      <div class="ticker-card">
        <div class="ticker-header">
          <span style="font-weight:700; font-size:0.95rem; color:#0f172a;">Today's Ingested Purchase Transactions (FPS)</span>
        </div>
        <table class="ticker-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Txn ID</th>
              <th>Card No</th>
              <th>Item</th>
              <th>Qty Dispensed</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            ${data.recent_transactions.length > 0 ? data.recent_transactions.map(t => `
              <tr>
                <td>${t.time}</td>
                <td><code>${t.id}</code></td>
                <td>${t.card_no}</td>
                <td>${t.item_name}</td>
                <td><strong>${t.qty_kg} kg</strong> (${t.bags} bags)</td>
                <td><span class="source-pill" style="padding:2px 8px; font-size:0.7rem;">${t.source}</span></td>
              </tr>
            `).join("") : '<tr><td colspan="6" style="text-align:center; color:#94a3b8; padding:14px;">No purchases recorded yet today for this shop.</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
  }

  // -------------------------------------------------------------
  // REAL-TIME FEED TICKER & LIVE POLLING
  // -------------------------------------------------------------
  function startLiveFeed() {
    if (liveFeedInterval) clearInterval(liveFeedInterval);

    liveFeedInterval = setInterval(() => {
      fetch("/api/transactions/live?limit=6")
        .then((res) => res.json())
        .then((data) => {
          if (data && data.transactions && data.transactions.length > 0) {
            updateLiveTickerUI(data.transactions);
          }
        })
        .catch(() => {});
    }, 2500);
  }

  function updateLiveTickerUI(transactions) {
    const tbody = document.getElementById("liveTickerBody");
    if (!tbody || currentLevel !== "state") return;

    // Check if new transaction arrived
    const newest = transactions[0];
    if (newest && newest.id !== lastSeenTxnId) {
      lastSeenTxnId = newest.id;
      // Prepend or re-render
      tbody.innerHTML = transactions.map(t => renderTickerRow(t)).join("");
    }
  }

  function renderTickerRow(t) {
    return `
      <tr class="ticker-row" style="cursor:pointer;" onclick="LiveDashboard.drillDownToShop('${t.shop_id}')">
        <td style="font-family:monospace; color:#64748b;">${t.time}</td>
        <td><strong>${t.shop_name}</strong><br/><span style="font-size:0.7rem; color:#94a3b8;">${t.shop_id}</span></td>
        <td><code>${t.card_no}</code></td>
        <td><strong>${t.item_name}</strong></td>
        <td><span style="font-weight:700; color:#1e3a8a;">${t.qty_kg} kg</span> <span style="font-size:0.75rem; color:#64748b;">(${t.bags} b)</span></td>
        <td><span class="source-pill" style="padding:2px 6px; font-size:0.7rem;">${t.source}</span></td>
      </tr>
    `;
  }

  function updateBreadcrumbs(crumbs) {
    const container = document.getElementById("dynamicBreadcrumb");
    if (!container) return;

    container.innerHTML = crumbs
      .map((c, idx) => {
        const isLast = idx === crumbs.length - 1;
        if (isLast) {
          return `<span style="color:#0f172a; font-weight:700;">${c.name}</span>`;
        }
        return `<a href="javascript:void(0)" onclick="${c.action}" style="color:#2563eb; text-decoration:none; font-weight:600;">${c.name}</a> <span class="breadcrumb-separator">&gt;</span>`;
      })
      .join(" ");
  }

  // -------------------------------------------------------------
  // CONTROLS: SIMULATOR & DATA SOURCE
  // -------------------------------------------------------------
  function bindControls() {
    const btnSimToggle = document.getElementById("btnToggleSimulator");
    if (btnSimToggle) {
      btnSimToggle.addEventListener("click", toggleSimulator);
    }

    const selectSource = document.getElementById("dataSourceSelect");
    if (selectSource) {
      selectSource.addEventListener("change", (e) => switchDataSource(e.target.value));
    }
  }

  function toggleSimulator() {
    const btn = document.getElementById("btnToggleSimulator");
    fetch("/api/simulator/status")
      .then((res) => res.json())
      .then((status) => {
        if (status.is_running) {
          fetch("/api/simulator/stop", { method: "POST" })
            .then(() => {
              if (btn) btn.innerHTML = "▶ Start Simulator";
              showNotification("Simulator Paused", "Background purchase generation paused.");
            });
        } else {
          fetch("/api/simulator/start?interval=2.0", { method: "POST" })
            .then(() => {
              if (btn) btn.innerHTML = "⏸ Pause Simulator";
              showNotification("Simulator Running", "Simulating live purchases across Tamil Nadu shops.");
            });
        }
      });
  }

  function switchDataSource(sourceName) {
    fetch(`/api/ingest/source/activate?source_name=${sourceName}`, { method: "POST" })
      .then((res) => res.json())
      .then((data) => {
        showNotification("Data Source Activated", data.message);
        const pill = document.getElementById("activeSourcePill");
        if (pill) pill.innerText = sourceName.toUpperCase();
      });
  }

  function toggleLanguage() {
    currentLang = currentLang === "en" ? "ta" : "en";
    const btn = document.getElementById("btnLangToggle");
    if (btn) btn.innerText = currentLang === "en" ? "தமிழ்" : "English";

    // Refresh current view
    if (currentLevel === "state") loadStateOverview();
    else if (currentLevel === "district") drillDownToDistrict(currentDistrictId);
    else if (currentLevel === "godown") drillDownToGodown(currentGodownId);
    else if (currentLevel === "shop") drillDownToShop(currentShopId);
  }

  function showNotification(title, message) {
    // Simple toast notification
    const toast = document.createElement("div");
    toast.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; background: #0f172a; color: #ffffff;
      padding: 12px 18px; border-radius: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.3);
      z-index: 9999; font-size: 0.85rem; border-left: 4px solid #10b981; animation: tickerSlideIn 0.3s;
    `;
    toast.innerHTML = `<strong>${title}</strong><div style="font-size:0.8rem; color:#94a3b8; margin-top:2px;">${message}</div>`;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  return {
    init: init,
    loadStateOverview: loadStateOverview,
    drillDownToDistrict: drillDownToDistrict,
    drillDownToGodown: drillDownToGodown,
    drillDownToShop: drillDownToShop,
    toggleSimulator: toggleSimulator,
    switchDataSource: switchDataSource,
    toggleLanguage: toggleLanguage,
  };
})();

// Auto-boot on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  LiveDashboard.init();
});
