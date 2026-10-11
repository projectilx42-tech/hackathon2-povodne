// Result layers on the map: registry, layers panel (toggle / opacity), legend, popups, settlement selection.
import { maplibregl } from './map.js';
import { getFileJson, getOverlays } from './api.js';
import { el, esc } from './util.js';

const C = { water: '#3987e5', debris: '#b9822a', cut: '#e5484d', bldg: '#ec835a', ok: '#12b312', deg: '#fab219', road: '#8a8a82', sel: '#ffe066' };
const FILES = {
  flood: 'flood/flood_polygons.geojson', buildings: 'damage/buildings_damage.geojson', roads: 'damage/roads_damage.geojson',
  bridges: 'damage/bridges_damage.geojson', settlements: 'network/settlements_access.geojson', cuts: 'network/road_cuts.geojson', floodpath: 'floodpath/path.geojson',
};
const EMPTY = { type: 'FeatureCollection', features: [] };
const fcOf = (d, pred) => ({ type: 'FeatureCollection', features: (d?.features ?? []).filter(pred ?? (() => true)) });

// ---- marker icons (colour + shape, so they work for colour-blind users) ----
function icon(draw) {
  const S = 56, c = document.createElement('canvas');
  c.width = c.height = S;
  const x = c.getContext('2d');
  x.lineJoin = 'round'; x.lineCap = 'round';
  draw(x, S);
  return x.getImageData(0, 0, S, S);
}
const ICONS = {
  'st-ok': icon((x, S) => { x.beginPath(); x.arc(S / 2, S / 2, 17, 0, 7); x.fillStyle = C.ok; x.fill(); x.lineWidth = 5; x.strokeStyle = '#0b0f14'; x.stroke(); }),
  'st-deg': icon((x, S) => { x.beginPath(); x.moveTo(S / 2, 9); x.lineTo(S - 9, S - 12); x.lineTo(9, S - 12); x.closePath(); x.fillStyle = C.deg; x.fill(); x.lineWidth = 5; x.strokeStyle = '#0b0f14'; x.stroke(); }),
  'st-cut': icon((x, S) => {
    x.beginPath(); x.moveTo(S / 2, 6); x.lineTo(S - 6, S / 2); x.lineTo(S / 2, S - 6); x.lineTo(6, S / 2); x.closePath();
    x.fillStyle = C.cut; x.fill(); x.lineWidth = 5; x.strokeStyle = '#0b0f14'; x.stroke();
    x.beginPath(); x.moveTo(20, 20); x.lineTo(36, 36); x.moveTo(36, 20); x.lineTo(20, 36); x.lineWidth = 5; x.strokeStyle = '#fff'; x.stroke();
  }),
  'st-none': icon((x, S) => { x.beginPath(); x.arc(S / 2, S / 2, 14, 0, 7); x.fillStyle = '#6b7684'; x.fill(); x.lineWidth = 4; x.strokeStyle = '#0b0f14'; x.stroke(); }),
  'br-hit': icon((x, S) => {
    x.beginPath(); x.moveTo(12, 12); x.lineTo(S - 12, S - 12); x.moveTo(S - 12, 12); x.lineTo(12, S - 12);
    x.lineWidth = 13; x.strokeStyle = '#0b0f14'; x.stroke(); x.lineWidth = 7; x.strokeStyle = C.cut; x.stroke();
  }),
  'br-ok': icon((x, S) => { x.fillStyle = '#9aa7b5'; x.fillRect(19, 19, 18, 18); x.lineWidth = 4; x.strokeStyle = '#0b0f14'; x.strokeRect(19, 19, 18, 18); }),
};
const STATUS_ICON = ['match', ['get', 'status'], 'cut_off', 'st-cut', 'degraded', 'st-deg', 'connected', 'st-ok', 'st-none'];

// ---- layer definitions ----
// add(map, data, ov): adds map layers; returns nothing. ids: map layer ids owned by the entry.
const DEFS = [
  { id: 'imagery_pre', label: 'Imagery before (S2)', group: 'Imagery', base: 1, off: true,
    ok: (d, ov) => !!ov.s2_pre, why: 'No pre-event optical image in this run',
    legend: [],
    add(map, d, ov) { addImage(map, 'imagery_pre', ov.s2_pre); map.addLayer({ id: 'imagery_pre', type: 'raster', source: 'imagery_pre', layout: { visibility: 'none' }, paint: { 'raster-opacity': 1 } }); } },
  { id: 'imagery_post', label: 'Imagery after (S2)', group: 'Imagery', base: 1, off: true,
    ok: (d, ov) => !!ov.s2_post, why: 'No usable post-event optical image (clouds?)',
    legend: [],
    add(map, d, ov) { addImage(map, 'imagery_post', ov.s2_post); map.addLayer({ id: 'imagery_post', type: 'raster', source: 'imagery_post', layout: { visibility: 'none' }, paint: { 'raster-opacity': 1 } }); } },
  { id: 'layover', label: 'Layover / shadow mask', group: 'Imagery', base: 0.6, off: true,
    ok: (d, ov) => !!ov.layover_shadow, why: 'Not available in this run', legend: [{ t: 'fill', c: '#a78bfa', l: 'Radar layover / shadow (unusable)' }],
    add(map, d, ov) { addImage(map, 'layover', ov.layover_shadow); map.addLayer({ id: 'layover', type: 'raster', source: 'layover', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.6 } }); } },
  { id: 'flood_prob', label: 'Flood probability', group: 'Flood', base: 0.85, off: true, threshold: true,
    ok: (d, ov) => !!ov.flood_prob, why: 'Not available in this run', legend: [{ t: 'ramp', l: 'Flood probability (above threshold)' }],
    add(map, d, ov) { addImage(map, 'flood_prob', ov.flood_prob); map.addLayer({ id: 'flood_prob', type: 'raster', source: 'flood_prob', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.85, 'raster-fade-duration': 0 } }); } },
  { id: 'water', label: 'Flood water', group: 'Flood', base: 0.55,
    ok: d => (d.flood?.features ?? []).some(f => f.properties.class === 'water'), why: 'No new water detected', legend: [{ t: 'fill', c: C.water, l: 'Flood water (new)' }],
    add(map, d) { map.addSource('water', { type: 'geojson', data: fcOf(d.flood, f => f.properties.class === 'water') }); map.addLayer({ id: 'water', type: 'fill', source: 'water', paint: { 'fill-color': C.water, 'fill-opacity': 0.55, 'fill-outline-color': '#86b6ef' } }); } },
  { id: 'debris', label: 'Debris / mud', group: 'Flood', base: 0.6,
    ok: d => (d.flood?.features ?? []).some(f => f.properties.class === 'debris'), why: 'Not available yet (debris detection module)', legend: [{ t: 'fill', c: C.debris, l: 'Debris / mud' }],
    add(map, d) { map.addSource('debris', { type: 'geojson', data: fcOf(d.flood, f => f.properties.class === 'debris') }); map.addLayer({ id: 'debris', type: 'fill', source: 'debris', paint: { 'fill-color': C.debris, 'fill-opacity': 0.6, 'fill-outline-color': '#e0a64a' } }); } },
  { id: 'roads', label: 'Roads', group: 'Damage', base: 0.9,
    ok: d => !!d.roads, why: 'No road data', legend: [{ t: 'line', c: C.road, l: 'Road' }, { t: 'line', c: C.cut, l: 'Road hit by flood' }],
    add(map, d) {
      map.addSource('roads', { type: 'geojson', data: d.roads });
      map.addLayer({ id: 'roads', type: 'line', source: 'roads', layout: { 'line-cap': 'round' }, paint: { 'line-color': ['case', ['==', ['get', 'hit'], true], C.cut, C.road], 'line-width': ['case', ['==', ['get', 'hit'], true], 3, 1.6], 'line-opacity': 0.9 } });
    } },
  { id: 'cuts', label: 'Cut road sections', group: 'Damage', base: 1,
    ok: d => (d.cuts?.features ?? []).length > 0, why: 'No cut road sections', legend: [{ t: 'dash', c: C.cut, l: 'Cut road section' }],
    add(map, d) {
      map.addSource('cuts', { type: 'geojson', data: d.cuts });
      map.addLayer({ id: 'cuts', type: 'line', source: 'cuts', layout: { 'line-cap': 'butt' }, paint: { 'line-color': C.cut, 'line-width': 5, 'line-dasharray': [1.2, 1], 'line-opacity': 1 } });
      map.addLayer({ id: 'cuts-hl', type: 'line', source: 'cuts', filter: ['==', ['get', 'osm_id'], ''], layout: { 'line-cap': 'round' }, paint: { 'line-color': C.sel, 'line-width': 8, 'line-opacity': 0.9 } });
    }, extraIds: ['cuts-hl'] },
  { id: 'buildings', label: 'Buildings hit', group: 'Damage', base: 0.9,
    ok: d => !!d.buildings, why: 'No building data', legend: [{ t: 'fill', c: C.bldg, l: 'Building hit' }],
    add(map, d) { map.addSource('buildings', { type: 'geojson', data: fcOf(d.buildings, f => f.properties.hit) }); map.addLayer({ id: 'buildings', type: 'fill', source: 'buildings', minzoom: 11, paint: { 'fill-color': C.bldg, 'fill-opacity': 0.9, 'fill-outline-color': '#fff' } }); map.addLayer({ id: 'buildings-pt', type: 'circle', source: 'buildings', maxzoom: 11, paint: { 'circle-radius': 3, 'circle-color': C.bldg, 'circle-stroke-width': 1, 'circle-stroke-color': '#0b0f14' } }); }, extraIds: ['buildings-pt'] },
  { id: 'bridges', label: 'Bridges', group: 'Damage', base: 1,
    ok: d => (d.bridges?.features ?? []).length > 0, why: 'No bridge data', legend: [{ t: 'icon', i: 'br-hit', l: 'Bridge hit (suspect)' }, { t: 'icon', i: 'br-ok', l: 'Bridge not hit' }],
    add(map, d) { map.addSource('bridges', { type: 'geojson', data: d.bridges }); map.addLayer({ id: 'bridges', type: 'symbol', source: 'bridges', layout: { 'icon-image': ['case', ['==', ['get', 'hit'], true], 'br-hit', 'br-ok'], 'icon-size': 0.55, 'icon-allow-overlap': true } }); } },
  { id: 'settlements', label: 'Settlements', group: 'Access', base: 1,
    ok: d => (d.settlements?.features ?? []).length > 0, why: 'No settlement data',
    legend: [{ t: 'icon', i: 'st-ok', l: 'Connected' }, { t: 'icon', i: 'st-deg', l: 'Degraded (long detour)' }, { t: 'icon', i: 'st-cut', l: 'Cut off' }],
    add(map, d) {
      map.addSource('settlements', { type: 'geojson', data: d.settlements });
      map.addLayer({ id: 'settlements', type: 'symbol', source: 'settlements', layout: { 'icon-image': STATUS_ICON, 'icon-size': 0.62, 'icon-allow-overlap': true } });
    } },
  { id: 'floodpath', label: 'Flood path (bonus)', group: 'Access', base: 0.9, off: true,
    ok: d => !!d.floodpath, why: 'Not available yet', legend: [{ t: 'line', c: '#22d3ee', l: 'Flood path' }],
    add(map, d) { map.addSource('floodpath', { type: 'geojson', data: d.floodpath }); map.addLayer({ id: 'floodpath', type: 'line', source: 'floodpath', layout: { visibility: 'none' }, paint: { 'line-color': '#22d3ee', 'line-width': 4, 'line-opacity': 0.9 } }); } },
];

function addImage(map, id, ov) {
  const [w, s, e, n] = ov.bounds;
  map.addSource(id, { type: 'image', url: ov.url, coordinates: [[w, n], [e, n], [e, s], [w, s]] });
}

const OPACITY_PROP = { fill: 'fill-opacity', line: 'line-opacity', raster: 'raster-opacity', circle: 'circle-opacity', symbol: 'icon-opacity' };

export function createLayers(map, { panelEl, legendEl, onSettlement, onFeatureInfo }) {
  let current = null; // {runId, data, ov, state: {id: {on, opacity}}, ownedLayers, ownedSources}
  let popup = null;
  const handlers = [];
  for (const [name, img] of Object.entries(ICONS)) if (!map.hasImage(name)) map.addImage(name, img, { pixelRatio: 2 });

  const ids = def => [def.id, ...(def.extraIds ?? [])].filter(i => map.getLayer(i));
  function applyVisibility(def) {
    const on = current.state[def.id].on && !current.hidden;
    for (const i of ids(def)) map.setLayoutProperty(i, 'visibility', on ? 'visible' : 'none');
  }
  function applyOpacity(def) {
    for (const i of ids(def)) {
      const prop = OPACITY_PROP[map.getLayer(i).type];
      if (prop && !(def.id === 'buildings' && i === 'buildings-pt')) map.setPaintProperty(i, prop, current.state[def.id].opacity);
    }
  }

  function clear() {
    if (!current) return;
    popup?.remove();
    for (const [evt, layer, fn] of handlers.splice(0)) map.off(evt, layer, fn);
    for (const l of current.ownedLayers) if (map.getLayer(l)) map.removeLayer(l);
    for (const s of current.ownedSources) if (map.getSource(s)) map.removeSource(s);
    for (const s of ['sel']) { if (map.getLayer(`${s}-ring`)) map.removeLayer(`${s}-ring`); if (map.getSource(s)) map.removeSource(s); }
    current = null;
    panelEl.replaceChildren();
    legendEl.replaceChildren();
    legendEl.hidden = true;
  }

  async function load(runId) {
    clear();
    const [ovList, ...loaded] = await Promise.all([getOverlays(runId).catch(() => []), ...Object.entries(FILES).map(([k, p]) => getFileJson(runId, p).then(v => [k, v]))]);
    const data = Object.fromEntries(loaded);
    const ov = Object.fromEntries(ovList.map(o => [o.name, o]));
    current = { runId, data, ov, state: {}, ownedLayers: [], ownedSources: [], hidden: false, ready: {} };
    for (const def of DEFS) {
      const ok = def.ok(data, ov);
      current.ready[def.id] = ok;
      current.state[def.id] = { on: ok && !def.off, opacity: def.base };
      if (!ok) continue;
      const before = new Set(map.getStyle().layers.map(l => l.id));
      const beforeSrc = new Set(Object.keys(map.getStyle().sources));
      def.add(map, data, ov);
      for (const l of map.getStyle().layers) if (!before.has(l.id)) current.ownedLayers.push(l.id);
      for (const s of Object.keys(map.getStyle().sources)) if (!beforeSrc.has(s)) current.ownedSources.push(s);
      applyVisibility(def);
    }
    // selection ring for settlements
    map.addSource('sel', { type: 'geojson', data: EMPTY });
    map.addLayer({ id: 'sel-ring', type: 'circle', source: 'sel', paint: { 'circle-radius': 17, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': C.sel, 'circle-stroke-width': 3 } });
    wireInteractions();
    if (current.ready.flood_prob) applyThreshold(0.5);
    renderPanel();
    renderLegend();
    return { data, ov };
  }

  // ---- popups + clicks ----
  function wireInteractions() {
    const on = (evt, layer, fn) => { map.on(evt, layer, fn); handlers.push([evt, layer, fn]); };
    for (const layer of ['settlements', 'bridges', 'cuts', 'roads', 'buildings', 'buildings-pt']) {
      if (!map.getLayer(layer)) continue;
      on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer'; });
      on('mouseleave', layer, () => { map.getCanvas().style.cursor = ''; });
    }
    if (map.getLayer('settlements')) {
      on('click', 'settlements', e => { e.originalEvent.stopPropagation?.(); onSettlement?.(e.features[0].properties.osm_id); });
      on('mouseenter', 'settlements', e => {
        popup?.remove();
        const p = e.features[0].properties;
        popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14, className: 'dark-popup' }).setLngLat(e.features[0].geometry.coordinates).setText(p.name ?? 'Settlement').addTo(map);
      });
      on('mouseleave', 'settlements', () => popup?.remove());
    }
    for (const layer of ['bridges', 'cuts', 'roads', 'buildings', 'buildings-pt']) {
      if (map.getLayer(layer)) on('click', layer, e => {
        if (map.queryRenderedFeatures(e.point, { layers: ['settlements'].filter(l => map.getLayer(l)) }).length) return;
        popup?.remove();
        popup = new maplibregl.Popup({ className: 'dark-popup', offset: 8 }).setLngLat(e.lngLat).setDOMContent(onFeatureInfo(layer, e.features[0].properties)).addTo(map);
      });
    }
  }

  // ---- flood probability threshold (client-side) ----
  let probImg = null;
  async function applyThreshold(thr) {
    const o = current?.ov.flood_prob;
    if (!o || !map.getSource('flood_prob')) return;
    if (!probImg) {
      probImg = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = o.url; });
    }
    const c = document.createElement('canvas');
    c.width = probImg.naturalWidth; c.height = probImg.naturalHeight;
    const x = c.getContext('2d', { willReadFrequently: true });
    x.drawImage(probImg, 0, 0);
    const im = x.getImageData(0, 0, c.width, c.height), d = im.data;
    for (let i = 0; i < d.length; i += 4) {
      const p = d[i] / 255;
      if (p >= thr) { const k = (p - thr) / Math.max(1 - thr, 1e-6); d[i] = 255; d[i + 1] = Math.round(224 - 165 * k); d[i + 2] = Math.round(102 - 60 * k); d[i + 3] = 215; }
      else d[i + 3] = 0;
    }
    x.putImageData(im, 0, 0);
    const [w, s, e, n] = o.bounds;
    map.getSource('flood_prob').updateImage({ url: c.toDataURL(), coordinates: [[w, n], [e, n], [e, s], [w, s]] });
  }

  // ---- layers panel ----
  function renderPanel() {
    panelEl.replaceChildren();
    let group = null;
    for (const def of DEFS) {
      if (def.group !== group) { group = def.group; panelEl.append(el('div', { class: 'lp-group', text: group })); }
      const st = current.state[def.id];
      const ok = current.ready[def.id];
      const cb = el('input', { type: 'checkbox', id: `lp-${def.id}`, disabled: !ok });
      cb.checked = ok && st.on;
      cb.addEventListener('change', () => { st.on = cb.checked; applyVisibility(def); renderLegend(); });
      const lg = def.legend[0];
      let sw;
      if (lg?.t === 'icon') { const c = document.createElement('canvas'); c.width = c.height = 14; c.getContext('2d').drawImage(iconCanvas(lg.i), 0, 0, 14, 14); c.className = 'swatch-icon'; sw = c; }
      else if (lg?.c) sw = el('i', { class: `swatch${lg.t === 'line' || lg.t === 'dash' ? ' line' : ''}`, style: `--c:${lg.c}` });
      else sw = el('i', { class: 'swatch hollow' });
      const row = el('div', { class: `lp-row${ok ? '' : ' disabled'}`, title: ok ? '' : def.why },
        el('label', { for: `lp-${def.id}` }, cb, sw, el('span', { text: def.label })),
        ok ? el('input', { type: 'range', min: 0, max: 1, step: 0.05, value: st.opacity, class: 'lp-opacity', 'aria-label': `${def.label} opacity`, title: 'Opacity', oninput: e => { st.opacity = +e.target.value; applyOpacity(def); } })
           : el('span', { class: 'lp-why', text: def.why }));
      panelEl.append(row);
      if (def.threshold && ok) {
        let raf = 0;
        panelEl.append(el('div', { class: 'lp-sub' }, el('span', { text: 'Threshold' }),
          el('input', { type: 'range', min: 0.05, max: 0.95, step: 0.05, value: 0.5, 'aria-label': 'Flood probability threshold', oninput: e => { cancelAnimationFrame(raf); const v = +e.target.value; raf = requestAnimationFrame(() => applyThreshold(v)); } })));
      }
    }
  }

  function renderLegend() {
    legendEl.replaceChildren();
    if (!current) { legendEl.hidden = true; return; }
    const items = [];
    for (const def of DEFS) if (current.ready[def.id] && current.state[def.id].on) items.push(...def.legend);
    legendEl.hidden = items.length === 0;
    legendEl.append(el('div', { class: 'lg-title', text: 'Legend' }));
    for (const it of items) {
      let sw;
      if (it.t === 'icon') { const c = document.createElement('canvas'); c.width = c.height = 20; c.getContext('2d').drawImage(iconCanvas(it.i), 0, 0, 20, 20); sw = c; }
      else if (it.t === 'ramp') sw = el('span', { class: 'sw ramp' });
      else sw = el('span', { class: `sw ${it.t}`, style: `--c:${it.c}` });
      legendEl.append(el('div', { class: 'lg-item' }, sw, el('span', { text: it.l })));
    }
  }
  const iconCache = {};
  function iconCanvas(name) {
    if (!iconCache[name]) { const c = document.createElement('canvas'); c.width = c.height = 56; c.getContext('2d').putImageData(ICONS[name], 0, 0); iconCache[name] = c; }
    return iconCache[name];
  }

  return {
    load, clear,
    get data() { return current?.data; },
    get overlays() { return current?.ov; },
    isLoaded: () => !!current,
    /** Hide all vector layers while the before/after slider shows imagery. */
    setVectorsHidden(hidden) {
      if (!current) return;
      current.hidden = hidden;
      for (const def of DEFS) if (current.ready[def.id] && !def.id.startsWith('imagery')) applyVisibility(def);
    },
    setLayerOn(id, on) {
      const def = DEFS.find(d => d.id === id);
      if (!current || !current.ready[id]) return;
      current.state[id].on = on;
      applyVisibility(def);
      const cb = document.getElementById(`lp-${id}`); if (cb) cb.checked = on;
      renderLegend();
    },
    selectSettlement(osmId, { fly = true } = {}) {
      const f = current?.data.settlements?.features.find(x => x.properties.osm_id === osmId);
      if (!f) return null;
      map.getSource('sel').setData({ type: 'FeatureCollection', features: [f] });
      if (fly) map.flyTo({ center: f.geometry.coordinates, zoom: Math.max(map.getZoom(), 13), duration: 700 });
      return f;
    },
    clearSelection() { map.getSource('sel')?.setData(EMPTY); map.setFilter('cuts-hl', ['==', ['get', 'osm_id'], '']); },
    highlightCuts(osmIds) {
      if (!map.getLayer('cuts-hl')) return;
      map.setFilter('cuts-hl', ['in', ['get', 'osm_id'], ['literal', osmIds.length ? osmIds : ['']]]);
      this.setLayerOn('cuts', true);
      const feats = (current.data.cuts?.features ?? []).filter(f => osmIds.includes(f.properties.osm_id));
      const pts = feats.flatMap(f => f.geometry.coordinates);
      if (pts.length) {
        const b = new maplibregl.LngLatBounds(pts[0], pts[0]);
        pts.forEach(p => b.extend(p));
        map.fitBounds(b, { padding: 120, maxZoom: 14, duration: 700 });
      }
    },
  };
}
