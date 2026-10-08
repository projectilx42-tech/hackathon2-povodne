// Small geodesic helpers (no external dependencies).
const R = 6378137; // WGS84 equatorial radius, m
const rad = d => (d * Math.PI) / 180;

/** Geodesic area of a GeoJSON Polygon (outer ring only; holes ignored), in km². */
export function polygonAreaKm2(polygon) {
  const ring = polygon.coordinates[0];
  let sum = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [lon1, lat1] = ring[i];
    const [lon2, lat2] = ring[i + 1];
    sum += rad(lon2 - lon1) * (2 + Math.sin(rad(lat1)) + Math.sin(rad(lat2)));
  }
  return Math.abs((sum * R * R) / 2) / 1e6;
}

/** [minLon, minLat, maxLon, maxLat] of a GeoJSON Polygon. */
export function polygonBbox(polygon) {
  const xs = polygon.coordinates[0].map(c => c[0]);
  const ys = polygon.coordinates[0].map(c => c[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
