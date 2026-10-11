// Right-panel views: verdict + numbers + cut-off list, settlement detail, running stepper, error.
import { el, num, pct, km, minutes, icon } from './util.js';
import { fileUrl, fileExists } from './api.js';

const VERDICT = {
  flood_detected: { cls: 'bad', icon: 'alert', title: 'Flood detected' },
  no_significant_flooding: { cls: 'good', icon: 'check', title: 'No significant flooding detected' },
  insufficient_data: { cls: 'warn', icon: 'info', title: 'Insufficient data' },
};
const STATUS = { connected: ['ok', 'check', 'Connected'], degraded: ['warn', 'alert', 'Degraded (long detour)'], cut_off: ['bad', 'alert', 'Cut off'], no_road_pre_event: ['muted', 'info', 'No road before the event'] };
const STEP_LABEL = { acquire: 'Acquire satellite data', preprocess: 'Preprocess & align', flood_ai: 'Flood detection (AI)', debris: 'Debris / mud', damage: 'Damage overlay', network: 'Cut-off analysis', report: 'Statistics & report' };

const sec = (title, ...kids) => el('section', { class: 'sec' }, title ? el('h2', { text: title }) : null, ...kids);
const rows = list => el('dl', { class: 'rows' }, ...list.map(([k, v, strong]) => el('div', { class: 'row' }, el('dt', { text: k }), el('dd', { class: strong ? 'strong' : '', text: v }))));
const bar = (label, v) => el('div', { class: 'bar-row' }, el('span', { class: 'bar-l', text: label }),
  el('span', { class: 'bar' }, el('i', { style: `width:${v == null ? 0 : Math.max(0, Math.min(100, v))}%` })), el('span', { class: 'bar-v', text: pct(v) }));

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
  [/ohsome|openstreetmap|\bosm\b/i, 'The map data service (OpenStreetMap through ohsome) did not answer. Wait a few minutes and run again.'],
  [/timeout|timed out|connection|network|429|502|503|rate limit|temporar/i, 'A data service did not respond or is overloaded. Wait a minute and run again.'],
  [/memory|killed|oom/i, 'The computer ran out of memory. Try a smaller area.'],
];
const hintFor = text => HINTS.find(([re]) => re.test(text ?? ''))?.[1] ?? null;

/** Warnings from every place a step may write them, as plain strings without duplicates. */
function allWarnings(run, stats) {
  const raw = [...(stats?.warnings ?? []), ...(run.warnings ?? []), ...(run.acquire?.warnings ?? [])];
  return [...new Set(raw.map(w => (typeof w === 'string' ? w : (w?.message ?? JSON.stringify(w)))))];
}

/** What is missing, in plain sentences, from the coverage numbers and scene list (insufficient data / no flood context). */
function dataGaps(stats) {
  const sc = stats.scenes ?? {}, cov = stats.coverage ?? {}, gaps = [];
  if (!sc.s1_pre) gaps.push('No usable radar (Sentinel-1) image from before the event, taken from the same orbit as the after image.');
  if (!sc.s1_post) gaps.push('No usable radar (Sentinel-1) image from after the event.');
  if (cov.s1_valid_pct != null && cov.s1_valid_pct < 50) gaps.push(`Radar can see only ${num(cov.s1_valid_pct, 0)} % of the area (the rest is in radar shadow or has no data).`);
  if (!sc.s2_post) gaps.push('No clear optical (Sentinel-2) image after the event, so the result relies on radar only.');
  else if (cov.s2_post_clear_pct != null && cov.s2_post_clear_pct < 30) gaps.push(`The optical image after the event is mostly cloudy (${num(cov.s2_post_clear_pct, 0)} % clear).`);
  return gaps;
}

export function createResults(root, api) {
  // api: {layers, openSettlement, onBack, exportPng}
  function setView(...nodes) { root.replaceChildren(...nodes); root.parentElement.scrollTop = 0; }

  function renderRunning(status, { onCancel } = {}) {
    const steps = status.steps.map(s => {
      const glyph = { done: '✓', failed: '!', skipped: '–' }[s.state] ?? '';
      return el('li', { class: `step ${s.state}` }, el('span', { class: 'step-i', text: glyph }),
        el('div', { class: 'step-t' }, el('div', { text: STEP_LABEL[s.name] ?? s.name }), s.message ? el('div', { class: 'step-m', text: s.message }) : null),
        s.state === 'running' ? el('span', { class: 'spinner', 'aria-label': 'running' }) : s.state === 'skipped' ? el('span', { class: 'step-tag', text: 'skipped' }) : null);
    });
    const log = status.log_tail?.length ? el('pre', { class: 'log', text: status.log_tail.join('\n') }) : null;
    setView(sec(status.state === 'queued' ? 'Starting…' : 'Analysis running', el('ol', { class: 'stepper' }, steps), log,
      onCancel ? el('button', { class: 'btn danger-outline block', type: 'button', onclick: onCancel, text: 'Cancel run' }) : null));
  }

  function renderError(status, { onBack } = {}) {
    const cancelled = status.state === 'cancelled';
    const failedStep = status.steps?.find(x => x.state === 'failed');
    setView(sec(cancelled ? 'Run cancelled' : 'Run failed',
      failedStep ? el('p', { class: 'muted', style: 'margin-bottom:8px', text: `Stopped at: ${STEP_LABEL[failedStep.name] ?? failedStep.name}` }) : null,
      el('p', { class: `notice ${cancelled ? 'warn' : 'bad'}`, text: cancelled ? 'The run was cancelled. Nothing was produced.' : (status.error || 'The pipeline stopped unexpectedly.') }),
      cancelled ? null : el('p', { class: 'muted', style: 'margin-top:12px', text: hintFor(status.error) ?? 'Things to try: a smaller area, a different flood date, or your own before/after windows under Advanced. Missing satellite images are reported here instead of showing an empty map.' }),
      status.log_tail?.length ? el('details', { style: 'margin-top:12px' }, el('summary', { text: 'Log' }), el('pre', { class: 'log', text: status.log_tail.join('\n') })) : null,
      onBack ? el('button', { class: 'btn block', type: 'button', onclick: onBack, text: 'Back' }) : null));
  }

  async function renderResult(runId, run, stats) {
    if (!stats) { setView(sec('No results', el('p', { class: 'notice warn', text: 'This run has no statistics file (stats.json) yet.' }))); return; }
    const v = VERDICT[stats.verdict] ?? { cls: 'warn', icon: 'info', title: stats.verdict ?? 'Unknown' };
    const cov = stats.coverage ?? {}, fl = stats.flood ?? {}, dm = stats.damage ?? {}, ac = stats.access ?? {};
    const detected = stats.verdict === 'flood_detected', none = stats.verdict === 'no_significant_flooding', short = stats.verdict === 'insufficient_data';
    const gaps = dataGaps(stats);

    // headline: status + the one number rescuers need first
    const head = sec(null,
      el('div', { class: `statusline ${v.cls}` }, icon(v.icon), el('span', { text: v.title }), run.mock ? el('span', { class: 'badge sample', text: 'SAMPLE DATA' }) : null),
      ...(stats.verdict_reasons ?? []).map(t => el('p', { class: 'reason', text: t })),
      none ? el('p', { class: 'fine', text: 'Nothing significant was found in the satellite data that was available (see Data quality below). This does not prove that no flooding happened: parts of the area may be hidden from radar or covered by clouds.' }) : null,
      short ? el('p', { class: 'fine', text: 'The analysis could not be done reliably with the data that was available, so no flood map or damage numbers are shown.' }) : null,
      short && gaps.length ? el('ul', { class: 'gaps' }, ...gaps.map(g => el('li', { text: g }))) : null,
      short ? el('p', { class: 'fine', text: 'Try another date, a larger area, or your own before/after windows under Advanced.' }) : null,
      el('div', { class: 'run-meta' }, el('span', { text: `Flood date ${stats.event_date ?? run.event_date ?? '?'}` }), el('span', { text: `${num(stats.aoi_area_km2, 0)} km²` }),
        el('span', { text: `Sensitivity: ${run.sensitivity === 'sensitive' ? 'sensitive' : 'standard'}` }), el('span', { class: 'mono', text: runId })),
      detected ? (ac.settlements_total
        ? el('div', { class: 'hero' }, el('div', { class: 'hero-v' }, num(ac.cut_off, 0), el('small', { text: `of ${num(ac.settlements_total, 0)}` })),
            el('div', { class: 'hero-l', text: 'settlements cut off from the nearest town or hospital' }),
            el('div', { class: 'hero-s', text: `${num(ac.degraded, 0)} with a long detour · ${num(ac.connected, 0)} still connected` }))
        : el('div', { class: 'hero' }, el('div', { class: 'hero-v' }, num(fl.affected_km2, 1), el('small', { text: 'km²' })), el('div', { class: 'hero-l', text: 'flooded or covered by debris' }))) : null);

    const where = sec('Where the flood hit', rows([
      ['Flood water', `${num(fl.flooded_water_km2, 2)} km²`], ['Debris / mud', fl.debris_km2 == null ? 'not available' : `${num(fl.debris_km2, 2)} km²`], ['Affected area', `${num(fl.affected_km2, 2)} km²`, true]]));
    const noMap = 'no map data for this area';
    const damaged = sec('What was damaged', rows([
      ['Buildings hit', dm.buildings_total ? `${num(dm.buildings_hit, 0)} of ${num(dm.buildings_total, 0)}` : noMap],
      ['Roads hit', dm.roads_total_km ? `${num(dm.roads_hit_km, 1)} of ${num(dm.roads_total_km, 1)} km` : noMap],
      ['Bridges hit', dm.bridges_total ? `${num(dm.bridges_hit, 0)} of ${num(dm.bridges_total, 0)}` : noMap]]),
      !dm.buildings_total && !dm.roads_total_km ? el('p', { class: 'notice warn', text: 'No buildings or roads were found in the map data (OpenStreetMap before the event) for this area, or the map service was unavailable. Damage and cut-off results are therefore incomplete.' }) : null);

    const features = api.layers.data?.settlements?.features ?? [];
    const cut = features.filter(f => f.properties.status === 'cut_off').sort((a, b) => (b.properties.population ?? 0) - (a.properties.population ?? 0));
    const who = sec(`Who is cut off`, cut.length
      ? el('ul', { class: 'plist' }, ...cut.map(f => el('li', {}, el('button', { type: 'button', onclick: () => api.openSettlement(f.properties.osm_id) },
          el('span', { text: f.properties.name ?? `Unnamed ${f.properties.place ?? 'place'}` }),
          el('span', { class: 'pl-s muted', text: [f.properties.place, f.properties.population ? `~${num(f.properties.population, 0)} people` : null].filter(Boolean).join(' · ') })))))
      : el('p', { class: 'muted', text: ac.settlements_total
          ? 'No settlement lost its road connection to the nearest town or hospital.'
          : 'The cut-off analysis could not be done: no settlements or no road network were found in the map data for this area.' }));

    const optical = (label, v2, missing) => v2 == null ? el('div', { class: 'bar-row' }, el('span', { class: 'bar-l', text: label }), el('span', { class: 'bar' }), el('span', { class: 'bar-v', text: missing })) : bar(label, v2);
    const quality = sec('Data quality',
      bar('Radar (S1) valid', cov.s1_valid_pct), optical('Optical before, clear', cov.s2_pre_clear_pct, 'none'), optical('Optical after, clear', cov.s2_post_clear_pct, 'none'),
      el('div', { class: 'scene-list' }, ...Object.entries(stats.scenes ?? {}).map(([k, val]) => el('div', { class: 'scene' }, el('span', { class: 'muted', text: k.replace('_', ' ').toUpperCase() }), el('span', { class: 'mono', text: val ?? 'not available' })))),
      ...(!short ? gaps.map(g => el('p', { class: 'fine', text: g })) : []),
      ...selectionNotes(run).map(t => el('p', { class: 'fine', text: t })),
      ...allWarnings(run, stats).map(w => el('p', { class: 'notice warn', text: w })));

    const [hasPdf, hasMd] = await Promise.all([fileExists(runId, 'report/sitrep_en.pdf'), fileExists(runId, 'report/sitrep_en.md')]);
    const exportDefs = [
      ['Flood polygons (GeoJSON)', 'flood/flood_polygons.geojson'], ['Buildings damage (GeoJSON)', 'damage/buildings_damage.geojson'], ['Roads damage (GeoJSON)', 'damage/roads_damage.geojson'],
      ['Bridges damage (GeoJSON)', 'damage/bridges_damage.geojson'], ['Settlements access (GeoJSON)', 'network/settlements_access.geojson'], ['Cut roads (GeoJSON)', 'network/road_cuts.geojson'],
      ['Flood mask (GeoTIFF)', 'flood/flood_mask.tif'], ['Statistics (JSON)', 'stats.json'],
    ];
    const present = (await Promise.all(exportDefs.map(async ([l, p]) => (await fileExists(runId, p)) ? [l, p] : null))).filter(Boolean);
    const sitrep = hasPdf ? 'report/sitrep_en.pdf' : hasMd ? 'report/sitrep_en.md' : null;
    const actions = sec('Report & export',
      sitrep ? el('a', { class: 'btn primary block', style: 'margin-top:0', href: fileUrl(runId, sitrep, true) }, icon('download'), `Situation report (${sitrep.endsWith('pdf') ? 'PDF' : 'Markdown'})`)
             : el('button', { class: 'btn block', style: 'margin-top:0', type: 'button', disabled: true, title: 'The situation report is generated by the report module (not available yet)' }, icon('download'), 'Situation report — not available yet'),
      el('details', { class: 'export' }, el('summary', { text: 'Export data' }),
        el('ul', { class: 'plist flat' }, ...present.map(([l, p]) => el('li', {}, el('a', { href: fileUrl(runId, p, true), text: l }))),
          el('li', {}, el('button', { type: 'button', class: 'linklike', onclick: api.exportPng, text: 'Map view (PNG)' })))));

    setView(...(detected ? [head, where, damaged, who, quality, actions] : none ? [head, quality, where, actions] : [head, quality, actions]));
  }

  function renderSettlement(f) {
    const p = f.properties;
    const [cls, ic, label] = STATUS[p.status] ?? ['muted', 'info', p.status];
    const cuts = (api.layers.data?.cuts?.features ?? []).filter(c => (p.blocking_cuts ?? []).includes(c.properties.osm_id));
    const cutOff = p.status === 'cut_off';
    const row = (k, a, b) => el('tr', {}, el('th', { text: k }), el('td', { text: a }), el('td', { text: b }));
    setView(
      el('button', { class: 'back', type: 'button', onclick: api.onBack }, icon('back'), 'Back to overview'),
      sec(null, el('h3', { class: 'sd-name', text: p.name ?? 'Unnamed place' }),
        el('div', { class: 'sd-meta' }, el('span', { class: `status ${cls}` }, icon(ic), label), el('span', { class: 'muted', text: [p.place, p.population ? `~${num(p.population, 0)} people` : null].filter(Boolean).join(' · ') }))),
      sec('Route to the nearest town or hospital',
        el('table', { class: 'kvt' }, el('thead', {}, el('tr', {}, el('th'), el('th', { text: 'Before' }), el('th', { text: 'After' }))),
          el('tbody', {},
            row('Destination', p.nearest_dest_pre ?? 'n/a', cutOff ? 'unreachable' : (p.nearest_dest_post ?? 'n/a')),
            row('Distance', km(p.dist_pre_m), cutOff ? '—' : km(p.dist_post_m)),
            row('Travel time', minutes(p.time_pre_s), cutOff ? '—' : minutes(p.time_post_s)),
            row('Detour', '', p.detour_factor ? `×${num(p.detour_factor, 1)}` : '—')))),
      sec(`Blocking sections (${cuts.length})`,
        cuts.length ? el('ul', { class: 'plist flat' }, ...cuts.map(c => el('li', { text: `${c.properties.is_bridge ? 'Bridge' : 'Road'}${c.properties.name ? ` “${c.properties.name}”` : ''} · ${km(c.properties.length_m)}` })))
                    : el('p', { class: 'muted', text: 'No blocking sections on the original route.' }),
        cuts.length ? el('button', { class: 'btn block', type: 'button', onclick: () => api.layers.highlightCuts(cuts.map(c => c.properties.osm_id)), text: 'Show blocking sections on map' }) : null));
  }

  function featureInfo(layer, p) {
    const rows = [['Type', p.kind ?? layer], ['Name', p.name], ['Hit', p.hit == null ? null : p.hit ? 'yes' : 'no'], ['Hit class', p.hit_class], ['Hit fraction', p.hit_fraction == null ? null : pct(p.hit_fraction * 100)],
      ['Confidence', p.confidence], ['Length', p.length_m ? km(p.length_m) : null], ['Settlements cut', p.n_settlements_cut]].filter(([, v]) => v != null && v !== '');
    return el('div', { class: 'popup-info' }, ...rows.map(([k, v]) => el('div', {}, el('span', { class: 'muted', text: `${k}: ` }), String(v))));
  }

  return { setView, renderRunning, renderError, renderResult, renderSettlement, featureInfo };
}
