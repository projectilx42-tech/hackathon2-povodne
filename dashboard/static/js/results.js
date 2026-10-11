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
      cancelled ? null : el('p', { class: 'muted', style: 'margin-top:12px', text: 'Things to try: a smaller area, a different flood date, or custom before/after windows under Advanced. Missing satellite scenes (for example no radar pair from the same orbit) are reported here instead of an empty map.' }),
      status.log_tail?.length ? el('details', { style: 'margin-top:12px' }, el('summary', { text: 'Log' }), el('pre', { class: 'log', text: status.log_tail.join('\n') })) : null,
      onBack ? el('button', { class: 'btn block', type: 'button', onclick: onBack, text: 'Back' }) : null));
  }

  async function renderResult(runId, run, stats) {
    if (!stats) { setView(sec('No results', el('p', { class: 'notice warn', text: 'This run has no statistics file (stats.json) yet.' }))); return; }
    const v = VERDICT[stats.verdict] ?? { cls: 'warn', icon: 'info', title: stats.verdict ?? 'Unknown' };
    const cov = stats.coverage ?? {}, fl = stats.flood ?? {}, dm = stats.damage ?? {}, ac = stats.access ?? {};

    // headline: status + the one number rescuers need first
    const head = sec(null,
      el('div', { class: `statusline ${v.cls}` }, icon(v.icon), el('span', { text: v.title }), run.mock ? el('span', { class: 'badge sample', text: 'SAMPLE DATA' }) : null),
      ...(stats.verdict_reasons ?? []).map(t => el('p', { class: 'reason', text: t })),
      el('div', { class: 'run-meta' }, el('span', { text: `Flood date ${stats.event_date ?? run.event_date ?? '?'}` }), el('span', { text: `${num(stats.aoi_area_km2, 0)} km²` }), el('span', { text: `Sensitivity: ${run.sensitivity === 'sensitive' ? 'sensitive' : 'standard'}` }), el('span', { class: 'mono', text: runId })),
      stats.verdict === 'flood_detected' ? (ac.settlements_total
        ? el('div', { class: 'hero' }, el('div', { class: 'hero-v' }, num(ac.cut_off, 0), el('small', { text: `of ${num(ac.settlements_total, 0)}` })),
            el('div', { class: 'hero-l', text: 'settlements cut off from the nearest town or hospital' }),
            el('div', { class: 'hero-s', text: `${num(ac.degraded, 0)} with a long detour · ${num(ac.connected, 0)} still connected` }))
        : el('div', { class: 'hero' }, el('div', { class: 'hero-v' }, num(fl.affected_km2, 1), el('small', { text: 'km²' })), el('div', { class: 'hero-l', text: 'flooded or covered by debris' }))) : null);

    const where = sec('Where the flood hit', rows([
      ['Flood water', `${num(fl.flooded_water_km2, 2)} km²`], ['Debris / mud', fl.debris_km2 == null ? 'n/a' : `${num(fl.debris_km2, 2)} km²`], ['Affected area', `${num(fl.affected_km2, 2)} km²`, true]]));
    const damaged = sec('What was damaged', rows([
      ['Buildings hit', `${num(dm.buildings_hit, 0)} of ${num(dm.buildings_total, 0)}`], ['Roads hit', `${num(dm.roads_hit_km, 1)} of ${num(dm.roads_total_km, 1)} km`], ['Bridges hit', `${num(dm.bridges_hit, 0)} of ${num(dm.bridges_total, 0)}`]]));

    const features = api.layers.data?.settlements?.features ?? [];
    const cut = features.filter(f => f.properties.status === 'cut_off').sort((a, b) => (b.properties.population ?? 0) - (a.properties.population ?? 0));
    const who = sec(`Who is cut off`, cut.length
      ? el('ul', { class: 'plist' }, ...cut.map(f => el('li', {}, el('button', { type: 'button', onclick: () => api.openSettlement(f.properties.osm_id) },
          el('span', { text: f.properties.name ?? `Unnamed ${f.properties.place ?? 'place'}` }),
          el('span', { class: 'pl-s muted', text: [f.properties.place, f.properties.population ? `~${num(f.properties.population, 0)} people` : null].filter(Boolean).join(' · ') })))))
      : el('p', { class: 'muted', text: 'No settlement lost its road connection to the nearest town or hospital.' }));

    const quality = sec('Data quality',
      bar('Radar (S1) valid', cov.s1_valid_pct), bar('Optical before, clear', cov.s2_pre_clear_pct), bar('Optical after, clear', cov.s2_post_clear_pct),
      el('div', { class: 'scene-list' }, ...Object.entries(stats.scenes ?? {}).map(([k, val]) => el('div', { class: 'scene' }, el('span', { class: 'muted', text: k.replace('_', ' ').toUpperCase() }), el('span', { class: 'mono', text: val ?? 'not available' })))),
      ...selectionNotes(run).map(t => el('p', { class: 'fine', text: t })),
      ...(stats.warnings ?? run.warnings ?? []).map(w => el('p', { class: 'notice warn', text: w })));

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

    setView(head, where, damaged, who, quality, actions);
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
