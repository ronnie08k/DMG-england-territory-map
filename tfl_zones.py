"""Fetch TfL tube/DLR/Overground/Elizabeth line stop points and their fare zones.

Used to reproduce the prior build's Zone-1 override: every dental practice whose
nearest station is in fare Zone 1 gets forced onto the NE London rep regardless
of what the distance-based territory optimizer decides.
"""
import json
from pathlib import Path

import numpy as np
import requests

DATA_DIR = Path("data")
CACHE_PATH = DATA_DIR / "tfl_stations.json"

MODES = ["tube", "dlr", "overground", "elizabeth-line"]


def fetch_stations() -> list[dict]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())

    stop_points = []
    for mode in MODES:
        resp = requests.get(f"https://api.tfl.gov.uk/StopPoint/Mode/{mode}", timeout=60)
        resp.raise_for_status()
        stop_points.extend(resp.json()["stopPoints"])
        print(f"  fetched {mode}: {len(resp.json()['stopPoints'])} stop points")

    stations = []
    for sp in stop_points:
        zone = None
        for prop in sp.get("additionalProperties", []):
            if prop.get("key") == "Zone":
                zone = prop.get("value")
        lat, lon = sp.get("lat"), sp.get("lon")
        if lat is None or lon is None:
            continue
        stations.append({
            "name": sp.get("commonName"),
            "lat": lat,
            "lon": lon,
            "zone": zone,
        })

    DATA_DIR.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(stations))
    return stations


def is_zone1(zone_str: str | None) -> bool:
    if not zone_str or zone_str == "NA":
        return False
    # Boundary zones are encoded like "1+2" or "1/2".
    return "1" in zone_str.replace("+", "/").split("/")


def tag_zone1(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """For each (lat, lon), find nearest station and return whether it's Zone 1."""
    stations = fetch_stations()
    s_lat = np.radians(np.array([s["lat"] for s in stations]))
    s_lon = np.radians(np.array([s["lon"] for s in stations]))
    s_zone1 = np.array([is_zone1(s["zone"]) for s in stations])

    p_lat = np.radians(lats)
    p_lon = np.radians(lons)

    result = np.zeros(len(lats), dtype=bool)
    # Chunk to keep memory bounded (N_practices x N_stations pairwise haversine).
    chunk = 500
    for start in range(0, len(lats), chunk):
        end = start + chunk
        dlat = p_lat[start:end, None] - s_lat[None, :]
        dlon = p_lon[start:end, None] - s_lon[None, :]
        a = np.sin(dlat / 2) ** 2 + np.cos(p_lat[start:end, None]) * np.cos(s_lat[None, :]) * np.sin(dlon / 2) ** 2
        dist = 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        nearest_idx = np.argmin(dist, axis=1)
        result[start:end] = s_zone1[nearest_idx]
    return result


if __name__ == "__main__":
    stations = fetch_stations()
    n_zone1 = sum(is_zone1(s["zone"]) for s in stations)
    print(f"{len(stations)} stations fetched, {n_zone1} tagged Zone 1")
