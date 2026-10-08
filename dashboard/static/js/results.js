// Right-panel views: verdict + numbers + cut-off list, settlement detail, running stepper, error.
import { el, num, pct, km, minutes } from './util.js';
import { fileUrl, fileExists } from './api.js';

const VERDICT = {
  flood_detected: { cls: 'bad', title: 'Flood detected' },
  no_significant_flooding: { cls: 'good', title: 'No significant flooding detected' },
  insufficient_data: { cls: 'warn', title: 'Insufficient data' },
};
const STATUS = { connected: ['ok', 'Connected'], degraded: ['warn', 'Degraded (long detour)'], cut_off: ['bad', 'Cut off'], no_road_pre_event: ['muted', 'No road before the event'] };
const STEP_LABEL = { acquire: 'Acquire satellite data', preprocess: 'Preprocess & align', flood_ai: 'Flood detection (AI)', debris: 'Debris / mud', damage: 'Damage overlay', network: 'Cut-off analysis', report: 'Statistics & report' };

const stat = (label, value, sub, cls = '') => el('div', { class: `stat ${cls}` }, el('div', { class: 'stat-v', text: value }), el('div', { class: 'stat-l', text: label }), sub ? el('div', { class: 'stat-s', text: sub }) : null);
const section = (title, ...kids) => el('section', { class: 'card' }, el('h2', { text: title }), ...kids);
const bar = (label, v) => el('div', { class: 'bar-row' }, el('span', { class: 'bar-l', text: label }),
  el('span', { class: 'bar' }, el('i', { style: `width:${v == null ? 0 : Math.max(0, Math.min(100, v))}%` })), el('span', { class: 'bar-v', text: pct(v) }));

export function createResults(root, api) {
  // api: {layers, onBack, map, exportPng, onZoomAoi}
  function setView(...nodes) { root.replaceChildren(...nodes); root.scrollTop = 0; }

  function renderRunning(status, { onCancel } = {}) {
    const steps = status.steps.map(s => {
      const icon = { done: '✓', running: '', failed: '!', skipped: '–', pending: '' }[s.state] ?? '';
      return el('li', { class: `step ${s.state}` }, el('span', { class: 'step-i', text: icon }),
        el('div', { class: 'step-t' }, el('div', { text: STEP_LABEL[s.name] ?? s.name }), s.message ? el('div', { class: 'step-m', text: s.message }) : null),
        s.state === 'running' ? el('span', { class: 'spinner', 'aria-label': 'running' }) : s.state === 'skipped' ? el('span', { class: 'step-tag', text: 'skipped' }) : null);
    });
    const log = status.log_tail?.length ? el('pre', { class: 'log', text: status.log_tail.join('\n') }) : null;
    setView(section(status.state === 'queued' ? 'Starting…' : 'Analysis running', el('ol', { class: 'stepper' }, steps), log,
      onCancel ? el('button', { class: 'btn danger-outline block', type: 'button', onclick: onCancel, text: 'Cancel run' }) : null));
  }

  function renderError(status, { onBack } = {}) {
    const cancelled = status.state === 'cancelled';
    setView(section(cancelled ? 'Run cancelled' : 'Run failed',
      el('p', { class: `notice ${cancelled ? 'warn' : 'bad'}`, text: cancelled ? 'The run was cancelled. Nothing was produced.' : (status.error || 'The pipeline stopped unexpectedly.') }),
      cancelled ? null : el('p', { class: 'muted', text: 'Things to try: a smaller area, a different flood date, or custom before/after windows under Advanced. Missing satellite scenes (for example no radar pair from the same orbit) are reported here instead of an empty map.' }),
      status.log_tail?.length ? el('details', {}, el('summary', { text: 'Log' }), el('pre', { class: 'log', text: status.log_tail.join('\n') })) : null,
      onBack ? el('button', { class: 'btn block', type: 'button', onclick: onBack, text: 'Back' }) : null));
  }

  async function renderResult(runId, run, stats) {
    if (!stats) {
      setView(section('No results', el('p', { class: 'notice warn', text: 'This run has no statistics file (stats.json) yet.' })));
      return;
    }
    const v = VERDICT[stats.verdict] ?? { cls: 'warn', title: stats.verdict ?? 'Unknown' };
    const cov = stats.coverage ?? {}, fl = stats.flood ?? {}, dm = stats.damage ?? {}, ac = stats.access ?? {};
    const mock = !!run.mock;

    const banner = el('div', { class: `verdict ${v.cls}` },
      el('div', { class: 'verdict-t', text: v.title }),
      mock ? el('span', { class: 'badge sample', text: 'SAMPLE DATA' }) : null,
      ...(stats.verdict_reasons ?? []).map(t => el('div', { class: 'verdict-r', text: t })));

    const meta = el('div', { class: 'run-meta' }, el('span', { text: `Flood date ${stats.event_date ?? run.event_date ?? '?'}` }), el('span', { text: `${num(stats.aoi_area_km2, 0)} km²` }), el('span', { class: 'mono', text: runId }));

    const quality = section('Data quality',
      bar('Radar (S1) valid', cov.s1_valid_pct), bar('Optical before, clear', cov.s2_pre_clear_pct), bar('Optical after, clear', cov.s2_post_clear_pct),
      el('div', { class: 'scene-list' }, ...Object.entries(stats.scenes ?? {}).map(([k, val]) => el('div', { class: 'scene' }, el('span', { class: 'muted', text: k.replace('_', ' ').toUpperCase() }), el('span', { class: 'mono', text: val ?? 'not available' })))),
      ...(stats.warnings ?? run.warnings ?? []).map(w => el('p', { class: 'notice warn', text: w })));

    const grid = section('Summary', el('div', { class: 'stat-grid' },
      stat('Flood water', `${num(fl.flooded_water_km2, 2)} km²`),
      stat('Debris / mud', fl.debris_km2 == null ? 'n/a' : `${num(fl.debris_km2, 2)} km²`),
      stat('Buildings hit', `${num(dm.buildings_hit, 0)} / ${num(dm.buildings_total, 0)}`),
      stat('Roads hit', `${num(dm.roads_hit_km, 1)} / ${num(dm.roads_total_km, 1)} km`),
      stat('Bridges hit', `${num(dm.bridges_hit, 0)} / ${num(dm.bridges_total, 0)}`),
      stat('Cut off', `${num(ac.cut_off, 0)} / ${num(ac.settlements_total, 0)}`, `${num(ac.degraded, 0)} degraded · ${num(ac.connected, 0)} connected`, ac.cut_off ? 'bad' : '')));

    // cut-off settlements
    const features = api.layers.data?.settlements?.features ?? [];
    const cut = features.filter(f => f.properties.status === 'cut_off');
    const list = section(`Settlements cut off (${cut.length})`,
      cut.length ? el('ul', { class: 'plist' }, ...cut.sort((a, b) => (b.properties.population ?? 0) - (a.properties.population ?? 0)).map(f =>
        el('li', {}, el('button', { type: 'button', onclick: () => api.openSettlement(f.properties.osm_id) },
          el('span', { class: 'pl-n', text: f.properties.name ?? `Unnamed ${f.properties.place ?? 'place'}` }),
          el('span', { class: 'pl-s muted', text: [f.properties.place, f.properties.population ? `~${num(f.properties.population, 0)} people` : null].filter(Boolean).join(' · ') })))))
        : el('p', { class: 'muted', text: 'No settlement lost its road connection to the nearest town or hospital.' }));

    // downloads
    const [hasPdf, hasMd] = await Promise.all([fileExists(runId, 'report/sitrep_en.pdf'), fileExists(runId, 'report/sitrep_en.md')]);
    const exportDefs = [
      ['Flood polygons (GeoJSON)', 'flood/flood_polygons.geojson'], ['Buildings damage (GeoJSON)', 'damage/buildings_damage.geojson'], ['Roads damage (GeoJSON)', 'damage/roads_damage.geojson'],
      ['Bridges damage (GeoJSON)', 'damage/bridges_damage.geojson'], ['Settlements access (GeoJSON)', 'network/settlements_access.geojson'], ['Cut roads (GeoJSON)', 'network/road_cuts.geojson'],
      ['Flood mask (GeoTIFF)', 'flood/flood_mask.tif'], ['Statistics (JSON)', 'stats.json'],
    ];
    const present = (await Promise.all(exportDefs.map(async ([l, p]) => (await fileExists(runId, p)) ? [l, p] : null))).filter(Boolean);
    const sitrep = hasPdf ? 'report/sitrep_en.pdf' : hasMd ? 'report/sitrep_en.md' : null;
    const actions = section('Report & export',
      sitrep ? el('a', { class: 'btn primary block', href: fileUrl(runId, sitrep, true), text: `⬇ Download situation report (${sitrep.endsWith('pdf') ? 'PDF' : 'Markdown'})` })
             : el('button', { class: 'btn block', type: 'button', disabled: true, title: 'The situation report is generated by the report module (not available yet)', text: '⬇ Situation report — not available yet' }),
      el('details', { class: 'export' }, el('summary', { text: 'Export data' }),
        el('ul', { class: 'plist flat' }, ...present.map(([l, p]) => el('li', {}, el('a', { href: fileUrl(runId, p, true), text: l }))),
          el('li', {}, el('button', { type: 'button', class: 'linklike', onclick: api.exportPng, text: 'Map view (PNG)' })))));

    setView(banner, meta, grid, list, quality, actions);
  }

  function renderSettlement(f, runId) {
    const p = f.properties;
    const [cls, label] = STATUS[p.status] ?? ['muted', p.status];
    const cuts = (api.layers.data?.cuts?.features ?? []).filter(c => (p.blocking_cuts ?? []).includes(c.properties.osm_id));
    const row = (k, a, b) => el('tr', {}, el('th', { text: k }), el('td', { text: a }), el('td', { text: b }));
    setView(
      el('button', { class: 'back', type: 'button', onclick: api.onBack, text: '← Back to overview' }),
      section('Settlement', el('h3', { class: 'sd-name', text: p.name ?? 'Unnamed place' }),
        el('div', { class: 'sd-meta' }, el('span', { class: `status ${cls}`, text: label }), el('span', { class: 'muted', text: [p.place, p.population ? `~${num(p.population, 0)} people` : null].filter(Boolean).join(' · ') }))),
      section('Route to nearest town or hospital',
        el('table', { class: 'kvt' }, el('thead', {}, el('tr', {}, el('th'), el('th', { text: 'Before' }), el('th', { text: 'After' }))),
          el('tbody', {},
            row('Destination', p.nearest_dest_pre ?? 'n/a', p.status === 'cut_off' ? 'unreachable' : (p.nearest_dest_post ?? 'n/a')),
            row('Distance', km(p.dist_pre_m), p.status === 'cut_off' ? '—' : km(p.dist_post_m)),
            row('Travel time', minutes(p.time_pre_s), p.status === 'cut_off' ? '—' : minutes(p.time_post_s)),
            row('Detour', '', p.detour_factor ? `×${num(p.detour_factor, 1)}` : '—')))),
      section(`Blocking sections (${cuts.length})`,
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
