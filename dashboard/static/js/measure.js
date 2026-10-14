// Distance / area measuring tool. Click to add points; double-click or Esc to finish; click the button to leave.
import { km } from './util.js';

const R = 6371008.8, rad = d => (d * Math.PI) / 180;
const hav = (a, b) => {
  const dLat = rad(b[1] - a[1]), dLon = rad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};
function areaKm2(pts) {
  let s = 0;
  for (let i = 0; i < pts.length; i++) { const [l1, a1] = pts[i], [l2, a2] = pts[(i + 1) % pts.length]; s += rad(l2 - l1) * (2 + Math.sin(rad(a1)) + Math.sin(rad(a2))); }
  return Math.abs((s * R * R) / 2) / 1e6;
}

export function createMeasure({ map, wrap, button, readout, onActive }) {
  let on = false, pts = [], done = false;
  const EMPTY = { type: 'FeatureCollection', features: [] };

  function ensure() {
    if (map.getSource('measure')) return;
    map.addSource('measure', { type: 'geojson', data: EMPTY });
    map.addLayer({ id: 'measure-fill', type: 'fill', source: 'measure', filter: ['==', '$type', 'Polygon'], paint: { 'fill-color': '#ffe066', 'fill-opacity': 0.12 } });
    map.addLayer({ id: 'measure-line', type: 'line', source: 'measure', paint: { 'line-color': '#ffe066', 'line-width': 2, 'line-dasharray': [2, 1] } });
    map.addLayer({ id: 'measure-pt', type: 'circle', source: 'measure', filter: ['==', '$type', 'Point'], paint: { 'circle-radius': 4, 'circle-color': '#ffe066', 'circle-stroke-color': '#0b0f14', 'circle-stroke-width': 1.5 } });
  }
  function render() {
    ensure();
    const feats = pts.map(p => ({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: p } }));
    if (pts.length > 1) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: pts.length > 2 && done ? [...pts, pts[0]] : pts } });
    if (pts.length > 2) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...pts, pts[0]]] } });
    map.getSource('measure').setData({ type: 'FeatureCollection', features: feats });
    const len = pts.slice(1).reduce((s, p, i) => s + hav(pts[i], p), 0);
    readout.hidden = pts.length === 0;
    const parts = [`Distance ${km(len)}`];
    if (pts.length > 2) parts.push(`Area ${areaKm2(pts).toFixed(2)} km²`);
    readout.textContent = pts.length ? parts.join(' · ') : '';
  }
  const onClick = e => { if (done) { pts = []; done = false; } pts.push([e.lngLat.lng, e.lngLat.lat]); render(); };
  const onDbl = e => { e.preventDefault(); done = true; pts.pop(); render(); };
  const onKey = e => { if (e.key === 'Escape') { pts = []; done = false; render(); } };

  function setOn(v) {
    on = v;
    button.setAttribute('aria-pressed', String(v));
    wrap.classList.toggle('measuring', v);
    onActive?.(v);
    if (v) { map.on('click', onClick); map.on('dblclick', onDbl); map.doubleClickZoom.disable(); window.addEventListener('keydown', onKey); }
    else { map.off('click', onClick); map.off('dblclick', onDbl); map.doubleClickZoom.enable(); window.removeEventListener('keydown', onKey); pts = []; done = false; render(); readout.hidden = true; }
  }
  button.addEventListener('click', () => setOn(!on));
  return { get active() { return on; }, off: () => on && setOn(false) };
}
