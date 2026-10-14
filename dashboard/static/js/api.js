// Thin client for the dashboard HTTP API (docs/ARCHITECTURE.md, "HTTP API").
async function json(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { const b = await res.json(); detail = typeof b.detail === 'string' ? b.detail : JSON.stringify(b.detail); } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return res.json();
}

export const fileUrl = (runId, path, download = false) =>
  `/api/runs/${encodeURIComponent(runId)}/files/${path}${download ? '?download=true' : ''}`;

export const getRuns = () => json('/api/runs');
export const getRun = id => json(`/api/runs/${encodeURIComponent(id)}`);
export const getStatus = id => json(`/api/runs/${encodeURIComponent(id)}/status`);
export const getOverlays = id => json(`/api/runs/${encodeURIComponent(id)}/overlays`);
export const cancelRun = id => json(`/api/runs/${encodeURIComponent(id)}/cancel`, { method: 'POST' });
export const startRun = body => json('/api/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

// Files the server listed for the run that is open: lets the page skip requests for optional outputs that do not exist.
let known = null;
export const rememberFiles = (runId, files) => { known = Array.isArray(files) ? { runId, set: new Set(files) } : null; };
const knownMissing = (runId, path) => known?.runId === runId && !known.set.has(path);

/** Fetch a run file as JSON; null when it does not exist (optional pipeline outputs). */
export async function getFileJson(runId, path) {
  if (knownMissing(runId, path)) return null;
  const res = await fetch(fileUrl(runId, path));
  if (!res.ok) return null;
  try { return await res.json(); } catch { return null; }
}

export async function fileExists(runId, path) {
  if (known?.runId === runId) return known.set.has(path);
  try { return (await fetch(fileUrl(runId, path), { method: 'HEAD' })).ok; } catch { return false; }
}

/** Trace the flood path downstream of a clicked point; resolves with {path, settlements, along, mock}. */
export const postFloodpath = (id, lon, lat) => json(`/api/runs/${encodeURIComponent(id)}/floodpath`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lon, lat }) });
