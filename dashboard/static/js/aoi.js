import { TerraDraw, TerraDrawRectangleMode, TerraDrawFreehandMode, TerraDrawSelectMode } from 'terra-draw';
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter';
import { maplibregl } from './map.js';

const ACCENT = '#4cc2ff';
const drawStyle = { fillColor: ACCENT, fillOpacity: 0.14, outlineColor: ACCENT, outlineWidth: 2 };

/**
 * Area-of-interest drawing (D-019): rectangle (default) and free shape, plus an edit mode.
 * Holds at most one feature. `onChange(polygon | null)` receives a GeoJSON Polygon in EPSG:4326.
 */
export function createAoi(map, { onChange, onToolChange }) {
  const draw = new TerraDraw({
    adapter: new TerraDrawMapLibreGLAdapter({ map, lib: maplibregl }),
    modes: [
      new TerraDrawRectangleMode({ styles: drawStyle }),
      new TerraDrawFreehandMode({ styles: { ...drawStyle, closingPointColor: ACCENT, closingPointOutlineColor: '#04202e' } }),
      new TerraDrawSelectMode({
        flags: {
          rectangle: { feature: { draggable: true, coordinates: { resizable: 'opposite' } } },
          freehand: { feature: { draggable: true } },
        },
        styles: {
          selectedPolygonColor: ACCENT, selectedPolygonFillOpacity: 0.14, selectedPolygonOutlineColor: ACCENT, selectedPolygonOutlineWidth: 2,
          selectionPointColor: '#ffffff', selectionPointOutlineColor: ACCENT,
          midPointColor: ACCENT, midPointOutlineColor: '#04202e',
        },
      }),
    ],
  });

  const MODE = { rectangle: 'rectangle', shape: 'freehand', edit: 'select' };
  let currentId = null;
  let tool = 'rectangle';

  const polygonOf = id => {
    const f = draw.getSnapshot().find(x => x.id === id);
    return f ? f.geometry : null;
  };
  const setTool = t => {
    tool = t;
    onToolChange?.(t);
  };

  draw.on('finish', (id, context) => {
    if (context.action === 'draw') {
      // Keep a single AOI: drop the previous one, then switch to edit mode on the new one.
      const stale = draw.getSnapshot().filter(f => f.id !== id).map(f => f.id);
      if (stale.length) draw.removeFeatures(stale);
      currentId = id;
      draw.setMode('select');
      draw.selectFeature(id);
      setTool('edit');
    }
    if (id === currentId) onChange(polygonOf(id));
  });

  draw.on('change', (ids, type) => {
    // Live updates while dragging/resizing in edit mode.
    if (type === 'update' && ids.includes(currentId)) onChange(polygonOf(currentId));
  });

  draw.start();
  draw.setMode(MODE.rectangle);

  return {
    setTool(t) {
      if (t === 'edit') {
        if (!currentId) return;
        draw.setMode('select');
        draw.selectFeature(currentId);
      } else {
        draw.setMode(MODE[t]);
      }
      setTool(t);
    },
    clear() {
      draw.clear();
      currentId = null;
      draw.setMode(MODE[tool === 'edit' ? 'rectangle' : tool]);
      if (tool === 'edit') setTool('rectangle');
      onChange(null);
    },
    hasArea: () => currentId !== null,
    fit(polygon) {
      const xs = polygon.coordinates[0].map(c => c[0]);
      const ys = polygon.coordinates[0].map(c => c[1]);
      map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: 80, duration: 500 });
    },
  };
}
