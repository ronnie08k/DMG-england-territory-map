"""Stage 3: render the self-contained Leaflet HTML map from data/territories.json."""
import json
from pathlib import Path

DATA_DIR = Path("data")
TERRITORIES_PATH = DATA_DIR / "territories.json"
POSTCODE_AREAS_PATH = DATA_DIR / "postcode_areas.geojson"
OUTPUT_PATH = Path("Dental_Practices_Heatmap.html")

HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>DMG Dental Practices — England Heatmap & Rep Territory Plan</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="vendor/leaflet.css" />
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
  #loading-overlay {{
    position:fixed; inset:0; z-index:5000; background:#14181f; color:#fff;
    display:flex; flex-direction:column; align-items:center; justify-content:center; gap:14px;
    font-size:14px;
  }}
  .spinner {{
    width:34px; height:34px; border-radius:50%; border:3px solid rgba(255,255,255,0.25);
    border-top-color:#fff; animation:spin .8s linear infinite;
  }}
  @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
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
</style>
</head>
<body>

<div id="loading-overlay"><div class="spinner"></div>Loading map&hellip;</div>

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

<script src="vendor/leaflet.js"></script>
<script src="vendor/leaflet-heat.js"></script>
<script>
const MAP_DATA = {map_data_json};
const POSTCODE_AREAS = {postcode_areas_json};

const REP_COLORS = ["#2a78d6", "#e34948", "#1baf7a", "#eda100", "#4a3aa7"];
const ORPHAN_COLOR = "#9a9890";

// Deferred one tick so the browser actually paints #loading-overlay before this
// heavy synchronous setup runs (a blocking <script> can otherwise suppress the
// first paint entirely, making the overlay never visibly appear).
setTimeout(initMap, 0);

function initMap() {{

const map = L.map('map', {{ preferCanvas: true }}).setView([52.9, -1.6], 6);

const voyager = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: 'abcd', maxZoom: 20
}}).addTo(map);

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

// ---- Points-by-rep layer (built lazily -- see buildPointsLayer below -- since it's
// ~10,900 circleMarkers and this layer is hidden by default) ----
const pointsLayer = L.layerGroup();
let pointsBuilt = false;
function escapeHtml(s) {{
  return s.replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
}}
function buildPointsLayer() {{
  const sharedCanvas = L.canvas({{ padding: 0.5 }});
  // One marker per practice (not two): Leaflet's canvas renderer redraws every path
  // on a renderer whenever any one changes, so halving the path count (was a separate
  // invisible radius-9 tap-target plus a visible radius-2.2 dot, ~21,826 paths total)
  // roughly halves the redraw cost of toggling this layer. radius 4 is a compromise
  // between the old tiny 2.2px dot and the old 9px tap-target -- a bit chunkier-looking
  // than before, but still reasonably tappable, for meaningfully less lag.
  MAP_DATA.points.forEach(p => {{
    const [lat, lon, ri, name, address] = p;
    const color = ri >= 0 ? REP_COLORS[ri] : ORPHAN_COLOR;
    const latlng = [lat, lon];
    const popupHtml = name ? `<b>${{escapeHtml(name)}}</b>${{address ? '<br>' + escapeHtml(address) : ''}}` : null;

    // Fully opaque so overlapping dots stay flat colour instead of blending into a glow.
    const marker = L.circleMarker(latlng, {{
      radius: 4, weight: 0, fillOpacity: 1, fillColor: color, renderer: sharedCanvas
    }}).addTo(pointsLayer);
    if (popupHtml) marker.bindPopup(popupHtml);
  }});
}}

// ---- Postcode area overlay (RG, LS, NG, ...), also built lazily (~240 layers,
// hidden by default) ----
const postcodeLayer = L.layerGroup();
let postcodeBuilt = false;
function buildPostcodeLayer() {{
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
}}
document.getElementById('toggle-postcodes').addEventListener('change', (e) => {{
  if (e.target.checked) {{
    if (!postcodeBuilt) {{ buildPostcodeLayer(); postcodeBuilt = true; }}
    postcodeLayer.addTo(map);
  }} else {{
    map.removeLayer(postcodeLayer);
  }}
}});

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
  if (e.target.checked) {{
    if (!pointsBuilt) {{ buildPointsLayer(); pointsBuilt = true; }}
    pointsLayer.addTo(map);
  }} else {{
    map.removeLayer(pointsLayer);
  }}
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

document.getElementById('loading-overlay').style.display = 'none';

}} // end initMap
</script>
</body>
</html>
"""


def main():
    territories = json.loads(TERRITORIES_PATH.read_text())
    postcode_areas = json.loads(POSTCODE_AREAS_PATH.read_text())
    n_total = len(territories["points"])

    html = HTML_TEMPLATE.format(
        n_total=n_total,
        distance_cap_km=200.0,
        map_data_json=json.dumps(territories),
        postcode_areas_json=json.dumps(postcode_areas),
    )
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
