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
  <li><b>Flood water</b>: a U-Net AI model on before/after radar plus terrain slope (trained on Kuro Siwo and Sen1Floods11), plus an optical model when the sky is clear. Held-out test F1 for flood: 0.78 on plains and hills (Kuro Siwo), 0.48 on mountain tiles.</li>
  <li><b>Debris, mud, flooded vegetation and buildings</b>: a change test against each pixel's own history, both pass directions, with a confidence level and a flood-free self-test (a false-alarm estimate).</li>
  <li><b>Damage</b> per building, road and bridge is shown as a range (certain … including possible). Bridges over flooded channels are marked <i>suspect</i>, not destroyed.</li>
  <li><b>Cut off</b>: own road graph from the pre-event OpenStreetMap snapshot; blocked road pieces are removed; a settlement is cut off when no road route to the nearest town or hospital remains, degraded when the detour is more than twice as long. Footpaths are not included.</li>
  <li>All numbers on the page come from the run's statistics file — none are typed in by hand.</li>
</ul>
<h3>Limitations</h3>
<ul>
  <li>Satellites revisit every few days. The system maps what <i>was</i> there on the satellite dates; it gives no early warning of sudden events such as a glacier collapse, and a very recent flood may have no “after” image yet.</li>
  <li>Radar <b>shadow and layover</b> hide parts of steep valleys; narrow, fast mountain rivers look like land to radar. The data-quality panel shows how much was usable.</li>
  <li>Optical images are often cloudy in the monsoon; then only radar is used and results are less detailed.</li>
  <li>10 m pixels: small buildings and narrow roads are only roughly assessed.</li>
  <li>The flood model is a change detector and is weaker in mountains; debris thresholds come from literature, not from Himalayan debris flows. It can be wrong in terrain unlike its training data.</li>
  <li>OpenStreetMap is incomplete in remote areas; footpaths and footbridges are not counted; no population estimates. Only the pre-event state is known.</li>
  <li>Helicopter landing-zone candidates come from the elevation model only and are <b>unverified</b>.</li>
  <li>“No significant flooding detected” means nothing was found in the available data; always check the coverage shown with the verdict.</li>
  <li>Educational prototype, not an operational tool. Do not base rescue decisions on it alone. No images of victims are used.</li>
</ul>
<h3>Attributions</h3>
<ul>
  <li>Contains modified Copernicus Sentinel data 2026.</li>
  <li>Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.</li>
  <li>© OpenStreetMap contributors (ODbL). Base maps: OpenStreetMap, OpenTopoMap (CC-BY-SA), EOxCloudless by EOX IT Services GmbH (Contains modified Copernicus Sentinel data).</li>
  <li>Training data: Bountos et al., 2024 (Kuro Siwo); Bonafilia et al., 2020 (Sen1Floods11).</li>
</ul>
`;
