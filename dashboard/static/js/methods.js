// Static text for the "Methods & Limitations" dialog (no user data -> safe to set as HTML).
// Keep in sync with docs/DECISIONS.md; this is also the base for the report's limitations section.
export const METHODS_HTML = `
<h3>What the system does</h3>
<p>For an area and a flood date it answers three questions for rescue teams: <b>where the flood hit</b>, <b>what is damaged</b>, and <b>who is cut off</b> — from free satellite data only.</p>
<h3>Data used</h3>
<ul>
  <li><b>Sentinel-1</b> radar (sees through clouds): images from the same orbit track before and after the event are compared.</li>
  <li><b>Sentinel-2</b> optical images when the sky is clear enough; <b>Copernicus DEM GLO-30</b> for terrain (slope, height above drainage).</li>
  <li><b>OpenStreetMap</b> as it was <i>before</i> the event (ohsome API snapshot): buildings, roads, bridges, settlements, hospitals.</li>
  <li>The flood model is trained on Kuro Siwo (Bountos et al., 2024). Published damage maps (Copernicus EMS, UNOSAT) are <b>never</b> used as input — only to check results afterwards.</li>
</ul>
<h3>How the answers are produced</h3>
<ul>
  <li><b>Flood water</b>: an AI segmentation model on radar and terrain data. <b>Debris / mud</b>: a separate change-based algorithm, because mud and rock behave differently from open water in radar.</li>
  <li><b>Damage</b>: an OSM building, road or bridge counts as hit when it overlaps flooded or debris-covered pixels. Bridges over flooded channels are marked <i>suspect</i>, not confirmed destroyed.</li>
  <li><b>Cut off</b>: roads hit by the flood are removed from the pre-event road network; a settlement is cut off when no road route to the nearest town or hospital remains, degraded when the detour is more than twice as long.</li>
  <li>All numbers on the page come from the run's statistics file — none are typed in by hand.</li>
</ul>
<h3>Limitations</h3>
<ul>
  <li>Satellites revisit an area only every few days. The system maps what <i>was</i> there on the satellite dates; it cannot warn of a sudden event ahead of time and may miss short-lived water.</li>
  <li>Steep valleys cause radar <b>layover and shadow</b>: parts of the area cannot be assessed. The data-quality panel shows how much was usable.</li>
  <li>Optical images are often cloudy in the monsoon; then only radar is used and results are less detailed.</li>
  <li>10 m pixels: small buildings and narrow roads are only roughly assessed; a building “hit” means flood nearby, not a damage grade.</li>
  <li>OpenStreetMap is incomplete in remote areas (missing roads, buildings, bridges), and only the pre-event state is known. Cut-off results depend on the road network being present.</li>
  <li>Debris detection is heuristic and may confuse landslides, bare ground or snow with flood deposits.</li>
  <li>The AI model can be wrong, especially in terrain unlike its training data. Treat results as a first screening, not as ground truth.</li>
  <li>“No significant flooding detected” means nothing was found in the available data; always check the coverage shown with the verdict.</li>
  <li>Educational prototype, not an operational tool. Do not base rescue decisions on it alone.</li>
</ul>
<h3>Attributions</h3>
<ul>
  <li>Contains modified Copernicus Sentinel data 2026.</li>
  <li>Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.</li>
  <li>© OpenStreetMap contributors (ODbL). Base maps: OpenStreetMap, OpenTopoMap (CC-BY-SA), EOxCloudless by EOX IT Services GmbH (Contains modified Copernicus Sentinel data).</li>
  <li>Training data: Bountos et al., 2024 (Kuro Siwo).</li>
</ul>
`;
