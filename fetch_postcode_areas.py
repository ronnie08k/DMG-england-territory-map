"""Fetch UK postcode AREA boundaries (RG, LS, NG, ...) covering all of Great
Britain (England, Wales, Scotland), simplify them for a lightweight map
overlay, and cache the result as data/postcode_areas.geojson.
"""
import json
import time
from pathlib import Path

import requests
from shapely.geometry import shape, mapping

DATA_DIR = Path("data")
OUTPUT_PATH = DATA_DIR / "postcode_areas.geojson"
SIMPLIFY_TOLERANCE_DEG = 0.004  # ~400m, fine for a country-wide area overview

BASE_URL = "https://raw.githubusercontent.com/missinglink/uk-postcode-polygons/master/geojson/{area}.geojson"
REPO_CONTENTS_URL = "https://api.github.com/repos/missinglink/uk-postcode-polygons/contents/geojson"


def list_all_areas() -> list[str]:
    r = requests.get(REPO_CONTENTS_URL, timeout=20)
    r.raise_for_status()
    return sorted(f["name"].replace(".geojson", "") for f in r.json())


def main():
    areas = list_all_areas()
    print(f"{len(areas)} postcode areas to fetch (all of Great Britain): {areas}")

    features = []
    failed = []
    for area in areas:
        fc = None
        for attempt in range(4):
            try:
                r = requests.get(BASE_URL.format(area=area), timeout=20)
                r.raise_for_status()
                fc = r.json()
                break
            except Exception as e:
                if attempt == 3:
                    failed.append(area)
                    print(f"  {area}: FAILED after retries ({e})")
                else:
                    time.sleep(1.5 * (attempt + 1))
        if fc is None:
            continue

        geoms = [shape(f["geometry"]) for f in fc["features"]]
        merged = geoms[0]
        for g in geoms[1:]:
            merged = merged.union(g)
        simplified = merged.simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)

        label_point = simplified.representative_point()
        features.append({
            "type": "Feature",
            "properties": {"area": area, "labelLat": label_point.y, "labelLon": label_point.x},
            "geometry": mapping(simplified),
        })
        print(f"  {area}: ok ({len(fc['features'])} raw parts)")

    if failed:
        print(f"Failed to fetch: {failed}")

    out = {"type": "FeatureCollection", "features": features}
    DATA_DIR.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(out, separators=(",", ":")))
    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
