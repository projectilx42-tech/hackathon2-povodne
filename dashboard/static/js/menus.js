// Top-bar popovers (Advanced windows, Examples, History) and place search.
import { getRuns } from './api.js';
import { el, num } from './util.js';

const openPops = [];
export function popover(button, pop, onOpen) {
  const close = () => { pop.hidden = true; button.setAttribute('aria-expanded', 'false'); };
  openPops.push(close);
  button.addEventListener('click', e => {
    e.stopPropagation();
    const willOpen = pop.hidden;
    openPops.forEach(c => c());
    if (willOpen) { onOpen?.(); pop.hidden = false; button.setAttribute('aria-expanded', 'true'); }
  });
  pop.addEventListener('click', e => e.stopPropagation());
  return close;
}
document.addEventListener('click', () => openPops.forEach(c => c()));
document.addEventListener('keydown', e => { if (e.key === 'Escape') openPops.forEach(c => c()); });

// Presets only pre-fill the area and date; the pipeline then runs normally (nothing is hard-coded).
export const EXAMPLES = [
  { name: 'Trishuli / Bhote Koshi corridor, Nepal', note: 'Glacier-collapse flood, 26 Aug 2026 (approximate corridor)', date: '2026-08-26', bbox: [85.20, 28.00, 85.45, 28.27] },
];
export function renderExamples(pop, onPick) {
  pop.replaceChildren(el('h3', { text: 'Examples' }), el('p', { class: 'muted', text: 'Fills in the area and date. The analysis then runs on real satellite data as usual.' }),
    el('ul', { class: 'menu-list' }, ...EXAMPLES.map(x => el('li', {}, el('button', { type: 'button', onclick: () => onPick(x) }, x.name, el('span', { class: 'sub', text: `${x.note} · ${x.date}` }))))));
}

const VERDICT_BADGE = { flood_detected: ['bad', 'Flood'], no_significant_flooding: ['ok', 'No flood'], insufficient_data: ['warn', 'Little data'] };
export async function renderHistory(pop, onOpen) {
  pop.replaceChildren(el('h3', { text: 'Earlier runs' }), el('p', { class: 'muted', text: 'Loading…' }));
  let runs;
  try { runs = await getRuns(); } catch (e) { pop.replaceChildren(el('h3', { text: 'Earlier runs' }), el('p', { class: 'notice bad', text: `Could not load runs: ${e.message}` })); return; }
  const items = runs.map(r => {
    const vb = VERDICT_BADGE[r.verdict];
    const stateBadge = r.state && r.state !== 'done' ? el('span', { class: `badge ${r.state === 'failed' ? 'bad' : 'warn'}`, text: r.state }) : null;
    return el('li', {}, el('button', { type: 'button', onclick: () => onOpen(r) },
      el('span', { class: 'row' }, el('span', {}, `${r.event_date ?? '?'} · ${r.aoi_area_km2 != null ? num(r.aoi_area_km2, 0) + ' km²' : ''}`),
        el('span', {}, r.mock ? el('span', { class: 'badge sample', text: 'SAMPLE' }) : null, ' ', vb ? el('span', { class: `badge ${vb[0]}`, text: vb[1] }) : null, stateBadge)),
      el('span', { class: 'sub mono', text: r.run_id })));
  });
  pop.replaceChildren(el('h3', { text: 'Earlier runs' }), items.length ? el('ul', { class: 'menu-list' }, ...items) : el('p', { class: 'muted', text: 'No runs yet.' }));
}

// ---- place search (Nominatim, navigation only; never an input to the analysis) ----
const COORD = /^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$/;
export function setupSearch({ form, input, list, map }) {
  const hide = () => { list.hidden = true; list.replaceChildren(); };
  const flyTo = (lon, lat, bbox) => {
    hide();
    if (bbox) map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40, maxZoom: 14, duration: 800 });
    else map.flyTo({ center: [lon, lat], zoom: 12, duration: 800 });
  };
  const show = nodes => { list.replaceChildren(...nodes); list.hidden = false; };
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return hide();
    const m = q.match(COORD);
    if (m) {
      const [a, b] = [parseFloat(m[1]), parseFloat(m[2])];
      // "lat, lon" order; swap if the first value cannot be a latitude
      const [lat, lon] = Math.abs(a) <= 90 ? [a, b] : [b, a];
      if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) return flyTo(lon, lat);
    }
    show([el('li', { class: 'none', text: 'Searching…' })]);
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=6&accept-language=en&q=${encodeURIComponent(q)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const hits = await res.json();
      show(hits.length ? hits.map(h => el('li', {}, el('button', { type: 'button', onclick: () => { input.value = h.display_name.split(',')[0]; flyTo(+h.lon, +h.lat, h.boundingbox ? [+h.boundingbox[2], +h.boundingbox[0], +h.boundingbox[3], +h.boundingbox[1]] : null); } }, h.display_name)))
                       : [el('li', { class: 'none', text: 'No places found. Try another name or enter “lat, lon”.' })]);
    } catch (err) {
      show([el('li', { class: 'none', text: `Search is unavailable (${err.message}). You can still enter “lat, lon”.` })]);
    }
  });
  document.addEventListener('click', e => { if (!form.contains(e.target)) hide(); });
  input.addEventListener('keydown', e => { if (e.key === 'Escape') { hide(); input.blur(); } });
}
