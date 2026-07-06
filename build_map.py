"""Stage 3: render the self-contained Leaflet HTML map from data/territories.json."""
import base64
import json
from pathlib import Path

DATA_DIR = Path("data")
ASSETS_DIR = Path("assets")
TERRITORIES_PATH = DATA_DIR / "territories.json"
POSTCODE_AREAS_PATH = DATA_DIR / "postcode_areas.geojson"
LOGO_OUTLINE_PATH = ASSETS_DIR / "dmg-logo-outline.png"
LOGO_FILL_PATH = ASSETS_DIR / "dmg-logo-filled.png"
OUTPUT_PATH = Path("Dental_Practices_Heatmap.html")

HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>DMG Dental Practices — England Heatmap & Rep Territory Plan</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  html, body {{ margin:0; padding:0; height:100%; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
  #map {{ position:absolute; top:56px; bottom:0; left:0; right:0; }}
  #topbar {{
    position:absolute; top:0; left:0; right:0; height:56px; z-index:1000;
    background:#14181f; color:#fff; display:flex; align-items:center; padding:0 16px; gap:16px;
    box-shadow:0 2px 6px rgba(0,0,0,0.25);
  }}
  #topbar h1 {{ font-size:15px; font-weight:600; margin:0; white-space:nowrap; }}
  #topbar .sub {{ font-size:12px; color:#a9b0bd; }}
  .panel {{
    position:absolute; z-index:1000; background:#fff; border-radius:10px;
    box-shadow:0 2px 10px rgba(0,0,0,0.18); padding:12px 14px; font-size:13px; color:#1a1a1a;
  }}
  #legend {{ top:70px; right:12px; width:250px; max-height:calc(100vh - 100px); overflow-y:auto; }}
  #controls {{ top:70px; left:12px; width:210px; }}
  #search-box-wrap {{ position:relative; margin-bottom:4px; }}
  #search-input {{
    width:100%; box-sizing:border-box; padding:7px 26px 7px 9px; font-size:13px;
    border:1px solid #d8d5cd; border-radius:6px; outline:none; font-family:inherit;
  }}
  #search-input:focus {{ border-color:#2a78d6; }}
  #clear-search-marker {{
    display:none; position:absolute; right:4px; top:50%; transform:translateY(-50%);
    width:20px; height:20px; border:none; border-radius:50%; background:transparent;
    color:#898781; font-size:16px; line-height:1; cursor:pointer;
  }}
  #clear-search-marker:hover {{ background:#f4f2ee; color:#1a1a1a; }}
  #search-results:not(:empty) {{ margin-bottom:8px; max-height:220px; overflow-y:auto; }}
  .search-result {{ padding:6px 8px; border-radius:6px; cursor:pointer; }}
  .search-result:hover {{ background:#f4f2ee; }}
  .sr-name {{ font-weight:600; color:#1a1a1a; font-size:12.5px; }}
  .sr-addr {{ color:#82807a; font-size:11.5px; }}
  .search-empty {{ padding:6px 8px; color:#898781; font-size:12px; }}
  .panel h3 {{ margin:0 0 8px 0; font-size:12.5px; text-transform:uppercase; letter-spacing:.04em; color:#52514e; }}
  .row {{ display:flex; align-items:center; gap:8px; margin:5px 0; cursor:pointer; user-select:none; }}
  .swatch {{ width:13px; height:13px; border-radius:50%; flex:none; border:1px solid rgba(0,0,0,0.15); }}
  .rep-details {{ margin:2px 0; }}
  .rep-details summary {{ list-style:none; }}
  .rep-details summary::-webkit-details-marker {{ display:none; }}
  .rep-details summary::before {{
    content:'\\25B8'; display:inline-block; width:10px; color:#898781; font-size:10px;
    transition:transform .12s ease;
  }}
  .rep-details[open] summary::before {{ transform:rotate(90deg); }}
  .area-list {{
    margin:4px 0 8px 27px; display:flex; flex-wrap:wrap; gap:4px;
    max-height:150px; overflow-y:auto;
  }}
  .area-chip {{
    background:#f4f2ee; border-radius:5px; padding:2px 6px; font-size:11px; color:#3a3937; white-space:nowrap;
  }}
  .area-chip em {{ font-style:normal; color:#82807a; }}
  .grad-bar {{ height:10px; border-radius:5px; background:linear-gradient(to right,#2a78d6,#eda100,#e34948); margin:4px 0 2px 0; }}
  .grad-labels {{ display:flex; justify-content:space-between; font-size:10.5px; color:#898781; }}
  label.opt {{ display:flex; align-items:center; gap:7px; margin:6px 0; font-size:12.5px; cursor:pointer; }}
  .count {{ margin-left:auto; font-variant-numeric:tabular-nums; color:#52514e; font-size:12px; }}
  #tooltip {{
    position:absolute; z-index:1001; pointer-events:none; background:#14181f; color:#fff;
    padding:6px 9px; border-radius:6px; font-size:12px; display:none; box-shadow:0 2px 8px rgba(0,0,0,0.3);
  }}
  a.credit {{ color:#a9b0bd; }}
  .postcode-label {{
    font-size:11px; font-weight:600; color:#5a4a1f; text-shadow:0 0 3px #fff, 0 0 3px #fff, 0 0 3px #fff;
    white-space:nowrap; pointer-events:none;
  }}
  #loading-overlay {{
    position:fixed; inset:0; z-index:5000; background:#fff;
    display:flex; align-items:center; justify-content:center;
    opacity:1; transition:opacity 0.4s ease;
  }}
  #loading-overlay.hidden {{ opacity:0; pointer-events:none; }}
  .loading-caption {{
    position:absolute; top:36px; left:0; right:0; text-align:center;
    font-size:19px; color:#52514e; padding:0 20px;
  }}
  /* Logo assets are cropped tight to their content bounding box (384x97, a
     wide short wordmark) -- aspect-ratio keeps height proportional so the
     water-fill (which spans the full box height) actually crosses visible
     artwork almost immediately and for almost the entire 5s, instead of
     mostly empty canvas padding. */
  .loading-logo-wrap {{ position:relative; width:min(322px, 69vw); aspect-ratio: 384 / 97; }}
  .loading-logo-wrap img {{ position:absolute; inset:0; width:100%; height:100%; }}
  /* Water-fill: a gentle wave rises up the logo over exactly 5s, independent of
     real load time (see __ready/tryHideOverlay in the script below for the
     actual "is it safe to hide" gate). Same 7-point count at every keyframe so
     the browser can tween the polygon smoothly; amplitude is 0 at 0%/100%
     (clean start/end) and peaks at 50%, so the ripple settles flat once full. */
  .loading-logo-fill {{
    clip-path: polygon(0% 100%, 25% 100%, 50% 100%, 75% 100%, 100% 100%, 100% 100%, 0% 100%);
    animation: water-fill 5000ms linear forwards;
  }}
  @keyframes water-fill {{
    0%   {{ clip-path: polygon(0% 100%, 25% 100%, 50% 100%, 75% 100%, 100% 100%, 100% 100%, 0% 100%); }}
    25%  {{ clip-path: polygon(0% 75%, 25% 72.17%, 50% 75%, 75% 77.83%, 100% 75%, 100% 100%, 0% 100%); }}
    50%  {{ clip-path: polygon(0% 50%, 25% 46%, 50% 50%, 75% 54%, 100% 50%, 100% 100%, 0% 100%); }}
    75%  {{ clip-path: polygon(0% 25%, 25% 22.17%, 50% 25%, 75% 27.83%, 100% 25%, 100% 100%, 0% 100%); }}
    100% {{ clip-path: polygon(0% 0%, 25% 0%, 50% 0%, 75% 0%, 100% 0%, 100% 100%, 0% 100%); }}
  }}
</style>
</head>
<body>

<div id="loading-overlay">
  <div class="loading-caption">Please wait ~4 seconds for the map to finish loading once past this screen</div>
  <div class="loading-logo-wrap">
    <img class="loading-logo-outline" src="data:image/png;base64,{logo_outline_b64}" alt="">
    <img class="loading-logo-fill" src="data:image/png;base64,{logo_fill_b64}" alt="">
  </div>
</div>

<div id="topbar">
  <h1>England Dental Practices — Density &amp; 5-Rep Territory Plan</h1>
</div>

<div id="map"></div>
<div id="tooltip"></div>

<div class="panel" id="controls">
  <h3>Layers</h3>
  <label class="opt"><input type="checkbox" id="toggle-heat" checked> Practice density heatmap</label>
  <label class="opt"><input type="checkbox" id="toggle-points"> Practices coloured by rep territory</label>
  <label class="opt"><input type="checkbox" id="toggle-reps" checked> Rep HQ markers</label>
  <label class="opt"><input type="checkbox" id="toggle-postcodes"> Postcode areas</label>
  <h3 style="margin-top:14px;">Basemap</h3>
  <label class="opt"><input type="radio" name="base" id="base-voyager" checked> Detailed (towns &amp; cities)</label>
  <label class="opt"><input type="radio" name="base" id="base-osm"> OpenStreetMap standard</label>
</div>

<div class="panel" id="legend">
  <h3>Heatmap intensity</h3>
  <div class="grad-bar"></div>
  <div class="grad-labels"><span>fewer practices</span><span>denser</span></div>
  <h3 style="margin-top:14px;">Proposed rep territories</h3>
  <div id="search-box-wrap">
    <input type="text" id="search-input" placeholder="Search practice name...">
    <button id="clear-search-marker" title="Remove pin (keeps current zoom)">&times;</button>
  </div>
  <div id="search-results"></div>
  <div id="rep-legend"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<script>
// ---- Loading overlay: a minimum-5s branded splash so the map (and its initial
// tiles) get a real chance to finish setting up before anything's revealed.
// The fill's rise is a pure 5s CSS animation (see .loading-logo-fill/@keyframes
// water-fill above) -- it always takes the full 5s regardless of how fast the
// page actually loads. __ready tracks real completion (map/tiles/etc.) purely
// to decide when it's *safe* to hide: never before the 5s animation finishes,
// and never before the page is actually ready even if that's past 5s. If a
// milestone never fires for some reason, HARD_CAP_MS forces it open anyway
// rather than leaving the page stuck behind a white screen forever.
const __loadStart = Date.now();
const __loadingOverlay = document.getElementById('loading-overlay');
const MIN_DISPLAY_MS = 5000;
const HARD_CAP_MS = 15000;
let __ready = false;
let __overlayHidden = false;
function hideOverlay() {{
  if (__overlayHidden) return;
  __overlayHidden = true;
  __loadingOverlay.classList.add('hidden');
  setTimeout(() => {{ __loadingOverlay.style.display = 'none'; }}, 450);
}}
function tryHideOverlay() {{
  if (!__ready) return;
  setTimeout(hideOverlay, Math.max(0, MIN_DISPLAY_MS - (Date.now() - __loadStart)));
}}
setTimeout(hideOverlay, HARD_CAP_MS);

// Deferred one tick so the browser actually paints #loading-overlay (and starts
// the CSS water-fill animation) before this heavy synchronous setup runs. Also
// keeps MAP_DATA/POSTCODE_AREAS (1MB+ of literal data) declared *inside*
// initMap rather than at the top level: a JS engine must fully parse top-level
// code before executing anything, but can lazily skip over a not-yet-called
// function's body, so nesting the huge literals in here (instead of the
// module's top level) is what actually lets the first paint -- and the
// animation's start -- happen immediately instead of ~1s late.
setTimeout(initMap, 0);

function initMap() {{

const MAP_DATA = {map_data_json};
const POSTCODE_AREAS = {postcode_areas_json};

const REP_COLORS = ["#2a78d6", "#e34948", "#1baf7a", "#eda100", "#4a3aa7"];
const ORPHAN_COLOR = "#9a9890";

const map = L.map('map', {{ preferCanvas: true }}).setView([52.9, -1.6], 6);

const voyager = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: 'abcd', maxZoom: 20
}}).addTo(map);
voyager.on('load', () => {{ __ready = true; tryHideOverlay(); }});

const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  subdomains: 'abc', maxZoom: 19
}});

document.getElementById('base-voyager').addEventListener('change', () => {{ map.removeLayer(osm); voyager.addTo(map); }});
document.getElementById('base-osm').addEventListener('change', () => {{ map.removeLayer(voyager); osm.addTo(map); }});

// ---- Heatmap layer (tight resolution: small radius, real postcode-level coords) ----
const heatPoints = MAP_DATA.points.map(p => [p[0], p[1], 0.55]);
const heatLayer = L.heatLayer(heatPoints, {{
  radius: 10,
  blur: 14,
  maxZoom: 13,
  max: 1.0,
  minOpacity: 0.25,
  gradient: {{ 0.15: '#2a78d6', 0.4: '#5598e7', 0.6: '#eda100', 0.8: '#e87ba4', 1.0: '#e34948' }}
}}).addTo(map);

// ---- Points-by-rep layer ----
// Custom canvas layer instead of per-point L.circleMarker on a shared L.canvas
// renderer: Leaflet's canvas renderer has no incremental-redraw concept, so
// attaching/detaching *any* path forces a full clear-and-redraw of every path
// registered to that renderer -- with ~10,900 practices (an invisible radius-9
// tap-target plus a visible radius-2.2 dot per practice, ~21,800 paths total)
// that made every toggle cost 1.4-2.9s regardless of build caching (measured
// live with Playwright under 4x CPU throttling). This draws all dots in one
// manual canvas pass instead, and keeps the canvas mounted after the first
// build so repeat toggles are a plain display:none/'' flip -- no redraw, no
// Leaflet layer add/remove. Visual appearance (dot size/colour/opacity, ~9px
// tap radius) is unchanged from before.
//
// Zoom animation: a plain canvas doesn't participate in Leaflet's zoom
// transition on its own, so it would visibly freeze mid-zoom while the
// basemap scales underneath it. _onZoomAnim below replicates L.Renderer's own
// _updateTransform (see Leaflet's src/layer/vector/Renderer.js) so this canvas
// gets the same one-shot CSS scale+translate that Leaflet's built-in canvas
// renderer uses, animated smoothly by the browser via the .leaflet-zoom-anim
// transition rule already in leaflet.css -- not something bespoke.
function escapeHtml(s) {{
  return s.replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
}}
const PointsLayer = L.Layer.extend({{
  onAdd(map) {{
    this._map = map;
    if (!this._canvas) {{
      this._canvas = L.DomUtil.create('canvas', 'leaflet-zoom-animated points-layer-canvas');
      this._ctx = this._canvas.getContext('2d');
      map.getPane('overlayPane').appendChild(this._canvas);
      map.on('moveend zoomend resize viewreset', this._onViewChange, this);
      if (map._zoomAnimated) {{
        map.on('zoomanim', this._onZoomAnim, this);
      }}
      this._canvas.addEventListener('click', this._onClick.bind(this));
    }}
    this._canvas.style.display = '';
    this._redraw();
    return this;
  }},
  onRemove() {{
    this._canvas.style.display = 'none';
    return this;
  }},
  _onViewChange() {{
    if (this._canvas.style.display === 'none') return;
    this._redraw();
  }},
  _redraw() {{
    // setPosition resets the CSS transform to a plain translate (no scale),
    // clearing whatever mid-zoom scale _onZoomAnim last applied.
    L.DomUtil.setPosition(this._canvas, this._map.containerPointToLayerPoint([0, 0]));
    const size = this._map.getSize();
    this._canvas.width = size.x;
    this._canvas.height = size.y;
    this._center = this._map.getCenter();
    this._zoom = this._map.getZoom();
    this._draw();
  }},
  _onZoomAnim(e) {{
    // Exactly mirrors L.Renderer._updateTransform with padding 0.
    const scale = this._map.getZoomScale(e.zoom, this._zoom);
    const viewHalf = this._map.getSize().multiplyBy(0.5);
    const currentCenterPoint = this._map.project(this._center, e.zoom);
    const topLeftOffset = viewHalf.multiplyBy(-scale).add(currentCenterPoint)
      .subtract(this._map._getNewPixelOrigin(e.center, e.zoom));
    L.DomUtil.setTransform(this._canvas, topLeftOffset, scale);
  }},
  _draw() {{
    const ctx = this._ctx;
    ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
    this._hitPoints = [];
    for (const p of MAP_DATA.points) {{
      const [lat, lon, ri, name, address] = p;
      const pt = this._map.latLngToContainerPoint([lat, lon]);
      ctx.beginPath();
      ctx.fillStyle = ri >= 0 ? REP_COLORS[ri] : ORPHAN_COLOR;
      ctx.arc(pt.x, pt.y, 2.2, 0, Math.PI * 2);
      ctx.fill();
      if (name) this._hitPoints.push({{ x: pt.x, y: pt.y, lat, lon, name, address }});
    }}
  }},
  _onClick(e) {{
    const rect = this._canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    let closest = null, closestDist = 9; // matches the old invisible radius-9 tap-target
    for (const hp of this._hitPoints) {{
      const dist = Math.hypot(hp.x - x, hp.y - y);
      if (dist <= closestDist) {{ closest = hp; closestDist = dist; }}
    }}
    if (closest) {{
      // Stop this click reaching the map's own click handling -- otherwise Leaflet
      // treats it as "clicked empty map" and immediately closes the popup we just
      // opened, same as it would for any interactive layer's click if it didn't
      // stop propagation.
      L.DomEvent.stopPropagation(e);
      const popupHtml = `<b>${{escapeHtml(closest.name)}}</b>${{closest.address ? '<br>' + escapeHtml(closest.address) : ''}}`;
      L.popup().setLatLng([closest.lat, closest.lon]).setContent(popupHtml).openOn(this._map);
    }}
  }},
}});
const pointsLayer = new PointsLayer();

// Split into a couple of setTimeout(fn, 0)-chained stages so a slow device (or
// a much larger future dataset) still gives the browser a chance to repaint
// the water-fill animation between chunks, rather than one unbroken
// synchronous block for the whole of initMap.
setTimeout(initMapPart2, 0);

function initMapPart2() {{

// ---- Postcode area overlay (RG, LS, NG, ...) ----
const postcodeLayer = L.layerGroup();
L.geoJSON(POSTCODE_AREAS, {{
  style: {{ color: '#5a4a1f', weight: 1, opacity: 0.55, fill: false }},
  interactive: false
}}).addTo(postcodeLayer);
POSTCODE_AREAS.features.forEach(f => {{
  const {{ area, labelLat, labelLon }} = f.properties;
  L.marker([labelLat, labelLon], {{
    icon: L.divIcon({{ className: 'postcode-label', html: area, iconSize: [40, 14], iconAnchor: [20, 7] }}),
    interactive: false
  }}).addTo(postcodeLayer);
}});
document.getElementById('toggle-postcodes').addEventListener('change', (e) => {{
  e.target.checked ? postcodeLayer.addTo(map) : map.removeLayer(postcodeLayer);
}});

setTimeout(initMapPart3, 0);
}} // end initMapPart2

function initMapPart3() {{

// ---- Rep HQ markers ----
const repsLayer = L.layerGroup().addTo(map);
const tooltip = document.getElementById('tooltip');

function repIcon(color) {{
  return L.divIcon({{
    className: '',
    html: `<div style="width:22px;height:22px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);
            background:${{color}};border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,0.4);"></div>`,
    iconSize: [22,22], iconAnchor: [11,22]
  }});
}}

MAP_DATA.reps.forEach((rep, i) => {{
  const marker = L.marker([rep.lat, rep.lon], {{ icon: repIcon(REP_COLORS[i]) }}).addTo(repsLayer);
  marker.bindPopup(`<b>${{rep.name}}</b><br>${{rep.count.toLocaleString()}} practices in territory`);
  marker.on('mouseover', (e) => {{
    tooltip.style.display = 'block';
    tooltip.innerHTML = `<b>${{rep.name}}</b><br>${{rep.count.toLocaleString()}} practices`;
  }});
  marker.on('mousemove', (e) => {{
    tooltip.style.left = (e.originalEvent.pageX + 14) + 'px';
    tooltip.style.top = (e.originalEvent.pageY + 8) + 'px';
  }});
  marker.on('mouseout', () => {{ tooltip.style.display = 'none'; }});
}});

// legend (sorted highest-to-lowest by practice count; orphan row always pinned last, see below)
// Each rep is a <details> toggle -- click to expand the postcode areas it covers.
const legendEl = document.getElementById('rep-legend');
const sortedReps = MAP_DATA.reps.map((rep, i) => ({{ rep, i }})).sort((a, b) => b.rep.count - a.rep.count);
sortedReps.forEach(({{ rep, i }}) => {{
  const details = document.createElement('details');
  details.className = 'rep-details';

  const summary = document.createElement('summary');
  summary.className = 'row';
  summary.innerHTML = `<span class="swatch" style="background:${{REP_COLORS[i]}}"></span>${{escapeHtml(rep.name)}}<span class="count">${{rep.count.toLocaleString()}}</span>`;
  details.appendChild(summary);

  const areaList = document.createElement('div');
  areaList.className = 'area-list';
  areaList.innerHTML = (rep.areas || [])
    .map(a => `<span class="area-chip">${{escapeHtml(a.code)}} <em>${{escapeHtml(a.name)}}</em></span>`)
    .join('');
  details.appendChild(areaList);

  legendEl.appendChild(details);
}});
if (MAP_DATA.orphanCount > 0) {{
  const row = document.createElement('div');
  row.className = 'row';
  row.title = 'More than 200km ({distance_cap_km:.0f}km) from every proposed HQ';
  row.innerHTML = `<span class="swatch" style="background:${{ORPHAN_COLOR}}"></span>Beyond 200km of any hub<span class="count">${{MAP_DATA.orphanCount.toLocaleString()}}</span>`;
  legendEl.appendChild(row);
}}

document.getElementById('toggle-heat').addEventListener('change', (e) => {{
  e.target.checked ? heatLayer.addTo(map) : map.removeLayer(heatLayer);
}});
document.getElementById('toggle-points').addEventListener('change', (e) => {{
  e.target.checked ? pointsLayer.addTo(map) : map.removeLayer(pointsLayer);
}});
document.getElementById('toggle-reps').addEventListener('change', (e) => {{
  e.target.checked ? repsLayer.addTo(map) : map.removeLayer(repsLayer);
}});

// ---- Practice name search ----
const searchInput = document.getElementById('search-input');
const searchResultsEl = document.getElementById('search-results');
const clearMarkerBtn = document.getElementById('clear-search-marker');
const searchResultLayer = L.layerGroup().addTo(map);

function renderSearchResults(query) {{
  searchResultsEl.innerHTML = '';
  const q = query.trim().toLowerCase();
  if (q.length < 2) return;

  const matches = [];
  for (const p of MAP_DATA.points) {{
    if (p[3] && p[3].toLowerCase().includes(q)) {{
      matches.push(p);
      if (matches.length >= 12) break;
    }}
  }}

  if (matches.length === 0) {{
    const empty = document.createElement('div');
    empty.className = 'search-empty';
    empty.textContent = 'No practices found';
    searchResultsEl.appendChild(empty);
    return;
  }}

  matches.forEach(([lat, lon, ri, name, address]) => {{
    const item = document.createElement('div');
    item.className = 'search-result';
    item.innerHTML = `<div class="sr-name">${{escapeHtml(name)}}</div><div class="sr-addr">${{escapeHtml(address || '')}}</div>`;
    item.addEventListener('click', () => goToPractice(lat, lon, name, address));
    searchResultsEl.appendChild(item);
  }});
}}

function goToPractice(lat, lon, name, address) {{
  searchResultLayer.clearLayers();
  map.setView([lat, lon], 16);
  L.marker([lat, lon]).addTo(searchResultLayer)
    .bindPopup(`<b>${{escapeHtml(name)}}</b>${{address ? '<br>' + escapeHtml(address) : ''}}`)
    .openPopup();
  searchResultsEl.innerHTML = '';
  searchInput.value = name;
  clearMarkerBtn.style.display = 'block';
}}

// Removes the search pin only -- deliberately does NOT touch map.setView, so the
// map stays at whatever zoom/position the search left it at.
clearMarkerBtn.addEventListener('click', () => {{
  searchResultLayer.clearLayers();
  searchInput.value = '';
  searchResultsEl.innerHTML = '';
  clearMarkerBtn.style.display = 'none';
}});

searchInput.addEventListener('input', (e) => {{
  renderSearchResults(e.target.value);
  if (e.target.value.trim() === '') {{
    searchResultLayer.clearLayers();
    clearMarkerBtn.style.display = 'none';
  }}
}});
searchInput.addEventListener('focus', (e) => renderSearchResults(e.target.value));
document.addEventListener('click', (e) => {{
  if (e.target !== searchInput && !searchResultsEl.contains(e.target)) {{
    searchResultsEl.innerHTML = '';
  }}
}});

// Pre-warm the rep-territory canvas (normally lazily built on first toggle)
// while still behind the loading screen: add it to the map and immediately
// remove it again, forcing the one-time canvas creation + first draw pass
// now instead of on the user's first real click. Both calls are synchronous
// so nothing is ever actually painted on screen -- the checkbox itself stays
// unchecked throughout.
pointsLayer.addTo(map);
map.removeLayer(pointsLayer);

}} // end initMapPart3
}} // end initMap
</script>
</body>
</html>
"""


def main():
    territories = json.loads(TERRITORIES_PATH.read_text())
    postcode_areas = json.loads(POSTCODE_AREAS_PATH.read_text())
    n_total = len(territories["points"])
    logo_outline_b64 = base64.b64encode(LOGO_OUTLINE_PATH.read_bytes()).decode()
    logo_fill_b64 = base64.b64encode(LOGO_FILL_PATH.read_bytes()).decode()

    html = HTML_TEMPLATE.format(
        n_total=n_total,
        distance_cap_km=200.0,
        map_data_json=json.dumps(territories),
        postcode_areas_json=json.dumps(postcode_areas),
        logo_outline_b64=logo_outline_b64,
        logo_fill_b64=logo_fill_b64,
    )
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
