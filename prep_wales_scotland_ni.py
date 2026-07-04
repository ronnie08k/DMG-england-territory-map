"""Stage 1b: clean and geocode the Wales/Scotland/Northern Ireland dental
practices workbook, producing a CSV in the same shape as practices_geocoded.csv
so it can be concatenated with the England (CQC) data.

Unlike the CQC file, these three sheets (one per nation, from HIW/PHS/BSO
respectively) are clean, un-shifted data -- no column-corruption workarounds
needed, just per-sheet column-name normalization.
"""
import json
from pathlib import Path

import pandas as pd

from prep_data import geocode_postcodes, load_cache, make_session, normalize_postcode

XLSX_PATH = "Dental_Practices_Wales_Scotland_NI.xlsx"
DATA_DIR = Path("data")
OUTPUT_PATH = DATA_DIR / "practices_geocoded_uk.csv"


def load_wales() -> pd.DataFrame:
    df = pd.read_excel(XLSX_PATH, sheet_name="Wales (HIW)")
    out = pd.DataFrame({
        "Practice Name": df["Service name"],
        "raw_postcode": df["Postcode"],
        "address_parts": df[["Address line 1", "Address line 2"]].apply(
            lambda r: ", ".join(str(v) for v in r if pd.notna(v)), axis=1
        ),
        "Nation": "Wales",
    })
    return out


def load_scotland() -> pd.DataFrame:
    df = pd.read_excel(XLSX_PATH, sheet_name="Scotland (PHS)")
    out = pd.DataFrame({
        "Practice Name": df["Practice Name"],
        "raw_postcode": df["Postcode"],
        "address_parts": df[["Address Line 1", "Address Line 2"]].apply(
            lambda r: ", ".join(str(v) for v in r if pd.notna(v)), axis=1
        ),
        "Nation": "Scotland",
    })
    return out


def load_ni() -> pd.DataFrame:
    df = pd.read_excel(XLSX_PATH, sheet_name="Northern Ireland (BSO)")

    def split_name(addr: str) -> tuple[str, str]:
        first, _, rest = str(addr).partition(",")
        first = first.strip()
        if first[:1].isdigit():
            return str(addr).strip(), str(addr).strip()
        return first, rest.strip().lstrip(",").strip()

    parsed = df["ADDRESS"].apply(split_name)
    out = pd.DataFrame({
        "Practice Name": parsed.map(lambda t: t[0]),
        "raw_postcode": df["POSTCODE"],
        "address_parts": parsed.map(lambda t: t[1]),
        "Nation": "Northern Ireland",
    })
    return out


def main():
    parts = [load_wales(), load_scotland(), load_ni()]
    df = pd.concat(parts, ignore_index=True)
    n_total = len(df)
    print(f"Loaded {n_total} rows across Wales/Scotland/NI")

    df["extracted_postcode"] = df["raw_postcode"].apply(
        lambda v: normalize_postcode(str(v)) if pd.notna(v) else None
    )
    n_missing = df["extracted_postcode"].isna().sum()
    if n_missing:
        print(f"WARNING: {n_missing} rows have no valid postcode, dropping:")
        print(df[df["extracted_postcode"].isna()][["Practice Name", "raw_postcode"]].to_string())
    df = df[df["extracted_postcode"].notna()].copy()

    n_before_dedup = len(df)
    df = df.drop_duplicates(subset=["Practice Name", "extracted_postcode"], keep="first")
    print(f"Dropped {n_before_dedup - len(df)} Name+Postcode duplicates -> {len(df)} remaining")

    df["display_address"] = df.apply(
        lambda r: ", ".join(p for p in [r["address_parts"], r["extracted_postcode"]] if p), axis=1
    )

    unique_postcodes = df["extracted_postcode"].unique().tolist()
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

    df["City / Town"] = None
    df["Region"] = None
    df["ASM Name"] = None
    df["Area"] = None

    out_cols = [
        "Location ID", "Practice Name", "extracted_postcode", "display_address", "lat", "lon",
        "geocode_precision", "admin_district", "City / Town", "Region",
        "ASM Name", "Area", "Nation",
    ]
    df["Location ID"] = None
    DATA_DIR.mkdir(exist_ok=True)
    df[out_cols].to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT_PATH}")

    print("\nBy nation:")
    print(df["Nation"].value_counts().to_string())


if __name__ == "__main__":
    main()
