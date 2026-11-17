/* NULL · Istanbul's earthquake assembly areas: on the map, out of reach — #30DayMapChallenge 2026 · Day 18 */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const fmt = (v, d = 0) => v == null || Number.isNaN(v) ? "–" : Number(v).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = (v, d = 0) => v == null ? "–" : fmt(v * 100, d) + "%";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const dark = document.documentElement.dataset.theme === "dark";
  // walking distance classes: calm teal → sand → rust; NULL = beyond reach
  const BRK = [250, 500, 1000, 2000];
  const COL = dark ? ["#5fa8a0", "#9cc3a0", "#e2c27c", "#d98a4e", "#b3473a"] : ["#3f8f88", "#86b58c", "#d9b25e", "#cf7a3c", "#a63a2e"];
  const NOWAY = dark ? "#5a5550" : "#9a948a";
  const LBL = ["< 250 m", "250–500 m", "500 m – 1 km", "1–2 km", "> 2 km"];
  const WALK = 4.5 * 1000 / 60;                                       // metres per minute
  let map, S, M, P, D, popup, TI = null, TC = {}, layer = "b";

  const j = (u) => fetch(u, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(u + " " + r.status); return r.json(); });
  Promise.all([j("data/stats.json"), j("data/mahalle.geojson"), j("data/points.geojson"), j("data/districts.geojson")])
    .then(([s, m, p, d]) => { S = s; M = m; P = p; D = d; initPanel(); initMap(); })
    .catch((e) => { $("#loading").textContent = "Could not load the data: " + e.message; });

  const dcol = ["step", ["get", "d"], COL[0], BRK[0], COL[1], BRK[1], COL[2], BRK[2], COL[3], BRK[3], COL[4]];

  function hatch() {                                                    // diagonal stripes for "no data"
    const c = document.createElement("canvas"); c.width = c.height = 12;
    const g = c.getContext("2d"); g.strokeStyle = dark ? "rgba(230,225,215,.55)" : "rgba(60,55,50,.5)"; g.lineWidth = 1.6;
    g.beginPath(); g.moveTo(-3, 15); g.lineTo(15, -3); g.moveTo(-3, 3); g.lineTo(3, -3); g.moveTo(9, 15); g.lineTo(15, 9); g.stroke();
    return g.getImageData(0, 0, 12, 12);
  }

  function initMap() {
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol("pmtiles", protocol.tile);
    map = new maplibregl.Map({
      container: "map", hash: true, attributionControl: false, maxZoom: 18.5,
      center: [28.98, 41.04], zoom: 10.3,
      style: `https://basemaps.cartocdn.com/gl/${dark ? "dark-matter" : "positron"}-gl-style/style.json`
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: "Assembly areas © İBB Açık Veri · © OpenStreetMap contributors · WorldPop (CC BY 4.0)" }));
    popup = new maplibregl.Popup({ closeButton: true, maxWidth: "320px", offset: 8 });
    map.on("load", () => {
      const first = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
      map.addImage("hatch", hatch(), { pixelRatio: 2 });
      map.addSource("m", { type: "geojson", data: M, promoteId: "mid" });
      map.addLayer({ id: "mf", type: "fill", source: "m", paint: {
        "fill-color": ["case", ["==", ["get", "share_out"], null], NOWAY,
          ["interpolate", ["linear"], ["get", "share_out"], 0, COL[0], 0.1, COL[1], 0.3, COL[2], 0.6, COL[3], 0.9, COL[4]]],
        "fill-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.75, 12.5, 0.6, 13.5, 0.12] } }, first);
      map.addLayer({ id: "mh", type: "fill", source: "m", filter: ["==", ["get", "gap"], true], paint: { "fill-pattern": "hatch", "fill-opacity": ["interpolate", ["linear"], ["zoom"], 12.5, 1, 14, 0.4] } }, first);
      map.addLayer({ id: "ml", type: "line", source: "m", paint: { "line-color": dark ? "rgba(255,255,255,.18)" : "rgba(40,35,30,.22)", "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.3, 14, 1] } }, first);
      map.addLayer({ id: "mls", type: "line", source: "m", paint: { "line-color": dark ? "#fff" : "#1f1d1a", "line-width": ["case", ["boolean", ["feature-state", "sel"], false], 2.5, 0] } }, first);
      map.addSource("b", { type: "vector", url: "pmtiles://" + new URL(`data/buildings.pmtiles?v=${S.build || 1}`, location.href).href });
      map.addLayer({ id: "bf", type: "fill", source: "b", "source-layer": "b", minzoom: 12.5,
        paint: { "fill-color": ["case", ["<", ["get", "d"], 0], NOWAY, dcol], "fill-opacity": ["interpolate", ["linear"], ["zoom"], 12.5, 0, 13.5, 0.92] } }, first);
      map.addSource("route", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "rglow", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": dark ? "rgba(255,255,255,.35)" : "rgba(255,255,255,.9)", "line-width": 9 } });
      map.addLayer({ id: "rline", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": ["get", "c"], "line-width": 4 } });
      map.addSource("p", { type: "geojson", data: P, promoteId: "i" });
      map.addLayer({ id: "pc", type: "circle", source: "p", paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 1.4, 12, 3, 15, ["case", ["==", ["get", "a"], null], 6, ["max", 5, ["min", 16, ["*", 0.12, ["sqrt", ["get", "a"]]]]]]],
        "circle-color": ["case", ["==", ["get", "a"], null], "rgba(0,0,0,0)", dark ? "#f4efe6" : "#2b2925"],
        "circle-stroke-color": dark ? "#f4efe6" : "#2b2925", "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 9, 0.4, 14, 1.6],
        "circle-opacity": 0.92 } });
      map.addLayer({ id: "pend", type: "circle", source: "route", filter: ["==", ["get", "k"], "end"], paint: { "circle-radius": 8, "circle-color": "#fff", "circle-stroke-color": ["get", "c"], "circle-stroke-width": 3 } });
      map.addLayer({ id: "pstart", type: "circle", source: "route", filter: ["==", ["get", "k"], "start"], paint: { "circle-radius": 5, "circle-color": ["get", "c"], "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
      map.on("click", (e) => {
        const p = map.queryRenderedFeatures(e.point, { layers: ["pc"] });
        if (p.length) return pointPopup(p[0], e.lngLat);
        const b = map.getZoom() >= 13 && map.queryRenderedFeatures(e.point, { layers: ["bf"] });
        if (b && b.length) return route(b[0], e.lngLat);
        const m = map.queryRenderedFeatures(e.point, { layers: ["mf"] });
        if (m.length) selectMah(m[0].properties.mid, false);
      });
      for (const id of ["pc", "bf", "mf"]) {
        map.on("mouseenter", id, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; });
      }
      map.on("mousemove", "mf", (e) => {
        if (map.getZoom() >= 13) { $("#tip").hidden = true; return; }
        const p = e.features[0].properties, t = $("#tip");
        t.hidden = false; t.style.left = e.point.x + 400 + "px"; t.style.top = e.point.y + 16 + "px";
        t.innerHTML = p.gap ? `<b>${esc(p.mahalle)}</b><small>${esc(p.district || "")} · buildings missing in OSM: data NULL</small>`
          : `<b>${esc(p.mahalle)}</b><small>${esc(p.district || "")} · ${pct(p.share_out)} of ${fmt(p.pop)} residents beyond 500 m</small>`;
      });
      map.on("mouseleave", "mf", () => { $("#tip").hidden = true; });
      map.on("zoom", legend);
      $("#loading").classList.add("done");
      try { if (!localStorage.getItem("d18intro")) $("#intro").hidden = false; } catch (e) { $("#intro").hidden = false; }
      legend();
    });
    window._map = map;
  }

  // ---------------------------------------------------------------- route from a building (walking tree tiles)
  async function tile(id) {
    if (!TI) TI = await j("data/tree/index.json");
    let lo = 0, hi = TI.s.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (TI.s[mid] <= id) lo = mid; else hi = mid - 1; }
    const k = TI.k[lo];
    if (!TC[k]) TC[k] = j(`data/tree/${k}.json`);
    return TC[k];
  }
  async function route(f, ll) {
    const p = f.properties;
    const c = p.d < 0 ? NOWAY : COL[BRK.findIndex((b) => p.d < b) < 0 ? 4 : BRK.findIndex((b) => p.d < b)];
    if (p.d < 0 || p.n < 0) {
      popup.setLngLat(ll).setHTML(`<div class="pop"><b>No mapped way nearby</b><small>No walkable street within 250 m in OpenStreetMap: the walk is NULL here.</small></div>`).addTo(map);
      return;
    }
    const pts = [[ll.lng, ll.lat]];
    let id = p.n, aid = p.a, guard = 0;
    while (id >= 0 && guard++ < 5000) {
      const t = await tile(id); const k = id - t.s;
      pts.push([t.x[k] / 1e5, t.y[k] / 1e5]);
      const nx = t.p[k];
      if (nx < 0) { aid = -2 - nx; break; }
      id = nx;
    }
    const A = P.features.find((x) => x.properties.i === aid);
    if (A && !(A.properties.a != null)) pts.push(A.geometry.coordinates);
    map.getSource("route").setData({ type: "FeatureCollection", features: [
      { type: "Feature", properties: { c }, geometry: { type: "LineString", coordinates: pts } },
      { type: "Feature", properties: { k: "start", c }, geometry: { type: "Point", coordinates: pts[0] } },
      { type: "Feature", properties: { k: "end", c }, geometry: { type: "Point", coordinates: pts[pts.length - 1] } }] });
    const a = A ? A.properties : {};
    const min = Math.max(1, Math.round(p.d / WALK));
    const verdict = p.d > 500 ? `<div class="verdict null"><b>NULL</b> · more than 500 m: this building is out of the planned reach.</div>` : `<div class="verdict ok">Within 500 m.</div>`;
    popup.setLngLat(ll).setHTML(`<div class="pop"><b>${fmt(p.d)} m walk · about ${min} min</b>
      <small>to <b>${esc(a.n || "an assembly area")}</b>${a.m ? `, ${esc(a.m)}` : ""}</small>
      <table class="ptab"><tr><td>area size</td><td>${a.a != null ? fmt(a.a) + " m² (est.)" : "<b>NULL</b> · not in the data"}</td></tr>
      <tr><td>residents here (est.)</td><td>${fmt(p.p, p.p < 10 ? 1 : 0)}</td></tr></table>${verdict}
      <small class="note">Shortest walk along OpenStreetMap streets and paths.</small></div>`).addTo(map);
  }
  function pointPopup(f, ll) {
    const a = f.properties;
    popup.setLngLat(ll).setHTML(`<div class="pop"><b>${esc(a.n)}</b><small>${esc([a.m, a.dt].filter(Boolean).join(" · "))}</small>
      <table class="ptab"><tr><td>area size</td><td>${a.a != null ? fmt(a.a) + " m² (est. from OSM)" : "<b>NULL</b> · not in the data, no open space mapped"}</td></tr>
      ${a.k ? `<tr><td>mapped as</td><td>${esc(a.k)}</td></tr>` : ""}<tr><td>capacity</td><td><b>NULL</b> · not published</td></tr>
      ${a.w === false ? `<tr><td>access</td><td><b>NULL</b> · no walkable way within 150 m</td></tr>` : ""}</table></div>`).addTo(map);
  }

  // ---------------------------------------------------------------- panel
  let selM = null;
  function selectMah(mid, fly = true) {
    const f = M.features.find((x) => x.properties.mid === +mid); if (!f) return;
    if (selM != null) map.setFeatureState({ source: "m", id: selM }, { sel: false });
    selM = +mid; map.setFeatureState({ source: "m", id: selM }, { sel: true });
    const p = f.properties;
    if (fly) map.fitBounds(bbox(f.geometry), { padding: { top: 60, bottom: 60, left: 420, right: 60 }, maxZoom: 15.5, duration: 900 });
    const el = $("#detail"); el.hidden = false;
    el.innerHTML = `<button class="close" aria-label="Close">×</button><h3>${esc(p.mahalle)}</h3><p class="hint" style="margin:0">${esc(p.district || "")}</p>
      ${p.gap ? `<p class="verdict null"><b>Data NULL.</b> Most residents here live where OpenStreetMap has no buildings, so the walk cannot be measured house by house.</p>` : ""}
      <div class="kpis"><div class="kpi"><b>${pct(p.share_out)}</b><span>residents beyond 500 m</span></div>
      <div class="kpi"><b>${fmt(p.out)}</b><span>people beyond 500 m</span></div><div class="kpi"><b>${fmt(p.n)}</b><span>assembly areas</span></div></div>
      <p class="hint">${fmt(p.pop)} residents (WorldPop 2020). ${p.n ? `Area known for ${fmt(p.n - p.area_null)} of ${fmt(p.n)} assembly areas${p.m2pp != null && p.area_null < p.n ? `: about ${fmt(p.m2pp, 1)} m² per resident` : ""}.` : "<b>No assembly area at all inside this mahalle.</b>"}</p>`;
    el.querySelector(".close").onclick = () => { el.hidden = true; map.setFeatureState({ source: "m", id: selM }, { sel: false }); selM = null; };
  }
  function bbox(g) {
    let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
    const walk = (c) => typeof c[0] === "number" ? (x0 = Math.min(x0, c[0]), y0 = Math.min(y0, c[1]), x1 = Math.max(x1, c[0]), y1 = Math.max(y1, c[1])) : c.forEach(walk);
    walk(g.coordinates); return [[x0, y0], [x1, y1]];
  }
  function initPanel() {
    const so = S.share_over || {};
    $("#lede").innerHTML = `Istanbul lists <b>${fmt(S.points.total)}</b> earthquake assembly areas. Along real streets, <b>${pct(so["500"])}</b> of residents, about <b>${fmt(S.people_over_500 / 1e6, 1)} million people</b>, live more than a 500 m walk from the nearest one. <i>Tap a building to see its route.</i>`;
    const bands = [1 - (so["250"] ?? 0), (so["250"] ?? 0) - (so["500"] ?? 0), (so["500"] ?? 0) - (so["1000"] ?? 0), (so["1000"] ?? 0) - (so["2000"] ?? 0), so["2000"] ?? 0];
    $("#walkStack").innerHTML = bands.map((v, i) => `<i style="width:${v * 100}%;background:${COL[i]}" title="${LBL[i]}: ${pct(v, 1)}"></i>`).join("");
    $("#walkKey").innerHTML = bands.map((v, i) => `<span><i style="background:${COL[i]}"></i>${LBL[i]} <b>${pct(v)}</b></span>`).join("");
    const dr = (S.districts || []).filter((d) => d.pop > 20000).slice(0, 12), mx = Math.max(...dr.map((d) => d.share_out || 0), 0.01);
    $("#distRank").innerHTML = dr.map((d, i) => `<li data-d="${esc(d.district)}"><span class="n">${i + 1}</span><span>${esc(d.district)}<small>${fmt(d.out)} of ${fmt(d.pop)} residents</small></span>
      <span class="bar" style="width:${Math.max(4, 64 * (d.share_out || 0) / mx)}px;background:${COL[3]}"></span><span class="v">${pct(d.share_out)}</span></li>`).join("");
    $$("#distRank li").forEach((li) => li.onclick = () => { const f = D.features.find((x) => x.properties.district === li.dataset.d); if (f) map.fitBounds(bbox(f.geometry), { padding: { top: 40, bottom: 40, left: 420, right: 40 }, duration: 900 }); });
    const wm = (S.worst_mahalle || []).slice(0, 10), m2 = Math.max(...wm.map((d) => d.out), 1);
    $("#mahRank").innerHTML = wm.map((d, i) => `<li data-n="${esc(d.mahalle)}" data-dt="${esc(d.district || "")}"><span class="n">${i + 1}</span><span>${esc(d.mahalle)}<small>${esc(d.district || "")} · ${pct(d.share_out)} of ${fmt(d.pop)}</small></span>
      <span class="bar" style="width:${Math.max(4, 64 * d.out / m2)}px;background:${COL[4]}"></span><span class="v">${fmt(d.out / 1000, 1)}k</span></li>`).join("");
    $$("#mahRank li").forEach((li) => li.onclick = () => { const f = M.features.find((x) => x.properties.mahalle === li.dataset.n && (x.properties.district || "") === li.dataset.dt); if (f) selectMah(f.properties.mid); });
    const pt = S.points;
    const gaps = M.features.filter((f) => f.properties.gap).length, none = M.features.filter((f) => f.properties.n === 0 && f.properties.pop > 300).length;
    $("#nulls").innerHTML = `<ul class="nl">
      <li><b>${fmt(pt.total)} of ${fmt(pt.total)}</b> assembly areas have no area and no capacity in the official data.</li>
      <li><b>${fmt(pt.area_null)}</b> do not lie in any mapped park, square or yard, so even their size stays unknown (hollow dots).</li>
      <li><b>${fmt(pt.off_network)}</b> are more than 150 m from any walkable way in OpenStreetMap.</li>
      <li><b>${fmt(none)}</b> neighbourhoods with residents have no assembly area inside their borders.</li>
      <li><b>${fmt(gaps)}</b> neighbourhoods are hatched: most of their residents live where OSM has no buildings, so their walk is a data NULL, not a result.</li>
      <li><b>${fmt(S.buildings.people_in_cells_without_buildings)}</b> residents live in 100 m cells with no mapped home.</li></ul>`;
    $("#dq").innerHTML = `${fmt(S.buildings.total)} OSM buildings, ${fmt(S.buildings.residential)} of them residential-looking. ${fmt(pt.in_open_space)} of ${fmt(pt.total)} assembly points lie in a mapped open space.`;
    const go = () => {
      const q = $("#q").value.trim().toLocaleLowerCase("tr"); if (!q) return;
      const m = M.features.find((f) => (f.properties.mahalle || "").toLocaleLowerCase("tr").includes(q)) || null;
      if (m) { selectMah(m.properties.mid); $("#qMsg").textContent = ""; return; }
      const d = D.features.find((f) => (f.properties.district || "").toLocaleLowerCase("tr").includes(q));
      if (d) { map.fitBounds(bbox(d.geometry), { padding: { top: 40, bottom: 40, left: 420, right: 40 }, duration: 900 }); $("#qMsg").textContent = ""; return; }
      const p = P.features.find((f) => (f.properties.n || "").toLocaleLowerCase("tr").includes(q));
      if (p) { map.flyTo({ center: p.geometry.coordinates, zoom: 16.5, duration: 900 }); pointPopup(p, { lng: p.geometry.coordinates[0], lat: p.geometry.coordinates[1] }); $("#qMsg").textContent = ""; return; }
      $("#qMsg").textContent = "Nothing found. Try a mahalle, district or park name.";
    };
    $("#qGo").onclick = go; $("#q").onkeydown = (e) => { if (e.key === "Enter") go(); };
    $$("#layerSeg button").forEach((b) => b.onclick = () => {
      layer = b.dataset.l; $$("#layerSeg button").forEach((x) => x.classList.toggle("on", x === b));
      if (layer === "m") map.easeTo({ zoom: Math.min(map.getZoom(), 11.5), duration: 700 }); else map.easeTo({ zoom: Math.max(map.getZoom(), 14.5), duration: 700 });
    });
    $("#themeBtn").textContent = dark ? "☀ Light map" : "☾ Dark map";
    $("#themeBtn").onclick = () => { const u = new URL(location.href); u.searchParams.set("theme", dark ? "light" : "dark"); location.href = u.toString(); };
    $("#introGo").onclick = () => { $("#intro").hidden = true; try { localStorage.setItem("d18intro", "1"); } catch (e) { /* ignore */ } $("#q").focus(); };
  }
  function legend() {
    const z = map ? map.getZoom() : 10, L = $("#legend");
    const ramp = COL.map((c, i) => `<div class="lg-row"><i class="sq" style="background:${c}"></i>${LBL[i]}${i >= 2 ? " <small>NULL · beyond 500 m</small>" : ""}</div>`).join("");
    if (z >= 13) {
      L.innerHTML = `<div class="lg-title">Walk to the nearest assembly area</div><div class="lg-sub">every building, along OSM streets · tap one for its route</div>${ramp}
        <div class="lg-row"><i class="sq" style="background:${NOWAY}"></i>no mapped way within 250 m</div>
        <div class="lg-row"><i style="background:${dark ? "#f4efe6" : "#2b2925"}"></i>assembly area <small>size from OSM</small></div>
        <div class="lg-row"><i style="border:1.6px solid ${dark ? "#f4efe6" : "#2b2925"}"></i>assembly area, size NULL</div>`;
    } else {
      L.innerHTML = `<div class="lg-title">Residents beyond a 500 m walk</div><div class="lg-sub">share per neighbourhood (mahalle) · zoom in for buildings</div>
        <div class="lg-bar" style="background:linear-gradient(90deg,${COL.join(",")})"></div><div class="lg-ticks"><span>0%</span><span>10%</span><span>30%</span><span>60%</span><span>90%+</span></div>
        <div class="lg-row" style="margin-top:8px"><i class="sq hatchsw"></i>data NULL: buildings missing in OSM</div>`;
    }
  }
})();
