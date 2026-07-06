"""Stage 1c: extract Republic of Ireland dental practices for the map.

Unlike the CQC (England) and Wales/Scotland/NI sources, this workbook already
has resolved Latitude/Longitude for every row (from the sales-intelligence
enrichment), so no postcode geocoding is needed here -- just pull the columns
straight through. Ireland practices aren't part of the 5-rep England
territory system (they're not reachable from any hub), so this writes a
simple standalone CSV; assign_territories.py appends them as unassigned
(orphan) points directly rather than running them through the rep-assignment
pipeline.
"""
from pathlib import Path

import pandas as pd

XLSX_PATH = "Dental_Practices_Ireland_Sales_Intelligence.xlsm"
DATA_DIR = Path("data")
OUTPUT_PATH = DATA_DIR / "practices_ireland.csv"


def build_display_address(row: pd.Series) -> str:
    parts = []
    for col in ("Address", "Town", "County", "Eircode"):
        val = row[col]
        if isinstance(val, str) and val.strip():
            val = val.strip()
            if not parts or val.lower() != parts[-1].lower():
                parts.append(val)
    return ", ".join(parts)


def main():
    df = pd.read_excel(XLSX_PATH, sheet_name="Accounts")
    n_total = len(df)
    print(f"Loaded {n_total} rows from the Accounts sheet")

    df = df[df["Practice Name"].notna() & df["Latitude"].notna() & df["Longitude"].notna()].copy()
    print(f"Dropped {n_total - len(df)} rows missing name/lat/lon -> {len(df)} remaining")

    df["display_address"] = df.apply(build_display_address, axis=1)

    out = pd.DataFrame({
        "Practice Name": df["Practice Name"],
        "lat": df["Latitude"].astype(float),
        "lon": df["Longitude"].astype(float),
        "display_address": df["display_address"],
        "Nation": "Ireland",
    })
    DATA_DIR.mkdir(exist_ok=True)
    out.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(out)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
