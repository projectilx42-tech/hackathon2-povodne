// Frontend configuration. Base maps are display-only; the pipeline never reads them (D-020).
export const DEFAULT_VIEW = { center: [85.3, 28.1], zoom: 8 }; // Nepal, Trishuli corridor region
export const AREA_WARN_KM2 = 900; // ~30 x 30 km target for a run (docs/TASK.md)

const OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export const BASEMAPS = [
  {
    // Dark style = standard OSM tiles with inverted luminance (CARTO Dark Matter now requires an API key).
    id: 'dark', label: 'Dark',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    tileSize: 256, maxzoom: 19,
    paint: { 'raster-brightness-min': 1, 'raster-brightness-max': 0, 'raster-hue-rotate': 180, 'raster-saturation': -0.3, 'raster-contrast': -0.15 },
    attribution: OSM_ATTR,
  },
  {
    id: 'osm', label: 'OSM',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    tileSize: 256, maxzoom: 19,
    attribution: OSM_ATTR,
  },
  {
    id: 'topo', label: 'Topo',
    tiles: ['a', 'b', 'c'].map(s => `https://${s}.tile.opentopomap.org/{z}/{x}/{y}.png`),
    tileSize: 256, maxzoom: 17,
    attribution: `${OSM_ATTR}, SRTM | &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)`,
  },
  {
    id: 'satellite', label: 'Satellite',
    tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg'],
    tileSize: 256, maxzoom: 14,
    attribution: '<a href="https://cloudless.eox.at">EOxCloudless</a> by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2024)',
  },
];
export const DEFAULT_BASEMAP = 'dark';
