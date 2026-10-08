// Before / after swipe: twin map clipped on the right side of a draggable handle (shows the "after" image).
import { createTwinMap } from './map.js';
import { maplibregl } from './map.js';

export function createCompare({ map, wrap, handle, tags, onToggle }) {
  let twin = null, active = false, x = 0.5;

  function clip() {
    const px = wrap.clientWidth * x;
    wrap.querySelector('#map2').style.clipPath = `inset(0 0 0 ${px}px)`;
    handle.style.left = `${px}px`;
  }
  const sync = () => twin?.jumpTo({ center: map.getCenter(), zoom: map.getZoom() });

  handle.addEventListener('pointerdown', e => {
    handle.setPointerCapture(e.pointerId);
    const move = ev => { const r = wrap.getBoundingClientRect(); x = Math.min(0.98, Math.max(0.02, (ev.clientX - r.left) / r.width)); clip(); };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', () => handle.removeEventListener('pointermove', move), { once: true });
  });
  window.addEventListener('resize', () => active && (twin.resize(), clip()));

  return {
    get active() { return active; },
    async enable({ pre, post, basemap }) {
      const [w, s, e, n] = pre.bounds;
      const coords = [[w, n], [e, n], [e, s], [w, s]];
      if (!twin) {
        twin = createTwinMap('map2', map, basemap);
        await new Promise(r => twin.once('load', r));
      }
      for (const l of ['cmp-post']) if (twin.getLayer(l)) twin.removeLayer(l);
      if (twin.getSource('cmp-post')) twin.removeSource('cmp-post');
      twin.addSource('cmp-post', { type: 'image', url: post.url, coordinates: coords });
      twin.addLayer({ id: 'cmp-post', type: 'raster', source: 'cmp-post', paint: { 'raster-fade-duration': 0 } });
      active = true;
      wrap.classList.add('comparing');
      handle.hidden = tags.hidden = false;
      twin.resize(); sync(); clip();
      map.on('move', sync);
      onToggle?.(true);
    },
    disable() {
      if (!active) return;
      active = false;
      map.off('move', sync);
      wrap.classList.remove('comparing');
      handle.hidden = tags.hidden = true;
      onToggle?.(false);
    },
    setBasemap(id) {
      if (!twin) return;
      for (const l of twin.getStyle().layers) if (l.id.startsWith('bm-')) twin.setLayoutProperty(l.id, 'visibility', l.id === `bm-${id}` ? 'visible' : 'none');
    },
  };
}
