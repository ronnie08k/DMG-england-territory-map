"""Stage 1: clean, dedupe, and geocode the CQC dental practices spreadsheet.

The xlsx's own Latitude/Longitude columns are corrupted (Longitude often holds
constituency-name text; Latitude holds what looks like the true longitude) so
they are ignored entirely. The Postcode column is also blank for ~9,300 rows
because the real postcode is shifted into County or City / Town for those
rows (an upstream column-offset bug) -- recovered here via a regex scan.
"""
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

XLSX_PATH = "CQC_Dental_Practices_May2026 1.xlsx"
DATA_DIR = Path("data")
CACHE_PATH = DATA_DIR / "geocode_cache.json"
OUTPUT_PATH = DATA_DIR / "practices_geocoded.csv"

POSTCODE_RE = re.compile(r"^([A-Z]{1,2}[0-9][A-Z0-9]?)\s*([0-9][A-Z]{2})$", re.I)
POSTCODE_COLUMNS = ["Postcode", "County", "City / Town", "Address Line 1", "Address Line 2"]


def normalize_postcode(raw: str) -> str | None:
    m = POSTCODE_RE.match(raw.strip())
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2).upper()}"


def extract_postcode(row: pd.Series) -> tuple[str | None, str | None]:
    for col in POSTCODE_COLUMNS:
        val = row[col]
        if isinstance(val, str):
            pc = normalize_postcode(val)
            if pc:
                return pc, col
    return None, None


ADDRESS_LINE_COLS = ["Address Line 1", "Address Line 2", "City / Town"]
_ID_LIKE_RE = re.compile(r"^[0-9]{5,}$")


def build_display_address(row: pd.Series, postcode: str | None) -> str:
    """Best-effort address string. Several address columns are shifted/corrupted
    in the same way the postcode column is (see module docstring), so this skips
    any field that looks like a postcode or a long numeric ID rather than a real
    address line/town, and always appends the already-recovered postcode."""
    parts: list[str] = []
    for col in ADDRESS_LINE_COLS:
        val = row[col]
        if not isinstance(val, str):
            continue
        val = val.strip()
        if not val or normalize_postcode(val) or _ID_LIKE_RE.match(val.replace(" ", "")):
            continue
        if val not in parts:
            parts.append(val)
    if postcode:
        parts.append(postcode)
    return ", ".join(parts)


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache))


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def geocode_postcodes(postcodes: list[str], cache: dict, session: requests.Session) -> None:
    todo = [pc for pc in postcodes if pc not in cache]
    print(f"Geocoding {len(todo)} uncached postcodes ({len(postcodes) - len(todo)} already cached)...")
    for i in range(0, len(todo), 100):
        batch = todo[i : i + 100]
        resp = session.post(
            "https://api.postcodes.io/postcodes",
            json={"postcodes": batch},
            timeout=15,
        )
        resp.raise_for_status()
        for item in resp.json()["result"]:
            query = item["query"]
            result = item["result"]
            if result:
                cache[query] = {
                    "lat": result["latitude"],
                    "lon": result["longitude"],
                    "admin_district": result.get("admin_district"),
                    "precision": "exact",
                }
            else:
                cache[query] = None
        save_cache(cache)
        print(f"  batch {i // 100 + 1}/{-(-len(todo) // 100)} done")

    # Retry failures with outcode-level fallback.
    still_failed = [pc for pc in postcodes if cache.get(pc) is None]
    if still_failed:
        print(f"Falling back to outcode centroid for {len(still_failed)} unresolved postcodes...")
        outcode_cache: dict[str, dict | None] = {}
        for pc in still_failed:
            outcode = pc.split(" ")[0]
            if outcode not in outcode_cache:
                r = session.get(f"https://api.postcodes.io/outcodes/{outcode}", timeout=10)
                if r.ok and r.json().get("result"):
                    res = r.json()["result"]
                    outcode_cache[outcode] = {"lat": res["latitude"], "lon": res["longitude"]}
                else:
                    outcode_cache[outcode] = None
                time.sleep(0.05)
            fallback = outcode_cache[outcode]
            if fallback:
                cache[pc] = {
                    "lat": fallback["lat"],
                    "lon": fallback["lon"],
                    "admin_district": None,
                    "precision": "outcode_fallback",
                }
            else:
                cache[pc] = None
        save_cache(cache)


def main() -> None:
    df = pd.read_excel(XLSX_PATH)
    n_total = len(df)
    print(f"Loaded {n_total} rows")

    extracted = df.apply(extract_postcode, axis=1, result_type="expand")
    df["extracted_postcode"] = extracted[0]
    df["postcode_source_col"] = extracted[1]

    n_missing_pc = df["extracted_postcode"].isna().sum()
    if n_missing_pc:
        print(f"WARNING: {n_missing_pc} rows have no recoverable postcode:")
        print(df[df["extracted_postcode"].isna()][["Location ID", "Practice Name"]].to_string())
    print("Postcode recovered from column:")
    print(df["postcode_source_col"].value_counts(dropna=False).to_string())

    n_dormant = (df["Dormant"] == "Y").sum()
    df = df[df["Dormant"] != "Y"].copy()
    print(f"Dropped {n_dormant} dormant rows -> {len(df)} remaining")

    n_before_exact_dedup = len(df)
    df = df.drop_duplicates(
        subset=["Practice Name", "extracted_postcode", "Address Line 1", "Address Line 2"],
        keep="first",
    )
    print(f"Dropped {n_before_exact_dedup - len(df)} exact duplicate rows -> {len(df)} remaining")

    n_before_name_pc_dedup = len(df)
    df = df.drop_duplicates(subset=["Practice Name", "extracted_postcode"], keep="first")
    print(f"Dropped {n_before_name_pc_dedup - len(df)} more Name+Postcode duplicates -> {len(df)} remaining")

    df["display_address"] = df.apply(
        lambda row: build_display_address(row, row["extracted_postcode"]), axis=1
    )

    unique_postcodes = df["extracted_postcode"].dropna().unique().tolist()
    print(f"{len(unique_postcodes)} unique postcodes to geocode")

    cache = load_cache()
    session = make_session()
    geocode_postcodes(unique_postcodes, cache, session)

    n_exact = sum(1 for pc in unique_postcodes if cache.get(pc) and cache[pc]["precision"] == "exact")
    n_fallback = sum(1 for pc in unique_postcodes if cache.get(pc) and cache[pc]["precision"] == "outcode_fallback")
    n_failed = sum(1 for pc in unique_postcodes if not cache.get(pc))
    print(f"Geocode hit-rate: {n_exact} exact, {n_fallback} outcode-fallback, {n_failed} failed "
          f"({(n_exact + n_fallback) / len(unique_postcodes):.1%} resolved)")

    df["lat"] = df["extracted_postcode"].map(lambda pc: cache[pc]["lat"] if cache.get(pc) else None)
    df["lon"] = df["extracted_postcode"].map(lambda pc: cache[pc]["lon"] if cache.get(pc) else None)
    df["admin_district"] = df["extracted_postcode"].map(lambda pc: cache[pc]["admin_district"] if cache.get(pc) else None)
    df["geocode_precision"] = df["extracted_postcode"].map(lambda pc: cache[pc]["precision"] if cache.get(pc) else "failed")

    n_before_geo_drop = len(df)
    df = df[df["lat"].notna()].copy()
    print(f"Dropped {n_before_geo_drop - len(df)} rows with no geocode -> {len(df)} final rows")

    df["Nation"] = "England"

    out_cols = [
        "Location ID", "Practice Name", "extracted_postcode", "display_address", "lat", "lon",
        "geocode_precision", "admin_district", "City / Town", "Region",
        "ASM Name", "Area", "Nation",
    ]
    DATA_DIR.mkdir(exist_ok=True)
    df[out_cols].to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
