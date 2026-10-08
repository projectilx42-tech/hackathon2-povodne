import * as maplibregl from 'maplibre-gl';
import { BASEMAPS, DEFAULT_BASEMAP, DEFAULT_VIEW } from './config.js';

export { maplibregl };

/** One style holding every base map as a raster layer; switching only toggles visibility,
 *  so drawn/overlay layers survive a base map change. */
export function buildStyle(active = DEFAULT_BASEMAP) {
  const sources = {};
  const layers = [];
  for (const b of BASEMAPS) {
    sources[`bm-${b.id}`] = { type: 'raster', tiles: b.tiles, tileSize: b.tileSize, maxzoom: b.maxzoom, attribution: b.attribution };
    layers.push({ id: `bm-${b.id}`, type: 'raster', source: `bm-${b.id}`, layout: { visibility: b.id === active ? 'visible' : 'none' }, paint: b.paint ?? {} });
  }
  return { version: 8, sources, layers };
}

export function createMap(container) {
  const map = new maplibregl.Map({
    container,
    style: buildStyle(),
    center: DEFAULT_VIEW.center,
    zoom: DEFAULT_VIEW.zoom,
    attributionControl: { compact: true },
    maxPitch: 0, // 2D only
    dragRotate: false,
    canvasContextAttributes: { preserveDrawingBuffer: true }, // needed for the PNG export
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
  return map;
}

/** Non-interactive twin map used by the before/after slider. */
export function createTwinMap(container, main, basemap) {
  const twin = new maplibregl.Map({ container, style: buildStyle(basemap), center: main.getCenter(), zoom: main.getZoom(), interactive: false, attributionControl: false });
  return twin;
}

export function setBasemap(map, id) {
  for (const b of BASEMAPS) map.setLayoutProperty(`bm-${b.id}`, 'visibility', b.id === id ? 'visible' : 'none');
}
