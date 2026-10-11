import { createMap, setBasemap } from './map.js';
import { createAoi } from './aoi.js';
import { createLayers } from './layers.js';
import { createResults } from './results.js';
import { createCompare } from './compare.js';
import { createMeasure } from './measure.js';
import { popover, renderExamples, renderHistory, setupSearch } from './menus.js';
import { METHODS_HTML } from './methods.js';
import { BASEMAPS, DEFAULT_BASEMAP, AREA_WARN_KM2, applyConfig } from './config.js';
import { polygonAreaKm2, polygonBbox } from './geo.js';
import { startRun, getRun, getStatus, cancelRun } from './api.js';
import { $, el, safeStore, icon } from './util.js';

try { applyConfig(await (await fetch('/api/config')).json()); } catch { /* keep the default base maps */ }
const map = createMap('map');
const wrap = $('map-wrap');
let aoi = null;           // current area (GeoJSON Polygon) or null
let currentRunId = null;  // run shown in the panel
let pollTimer = null;
let running = false;
let basemap = DEFAULT_BASEMAP;
let areaTool = null, layers = null, results = null, compare = null, measure = null;
let overviewNodes = null;
let sensitivity = 'standard'; // 'standard' | 'sensitive'

const today = new Date().toISOString().slice(0, 10);

// ---------- toast ----------
let toastTimer;
function toast(msg, ms = 4500) {
  const t = $('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, ms);
}

// ---------- base map switcher ----------
const bmBox = $('basemaps');
for (const b of BASEMAPS) {
  const btn = el('button', { type: 'button', 'data-id': b.id, class: b.id === basemap ? 'active' : '', text: b.label });
  btn.addEventListener('click', () => {
    basemap = b.id;
    setBasemap(map, b.id);
    compare?.setBasemap(b.id);
    bmBox.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === btn));
  });
  bmBox.append(btn);
}
map.on('mousemove', e => { $('coords').textContent = `${e.lngLat.lat.toFixed(4)}°N  ${e.lngLat.lng.toFixed(4)}°E  ·  z${map.getZoom().toFixed(1)}`; });

// ---------- area drawing ----------
const toolButtons = [...document.querySelectorAll('#tool-group button')];
const showTool = t => toolButtons.forEach(b => b.classList.toggle('active', b.dataset.tool === t));
toolButtons.forEach(b => b.addEventListener('click', () => {
  if (measure?.active) measure.off();
  // clicking the active draw tool again cancels drawing and returns to panning
  const t = b.dataset.tool;
  areaTool?.setTool(b.classList.contains('active') && (t === 'rectangle' || t === 'shape') ? 'pan' : t);
}));
$('clear-aoi').addEventListener('click', () => areaTool?.clear());

const fmtArea = km2 => (km2 >= 100 ? km2.toFixed(0) : km2.toFixed(1)) + ' km²';
function renderAoi() {
  const has = !!aoi;
  $('clear-aoi').disabled = !has;
  toolButtons.find(b => b.dataset.tool === 'edit').disabled = !has;
  $('selection-empty').hidden = has;
  $('selection-info').hidden = !has;
  const chip = $('aoi-chip'), warn = $('selection-warn');
  chip.hidden = !has; warn.hidden = true; chip.classList.remove('warn');
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

// ---------- date, advanced windows, run button ----------
const dateInput = $('event-date');
dateInput.max = today;
dateInput.addEventListener('input', () => { updateRun(); validateWindows(); });

const winIds = ['pre-from', 'pre-to', 'post-from', 'post-to'];
function windows() {
  const v = Object.fromEntries(winIds.map(i => [i, $(i).value]));
  const any = winIds.some(i => v[i]);
  const pre = v['pre-from'] && v['pre-to'] ? [v['pre-from'], v['pre-to']] : null;
  const post = v['post-from'] && v['post-to'] ? [v['post-from'], v['post-to']] : null;
  return { any, pre, post, complete: (!!v['pre-from'] === !!v['pre-to']) && (!!v['post-from'] === !!v['post-to']) };
}
function validateWindows() {
  const w = windows(), warn = $('adv-warn'), d = dateInput.value;
  let msg = '';
  if (!w.complete) msg = 'Fill in both dates of a window, or leave it empty.';
  else if (w.pre && w.pre[0] > w.pre[1]) msg = 'The “before” window ends before it starts.';
  else if (w.post && w.post[0] > w.post[1]) msg = 'The “after” window ends before it starts.';
  else if (d && w.pre && w.pre[1] >= d) msg = 'The “before” window should end before the flood date.';
  else if (d && w.post && w.post[0] < d) msg = 'The “after” window should not start before the flood date.';
  warn.textContent = msg; warn.hidden = !msg;
  $('adv-dot').hidden = !(w.any || sensitivity !== 'standard' || $('event-time').value);
  return { hard: !w.complete || /ends before it starts/.test(msg) };
}
winIds.forEach(i => $(i).addEventListener('input', validateWindows));
$('event-time').addEventListener('input', validateWindows);
const SENS_HELP = {
  standard: 'Balanced: marks flooded area only where the model is fairly sure. Fewer false alarms.',
  sensitive: 'Finds more flooded area, including uncertain places, but also gives more false alarms. Use it when missing a flood is worse than a false alarm.',
};
function setSensitivity(v) {
  sensitivity = v;
  document.querySelectorAll('#sens-group button').forEach(b => b.classList.toggle('active', b.dataset.sens === v));
  $('sens-help').textContent = SENS_HELP[v];
  validateWindows();
}
document.querySelectorAll('#sens-group button').forEach(b => b.addEventListener('click', () => setSensitivity(b.dataset.sens)));
$('adv-reset').addEventListener('click', () => { winIds.forEach(i => { $(i).value = ''; }); $('event-time').value = ''; setSensitivity('standard'); });

function updateRun() {
  const btn = $('run-btn');
  if (running) { btn.disabled = false; btn.replaceChildren(icon('stop'), 'Cancel'); btn.classList.remove('primary'); btn.classList.add('danger-outline'); btn.title = 'Cancel the running analysis'; return; }
  btn.replaceChildren(icon('play'), 'Run'); btn.classList.add('primary'); btn.classList.remove('danger-outline');
  const ok = !!aoi && /^\d{4}-\d{2}-\d{2}$/.test(dateInput.value) && dateInput.value <= today;
  btn.disabled = !ok;
  btn.title = ok ? 'Run the analysis' : 'Select an area and a date first';
}

$('run-btn').addEventListener('click', async () => {
  if (running) return doCancel();
  if (validateWindows().hard) { toast('Check the Advanced windows first.'); return; }
  const w = windows();
  const body = { aoi, event_date: dateInput.value, sensitivity };
  if (w.pre) body.pre_window = w.pre;
  if (w.post) body.post_window = w.post;
  if ($('event-time').value) body.event_time = $('event-time').value;
  try {
    const { run_id } = await startRun(body);
    resetResultView();
    beginRunning(run_id);
  } catch (e) { toast(`Could not start the run: ${e.message}`); }
});

async function doCancel() {
  if (!currentRunId) return;
  try { await cancelRun(currentRunId); } catch (e) { toast(`Could not cancel: ${e.message}`); }
}

// ---------- run lifecycle ----------
function resetResultView() {
  stopPolling();
  if (compare?.active) toggleCompare();
  layers?.clear();
  $('layers-card').hidden = true;
  $('cmp-btn').disabled = true;
  overviewNodes = null;
  $('state').replaceChildren();
}
function stopPolling() { clearInterval(pollTimer); pollTimer = null; }

function beginRunning(runId) {
  currentRunId = runId;
  running = true;
  $('tip-card').hidden = true;
  updateRun();
  const tick = async () => {
    let st;
    try { st = await getStatus(runId); } catch (e) { toast(`Lost contact with the server: ${e.message}`); return; }
    if (st.state === 'done') { stopPolling(); running = false; updateRun(); await showResults(runId); }
    else if (st.state === 'failed' || st.state === 'cancelled') { stopPolling(); running = false; updateRun(); results.renderError(st, {}); }
    else results.renderRunning(st, { onCancel: doCancel });
  };
  tick();
  pollTimer = setInterval(tick, 1500);
}

async function showResults(runId) {
  currentRunId = runId;
  let detail;
  try { detail = await getRun(runId); } catch (e) { toast(`Could not open the run: ${e.message}`); return; }
  const { run, stats } = detail;
  $('tip-card').hidden = true;
  if (run.aoi) {
    const rect = run.aoi.coordinates[0].length === 5;
    areaTool.setPolygon(run.aoi, rect ? 'rectangle' : 'freehand');
    const [w, s, e, n] = polygonBbox(run.aoi);
    map.fitBounds([[w, s], [e, n]], { padding: { top: 70, bottom: 70, left: 290, right: 70 }, duration: 800 });
  }
  if (run.event_date) { dateInput.value = run.event_date; updateRun(); }
  await layers.load(runId);
  // keep drawing / measuring layers above the result layers
  for (const l of map.getStyle().layers) if (l.id.startsWith('td-') || l.id.startsWith('measure')) map.moveLayer(l.id);
  $('layers-card').hidden = false;
  const ov = layers.overlays ?? {};
  $('cmp-btn').disabled = !(ov.s2_pre && ov.s2_post);
  overviewNodes = null;
  await results.renderResult(runId, run, stats);
}

async function openRunSummary(r) {
  $('hist-pop').hidden = true;
  stopPolling(); running = false; resetResultView(); updateRun();
  try {
    const st = await getStatus(r.run_id);
    if (st.state === 'queued' || st.state === 'running') return beginRunning(r.run_id);
    if (st.state === 'failed' || st.state === 'cancelled') { currentRunId = r.run_id; return results.renderError(st, {}); }
  } catch { /* fall through and try to show results */ }
  await showResults(r.run_id);
}

// ---------- settlement detail ----------
function openSettlement(osmId) {
  const f = layers.selectSettlement(osmId);
  if (!f) return;
  const root = $('state');
  if (!overviewNodes) overviewNodes = [...root.children];
  results.renderSettlement(f);
}
function backToOverview() {
  layers.clearSelection();
  if (overviewNodes) { results.setView(...overviewNodes); overviewNodes = null; }
}

function exportPng() {
  map.once('render', () => map.getCanvas().toBlob(b => {
    if (!b) return toast('Could not export the map view.');
    const a = el('a', { href: URL.createObjectURL(b), download: `map-${currentRunId ?? 'view'}.png` });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }));
  map.triggerRepaint();
}

// ---------- before / after ----------
async function toggleCompare() {
  if (compare.active) {
    compare.disable();
    layers.setLayerOn('imagery_pre', false);
    layers.setVectorsHidden(false);
    $('cmp-btn').lastElementChild.textContent = 'Before / after slider';
    return;
  }
  const ov = layers.overlays ?? {};
  if (!(ov.s2_pre && ov.s2_post)) return;
  layers.setVectorsHidden(true);
  layers.setLayerOn('imagery_pre', true);
  layers.setLayerOn('imagery_post', false);
  await compare.enable({ pre: ov.s2_pre, post: ov.s2_post, basemap });
  $('cmp-btn').lastElementChild.textContent = 'Exit before / after';
}
$('cmp-btn').addEventListener('click', toggleCompare);

// ---------- panels & misc ----------
$('layers-toggle').addEventListener('click', () => {
  const card = $('layers-card');
  card.classList.toggle('collapsed');
  $('layers-toggle').setAttribute('aria-expanded', String(!card.classList.contains('collapsed')));
});
if (safeStore.get('tipHidden') === '1') $('tip-card').hidden = true;
$('tip-close').addEventListener('click', () => { $('tip-card').hidden = true; safeStore.set('tipHidden', '1'); });

$('methods-body').innerHTML = METHODS_HTML;
$('methods-btn').addEventListener('click', () => $('methods-modal').showModal());
$('methods-modal').addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.close(); });

popover($('adv-btn'), $('adv-pop'));
popover($('ex-btn'), $('ex-pop'), () => renderExamples($('ex-pop'), pickExample));
popover($('hist-btn'), $('hist-pop'), () => renderHistory($('hist-pop'), openRunSummary));
setupSearch({ form: $('search-form'), input: $('search-input'), list: $('search-results'), map });

function pickExample(x) {
  $('ex-pop').hidden = true;
  const [w, s, e, n] = x.bbox;
  resetResultView();
  areaTool.setPolygon({ type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] }, 'rectangle');
  dateInput.value = x.date;
  updateRun(); validateWindows();
  map.fitBounds([[w, s], [e, n]], { padding: 90, duration: 800 });
}

// ---------- start once the style is ready ----------
map.on('load', () => {
  areaTool = createAoi(map, { onToolChange: showTool, onChange: p => { aoi = p; renderAoi(); } });
  layers = createLayers(map, {
    panelEl: $('layers-panel'), legendEl: $('legend'),
    onSettlement: openSettlement,
    onFeatureInfo: (layer, props) => results.featureInfo(layer, props),
  });
  results = createResults($('state'), { layers, openSettlement, onBack: backToOverview, exportPng });
  compare = createCompare({ map, wrap, handle: $('cmp-handle'), tags: $('cmp-tags') });
  measure = createMeasure({ map, wrap, button: $('measure-btn'), readout: $('measure-readout'), onActive: on => (on ? areaTool.pause() : areaTool.resume()) });
  renderAoi();
});
renderAoi();
validateWindows();
