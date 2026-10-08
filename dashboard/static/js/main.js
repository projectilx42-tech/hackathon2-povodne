import { createMap, setBasemap } from './map.js';
import { createAoi } from './aoi.js';
import { BASEMAPS, DEFAULT_BASEMAP, AREA_WARN_KM2 } from './config.js';
import { polygonAreaKm2, polygonBbox } from './geo.js';

const $ = id => document.getElementById(id);
const safe = {
  get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
};

const map = createMap('map');
let aoi = null; // GeoJSON Polygon or null

// ---- base map switcher ----
const bmBox = $('basemaps');
for (const b of BASEMAPS) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = b.label;
  btn.dataset.id = b.id;
  btn.classList.toggle('active', b.id === DEFAULT_BASEMAP);
  btn.addEventListener('click', () => {
    setBasemap(map, b.id);
    bmBox.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === btn));
  });
  bmBox.append(btn);
}

// ---- cursor coordinates ----
map.on('mousemove', e => {
  $('coords').textContent = `${e.lngLat.lat.toFixed(4)}°N  ${e.lngLat.lng.toFixed(4)}°E  ·  z${map.getZoom().toFixed(1)}`;
});

// ---- toast ----
let toastTimer;
function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 4000);
}

// ---- area drawing ----
const toolButtons = [...document.querySelectorAll('#tool-group button')];
function showTool(t) {
  toolButtons.forEach(b => b.classList.toggle('active', b.dataset.tool === t));
}

let areaTool = null; // created once the map style has loaded
map.on('load', () => {
  areaTool = createAoi(map, {
    onToolChange: showTool,
    onChange: polygon => { aoi = polygon; renderAoi(); },
  });
});

toolButtons.forEach(b => b.addEventListener('click', () => areaTool?.setTool(b.dataset.tool)));
$('clear-aoi').addEventListener('click', () => areaTool?.clear());

const fmtArea = km2 => (km2 >= 100 ? km2.toFixed(0) : km2.toFixed(1)) + ' km²';

function renderAoi() {
  const has = !!aoi;
  $('clear-aoi').disabled = !has;
  toolButtons.find(b => b.dataset.tool === 'edit').disabled = !has;
  $('selection-empty').hidden = has;
  $('selection-info').hidden = !has;
  const chip = $('aoi-chip');
  chip.hidden = !has;
  const warn = $('selection-warn');
  warn.hidden = true;
  chip.classList.remove('warn');
  if (has) {
    const km2 = polygonAreaKm2(aoi);
    const [w, s, e, n] = polygonBbox(aoi);
    chip.textContent = fmtArea(km2);
    $('sel-area').textContent = fmtArea(km2);
    $('sel-bbox').textContent = `${s.toFixed(3)}–${n.toFixed(3)}°N, ${w.toFixed(3)}–${e.toFixed(3)}°E`;
    if (km2 > AREA_WARN_KM2) {
      chip.classList.add('warn');
      warn.textContent = `This area is larger than ~${AREA_WARN_KM2} km² (about 30 × 30 km). The run will take much longer; a smaller area is recommended.`;
      warn.hidden = false;
    }
  }
  updateRun();
}

// ---- date + run ----
const dateInput = $('event-date');
const today = new Date().toISOString().slice(0, 10);
dateInput.max = today;
dateInput.addEventListener('input', updateRun);

function updateRun() {
  const ok = !!aoi && /^\d{4}-\d{2}-\d{2}$/.test(dateInput.value) && dateInput.value <= today;
  const btn = $('run-btn');
  btn.disabled = !ok;
  btn.title = ok ? 'Run the analysis' : 'Select an area and a date first';
}

$('run-btn').addEventListener('click', () => {
  // Placeholder: the pipeline (M1–M6) is not connected yet (POST /api/runs, see docs/ARCHITECTURE.md).
  toast('The analysis pipeline is not connected yet — this button will start the run.');
});

// ---- tip card ----
if (safe.get('tipHidden') === '1') $('tip-card').hidden = true;
$('tip-close').addEventListener('click', () => { $('tip-card').hidden = true; safe.set('tipHidden', '1'); });

renderAoi();
