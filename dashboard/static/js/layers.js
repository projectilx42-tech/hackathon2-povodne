// Result layers on the map: registry, layers panel (toggle / opacity), legend, popups, settlement selection, flood path.
import { maplibregl } from './map.js';
import { getFileJson, getOverlays } from './api.js';
import { el } from './util.js';
import { C, SUBTYPE, GRADE, IMPACT, ROAD_STATUS } from './labels.js';

const FILES = {
  flood: 'flood/flood_polygons.geojson', debrisPolys: 'flood/debris_polygons.geojson',
  buildings: 'damage/buildings_damage.geojson', roads: 'damage/roads_damage.geojson', bridges: 'damage/bridges_damage.geojson',
  areas: 'damage/settlement_areas.geojson', facilities: 'network/facilities_access.geojson', facilitiesDmg: 'damage/facilities_damage.geojson',
  settlements: 'network/settlements_access.geojson', cuts: 'network/road_cuts.geojson', landing: 'network/landing_zones.geojson',
  repair: 'network/repair_priority.json', damageSummary: 'damage/damage_summary.json', graphStats: 'network/graph_stats.json',
  floodpath: 'floodpath/path.geojson', floodpathSettlements: 'floodpath/settlements_on_path.geojson', floodpathAlong: 'floodpath/along_path.json',
};
const EMPTY = { type: 'FeatureCollection', features: [] };
const fcOf = (d, pred) => ({ type: 'FeatureCollection', features: (d?.features ?? []).filter(pred ?? (() => true)) });
const has = d => (d?.features ?? []).length > 0;

// ---- marker icons (colour + shape, so they work for colour-blind users) ----
function icon(draw) {
  const S = 56, c = document.createElement('canvas');
  c.width = c.height = S;
  const x = c.getContext('2d');
  x.lineJoin = 'round'; x.lineCap = 'round';
  draw(x, S);
  return x.getImageData(0, 0, S, S);
}
const OUTLINE = '#0b0f14';
const diamond = (x, S, fill, stroke) => { x.beginPath(); x.moveTo(S / 2, 6); x.lineTo(S - 6, S / 2); x.lineTo(S / 2, S - 6); x.lineTo(6, S / 2); x.closePath(); x.fillStyle = fill; x.fill(); x.lineWidth = 5; x.strokeStyle = stroke; x.stroke(); };
const square = (x, S, fill) => { x.beginPath(); x.roundRect(11, 11, S - 22, S - 22, 6); x.fillStyle = fill; x.fill(); x.lineWidth = 5; x.strokeStyle = OUTLINE; x.stroke(); };
const glyph = (x, text, color) => { x.fillStyle = color; x.font = 'bold 24px system-ui, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(text, 28, 30); };
const ICONS = {
  'st-ok': icon((x, S) => { x.beginPath(); x.arc(S / 2, S / 2, 17, 0, 7); x.fillStyle = C.ok; x.fill(); x.lineWidth = 5; x.strokeStyle = OUTLINE; x.stroke(); }),
  'st-deg': icon((x, S) => { x.beginPath(); x.moveTo(S / 2, 9); x.lineTo(S - 9, S - 12); x.lineTo(9, S - 12); x.closePath(); x.fillStyle = C.deg; x.fill(); x.lineWidth = 5; x.strokeStyle = OUTLINE; x.stroke(); }),
  'st-pos': icon((x, S) => { diamond(x, S, C.amber, OUTLINE); glyph(x, '?', OUTLINE); }),
  'st-cut': icon((x, S) => {
    diamond(x, S, C.cut, OUTLINE);
    x.beginPath(); x.moveTo(20, 20); x.lineTo(36, 36); x.moveTo(36, 20); x.lineTo(20, 36); x.lineWidth = 5; x.strokeStyle = '#fff'; x.stroke();
  }),
  'st-none': icon((x, S) => { x.beginPath(); x.arc(S / 2, S / 2, 14, 0, 7); x.fillStyle = '#6b7684'; x.fill(); x.lineWidth = 4; x.strokeStyle = OUTLINE; x.stroke(); }),
  'br-hit': icon((x, S) => {
    x.beginPath(); x.moveTo(12, 12); x.lineTo(S - 12, S - 12); x.moveTo(S - 12, 12); x.lineTo(12, S - 12);
    x.lineWidth = 13; x.strokeStyle = OUTLINE; x.stroke(); x.lineWidth = 7; x.strokeStyle = C.cut; x.stroke();
  }),
  'br-sus': icon((x, S) => { x.beginPath(); x.moveTo(S / 2, 8); x.lineTo(S - 8, S - 10); x.lineTo(8, S - 10); x.closePath(); x.fillStyle = 'rgba(0,0,0,0)'; x.lineWidth = 9; x.strokeStyle = OUTLINE; x.stroke(); x.lineWidth = 5; x.strokeStyle = C.amber; x.stroke(); }),
  'br-ok': icon((x, S) => { x.fillStyle = '#9aa7b5'; x.fillRect(19, 19, 18, 18); x.lineWidth = 4; x.strokeStyle = OUTLINE; x.strokeRect(19, 19, 18, 18); }),
  'fc-ok': icon((x, S) => square(x, S, C.ok)),
  'fc-pos': icon((x, S) => { square(x, S, C.amber); glyph(x, '?', OUTLINE); }),
  'fc-cut': icon((x, S) => { square(x, S, C.cut); x.beginPath(); x.moveTo(21, 21); x.lineTo(35, 35); x.moveTo(35, 21); x.lineTo(21, 35); x.lineWidth = 4; x.strokeStyle = '#fff'; x.stroke(); }),
  'fc-none': icon((x, S) => square(x, S, '#6b7684')),
};
const STATUS_ICON = ['match', ['get', 'status'], 'cut_off', 'st-cut', 'possibly_cut_off', 'st-pos', 'degraded', 'st-deg', 'connected', 'st-ok', 'st-none'];
const FACILITY_ICON = ['match', ['get', 'access'], 'cut_off', 'fc-cut', 'possibly_cut_off', 'fc-pos', 'no_road_pre_event', 'fc-none', 'fc-ok'];
const subtypeColor = ['match', ['get', 'subtype'], ...Object.entries(SUBTYPE).flatMap(([k, v]) => [k, v.color]), SUBTYPE.unknown.color];
const confOpacity = v => ['match', ['get', 'confidence'], 'high', 0.78 * v, 'medium', 0.58 * v, 'low', 0.38 * v, 0.55 * v];
const roadColor = ['case', ['==', ['get', 'status'], 'blocked'], C.cut, ['==', ['get', 'status'], 'possibly_blocked'], C.amber, ['==', ['get', 'hit'], true], C.cut, C.road];
const roadWidth = ['case', ['==', ['get', 'status'], 'blocked'], 3.4, ['==', ['get', 'status'], 'possibly_blocked'], 3, ['==', ['get', 'hit'], true], 3.2, 1.6];
const impactRing = ['match', ['get', 'impact_level'], 'critical', IMPACT.critical.color, 'severe', IMPACT.severe.color, 'moderate', IMPACT.moderate.color, 'rgba(0,0,0,0)'];

function addImage(map, id, ov) {
  const [w, s, e, n] = ov.bounds;
  map.addSource(id, { type: 'image', url: ov.url, coordinates: [[w, n], [e, n], [e, s], [w, s]] });
}
const imageLayer = (id, opacity) => ({ id, type: 'raster', source: id, layout: { visibility: 'none' }, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0 } });
const debrisData = d => (has(d.debrisPolys) ? d.debrisPolys : fcOf(d.flood, f => f.properties.class === 'debris'));
const facilityData = d => (has(d.facilities) ? d.facilities : d.facilitiesDmg);

// ---- layer definitions ----
// ok(data, overlays): is there data for this run;  add(map, data, overlays): add map layers;  legend: items or function(data)
const DEFS = [
  { id: 'imagery_pre', label: 'Imagery before (S2)', group: 'Imagery', base: 1, off: true, ok: (d, ov) => !!ov.s2_pre, why: 'No pre-event optical image in this run', legend: [],
    add(map, d, ov) { addImage(map, 'imagery_pre', ov.s2_pre); map.addLayer(imageLayer('imagery_pre', 1)); } },
  { id: 'imagery_post', label: 'Imagery after (S2)', group: 'Imagery', base: 1, off: true, ok: (d, ov) => !!ov.s2_post, why: 'No usable post-event optical image (clouds?)', legend: [],
    add(map, d, ov) { addImage(map, 'imagery_post', ov.s2_post); map.addLayer(imageLayer('imagery_post', 1)); } },
  { id: 'layover', label: 'Layover / shadow mask', group: 'Imagery', base: 0.6, off: true, ok: (d, ov) => !!ov.layover_shadow, why: 'Not available in this run',
    legend: [{ t: 'fill', c: '#a78bfa', l: 'Radar layover / shadow (unusable)' }],
    add(map, d, ov) { addImage(map, 'layover', ov.layover_shadow); map.addLayer(imageLayer('layover', 0.6)); } },

  { id: 'flood_prob', label: 'Flood probability', group: 'Flood', base: 0.85, off: true, threshold: true, ok: (d, ov) => !!ov.flood_prob, why: 'Not available in this run',
    legend: [{ t: 'ramp', l: 'Flood probability (above threshold)' }],
    add(map, d, ov) { addImage(map, 'flood_prob', ov.flood_prob); map.addLayer(imageLayer('flood_prob', 0.85)); } },
  { id: 'water', label: 'Flood water', group: 'Flood', base: 0.55, ok: d => (d.flood?.features ?? []).some(f => f.properties.class === 'water'), why: 'No new water detected',
    legend: [{ t: 'fill', c: C.water, l: 'Flood water (new)' }],
    add(map, d) {
      map.addSource('water', { type: 'geojson', data: fcOf(d.flood, f => f.properties.class === 'water') });
      map.addLayer({ id: 'water', type: 'fill', source: 'water', paint: { 'fill-color': C.water, 'fill-opacity': 0.55, 'fill-outline-color': '#86b6ef' } });
    } },
  { id: 'debris', label: 'Debris, mud & surface change', group: 'Flood', base: 1, ok: d => has(debrisData(d)), why: 'No surface change mapped in this run',
    legend: d => {
      const seen = new Set(debrisData(d).features.map(f => f.properties.subtype ?? 'unknown'));
      return [...Object.keys(SUBTYPE).filter(k => seen.has(k)).map(k => ({ t: 'fill', c: SUBTYPE[k].color, l: SUBTYPE[k].label })), { t: 'text', l: 'Fainter colour = lower confidence' }];
    },
    add(map, d) {
      map.addSource('debris', { type: 'geojson', data: debrisData(d) });
      map.addLayer({ id: 'debris', type: 'fill', source: 'debris', paint: { 'fill-color': subtypeColor, 'fill-opacity': confOpacity(1), 'fill-outline-color': 'rgba(255,255,255,.55)' } });
    },
    setOpacity(map, v) { map.setPaintProperty('debris', 'fill-opacity', confOpacity(v)); } },
  { id: 'confidence', label: 'Confidence map', group: 'Flood', base: 0.9, off: true, ok: (d, ov) => !!ov.confidence, why: 'Not available in this run',
    legend: [{ t: 'fill', c: '#2ea043', l: 'High confidence (affected area)' }, { t: 'fill', c: '#e3b341', l: 'Medium confidence' }, { t: 'fill', c: '#f85149', l: 'Low confidence' },
      { t: 'fill', c: '#8b949e', l: 'Not evaluated' }, { t: 'text', l: 'Faint red outside the flood = unsure that it is dry' }],
    add(map, d, ov) { addImage(map, 'confidence', ov.confidence); map.addLayer(imageLayer('confidence', 0.9)); } },
  { id: 'observability', label: 'What could be seen', group: 'Flood', base: 0.9, off: true, ok: (d, ov) => !!ov.debris_observability, why: 'Not available in this run',
    legend: [{ t: 'hatch', c: '#0b0f14', l: 'Cannot be seen (radar shadow, clouds)' }, { t: 'hatch', c: C.amber, l: 'Insensitive (dense forest or buildings)' }, { t: 'text', l: 'Unmarked = seen' }],
    add(map, d, ov) { addImage(map, 'observability', ov.debris_observability); map.addLayer(imageLayer('observability', 0.9)); } },

  { id: 'areas', label: 'Settlement areas', group: 'Damage', base: 1, off: true, ok: d => has(d.areas), why: 'Not available in this run',
    legend: [{ t: 'fill', c: IMPACT.critical.color, l: 'Settlement area, colour = impact' }],
    add(map, d) {
      map.addSource('areas', { type: 'geojson', data: d.areas });
      const col = ['match', ['get', 'impact_level'], 'critical', IMPACT.critical.color, 'severe', IMPACT.severe.color, 'moderate', IMPACT.moderate.color, 'low', IMPACT.low.color, 'rgba(0,0,0,0)'];
      map.addLayer({ id: 'areas', type: 'fill', source: 'areas', layout: { visibility: 'none' }, paint: { 'fill-color': col, 'fill-opacity': 0.2, 'fill-outline-color': col } });
      map.addLayer({ id: 'areas-line', type: 'line', source: 'areas', layout: { visibility: 'none' }, paint: { 'line-color': col, 'line-width': 1.5, 'line-opacity': 0.9 } });
    }, extraIds: ['areas-line'] },
  { id: 'roads', label: 'Roads', group: 'Damage', base: 0.9, ok: d => !!d.roads, why: 'No road data',
    legend: [{ t: 'line', c: C.road, l: 'Road' }, { t: 'line', c: C.amber, l: 'Possibly blocked' }, { t: 'line', c: C.cut, l: 'Blocked by the flood' }],
    add(map, d) {
      map.addSource('roads', { type: 'geojson', data: d.roads });
      map.addLayer({ id: 'roads', type: 'line', source: 'roads', layout: { 'line-cap': 'round' }, paint: { 'line-color': roadColor, 'line-width': roadWidth, 'line-opacity': 0.9 } });
      map.addLayer({ id: 'roads-gap', type: 'line', source: 'roads', filter: ['==', ['get', 'status'], 'possibly_blocked'], paint: { 'line-color': '#1a1a19', 'line-width': 3, 'line-dasharray': [1, 1.4] } });
    }, extraIds: ['roads-gap'] },
  { id: 'cuts', label: 'Cut road sections', group: 'Damage', base: 1, ok: d => has(d.cuts), why: 'No cut road sections',
    legend: [{ t: 'dash', c: C.cut, l: 'Cut road section (blocked)' }, { t: 'dash', c: C.amber, l: 'Possibly cut section' }],
    add(map, d) {
      map.addSource('cuts', { type: 'geojson', data: d.cuts });
      map.addLayer({ id: 'cuts', type: 'line', source: 'cuts', layout: { 'line-cap': 'butt' }, paint: { 'line-color': ['match', ['get', 'status'], 'possibly_blocked', C.amber, 'suspect', C.amber, C.cut], 'line-width': 5, 'line-dasharray': [1.2, 1], 'line-opacity': 1 } });
      map.addLayer({ id: 'cuts-hl', type: 'line', source: 'cuts', filter: ['==', ['get', 'osm_id'], ''], layout: { 'line-cap': 'round' }, paint: { 'line-color': C.sel, 'line-width': 8, 'line-opacity': 0.9 } });
    }, extraIds: ['cuts-hl'] },
  { id: 'buildings', label: 'Buildings hit', group: 'Damage', base: 0.9, ok: d => !!d.buildings, why: 'No building data',
    legend: [{ t: 'fill', c: GRADE.likely_destroyed.color, l: 'Building likely destroyed' }, { t: 'fill', c: GRADE.affected.color, l: 'Building affected' }, { t: 'fill', c: GRADE.possibly_affected.color, l: 'Building possibly affected' }],
    add(map, d) {
      const col = ['match', ['get', 'grade'], 'likely_destroyed', GRADE.likely_destroyed.color, 'possibly_affected', GRADE.possibly_affected.color, GRADE.affected.color];
      map.addSource('buildings', { type: 'geojson', data: fcOf(d.buildings, f => f.properties.hit && f.properties.grade !== 'none') });
      map.addLayer({ id: 'buildings', type: 'fill', source: 'buildings', minzoom: 11, paint: { 'fill-color': col, 'fill-opacity': 0.9, 'fill-outline-color': '#fff' } });
      map.addLayer({ id: 'buildings-pt', type: 'circle', source: 'buildings', maxzoom: 11, paint: { 'circle-radius': 3, 'circle-color': col, 'circle-stroke-width': 1, 'circle-stroke-color': OUTLINE } });
    }, extraIds: ['buildings-pt'] },
  { id: 'bridges', label: 'Bridges', group: 'Damage', base: 1, ok: d => has(d.bridges), why: 'No bridge data',
    legend: [{ t: 'icon', i: 'br-hit', l: 'Bridge blocked' }, { t: 'icon', i: 'br-sus', l: 'Bridge suspect (not confirmed)' }, { t: 'icon', i: 'br-ok', l: 'Bridge passable' }],
    add(map, d) {
      map.addSource('bridges', { type: 'geojson', data: d.bridges });
      map.addLayer({ id: 'bridges', type: 'symbol', source: 'bridges', layout: { 'icon-image': ['match', ['get', 'status'], 'blocked', 'br-hit', 'suspect', 'br-sus', 'passable', 'br-ok', ['case', ['==', ['get', 'hit'], true], 'br-hit', 'br-ok']], 'icon-size': 0.55, 'icon-allow-overlap': true } });
    } },
  { id: 'facilities', label: 'Key places', group: 'Damage', base: 1, ok: d => has(facilityData(d)), why: 'No key places in the map data',
    legend: [{ t: 'icon', i: 'fc-ok', l: 'Key place reachable' }, { t: 'icon', i: 'fc-pos', l: 'Key place possibly cut off' }, { t: 'icon', i: 'fc-cut', l: 'Key place cut off' }, { t: 'ring', c: C.cut, l: 'Red ring = hit by the flood' }],
    add(map, d) {
      map.addSource('facilities', { type: 'geojson', data: facilityData(d) });
      map.addLayer({ id: 'facilities-ring', type: 'circle', source: 'facilities', filter: ['==', ['get', 'hit'], true], paint: { 'circle-radius': 13, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': C.cut, 'circle-stroke-width': 2.5 } });
      map.addLayer({ id: 'facilities', type: 'symbol', source: 'facilities', layout: { 'icon-image': FACILITY_ICON, 'icon-size': 0.5, 'icon-allow-overlap': true } });
    }, extraIds: ['facilities-ring'] },

  { id: 'settlements', label: 'Settlements', group: 'Access', base: 1, ok: d => has(d.settlements), why: 'No settlement data',
    legend: [{ t: 'icon', i: 'st-ok', l: 'Connected' }, { t: 'icon', i: 'st-deg', l: 'Degraded (long detour)' }, { t: 'icon', i: 'st-pos', l: 'Possibly cut off' }, { t: 'icon', i: 'st-cut', l: 'Cut off' },
      { t: 'ring', c: IMPACT.severe.color, l: 'Coloured ring = impact (red severe, amber moderate)' }],
    add(map, d) {
      map.addSource('settlements', { type: 'geojson', data: d.settlements });
      map.addLayer({ id: 'settlements-ring', type: 'circle', source: 'settlements', paint: { 'circle-radius': 15, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': impactRing, 'circle-stroke-width': 2.5 } });
      map.addLayer({ id: 'settlements', type: 'symbol', source: 'settlements', layout: { 'icon-image': STATUS_ICON, 'icon-size': 0.62, 'icon-allow-overlap': true } });
    }, extraIds: ['settlements-ring'] },
  { id: 'landing', label: 'Helicopter landing candidates', tag: 'unverified', group: 'Access', base: 1, off: true, ok: d => has(d.landing), why: 'Not available in this run',
    legend: [{ t: 'fill', c: '#2dd4bf', l: 'Landing candidate, gentle slope (UNVERIFIED)' }, { t: 'fill', c: '#99f6e4', l: 'Landing candidate, steeper (UNVERIFIED)' }, { t: 'icon', i: 'lz-h', l: 'Mapped helipad (UNVERIFIED)' }],
    add(map, d) {
      map.addSource('landing', { type: 'geojson', data: d.landing });
      const col = ['match', ['get', 'class'], 'suitable', '#2dd4bf', '#99f6e4'];
      map.addLayer({ id: 'landing', type: 'fill', source: 'landing', filter: ['==', ['geometry-type'], 'Polygon'], layout: { visibility: 'none' }, paint: { 'fill-color': col, 'fill-opacity': 0.5 } });
      map.addLayer({ id: 'landing-line', type: 'line', source: 'landing', filter: ['==', ['geometry-type'], 'Polygon'], layout: { visibility: 'none' }, paint: { 'line-color': '#0f766e', 'line-width': 2, 'line-dasharray': [2, 1] } });
      map.addLayer({ id: 'landing-pt', type: 'circle', source: 'landing', filter: ['==', ['geometry-type'], 'Point'], layout: { visibility: 'none' }, paint: { 'circle-radius': 7, 'circle-color': '#8b5cf6', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } });
    }, extraIds: ['landing-line', 'landing-pt'] },
  { id: 'floodpath', label: 'Flood path from a point', group: 'Access', base: 0.9, ok: d => has(d.floodpath), why: 'Click "Flood path" on the map, then a point',
    legend: [{ t: 'line', c: '#22d3ee', l: 'Flood path (downstream)' }, { t: 'fill', c: '#22d3ee', l: 'Corridor near the river' }],
    add(map, d) { addFloodpathLayers(map, d.floodpath, d.floodpathSettlements); }, extraIds: ['floodpath-corridor', 'floodpath-pts', 'floodpath-start'] },
];
ICONS['lz-h'] = icon((x, S) => { x.beginPath(); x.arc(S / 2, S / 2, 17, 0, 7); x.fillStyle = '#8b5cf6'; x.fill(); x.lineWidth = 4; x.strokeStyle = '#fff'; x.stroke(); glyph(x, 'H', '#fff'); });

function addFloodpathLayers(map, path, pts) {
  const data = path ?? EMPTY;
  const line = fcOf(data, f => f.properties.kind === 'path');
  const corridor = fcOf(data, f => f.properties.kind === 'corridor');
  const start = { type: 'FeatureCollection', features: line.features.map(f => ({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: f.geometry.coordinates[0] } })) };
  map.addSource('floodpath-corridor', { type: 'geojson', data: corridor });
  map.addSource('floodpath', { type: 'geojson', data: line });
  map.addSource('floodpath-pts', { type: 'geojson', data: pts ?? EMPTY });
  map.addSource('floodpath-start', { type: 'geojson', data: start });
  map.addLayer({ id: 'floodpath-corridor', type: 'fill', source: 'floodpath-corridor', paint: { 'fill-color': '#22d3ee', 'fill-opacity': 0.14 } });
  map.addLayer({ id: 'floodpath', type: 'line', source: 'floodpath', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#22d3ee', 'line-width': 4, 'line-opacity': 0.95 } });
  map.addLayer({ id: 'floodpath-pts', type: 'circle', source: 'floodpath-pts', paint: { 'circle-radius': 8, 'circle-color': 'rgba(34,211,238,.25)', 'circle-stroke-color': '#22d3ee', 'circle-stroke-width': 2.5 } });
  map.addLayer({ id: 'floodpath-start', type: 'circle', source: 'floodpath-start', paint: { 'circle-radius': 6, 'circle-color': '#fff', 'circle-stroke-color': '#0b0f14', 'circle-stroke-width': 2 } });
}

const OPACITY_PROP = { fill: 'fill-opacity', line: 'line-opacity', raster: 'raster-opacity', circle: 'circle-opacity', symbol: 'icon-opacity' };
const POPUP_LAYERS = ['bridges', 'cuts', 'roads', 'buildings', 'buildings-pt', 'debris', 'facilities', 'landing', 'landing-pt', 'areas'];

export function createLayers(map, { panelEl, legendEl, onSettlement, onFeatureInfo }) {
  let current = null; // {runId, data, ov, state: {id: {on, opacity}}, ready, ownedLayers, ownedSources, hidden}
  let popup = null;
  const handlers = [];
  for (const [name, img] of Object.entries(ICONS)) if (!map.hasImage(name)) map.addImage(name, img, { pixelRatio: 2 });

  const ids = def => [def.id, ...(def.extraIds ?? [])].filter(i => map.getLayer(i));
  function applyVisibility(def) {
    const on = current.state[def.id].on && !current.hidden;
    for (const i of ids(def)) map.setLayoutProperty(i, 'visibility', on ? 'visible' : 'none');
  }
  function applyOpacity(def) {
    if (def.setOpacity) return def.setOpacity(map, current.state[def.id].opacity);
    for (const i of ids(def)) {
      const prop = OPACITY_PROP[map.getLayer(i).type];
      if (prop && !['buildings-pt', 'roads-gap', 'cuts-hl', 'settlements-ring', 'facilities-ring', 'areas-line', 'landing-line', 'landing-pt', 'floodpath-start', 'floodpath-pts'].includes(i)) map.setPaintProperty(i, prop, current.state[def.id].opacity);
    }
  }

  function clear() {
    if (!current) return;
    popup?.remove();
    for (const [evt, layer, fn] of handlers.splice(0)) map.off(evt, layer, fn);
    for (const l of [...current.ownedLayers, 'sel-ring']) if (map.getLayer(l)) map.removeLayer(l);
    for (const s of [...current.ownedSources, 'sel']) if (map.getSource(s)) map.removeSource(s);
    current = null; probImg = null;
    panelEl.replaceChildren();
    legendEl.replaceChildren();
    legendEl.hidden = true;
  }

  /** Add the map layers of one definition and remember what it created (so clear() can remove it). */
  function build(def) {
    const beforeL = new Set(map.getStyle().layers.map(l => l.id));
    const beforeS = new Set(Object.keys(map.getStyle().sources));
    def.add(map, current.data, current.ov);
    for (const l of map.getStyle().layers) if (!beforeL.has(l.id)) current.ownedLayers.push(l.id);
    for (const s of Object.keys(map.getStyle().sources)) if (!beforeS.has(s)) current.ownedSources.push(s);
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
      build(def);
      applyVisibility(def);
    }
    map.addSource('sel', { type: 'geojson', data: EMPTY });
    map.addLayer({ id: 'sel-ring', type: 'circle', source: 'sel', paint: { 'circle-radius': 17, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': C.sel, 'circle-stroke-width': 3 } });
    wireInteractions();
    if (current.ready.flood_prob) applyThreshold(0.5);
    if (current.ready.observability) recolorObservability();
    renderPanel();
    renderLegend();
    return { data, ov };
  }

  function bindFloodpathClick() {
    if (!map.getLayer('floodpath-pts') || handlers.some(h => h[0] === 'click' && h[1] === 'floodpath-pts')) return;
    const fn = e => onSettlement?.(e.features[0].properties.osm_id);
    map.on('click', 'floodpath-pts', fn); handlers.push(['click', 'floodpath-pts', fn]);
  }

  // ---- popups + clicks ----
  function wireInteractions() {
    const on = (evt, layer, fn) => { map.on(evt, layer, fn); handlers.push([evt, layer, fn]); };
    for (const layer of ['settlements', 'floodpath-pts', ...POPUP_LAYERS]) {
      if (!map.getLayer(layer)) continue;
      on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer'; });
      on('mouseleave', layer, () => { map.getCanvas().style.cursor = ''; });
    }
    if (map.getLayer('settlements')) {
      on('click', 'settlements', e => { onSettlement?.(e.features[0].properties.osm_id); });
      on('mouseenter', 'settlements', e => {
        popup?.remove();
        const p = e.features[0].properties;
        popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14, className: 'dark-popup' }).setLngLat(e.features[0].geometry.coordinates).setText(p.name ?? 'Settlement').addTo(map);
      });
      on('mouseleave', 'settlements', () => popup?.remove());
    }
    bindFloodpathClick();
    for (const layer of POPUP_LAYERS) {
      if (!map.getLayer(layer)) continue;
      on('click', layer, e => {
        const over = ['settlements', 'floodpath-pts', 'facilities'].filter(l => l !== layer && map.getLayer(l));
        if (over.length && map.queryRenderedFeatures(e.point, { layers: over }).length) return;
        popup?.remove();
        popup = new maplibregl.Popup({ className: 'dark-popup', offset: 8, maxWidth: '320px' }).setLngLat(e.lngLat).setDOMContent(onFeatureInfo(layer, e.features[0].properties)).addTo(map);
      });
    }
  }

  // ---- raster overlays recoloured in the browser ----
  const loadImage = url => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
  let probImg = null;
  async function applyThreshold(thr) {
    const o = current?.ov.flood_prob;
    if (!o || !map.getSource('flood_prob')) return;
    probImg ??= await loadImage(o.url);
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
    map.getSource('flood_prob')?.updateImage({ url: c.toDataURL(), coordinates: [[w, n], [e, n], [e, s], [w, s]] });
  }
  /** debris_observability.png: R = code of flood/debris_observability.tif (1 seen, 2 cannot be seen, 3 insensitive). */
  async function recolorObservability() {
    const o = current?.ov.debris_observability;
    if (!o || !map.getSource('observability')) return;
    const img = await loadImage(o.url);
    const c = document.createElement('canvas');
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    const x = c.getContext('2d', { willReadFrequently: true });
    x.drawImage(img, 0, 0);
    const im = x.getImageData(0, 0, c.width, c.height), d = im.data;
    for (let i = 0, p = 0; i < d.length; i += 4, p++) {
      const code = d[i], stripe = (((p % c.width) + Math.floor(p / c.width)) & 7) < 4;
      if (code === 2) { d[i] = 12; d[i + 1] = 12; d[i + 2] = 16; d[i + 3] = stripe ? 170 : 70; }
      else if (code === 3) { d[i] = 250; d[i + 1] = 178; d[i + 2] = 25; d[i + 3] = stripe ? 120 : 30; }
      else d[i + 3] = 0;
    }
    x.putImageData(im, 0, 0);
    const [w, s, e, n] = o.bounds;
    map.getSource('observability')?.updateImage({ url: c.toDataURL(), coordinates: [[w, n], [e, n], [e, s], [w, s]] });
  }

  // ---- layers panel ----
  function swatchFor(def) {
    const lg = typeof def.legend === 'function' ? def.legend(current.data)[0] : def.legend[0];
    if (lg?.t === 'icon') { const c = document.createElement('canvas'); c.width = c.height = 14; c.getContext('2d').drawImage(iconCanvas(lg.i), 0, 0, 14, 14); c.className = 'swatch-icon'; return c; }
    if (lg?.c) return el('i', { class: `swatch${lg.t === 'line' || lg.t === 'dash' ? ' line' : ''}`, style: `--c:${lg.c}` });
    return el('i', { class: 'swatch hollow' });
  }
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
      const row = el('div', { class: `lp-row${ok ? '' : ' disabled'}`, title: ok ? '' : def.why },
        el('label', { for: `lp-${def.id}` }, cb, ok ? swatchFor(def) : el('i', { class: 'swatch hollow' }), el('span', { text: def.label }), def.tag ? el('em', { class: 'tag', text: def.tag }) : null),
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
    for (const def of DEFS) if (current.ready[def.id] && current.state[def.id].on) items.push(...(typeof def.legend === 'function' ? def.legend(current.data) : def.legend));
    legendEl.hidden = items.length === 0;
    legendEl.append(el('div', { class: 'lg-title', text: 'Legend' }));
    for (const it of items) {
      if (it.t === 'text') { legendEl.append(el('div', { class: 'lg-note', text: it.l })); continue; }
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

  const boundsOf = coords => {
    const flat = []; const walk = a => (typeof a[0] === 'number' ? flat.push(a) : a.forEach(walk)); walk(coords);
    const b = new maplibregl.LngLatBounds(flat[0], flat[0]); flat.forEach(p => b.extend(p)); return b;
  };

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
    clearSelection() { map.getSource('sel')?.setData(EMPTY); if (map.getLayer('cuts-hl')) map.setFilter('cuts-hl', ['==', ['get', 'osm_id'], '']); },
    highlightCuts(osmIds) {
      if (!map.getLayer('cuts-hl')) return;
      map.setFilter('cuts-hl', ['in', ['get', 'osm_id'], ['literal', osmIds.length ? osmIds : ['']]]);
      this.setLayerOn('cuts', true);
      const feats = (current.data.cuts?.features ?? []).filter(f => osmIds.includes(f.properties.osm_id));
      if (feats.length) map.fitBounds(boundsOf(feats.map(f => f.geometry.coordinates)), { padding: 120, maxZoom: 14, duration: 700 });
    },
    flyToPoint(lon, lat, zoom = 14) { map.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), zoom), duration: 700 }); },
    flyToFeature(f) {
      if (f.geometry.type === 'Point') return this.flyToPoint(...f.geometry.coordinates);
      map.fitBounds(boundsOf(f.geometry.coordinates), { padding: 120, maxZoom: 15, duration: 700 });
    },
    /** Show a flood path result ({path, settlements}) on the map (replaces an earlier one). */
    setFloodpath(result) {
      if (!current) return;
      for (const l of ['floodpath-start', 'floodpath-pts', 'floodpath', 'floodpath-corridor']) if (map.getLayer(l)) map.removeLayer(l);
      for (const s of ['floodpath-start', 'floodpath-pts', 'floodpath', 'floodpath-corridor']) if (map.getSource(s)) map.removeSource(s);
      current.data.floodpath = result.path; current.data.floodpathSettlements = result.settlements;
      const def = DEFS.find(d => d.id === 'floodpath');
      build(def);
      current.ready.floodpath = true; current.state.floodpath.on = true;
      applyVisibility(def); renderPanel(); renderLegend();
      const line = (result.path?.features ?? []).find(f => f.properties.kind === 'path');
      if (line) map.fitBounds(boundsOf(line.geometry.coordinates), { padding: { top: 90, bottom: 90, left: 300, right: 90 }, maxZoom: 14, duration: 800 });
      bindFloodpathClick();
    },
    clearFloodpath() {
      if (!current) return;
      for (const l of ['floodpath-start', 'floodpath-pts', 'floodpath', 'floodpath-corridor']) if (map.getLayer(l)) map.removeLayer(l);
      for (const s of ['floodpath-start', 'floodpath-pts', 'floodpath', 'floodpath-corridor']) if (map.getSource(s)) map.removeSource(s);
      current.data.floodpath = null; current.data.floodpathSettlements = null; current.ready.floodpath = false;
      renderPanel(); renderLegend();
    },
  };
}
