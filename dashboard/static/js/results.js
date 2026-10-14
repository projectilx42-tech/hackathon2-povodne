// Right-panel views: result overview, settlement detail, flood path, running stepper, errors and notices.
import { el, num, pct, km, minutes, icon } from './util.js';
import { fileUrl, fileExists } from './api.js';
import { NOTICE_TITLES } from './notice_titles.js';
import { SUBTYPE, GRADE, IMPACT, ACCESS, ROAD_STATUS, FACILITY_ACCESS, LANDING, CONF_LABEL, kindLabel } from './labels.js';

const VERDICT = {
  flood_detected: { cls: 'bad', icon: 'alert', title: 'Flood detected' },
  no_significant_flooding: { cls: 'good', icon: 'check', title: 'No significant flooding detected' },
  insufficient_data: { cls: 'warn', icon: 'info', title: 'Insufficient data' },
};
const STEP_LABEL = {
  acquire: 'Acquire satellite data', preprocess: 'Preprocess & align', flood_ai: 'Flood detection (AI)', confidence: 'Confidence map', s1anomaly: 'Radar change vs. normal year',
  debris: 'Debris, mud & surface change', envelope: 'Water-level envelope', combine: 'Combine water and debris maps', damage: 'Damage overlay',
  network: 'Cut-off analysis', report: 'Statistics & report',
};

const sec = (title, ...kids) => el('section', { class: 'sec' }, title ? el('h2', { text: title }) : null, ...kids);
const rows = list => el('dl', { class: 'rows' }, ...list.filter(Boolean).map(([k, v, strong]) => el('div', { class: 'row' }, el('dt', { text: k }), el('dd', { class: strong ? 'strong' : '', text: v }))));
const bar = (label, v, none = 'n/a') => el('div', { class: 'bar-row' }, el('span', { class: 'bar-l', text: label }),
  el('span', { class: 'bar' }, el('i', { style: `width:${v == null ? 0 : Math.max(0, Math.min(100, v))}%` })), el('span', { class: 'bar-v', text: v == null ? none : pct(v) }));
const badge = (text, cls = '') => el('span', { class: `badge ${cls}`, text });
const pill = (text, color) => el('span', { class: 'pill', style: `--c:${color}`, text });
const plural = (n, one, many = `${one}s`) => (n === 1 ? one : many);
/** Long lists show the first `limit` rows; a button reveals the rest (keeps the panel short and fast). Returns the button or null. */
function moreButton(items, limit, noun) {
  if (items.length <= limit) return null;
  const rest = items.slice(limit);
  rest.forEach(n => { n.hidden = true; });
  const btn = el('button', { type: 'button', class: 'linklike more', text: `Show all ${items.length} ${noun}`, onclick: () => { rest.forEach(n => { n.hidden = false; }); btn.remove(); } });
  return btn;
}
const fmtArea = km2 => (km2 == null ? 'n/a' : km2 >= 1 ? `${num(km2, 2)} km²` : `${num(km2 * 100, 1)} ha`);

// ---------- notices (run.json.notices, docs/NOTICES.md) ----------
const humanize = code => String(code ?? 'notice').replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
export const noticeTitle = n => NOTICE_TITLES[n.code]?.title ?? humanize(n.code);

/** Errors / warnings / infos from run.json.notices; legacy plain-text warnings are added only when they are not already covered. */
export function noticeBuckets(run, stats) {
  const n = run.notices ?? [];
  const known = new Set(n.map(x => String(x.message).trim()));
  const legacyRaw = [...(stats?.warnings ?? []), ...(n.length ? [] : [...(run.warnings ?? []), ...(run.acquire?.warnings ?? [])])];
  const legacy = [...new Set(legacyRaw.map(w => (typeof w === 'string' ? w : (w?.message ?? ''))).map(w => w.trim()).filter(w => w && !known.has(w)))]
    .map(message => ({ code: 'warning', severity: 'warning', message, step: null }));
  return { errors: n.filter(x => x.severity === 'error'), warnings: [...n.filter(x => x.severity === 'warning'), ...legacy], infos: n.filter(x => x.severity === 'info') };
}
const noticeItem = (n, cls) => el('div', { class: `notice ${cls}` }, n.code !== 'warning' ? el('strong', { text: `${noticeTitle(n)}. ` }) : null, n.message);

/** Red strip at the top of the panel: the answer the user wanted is missing. */
function alertBar(errors) {
  if (!errors.length) return null;
  return el('div', { class: 'alertbar', role: 'alert' }, icon('alert'),
    el('div', {}, ...errors.map(n => el('div', { class: 'alert-item' }, el('strong', { text: noticeTitle(n) }), el('span', { text: n.message })))));
}

const infoOf = (run, code) => (run.notices ?? []).find(n => n.code === code);
function afterImageLine(run) {
  const n = infoOf(run, 'post_image_date');
  if (n?.details?.datetime_local) {
    const d = n.details, t = String(d.datetime_local).replace('T', ' ');
    return `After-image: ${t} local time${d.days_after_event != null ? ` · ${d.days_after_event} day${d.days_after_event === 1 ? '' : 's'} after the event` : ''}`;
  }
  const post = run.acquire?.s1?.post?.[0]?.datetime;
  return post ? `After-image: ${String(post).slice(0, 16).replace('T', ' ')} UTC` : null;
}

/** Small line chart of the water share before the flood (acquire.s1.pre_selection.series). */
function waterSeriesChart(sel) {
  const s = (sel?.series ?? []).filter(p => p.water_frac != null);
  if (s.length < 2) return null;
  const W = 300, H = 84, P = 14, ymax = Math.max(0.05, ...s.map(p => p.water_frac)) * 1.15;
  const t0 = Date.parse(s[0].date), t1 = Date.parse(s[s.length - 1].date) || t0 + 1;
  const X = d => P + (W - 2 * P) * ((Date.parse(d) - t0) / Math.max(t1 - t0, 1)), Y = v => H - P - (H - 2 * P) * (v / ymax);
  const ns = 'http://www.w3.org/2000/svg';
  const mk = (tag, attrs, text) => { const e = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text != null) e.textContent = text; return e; };
  const svg = mk('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-label': 'Share of water in the valley bottom before the event' });
  svg.append(mk('line', { x1: P, y1: H - P, x2: W - P, y2: H - P, class: 'ax' }));
  if (sel.onset_date) svg.append(mk('line', { x1: X(sel.onset_date), y1: P - 4, x2: X(sel.onset_date), y2: H - P, class: 'onset' }), mk('text', { x: X(sel.onset_date) + 3, y: P + 2, class: 'cl' }, 'water starts rising'));
  svg.append(mk('polyline', { points: s.map(p => `${X(p.date)},${Y(p.water_frac)}`).join(' '), class: 'ln' }));
  const chosen = new Set(sel.chosen_pre ?? []);
  for (const p of s) svg.append(mk('circle', { cx: X(p.date), cy: Y(p.water_frac), r: chosen.has(p.date) ? 4.5 : 2.5, class: chosen.has(p.date) ? 'pt chosen' : 'pt' }));
  svg.append(mk('text', { x: P, y: H - 2, class: 'cl' }, s[0].date.slice(5)), mk('text', { x: W - P, y: H - 2, class: 'cl', 'text-anchor': 'end' }, s[s.length - 1].date.slice(5)));
  return el('figure', { class: 'figure' }, svg, el('figcaption', { class: 'fine', text: 'Share of water in the valley bottom, radar passes before the event. Large dot = before-image used.' }));
}

// Why these radar images were chosen (run.json.acquire.s1), shown as plain sentences.
function selectionNotes(run) {
  const s1 = run.acquire?.s1 ?? {}, notes = [];
  if (s1.primary_reason) notes.push(`Main radar pass: ${s1.primary_reason}.`);
  const sel = s1.pre_selection;
  if (sel) {
    const dates = (sel.chosen_pre ?? []).join(' + ');
    notes.push(`Before image${dates ? ` (${dates})` : ''}: ${sel.reason ?? 'selected automatically'}${sel.user_window ? ' — your window was only checked, not changed' : ''}.`);
  }
  return notes;
}

const HINTS = [
  [/cdse|credential|client[_ ]?id|client[_ ]?secret|oauth|unauthori[sz]ed|401|403/i, 'Downloading satellite data needs a free Copernicus account key. Set it up as described in the README, then run again.'],
  [/model.*(not found|missing)|weights|\.pt\b/i, 'The trained flood model was not found on this computer. See the README for how to install it, then run again.'],
  [/no .*(scene|product|image|pair|pass)|not enough|insufficient|no data/i, 'No suitable satellite images were found for this area and date. Try another date, a larger area, or your own before/after windows under Advanced.'],
  [/ohsome|openstreetmap|\bosm\b/i, 'The map data service (OpenStreetMap through ohsome) did not answer or needs a key. See the README, wait a few minutes and run again.'],
  [/timeout|timed out|connection|network|429|502|503|rate limit|temporar/i, 'A data service did not respond or is overloaded. Wait a minute and run again.'],
  [/memory|killed|oom/i, 'The computer ran out of memory. Try a smaller area.'],
];
const hintFor = text => HINTS.find(([re]) => re.test(text ?? ''))?.[1] ?? null;

/** What is missing, in plain sentences, from the coverage numbers and scene list. */
function dataGaps(stats) {
  const sc = stats.scenes ?? {}, cov = stats.coverage ?? {}, gaps = [];
  if (!sc.s1_pre) gaps.push('No usable radar (Sentinel-1) image from before the event, taken from the same orbit as the after image.');
  if (!sc.s1_post) gaps.push('No usable radar (Sentinel-1) image from after the event.');
  if (cov.s1_valid_pct != null && cov.s1_valid_pct < 50) gaps.push(`Radar can see only ${num(cov.s1_valid_pct, 0)} % of the area (the rest is in radar shadow or has no data).`);
  if (!sc.s2_post) gaps.push('No clear optical (Sentinel-2) image after the event, so the result relies on radar only.');
  else if (cov.s2_post_clear_pct != null && cov.s2_post_clear_pct < 30) gaps.push(`The optical image after the event is mostly cloudy (${num(cov.s2_post_clear_pct, 0)} % clear).`);
  return gaps;
}

const SENS_TEXT = { standard: 'Standard sensitivity: flooded area only where the model is fairly sure.', sensitive: 'Sensitive mode: uncertain places are included too, so there are more false alarms.' };

export function createResults(root, api) {
  // api: {layers, openSettlement, onBack, exportPng, onFloodpathClear}
  function setView(...nodes) { root.replaceChildren(...nodes.filter(Boolean)); root.parentElement.scrollTop = 0; }
  const alertSlot = document.getElementById('alert-slot');
  function setAlert(node) { alertSlot.replaceChildren(...(node ? [node] : [])); }

  function renderRunning(status, { onCancel } = {}) {
    const steps = status.steps.map(s => {
      const glyph = { done: '✓', failed: '!', skipped: '–' }[s.state] ?? '';
      return el('li', { class: `step ${s.state}` }, el('span', { class: 'step-i', text: glyph }),
        el('div', { class: 'step-t' }, el('div', { text: STEP_LABEL[s.name] ?? s.name }), s.message ? el('div', { class: 'step-m', text: s.message }) : null),
        s.state === 'running' ? el('span', { class: 'spinner', 'aria-label': 'running' }) : s.state === 'skipped' ? el('span', { class: 'step-tag', text: 'skipped' }) : null);
    });
    const log = status.log_tail?.length ? el('pre', { class: 'log', text: status.log_tail.join('\n') }) : null;
    const errs = (status.notices ?? []).filter(n => n.severity === 'error');
    setAlert(alertBar(errs));
    setView(sec(status.state === 'queued' ? 'Starting…' : 'Analysis running', el('ol', { class: 'stepper' }, steps), log,
      onCancel ? el('button', { class: 'btn danger-outline block', type: 'button', onclick: onCancel, text: 'Cancel run' }) : null));
  }

  function renderError(status, { onBack } = {}) {
    const cancelled = status.state === 'cancelled';
    const failedStep = status.steps?.find(x => x.state === 'failed');
    const errs = (status.notices ?? []).filter(n => n.severity === 'error');
    const covered = errs.some(n => status.error && n.message.includes(status.error.slice(0, 40)));
    setAlert(alertBar(errs));
    setView(sec(cancelled ? 'Run cancelled' : 'Run failed',
      failedStep ? el('p', { class: 'muted', style: 'margin-bottom:8px', text: `Stopped at: ${STEP_LABEL[failedStep.name] ?? failedStep.name}` }) : null,
      el('p', { class: `notice ${cancelled ? 'warn' : 'bad'}`, text: cancelled ? 'The run was cancelled. Nothing was produced.' : (covered && errs.length ? 'See the red message above for what went wrong.' : (status.error || 'The pipeline stopped unexpectedly.')) }),
      cancelled ? null : el('p', { class: 'muted', style: 'margin-top:12px', text: hintFor([status.error, ...errs.map(n => n.message)].join(' ')) ?? 'Things to try: a smaller area, a different flood date, or your own before/after windows under Advanced. Missing satellite images are reported here instead of showing an empty map.' }),
      status.log_tail?.length ? el('details', { style: 'margin-top:12px' }, el('summary', { text: 'Log' }), el('pre', { class: 'log', text: status.log_tail.join('\n') })) : null,
      onBack ? el('button', { class: 'btn block', type: 'button', onclick: onBack, text: 'Back' }) : null));
  }

  // ---------- result overview ----------
  async function renderResult(runId, run, stats) {
    const nb = noticeBuckets(run, stats);
    setAlert(alertBar(nb.errors));
    if (!stats) { setView(sec('No results', el('p', { class: 'notice warn', text: 'This run has no statistics file (stats.json) yet.' }))); return; }
    const v = VERDICT[stats.verdict] ?? { cls: 'warn', icon: 'info', title: stats.verdict ?? 'Unknown' };
    const D = api.layers.data ?? {};
    const cov = stats.coverage ?? {}, fl = stats.flood ?? {}, ac = stats.access ?? {};
    const detected = stats.verdict === 'flood_detected', none = stats.verdict === 'no_significant_flooding', short = stats.verdict === 'insufficient_data';
    const gaps = dataGaps(stats);
    const sum = D.damageSummary ?? {}, dm = stats.damage ?? {};
    const gs = D.graphStats?.settlements_by_status ?? null;
    const settl = D.settlements?.features ?? [];
    const cnt = k => gs?.[k] ?? settl.filter(f => f.properties.status === k).length;
    const nCut = ac.cut_off ?? cnt('cut_off'), nPos = cnt('possibly_cut_off'), nDeg = ac.degraded ?? cnt('degraded'), nConn = ac.connected ?? cnt('connected');

    // ----- headline -----
    const after = afterImageLine(run);
    const head = sec(null,
      el('div', { class: `statusline ${v.cls}` }, icon(v.icon), el('span', { text: v.title }), run.mock ? el('span', { class: 'badge sample', text: 'SAMPLE DATA' }) : run.example ? el('span', { class: 'badge example', text: 'EXAMPLE', title: 'Bundled example of a real finished analysis (slimmed)' }) : null),
      ...(stats.verdict_reasons ?? []).map(t => el('p', { class: 'reason', text: t })),
      none ? el('p', { class: 'fine', text: 'Nothing significant was found in the satellite data that was available (see Data quality below). This does not prove that no flooding happened: parts of the area may be hidden from radar or covered by clouds.' }) : null,
      short ? el('p', { class: 'fine', text: 'The analysis could not be done reliably with the data that was available, so no flood map or damage numbers are shown.' }) : null,
      short && gaps.length ? el('ul', { class: 'gaps' }, ...gaps.map(g => el('li', { text: g }))) : null,
      short ? el('p', { class: 'fine', text: 'Try another date, a larger area, or your own before/after windows under Advanced.' }) : null,
      after ? el('div', { class: 'afterline' }, icon('info'), el('span', { text: after })) : null,
      nb.warnings.length ? el('button', { class: 'linklike warnlink', type: 'button', onclick: () => root.querySelector('#quality-sec')?.scrollIntoView({ behavior: 'smooth' }), text: `${nb.warnings.length} warning${nb.warnings.length === 1 ? '' : 's'} — see Data quality` }) : null,
      el('div', { class: 'run-meta' }, el('span', { text: `Flood date ${stats.event_date ?? run.event_date ?? '?'}` }), el('span', { text: `${num(stats.aoi_area_km2, 0)} km²` }),
        el('span', { text: `Sensitivity: ${run.sensitivity === 'sensitive' ? 'sensitive' : 'standard'}` }), el('span', { class: 'mono', text: runId })),
      detected ? (ac.settlements_total
        ? el('div', { class: 'hero' }, el('div', { class: 'hero-v' }, num(nCut, 0), el('small', { text: `of ${num(ac.settlements_total, 0)}` })),
            el('div', { class: 'hero-l', text: 'settlements cut off from the nearest town or hospital' }),
            el('div', { class: 'hero-s', text: [nPos ? `${num(nPos, 0)} possibly cut off` : null, `${num(nDeg, 0)} with a long detour`, `${num(nConn, 0)} still connected`].filter(Boolean).join(' · ') }))
        : el('div', { class: 'hero' }, el('div', { class: 'hero-v' }, num(fl.affected_km2, 1), el('small', { text: 'km²' })), el('div', { class: 'hero-l', text: 'flooded or covered by debris' }))) : null);

    // ----- where the flood hit -----
    const subAreas = run.debris?.areas_km2 ?? (() => {
      const a = {};
      for (const f of (D.debrisPolys?.features ?? [])) a[f.properties.subtype ?? 'unknown'] = (a[f.properties.subtype ?? 'unknown'] ?? 0) + (f.properties.area_m2 ?? 0) / 1e6;
      return a;
    })();
    const subRows = Object.entries(subAreas).filter(([, v2]) => v2 > 0).sort((a, b) => b[1] - a[1]);
    const falseAlarm = infoOf(run, 'debris_false_alarm_estimate'), notSeen = infoOf(run, 'debris_not_observable');
    const where = sec('Where the flood hit',
      rows([['Flood water', fmtArea(fl.flooded_water_km2)], ['Debris, mud & surface change', fl.debris_km2 == null ? 'not available' : fmtArea(fl.debris_km2)], ['Affected area', fmtArea(fl.affected_km2), true]]),
      subRows.length ? el('ul', { class: 'subtypes' }, ...subRows.map(([k, a]) => el('li', {}, el('i', { class: 'swatch', style: `--c:${(SUBTYPE[k] ?? SUBTYPE.unknown).color}` }), el('span', { text: (SUBTYPE[k] ?? SUBTYPE.unknown).label }), el('b', { text: fmtArea(a) })))) : null,
      falseAlarm ? el('p', { class: 'fine', text: falseAlarm.message }) : null,
      notSeen ? el('p', { class: 'fine', text: notSeen.message }) : null);

    // ----- what was damaged -----
    const noMap = 'no map data';
    const bTot = sum.buildings_total ?? dm.buildings_total;
    const bLow = sum.buildings_hit_low ?? dm.buildings_hit, bHigh = sum.buildings_hit_high ?? bLow;
    const hitFac = Object.entries(sum.facilities_hit ?? {}).filter(([, n]) => n > 0);
    const damaged = sec('What was damaged', rows([
      ['Buildings hit', bTot ? (bLow === bHigh ? `${num(bLow, 0)} of ${num(bTot, 0)}` : `${num(bLow, 0)}–${num(bHigh, 0)} of ${num(bTot, 0)}`) : noMap],
      sum.buildings_likely_destroyed ? ['…of which likely destroyed', num(sum.buildings_likely_destroyed, 0)] : null,
      ['Roads blocked', (sum.roads_total_km ?? dm.roads_total_km) ? `${num(sum.roads_blocked_km ?? dm.roads_hit_km, 1)} of ${num(sum.roads_total_km ?? dm.roads_total_km, 1)} km` : noMap],
      sum.roads_possibly_blocked_km ? ['Roads possibly blocked', `${num(sum.roads_possibly_blocked_km, 1)} km`] : null,
      ['Bridges blocked', (sum.bridges_total ?? dm.bridges_total) ? `${num(sum.bridges_blocked ?? dm.bridges_hit, 0)} of ${num(sum.bridges_total ?? dm.bridges_total, 0)}` : noMap],
      sum.bridges_suspect ? ['Bridges suspect (not confirmed)', num(sum.bridges_suspect, 0)] : null]),
      bTot && bLow !== bHigh ? el('p', { class: 'fine', text: 'The range runs from certain damage to every building that may be affected.' }) : null,
      hitFac.length ? el('p', { class: 'fine', text: `Key places hit: ${hitFac.map(([k, n]) => `${n} ${kindLabel(k).toLowerCase()}`).join(', ')}.` }) : null,
      !bTot && !(sum.roads_total_km ?? dm.roads_total_km) ? el('p', { class: 'notice warn', text: 'No buildings or roads were found in the map data (OpenStreetMap before the event) for this area, or the map service was unavailable. Damage and cut-off results are therefore incomplete.' }) : null);

    // ----- who is cut off (most urgent first) -----
    const urgent = settl.filter(f => f.properties.priority_rank != null).sort((a, b) => a.properties.priority_rank - b.properties.priority_rank);
    const legacyCut = settl.filter(f => f.properties.status === 'cut_off').sort((a, b) => (b.properties.population ?? 0) - (a.properties.population ?? 0));
    const listed = urgent.length ? urgent : legacyCut;
    const listedRows = listed.map(f => settlementRow(f, urgent.length > 0));
    const whoMore = moreButton(listedRows, 20, 'settlements');
    const who = sec('Who is cut off',
      listed.length ? el('p', { class: 'fine', style: 'margin:0 0 6px', text: urgent.length ? 'Most urgent first (cut off, or hit hard).' : 'Largest first.' }) : null,
      listed.length
        ? el('div', {}, el('ul', { class: 'plist' }, ...listedRows), whoMore)
        : el('p', { class: 'muted', text: ac.settlements_total || settl.length ? 'No settlement lost its road connection to the nearest town or hospital.' : 'The cut-off analysis could not be done: no settlements or no road network were found in the map data for this area.' }));

    // ----- what to fix first -----
    const plan = Array.isArray(D.repair) ? D.repair : [];
    const repair = plan.length ? sec('What to fix first',
      el('p', { class: 'fine', style: 'margin:0 0 6px', text: 'A step-by-step plan: each step reconnects the most buildings per repaired section.' }),
      el('ol', { class: 'repair' }, ...plan.map(p => el('li', {}, el('button', { type: 'button', onclick: () => api.layers.highlightCuts(p.osm_ids ?? [p.osm_id]) },
        el('span', { class: 'rk', text: String(p.rank) }),
        el('span', { class: 'rt' }, el('b', { text: ([...new Set((p.names ?? [p.name]).filter(Boolean))].join(', ') || (p.is_bridge ? 'Unnamed bridge' : 'Unnamed road')) + (p.n_cuts > 1 ? ` (${p.n_cuts} sections)` : '') + (p.is_bridge && p.names?.some(Boolean) ? ' · bridge' : '') }),
          el('small', { text: `Reconnects ${p.reconnects_settlements} ${plural(p.reconnects_settlements, 'settlement')}, ${p.reconnects_buildings} ${plural(p.reconnects_buildings, 'building')} (${p.cumulative_buildings} in total after this step)` }),
          el('small', { class: 'muted', text: (p.settlements ?? []).join(', ') })))))),
      el('p', { class: 'fine', text: 'Sections only open the way if everything before them in the list is repaired too; the order is by usefulness, not by distance.' })) : null;

    // ----- key places -----
    const fac = (D.facilities?.features ?? []).slice().sort((a, b) => (a.properties.hit === b.properties.hit ? 0 : a.properties.hit ? -1 : 1) || String(a.properties.name).localeCompare(String(b.properties.name)));
    const placeRows = fac.map(f => {
      const p = f.properties, a = FACILITY_ACCESS[p.access] ?? FACILITY_ACCESS.connected, g = GRADE[p.grade] ?? GRADE.none;
      return el('tr', { class: 'clickrow', tabindex: 0, onclick: () => api.layers.flyToFeature(f), onkeydown: e => { if (e.key === 'Enter') api.layers.flyToFeature(f); } },
        el('td', {}, el('div', { text: p.name ?? `Unnamed ${kindLabel(p.kind).toLowerCase()}` }), el('small', { class: 'muted', text: kindLabel(p.kind) })),
        el('td', {}, el('span', { class: `status ${a.cls}`, text: a.label })), el('td', { text: p.grade && p.grade !== 'none' ? g.label : '—' }));
    });
    const placesMore = moreButton(placeRows, 12, 'key places');
    const places = fac.length ? sec('Key places',
      el('p', { class: 'fine', style: 'margin:0 0 6px', text: 'Places hit by the flood come first. Click a row to find it on the map.' }),
      el('table', { class: 'kvt places' }, el('thead', {}, el('tr', {}, el('th', { text: 'Place' }), el('th', { text: 'Access' }), el('th', { text: 'Damage' }))), el('tbody', {}, ...placeRows)),
      placesMore) : null;

    // ----- how sure is the system (flood/confidence.json via stats.confidence) -----
    const cf = stats.confidence;
    const CONF_COL = { high: '#2ea043', medium: '#e3b341', low: '#f85149' };
    const confSec = cf && cf.overall && cf.overall !== 'unknown' ? el('section', { class: 'sec', id: 'confidence-sec' }, el('h2', { text: 'How sure is the system' }),
      el('p', { class: 'strong' }, 'Overall confidence: ', pill(cf.overall, CONF_COL[cf.overall] ?? '#8b949e')),
      ...['high', 'medium', 'low'].map(k => bar(`${k[0].toUpperCase()}${k.slice(1)} confidence`, cf.levels_pct?.[k])),
      el('p', { class: 'fine', text: `Share of the ${cf.focus === 'affected' ? 'affected' : 'evaluated'} area. Switch on the “Confidence map” layer to see where the map is unsure.` }),
      ...(cf.reasons ?? []).map(r => el('p', { class: 'fine', text: `• ${r.text}.` }))) : null;

    // ----- data quality -----
    const optical = (label, v2) => bar(label, v2, 'none');
    const quality = el('section', { class: 'sec', id: 'quality-sec' }, el('h2', { text: 'Data quality' }),
      bar('Radar (S1) valid', cov.s1_valid_pct), optical('Optical before, clear', cov.s2_pre_clear_pct), optical('Optical after, clear', cov.s2_post_clear_pct),
      el('div', { class: 'scene-list' }, ...Object.entries(stats.scenes ?? {}).map(([k, val]) => el('div', { class: 'scene' }, el('span', { class: 'muted', text: k.replace('_', ' ').toUpperCase() }), el('span', { class: 'mono', text: val ?? 'not available' })))),
      ...(!short ? gaps.map(g => el('p', { class: 'fine', text: g })) : []),
      ...nb.warnings.map(n => noticeItem(n, 'warn')));

    // ----- how this was computed (info notices + choices) -----
    const sel = run.acquire?.s1?.pre_selection;
    const chart = waterSeriesChart(sel);
    const how = (nb.infos.length || selectionNotes(run).length || chart) ? el('details', { class: 'sec how' }, el('summary', { text: 'How this was computed' }),
      el('p', { class: 'fine', text: SENS_TEXT[run.sensitivity === 'sensitive' ? 'sensitive' : 'standard'] }),
      ...selectionNotes(run).map(t => el('p', { class: 'fine', text: t })),
      chart, ...nb.infos.filter(n => !['post_image_date', 'debris_false_alarm_estimate', 'debris_not_observable'].includes(n.code)).map(n => noticeItem(n, 'info'))) : null;

    // ----- report & export -----
    const [hasPdf, hasMd] = await Promise.all([fileExists(runId, 'report/sitrep_en.pdf'), fileExists(runId, 'report/sitrep_en.md')]);
    const exportDefs = [
      ['Flood polygons (GeoJSON)', 'flood/flood_polygons.geojson'], ['Debris and surface change (GeoJSON)', 'flood/debris_polygons.geojson'], ['Buildings damage (GeoJSON)', 'damage/buildings_damage.geojson'],
      ['Roads damage (GeoJSON)', 'damage/roads_damage.geojson'], ['Bridges damage (GeoJSON)', 'damage/bridges_damage.geojson'], ['Settlements access (GeoJSON)', 'network/settlements_access.geojson'],
      ['Cut roads (GeoJSON)', 'network/road_cuts.geojson'], ['Key places (GeoJSON)', 'network/facilities_access.geojson'], ['Landing candidates, unverified (GeoJSON)', 'network/landing_zones.geojson'],
      ['Repair plan (JSON)', 'network/repair_priority.json'], ['Flood mask (GeoTIFF)', 'flood/flood_mask.tif'], ['Statistics (JSON)', 'stats.json'],
    ];
    const present = (await Promise.all(exportDefs.map(async ([l, p]) => (await fileExists(runId, p)) ? [l, p] : null))).filter(Boolean);
    const sitrep = hasPdf ? 'report/sitrep_en.pdf' : hasMd ? 'report/sitrep_en.md' : null;
    const actions = sec('Report & export',
      sitrep ? el('div', {}, el('a', { class: 'btn primary block', style: 'margin-top:0', href: fileUrl(runId, sitrep, true) }, icon('download'), `Situation report (${sitrep.endsWith('pdf') ? 'PDF' : 'Markdown'})`),
               el('a', { class: 'more', href: fileUrl(runId, sitrep), target: '_blank', rel: 'noopener', text: 'Open in a new tab' }))
             : el('button', { class: 'btn block', style: 'margin-top:0', type: 'button', disabled: true, title: 'No situation report was produced for this run' }, icon('download'), 'Situation report — not available'),
      el('details', { class: 'export' }, el('summary', { text: 'Export data' }),
        el('ul', { class: 'plist flat' }, ...present.map(([l, p]) => el('li', {}, el('a', { href: fileUrl(runId, p, true), text: l }))),
          el('li', {}, el('button', { type: 'button', class: 'linklike', onclick: api.exportPng, text: 'Map view (PNG)' })))));

    const fp = el('div', { id: 'fp-slot' });
    setView(...(detected ? [head, where, confSec, damaged, who, repair, places, fp, quality, how, actions] : none ? [head, confSec, quality, where, how, actions] : [head, quality, how, actions]));
    if (D.floodpath) renderFloodpath({ path: D.floodpath, settlements: D.floodpathSettlements, along: D.floodpathAlong, restored: true });
  }

  // ---------- settlement row + detail ----------
  function settlementRow(f, withRank) {
    const p = f.properties, imp = IMPACT[p.impact_level], acc = ACCESS[p.status] ?? { label: p.status, cls: 'muted' };
    return el('li', {}, el('button', { type: 'button', onclick: () => api.openSettlement(p.osm_id) },
      withRank && p.priority_rank ? el('span', { class: 'rk', text: String(p.priority_rank) }) : null,
      el('span', { class: 'pl-main' }, el('span', { class: 'pl-n', text: p.name ?? `Unnamed ${p.place ?? 'place'}` }),
        el('small', { class: 'muted', text: [acc.label, p.population ? `~${num(p.population, 0)} people` : null, p.buildings_hit != null ? `${p.buildings_hit} ${plural(p.buildings_hit, 'building')} hit` : null].filter(Boolean).join(' · ') })),
      imp && p.impact_level !== 'none' && p.impact_level !== 'low' ? pill(imp.label, imp.color) : null));
  }

  function renderSettlement(f) {
    const p = f.properties, D = api.layers.data ?? {};
    const acc = ACCESS[p.status] ?? { label: p.status, cls: 'muted', icon: 'info' };
    const imp = IMPACT[p.impact_level];
    const cuts = (D.cuts?.features ?? []).filter(c => (p.blocking_cuts ?? []).includes(c.properties.osm_id));
    const cutOff = p.status === 'cut_off';
    const row = (k, a, b) => el('tr', {}, el('th', { text: k }), el('td', { text: a }), el('td', { text: b }));
    const lz = (D.landing?.features ?? []).filter(l => l.properties.settlement_id === p.osm_id);
    const hasBlds = p.buildings_total != null;
    setView(
      el('button', { class: 'back', type: 'button', onclick: api.onBack }, icon('back'), 'Back to overview'),
      sec(null, el('h3', { class: 'sd-name', text: p.name ?? 'Unnamed place' }),
        el('div', { class: 'sd-meta' }, el('span', { class: `status ${acc.cls}` }, icon(acc.icon), acc.label), imp && p.impact_level !== 'none' ? pill(`${imp.label} impact`, imp.color) : null,
          el('span', { class: 'muted', text: [p.place, p.population ? `~${num(p.population, 0)} people` : null].filter(Boolean).join(' · ') })),
        p.priority_rank ? el('p', { class: 'fine', text: `Urgency rank ${p.priority_rank} among the affected settlements.` }) : null,
        (p.impact_reasons ?? []).length ? el('ul', { class: 'gaps' }, ...p.impact_reasons.map(r => el('li', { text: r }))) : null),
      hasBlds ? sec('Buildings and surroundings', rows([
        ['Buildings hit', `${num(p.buildings_hit, 0)} of ${num(p.buildings_total, 0)}${p.buildings_hit_pct != null ? ` (${num(p.buildings_hit_pct, 0)} %)` : ''}`],
        p.buildings_likely_destroyed ? ['…likely destroyed', num(p.buildings_likely_destroyed, 0)] : null,
        p.flooded_area_pct != null ? ['Settlement area flooded', `${num(p.flooded_area_pct, 0)} %`] : null,
        p.roads_total != null ? ['Roads blocked in the area', `${num(p.roads_hit ?? 0, 0)} of ${num(p.roads_total, 0)}`] : null,
        (p.facilities_hit ?? []).length ? ['Important places hit', p.facilities_hit.map(kindLabel).join(', ')] : null])) : null,
      sec('Route to the nearest town or hospital',
        el('table', { class: 'kvt' }, el('thead', {}, el('tr', {}, el('th'), el('th', { text: 'Before' }), el('th', { text: 'After' }))),
          el('tbody', {},
            row('Destination', p.nearest_dest_pre ?? 'n/a', cutOff ? 'unreachable' : (p.nearest_dest_post ?? 'n/a')),
            row('Distance', km(p.dist_pre_m), cutOff ? '—' : km(p.dist_post_m)),
            row('Driving time', minutes(p.time_pre_s), cutOff ? '—' : minutes(p.time_post_s)),
            p.walk_time_pre_s != null ? row('Walking time', minutes(p.walk_time_pre_s), cutOff ? '—' : minutes(p.walk_time_post_s)) : null,
            row('Detour', '', p.detour_pct != null ? `+${num(p.detour_pct, 0)} %` : p.detour_factor ? `×${num(p.detour_factor, 1)}` : '—'),
            p.routes_pre != null ? row('Independent routes', num(p.routes_pre, 0), num(p.routes_post ?? 0, 0)) : null)),
        p.status === 'possibly_cut_off' ? el('p', { class: 'fine', text: 'There is still a route, but only through road or bridge sections that may be blocked. Treat the settlement as possibly cut off.' }) : null),
      sec(`Blocking sections (${cuts.length})`,
        cuts.length ? el('ul', { class: 'plist flat' }, ...cuts.map(c => el('li', { text: `${c.properties.is_bridge ? 'Bridge' : 'Road'}${c.properties.name ? ` “${c.properties.name}”` : ''} · ${km(c.properties.length_m)}${c.properties.repair_rank ? ` · repair step ${c.properties.repair_rank}` : ''}` })))
                    : el('p', { class: 'muted', text: 'No blocking sections on the original route.' }),
        cuts.length ? el('button', { class: 'btn block', type: 'button', onclick: () => api.layers.highlightCuts(cuts.map(c => c.properties.osm_id)), text: 'Show blocking sections on map' }) : null),
      lz.length ? sec('Helicopter landing candidates', el('p', { class: 'notice warn', text: 'UNVERIFIED. Found automatically from terrain slope and the map; nobody has checked them on the ground (obstacles, wires, ground, crowds).' }),
        el('ul', { class: 'plist' }, ...lz.map(l => el('li', {}, el('button', { type: 'button', onclick: () => { api.layers.setLayerOn('landing', true); api.layers.flyToFeature(l); } },
          el('span', { class: 'pl-main' }, el('span', { class: 'pl-n', text: LANDING[l.properties.class] ?? l.properties.class }), el('small', { class: 'muted', text: [l.properties.dist_m != null ? `${num(l.properties.dist_m, 0)} m from the settlement` : null, l.properties.mean_slope_deg != null ? `slope ${num(l.properties.mean_slope_deg, 0)}°` : null, l.properties.area_m2 ? `${num(l.properties.area_m2, 0)} m²` : null].filter(Boolean).join(' · ') })),
          badge('unverified', 'warn')))))) : null);
  }

  // ---------- flood path ----------
  function renderFloodpath(res) {
    const slot = root.querySelector('#fp-slot') ?? (() => { const s = el('div', { id: 'fp-slot' }); root.insertBefore(s, root.querySelector('#quality-sec') ?? null); return s; })();
    if (!res) { slot.replaceChildren(); return; }
    const line = (res.path?.features ?? []).find(f => f.properties.kind === 'path')?.properties ?? {};
    const sett = (res.settlements?.features ?? []);
    const along = res.along ?? {};
    const items = [
      ...sett.map(f => ({ d: f.properties.dist_along_km, kind: 'settlement', f })),
      ...(along.bridges ?? []).map(b => ({ d: b.dist_along_km, kind: 'bridge', b })),
      ...(along.places ?? []).map(b => ({ d: b.dist_along_km, kind: 'place', b })),
    ].sort((a, b) => a.d - b.d);
    slot.replaceChildren(sec('Flood path from the chosen point',
      res.mock ? el('p', { class: 'fine', text: 'SAMPLE DATA: the same example path is shown for any point.' }) : res.example ? el('p', { class: 'fine', text: 'Bundled example: this path was traced in advance from one point and is shown for any click. In your own runs it starts where you click.' }) : null,
      el('p', { class: 'fine', style: 'margin-top:0', text: `${num(line.length_km, 1)} km downstream · ${sett.length} settlement${sett.length === 1 ? '' : 's'} nearby · ordered by distance from the start (no travel times: there is no water-flow model).` }),
      items.length ? el('ol', { class: 'fp-list' }, ...items.map(it => {
        if (it.kind === 'settlement') {
          const p = it.f.properties, acc = ACCESS[p.status], imp = IMPACT[p.impact_level];
          return el('li', {}, el('button', { type: 'button', onclick: () => api.openSettlement(p.osm_id) }, el('span', { class: 'km', text: `${num(it.d, 1)} km` }),
            el('span', { class: 'pl-main' }, el('span', { class: 'pl-n', text: p.name ?? 'Unnamed' }),
              el('small', { class: 'muted', text: [p.height_above_path_m != null ? `${num(p.height_above_path_m, 0)} m above the river${p.in_corridor ? ' (in the corridor)' : ''}` : null, acc?.label].filter(Boolean).join(' · ') })),
            imp && !['none', 'low'].includes(p.impact_level) ? pill(imp.label, imp.color) : null));
        }
        const b = it.b;
        return el('li', {}, el('button', { type: 'button', onclick: () => api.layers.flyToPoint(b.lon, b.lat) }, el('span', { class: 'km', text: `${num(it.d, 1)} km` }),
          el('span', { class: 'pl-main' }, el('span', { class: 'pl-n', text: b.name ?? kindLabel(b.kind) }), el('small', { class: 'muted', text: kindLabel(b.kind) }))));
      })) : el('p', { class: 'muted', text: 'No settlements, bridges or key places were found along this path.' }),
      el('button', { class: 'btn block', type: 'button', onclick: () => { api.onFloodpathClear?.(); slot.replaceChildren(); }, text: 'Clear flood path' })));
    if (!res.restored) slot.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ---------- popups on the map ----------
  function featureInfo(layer, p) {
    const line = (k, v, cls) => (v == null || v === '' ? null : el('div', {}, el('span', { class: 'muted', text: `${k}: ` }), cls ? el('span', { class: cls, text: String(v) }) : String(v)));
    const base = layer === 'buildings-pt' ? 'buildings' : layer;
    let items;
    if (base === 'debris') {
      const st = SUBTYPE[p.subtype] ?? SUBTYPE.unknown;
      items = [line('Type', st.label), line('Confidence', CONF_LABEL[p.confidence] ?? p.confidence), line('Area', fmtArea((p.area_m2 ?? 0) / 1e6)), p.evidence ? el('p', { class: 'evidence', text: p.evidence }) : null];
    } else if (base === 'buildings') {
      items = [line('Building', (GRADE[p.grade] ?? {}).label ?? (p.hit ? 'Hit' : 'Not hit')), line('Flood type', p.hit_class), line('Confidence', p.confidence)];
    } else if (base === 'roads') {
      items = [line('Road', p.name), line('Status', (ROAD_STATUS[p.status] ?? {}).label ?? (p.hit ? 'Blocked' : 'Passable')), line('Length', p.length_m ? km(p.length_m) : null), line('In the flooded zone', p.hit_length_m ? km(p.hit_length_m) : null), line('Longest flooded stretch', p.max_run_m ? `${Math.round(p.max_run_m)} m` : null)];
    } else if (base === 'cuts') {
      items = [line(p.is_bridge ? 'Bridge' : 'Road', p.name), line('Status', (ROAD_STATUS[p.status] ?? {}).label ?? 'Cut'), line('Length', km(p.length_m)), line('Settlements cut', p.n_settlements_cut), line('Buildings cut off', p.n_buildings_cut), line('Repair step', p.repair_rank)];
    } else if (base === 'bridges') {
      items = [line('Bridge', p.name), line('Status', (ROAD_STATUS[p.status] ?? {}).label ?? (p.hit ? 'Hit' : 'Passable')), line('Confidence', p.confidence), p.status === 'suspect' ? el('p', { class: 'evidence', text: 'Suspect: debris or new water near the bridge, approaches still passable. Not confirmed damaged.' }) : null];
    } else if (base === 'facilities') {
      const a = FACILITY_ACCESS[p.access];
      items = [line('Place', p.name), line('Type', kindLabel(p.kind)), line('Damage', (GRADE[p.grade] ?? {}).label), line('Access', a?.label)];
    } else if (base === 'landing') {
      items = [el('p', { class: 'warnline', text: 'UNVERIFIED candidate' }), line('Kind', LANDING[p.class] ?? p.class), line('Near', p.settlement_name), line('Distance', p.dist_m != null ? `${Math.round(p.dist_m)} m` : null), line('Slope', p.mean_slope_deg != null ? `${num(p.mean_slope_deg, 0)}°` : null), line('Area', p.area_m2 ? `${num(p.area_m2, 0)} m²` : null), el('p', { class: 'evidence', text: 'Found from terrain slope and the map only. Not checked on the ground.' })];
    } else if (base === 'areas') {
      items = [line('Settlement', p.name), line('Impact', (IMPACT[p.impact_level] ?? {}).label), line('Buildings hit', `${p.buildings_affected ?? 0} affected, ${p.buildings_likely_destroyed ?? 0} likely destroyed of ${p.buildings_total ?? '?'}`), line('Area flooded', p.flooded_area_pct != null ? `${num(p.flooded_area_pct, 0)} %` : null)];
    } else {
      items = [line('Type', p.kind ?? layer), line('Name', p.name)];
    }
    return el('div', { class: 'popup-info' }, ...items.filter(Boolean));
  }

  return { setView, setAlert, renderRunning, renderError, renderResult, renderSettlement, renderFloodpath, featureInfo };
}
