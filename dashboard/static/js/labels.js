// Shared names and colours for the map layers and the side panel (one place, so legend, map and text always agree).
export const C = { water: '#3987e5', cut: '#e5484d', ok: '#12b312', deg: '#fab219', road: '#8a8a82', sel: '#ffe066', amber: '#fab219', orange: '#ec835a', crimson: '#a3162f' };

// Surface-change sub-types from the debris step (flood/debris_polygons.geojson: subtype)
export const SUBTYPE = {
  debris: { label: 'Debris (rock, gravel)', color: '#c58f2d' },
  mud: { label: 'Mud', color: '#8a5a44' },
  erosion: { label: 'Erosion (scoured banks)', color: '#d1633a' },
  flooded_vegetation: { label: 'Flooded vegetation', color: '#3fa66a' },
  flooded_builtup: { label: 'Flooded buildings / town', color: '#a67cd8' },
  damaged_builtup: { label: 'Damaged buildings', color: '#e0457b' },
  landslide: { label: 'Landslide (steep slope)', color: '#a3a32f' },
  unknown: { label: 'Other surface change', color: '#8e8d84' },
};
export const CONF_LABEL = { high: 'high', medium: 'medium', low: 'low' };

// Building damage grade (damage/buildings_damage.geojson: grade)
export const GRADE = {
  likely_destroyed: { label: 'Likely destroyed', color: C.crimson },
  affected: { label: 'Affected', color: C.orange },
  possibly_affected: { label: 'Possibly affected', color: C.amber },
  none: { label: 'Not affected', color: C.road },
};
// Road / bridge status
export const ROAD_STATUS = {
  blocked: { label: 'Blocked', color: C.cut },
  possibly_blocked: { label: 'Possibly blocked', color: C.amber },
  suspect: { label: 'Suspect (not confirmed)', color: C.amber },
  passable: { label: 'Passable', color: C.road },
};
// Settlement access status
export const ACCESS = {
  connected: { label: 'Connected', cls: 'ok', icon: 'check' },
  degraded: { label: 'Degraded (long detour)', cls: 'warn', icon: 'alert' },
  possibly_cut_off: { label: 'Possibly cut off', cls: 'warn', icon: 'alert' },
  cut_off: { label: 'Cut off', cls: 'bad', icon: 'alert' },
  no_road_pre_event: { label: 'No road before the event', cls: 'muted', icon: 'info' },
};
// Impact level of a settlement
export const IMPACT = {
  critical: { label: 'Critical', color: '#ff5c7a', rank: 4 },
  severe: { label: 'Severe', color: C.cut, rank: 3 },
  moderate: { label: 'Moderate', color: C.amber, rank: 2 },
  low: { label: 'Low', color: '#8e8d84', rank: 1 },
  none: { label: 'None', color: '#8e8d84', rank: 0 },
};
// Key places (facilities, pois)
export const KIND = {
  hospital: 'Hospital', clinic: 'Clinic', health_post: 'Health post', town: 'Town', school: 'School', power_plant: 'Power plant', dam: 'Dam',
  helipad: 'Helipad', bridge: 'Bridge', fire_station: 'Fire station', police: 'Police', bank: 'Bank', fuel: 'Fuel station', university: 'University',
};
export const kindLabel = k => KIND[k] ?? (k ? String(k).replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()) : 'Place');
export const LANDING = {
  suitable: 'Gentle slope (suitable)', caution: 'Steeper slope (use caution)', known_helipad: 'Mapped helipad (OpenStreetMap)',
};
export const FACILITY_ACCESS = {
  connected: { label: 'Reachable', cls: 'ok' }, possibly_cut_off: { label: 'Possibly cut off', cls: 'warn' }, cut_off: { label: 'Cut off', cls: 'bad' }, no_road_pre_event: { label: 'No road before', cls: 'muted' },
};
