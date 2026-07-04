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
  <div id="rep-legend"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<script>
const MAP_DATA = {map_data_json};
const POSTCODE_AREAS = {postcode_areas_json};

const REP_COLORS = ["#2a78d6", "#e34948", "#1baf7a", "#eda100", "#4a3aa7"];
const ORPHAN_COLOR = "#9a9890";

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

// ---- Points-by-rep layer ----
const pointsLayer = L.layerGroup();
const sharedCanvas = L.canvas({{ padding: 0.5 }});
function escapeHtml(s) {{
  return s.replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
}}
MAP_DATA.points.forEach(p => {{
  const [lat, lon, ri, name, address] = p;
  const color = ri >= 0 ? REP_COLORS[ri] : ORPHAN_COLOR;
  const latlng = [lat, lon];
  const popupHtml = name ? `<b>${{escapeHtml(name)}}</b>${{address ? '<br>' + escapeHtml(address) : ''}}` : null;

  // Bigger invisible hit-area underneath so tapping doesn't require pixel precision.
  // Leaflet's circle click detection is a pure geometric radius check, not pixel-based,
  // so fillOpacity 0 still registers clicks/taps with zero visual contribution (no glow
  // from thousands of overlapping near-transparent circles).
  if (popupHtml) {{
    L.circleMarker(latlng, {{
      radius: 9, weight: 0, fillOpacity: 0, fillColor: color, renderer: sharedCanvas
    }}).addTo(pointsLayer).bindPopup(popupHtml);
  }}

  // Small visible dot on top (not interactive so it doesn't block the hit-area click).
  // Fully opaque so overlapping dots stay flat colour instead of blending into a glow.
  L.circleMarker(latlng, {{
    radius: 2.2, weight: 0, fillOpacity: 1, fillColor: color,
    renderer: sharedCanvas, interactive: false
  }}).addTo(pointsLayer);
}});

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
