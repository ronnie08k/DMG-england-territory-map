"""Stage 2: territory assignment, redone per explicit geographic instructions.

Method:
  1. Rep "Leeds": every practice at or north of Chesterfield's latitude -- a flat
     horizontal line, no distance/capacity balancing. Leeds is the real existing
     manager for this area, so the hub stays fixed there (not a computed centroid).
  2. Rep "Solihull": every practice between Peterborough's latitude and
     Chesterfield's latitude, plus a pocket dipping down around Birmingham/
     Coventry so that conurbation is included. Solihull is the real existing
     manager for this area, so again the hub stays fixed there.
  3. The remaining "South" practices (below Peterborough's latitude, plus the
     Birmingham pocket carve-out) are split across 3 hubs: Reading (the third
     real existing manager, fixed) plus 2 free hubs located via a constrained
     Lloyd's iteration (k-means init, then iterate while Reading stays pinned),
     recentered on their own final territory's centroid once the assignment
     settles.
  4. Practices beyond ~200km (the prior OSRM-calibrated 3-hour-drive proxy) of
     their assigned southern hub become an "orphan" bucket.
  5. A capacity-constrained transportation-problem LP (scipy HiGHS, soft distance
     penalty so it's always feasible) assigns the southern practices across
     Reading + the 2 free hubs, capped at ~1.1x the even split.
  6. Zone-1 override: any practice whose nearest London tube/DLR/Overground/
     Elizabeth-line station is fare Zone 1 is forced onto whichever of the 5
     final hubs is closest to central London.
  7. The legacy ASM/Area split is reported next to the new split for comparison only.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import linprog
from sklearn.cluster import KMeans

from tfl_zones import tag_zone1

DATA_DIR = Path("data")
INPUT_PATH = DATA_DIR / "practices_geocoded.csv"
UK_INPUT_PATH = DATA_DIR / "practices_geocoded_uk.csv"
OUTPUT_JSON = DATA_DIR / "territories.json"
OUTPUT_CSV = DATA_DIR / "territory_assignment.csv"

# Manual postcode-AREA overrides (requested explicitly): these areas go whole to
# the given hub index regardless of what the geographic partition/LP would say.
# hub 1 = Solihull (fixed name); hub 3 = the westernmost southern free hub
# ("yellow", South-West-ish -- stable by construction since free hubs are
# sorted west-to-east, even though its name/exact position can shift by run).
# A value of ORPHAN forces the whole area to the beyond-200km/unassigned bucket.
ORPHAN = -1
AREA_OVERRIDES = {
    "WR": 1, "DY": 1, "WV": 1, "CV": 1, "B": 1, "SY": 1, "NR": 1, "LL": 1, "LN": 1,
    "CF": 3, "NP": 3, "SO": 3,
    # Resolved one-manager-per-postcode-area overlaps (2026-07-05):
    "AL": 2, "BN": 2, "CH": 1, "CR": 4, "CW": 1, "DG": ORPHAN, "LE": 1, "NE": 0,
    "NW": 4, "OX": 2, "PE": 1, "RH": 2, "S": 0, "SG": 4, "SW": 4,
    "TD": ORPHAN, "TN": 4, "TR": 3, "W": 4,
    # RG is Reading's own home postcode area -- lock it to Reading as a sanity
    # override regardless of what the area-level optimizer would otherwise pick.
    "RG": 2,
    # SE is inherently Greater London; its Zone-1 districts (SE1/SE17) were pulling it
    # apart from the rest of the area, which the area-level optimizer sent to Reading.
    # Keep the whole area with the London rep instead.
    "SE": 4,
    # Explicit requests (2026-07-05): NN to Solihull/red, PO/SP/SN to Somerset/yellow.
    "NN": 1, "PO": 3, "SP": 3, "SN": 3,
}

CHESTERFIELD_LAT = 53.2350
PETERBOROUGH_LAT = 52.5695
N_SOUTH_FREE_HUBS = 2
DISTANCE_CAP_KM = 200.0
EARTH_RADIUS_KM = 6371.0

LEEDS = {"name": "Leeds", "lat": 53.8008, "lon": -1.5491}
SOLIHULL = {"name": "Solihull", "lat": 52.4118, "lon": -1.7788}
READING = {"name": "Reading", "lat": 51.4543, "lon": -0.9781}

# The 2 free hubs' names are locked here rather than recomputed from their
# centroid's nearest town every run -- they'd already renamed once (Havering ->
# Barking and Dagenham) as overrides shifted the centroid, and would keep
# drifting with future edits otherwise.
FREE_HUB_NAMES = ["Somerset", "Barking and Dagenham"]


def midlands_south_boundary(lons):
    """Solihull's southern edge: Peterborough's latitude everywhere, except a dip
    down to 52.35 around Birmingham/Wolverhampton/Coventry (roughly lon -2.3 to
    -0.8) so that conurbation stays in Solihull's territory as requested, instead
    of falling just south of a strict flat Peterborough line."""
    pts_lon = np.array([-4.0, -2.3, -1.9, -1.3, -0.8, 1.5])
    pts_lat = np.array([PETERBOROUGH_LAT, PETERBOROUGH_LAT, 52.35, 52.35, PETERBOROUGH_LAT, PETERBOROUGH_LAT])
    return np.interp(lons, pts_lon, pts_lat)


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def dist_matrix(lats, lons, hub_lats, hub_lons):
    """N x H matrix of haversine distances (km)."""
    return haversine_km(
        lats[:, None], lons[:, None], hub_lats[None, :], hub_lons[None, :]
    )


def locate_free_hubs(lats, lons, fixed_lats, fixed_lons, k_free):
    """k_free hub locations via k-means init + Lloyd's iteration, with the given
    fixed hubs pinned throughout (they influence nearest-neighbour membership
    but never move)."""
    km = KMeans(n_clusters=k_free, n_init=10, random_state=0)
    km.fit(np.column_stack([lats, lons]))
    free_lats = km.cluster_centers_[:, 0].copy()
    free_lons = km.cluster_centers_[:, 1].copy()

    print(f"Running constrained Lloyd's iteration for {k_free} free hub(s)...")
    for it in range(25):
        all_lats = np.concatenate([fixed_lats, free_lats])
        all_lons = np.concatenate([fixed_lons, free_lons])
        d = dist_matrix(lats, lons, all_lats, all_lons)
        nearest = d.argmin(axis=1)
        new_lats, new_lons = free_lats.copy(), free_lons.copy()
        for c in range(k_free):
            mask = nearest == (len(fixed_lats) + c)
            if mask.sum() > 0:
                new_lats[c] = lats[mask].mean()
                new_lons[c] = lons[mask].mean()
        moved = np.abs(new_lats - free_lats).sum() + np.abs(new_lons - free_lons).sum()
        free_lats, free_lons = new_lats, new_lons
        if moved < 1e-5:
            print(f"  converged after {it + 1} iterations")
            break
    return free_lats, free_lons


def nearest_town_name(lat, lon, df):
    """Name-only lookup -- does NOT move the hub coordinate."""
    d = haversine_km(lat, lon, df["lat"].values, df["lon"].values)
    nearest_idx = d.argmin()
    town = df.iloc[nearest_idx]["admin_district"]
    if pd.isna(town):
        town = df.iloc[nearest_idx]["City / Town"]
    return str(town)


def solve_assignment(lats, lons, hub_lats, hub_lons, caps, weights):
    """Assigns whole units (postcode districts), each carrying a practice-count
    `weight`, to hubs -- never splits a unit's weight across two hubs, since each
    row's variables sum to exactly 1 (one hub gets the whole unit).
    caps: scalar (uniform cap) or a per-hub array/list of length h.
    """
    n, h = len(lats), len(hub_lats)
    cost = dist_matrix(lats, lons, hub_lats, hub_lons)
    # Soft penalty rather than a hard (0,0) bound beyond the cap: a hard exclusion
    # can make the LP outright infeasible if a pocket of units only has one hub
    # within cap and that hub's capacity is exceeded. The penalty keeps the
    # problem always feasible while still strongly discouraging over-cap
    # assignments; anything that ends up beyond the cap gets flagged as an
    # orphan by the caller based on the actual assigned distance.
    penalised_cost = np.where(cost > DISTANCE_CAP_KM, cost + 1e5, cost)
    # Weight cost by practice count so a large postcode district assigned far
    # away costs proportionally more (reflects real total travel burden).
    weighted_cost = penalised_cost * weights[:, None]

    c = weighted_cost.flatten()
    bounds = (0, 1)

    eq_rows = np.repeat(np.arange(n), h)
    eq_cols = np.arange(n * h)
    A_eq = sp.csr_matrix((np.ones(n * h), (eq_rows, eq_cols)), shape=(n, n * h))
    b_eq = np.ones(n)

    ub_rows = np.tile(np.arange(h), n)
    ub_cols = np.arange(n * h)
    ub_data = np.repeat(weights, h)
    A_ub = sp.csr_matrix((ub_data, (ub_rows, ub_cols)), shape=(h, n * h))
    b_ub = np.broadcast_to(np.asarray(caps, dtype=float), (h,)).copy()

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"LP failed: {res.message}")
    x = res.x.reshape(n, h)
    return x.argmax(axis=1)


def main():
    df = pd.read_csv(INPUT_PATH)
    uk_df = pd.read_csv(UK_INPUT_PATH)
    df = pd.concat([df, uk_df], ignore_index=True)
    print(f"Loaded {len(df)} practices total (incl. {len(uk_df)} from Wales/Scotland/Northern Ireland)")

    n_iow = int((df["admin_district"] == "Isle of Wight").sum())
    df = df[df["admin_district"] != "Isle of Wight"].reset_index(drop=True)
    print(f"Excluded {n_iow} Isle of Wight practices from the map entirely (per request)")

    # Assign whole postcode districts (outcodes), not individual practices, so a
    # single district (e.g. "RG1") never gets split between two managers.
    df["outcode"] = df["extracted_postcode"].str.split(" ").str[0]
    df["area"] = df["outcode"].str.extract(r"^([A-Z]{1,2})")
    oc = df.groupby("outcode").agg(
        lat=("lat", "mean"), lon=("lon", "mean"), weight=("lat", "size"), area=("area", "first"),
    ).reset_index()
    print(f"{len(oc)} postcode districts covering {len(df)} practices")

    oc_lats = oc["lat"].values
    oc_lons = oc["lon"].values
    oc_weights = oc["weight"].values

    # North/Midlands are a hard geographic partition by latitude with no
    # distance cap -- fine within England (Newcastle to Leeds is ~150km), but
    # now that Wales/Scotland/NI are in the mix, Scotland and Northern Ireland
    # (a separate island, unreachable by the same "drive there" logic) would
    # otherwise get dumped wholesale onto Leeds just by being north of
    # Chesterfield's latitude. So the same 200km cap used everywhere else also
    # applies here: anything north of the line but too far from Leeds/Solihull
    # becomes an orphan instead.
    oc_dist_leeds = haversine_km(oc_lats, oc_lons, LEEDS["lat"], LEEDS["lon"])
    oc_dist_solihull = haversine_km(oc_lats, oc_lons, SOLIHULL["lat"], SOLIHULL["lon"])

    south_boundary_lat = midlands_south_boundary(oc_lons)
    north_line_mask = oc_lats >= CHESTERFIELD_LAT
    mid_line_mask = (oc_lats >= south_boundary_lat) & (oc_lats < CHESTERFIELD_LAT)
    south_mask = oc_lats < south_boundary_lat

    north_mask = north_line_mask & (oc_dist_leeds <= DISTANCE_CAP_KM)
    mid_mask = mid_line_mask & (oc_dist_solihull <= DISTANCE_CAP_KM)
    north_mid_orphan_mask = (north_line_mask & ~north_mask) | (mid_line_mask & ~mid_mask)

    print(f"North of Chesterfield ({CHESTERFIELD_LAT}) -> Leeds: {oc_weights[north_mask].sum()} practices "
          f"({north_mask.sum()} postcode districts)")
    print(f"Midlands band incl. Birmingham/Coventry pocket -> Solihull: {oc_weights[mid_mask].sum()} practices "
          f"({mid_mask.sum()} postcode districts)")
    print(f"North/Midlands practices beyond {DISTANCE_CAP_KM:.0f}km of Leeds/Solihull -> orphan bucket: "
          f"{oc_weights[north_mid_orphan_mask].sum()} practices ({north_mid_orphan_mask.sum()} postcode districts)")
    print(f"South of Peterborough ({PETERBOROUGH_LAT}): {oc_weights[south_mask].sum()} practices "
          f"({south_mask.sum()} postcode districts)")

    south_outcodes = set(oc.loc[south_mask, "outcode"])
    south_practices_df = df[df["outcode"].isin(south_outcodes)]
    south_lats = oc_lats[south_mask]
    south_lons = oc_lons[south_mask]
    south_weights = oc_weights[south_mask]
    free_lats, free_lons = locate_free_hubs(
        south_lats, south_lons,
        np.array([READING["lat"]]), np.array([READING["lon"]]),
        N_SOUTH_FREE_HUBS,
    )
    # Stable ordering across reruns: west to east.
    order = np.argsort(free_lons)
    free_lats, free_lons = free_lats[order], free_lons[order]

    # hubs[0]=Leeds, [1]=Solihull, [2]=Reading are FIXED real manager locations.
    # hubs[3],[4] are the 2 free southern hubs -- working positions here, then
    # recentered on their own final territory's centroid further down.
    hubs = [dict(LEEDS), dict(SOLIHULL), dict(READING)]
    for k in range(N_SOUTH_FREE_HUBS):
        town = nearest_town_name(free_lats[k], free_lons[k], south_practices_df)
        hubs.append({"name": town, "lat": float(free_lats[k]), "lon": float(free_lons[k])})
        print(f"Free south hub {k+1} -> {town} ({free_lats[k]:.4f}, {free_lons[k]:.4f})")
    FIXED_HUB_IDX = {0, 1, 2}

    hub_lats = np.array([h["lat"] for h in hubs])
    hub_lons = np.array([h["lon"] for h in hubs])

    oc_rep_idx = np.full(len(oc), -1, dtype=int)
    oc_rep_idx[north_mask] = 0
    oc_rep_idx[mid_mask] = 1
    oc_is_orphan = north_mid_orphan_mask.copy()

    south_hub_lats = hub_lats[2:]
    south_hub_lons = hub_lons[2:]
    n_south_hubs = len(south_hub_lats)
    uniform_cap = int(np.ceil(south_weights.sum() / n_south_hubs * 1.1))

    # Rebalance: the manual AREA_OVERRIDES force-assign specific postcode areas onto
    # specific southern hubs *after* this optimizer runs, and they've been landing
    # disproportionately on Barking and Dagenham. Since an overridden district's
    # optimizer-stage assignment is thrown away regardless, exclude those districts
    # from the optimizer entirely (rather than just capping around them, which made the
    # problem infeasible -- total caps must still cover total demand) and only let it
    # freely place the non-overridden "free" postcode AREAS, with differentiated caps
    # sized to the free-pool total so the *final* per-hub totals (free + override) end
    # up close to even instead of the optimizer's own even split getting skewed
    # downstream. Assigning whole AREAS (not individual districts) here -- rather than
    # districts that get aggregated up after the fact -- guarantees the tighter caps
    # can never split a postcode area between two hubs, no matter how they're tuned.
    south_areas = oc.loc[south_mask, "area"].values
    south_override_mask = pd.Series(south_areas).isin(AREA_OVERRIDES).values
    free_areas = south_areas[~south_override_mask]
    free_lats_d = south_lats[~south_override_mask]
    free_lons_d = south_lons[~south_override_mask]
    free_weights_d = south_weights[~south_override_mask]

    free_area_df = pd.DataFrame({"area": free_areas, "lat": free_lats_d, "lon": free_lons_d, "weight": free_weights_d})
    area_agg = free_area_df.groupby("area").apply(
        lambda g: pd.Series({
            "lat": np.average(g["lat"], weights=g["weight"]),
            "lon": np.average(g["lon"], weights=g["weight"]),
            "weight": g["weight"].sum(),
        }), include_groups=False,
    ).reset_index()
    free_total = area_agg["weight"].sum()
    override_topup = {2: 670, 3: 494, 4: 1148}  # Reading, Somerset, Barking and Dagenham (known override gains)
    even_target = south_weights.sum() / n_south_hubs
    south_caps = np.array([
        max(even_target - override_topup[2], 0),
        max(even_target - override_topup[3], 0),
        max(even_target - override_topup[4], 0),
    ])
    print(f"South free-pool ({len(area_agg)} postcode areas, {free_total} of {south_weights.sum()} practices, "
          f"rest are override-locked) per-hub capacity caps: Reading={south_caps[0]:.0f}, "
          f"Somerset={south_caps[1]:.0f}, Barking and Dagenham={south_caps[2]:.0f} (even split would be {uniform_cap})")

    area_assigned = solve_assignment(
        area_agg["lat"].values, area_agg["lon"].values, south_hub_lats, south_hub_lons,
        south_caps, area_agg["weight"].values,
    )
    area_assigned_dist = dist_matrix(area_agg["lat"].values, area_agg["lon"].values, south_hub_lats, south_hub_lons)[
        np.arange(len(area_agg)), area_assigned
    ]
    area_is_orphan = area_assigned_dist > DISTANCE_CAP_KM
    n_south_orphan = int(area_agg.loc[area_is_orphan, "weight"].sum())
    print(f"{n_south_orphan} southern practices (in {int(area_is_orphan.sum())} postcode areas) ended up beyond "
          f"{DISTANCE_CAP_KM:.0f}km of their assigned hub -> orphan bucket")

    area_to_hub = dict(zip(area_agg["area"], area_assigned))
    area_to_orphan = dict(zip(area_agg["area"], area_is_orphan))
    south_assigned = np.full(south_mask.sum(), -1, dtype=int)
    south_is_orphan = np.zeros(south_mask.sum(), dtype=bool)
    free_idx = np.where(~south_override_mask)[0]
    south_assigned[free_idx] = [area_to_hub[a] for a in free_areas]
    south_is_orphan[free_idx] = [area_to_orphan[a] for a in free_areas]

    global_south_idx = np.where(south_mask)[0]
    oc_is_orphan[global_south_idx[south_is_orphan]] = True
    oc_rep_idx[global_south_idx] = np.where(south_is_orphan, -1, south_assigned + 2)  # offset: hubs 2,3,4 are southern

    oc_dist = dist_matrix(oc_lats, oc_lons, hub_lats, hub_lons)
    oc_min_dist = oc_dist.min(axis=1)

    zone1_mask = tag_zone1(oc_lats, oc_lons)
    central_london = (51.5074, -0.1278)
    hub_to_london = haversine_km(hub_lats, hub_lons, *central_london)
    ne_london_idx = int(np.argmin(hub_to_london))
    n_zone1_reassigned = int(oc_weights[(zone1_mask) & (oc_rep_idx != ne_london_idx) & (oc_rep_idx != -1)].sum())
    oc_rep_idx[zone1_mask & (oc_rep_idx != -1)] = ne_london_idx
    print(f"Zone-1 override: {n_zone1_reassigned} practices moved to {hubs[ne_london_idx]['name']}")

    # Manual postcode-AREA overrides: e.g. WR/DY/WV/CV go whole to Solihull,
    # CF/NP go whole to the yellow south-west hub, regardless of the above.
    for area, hub_i in AREA_OVERRIDES.items():
        area_mask = oc["area"] == area
        n_moved = int(oc_weights[area_mask & (oc_rep_idx != hub_i)].sum())
        oc_rep_idx[area_mask] = hub_i
        oc_is_orphan[area_mask] = hub_i == ORPHAN
        dest = "orphan/unassigned" if hub_i == ORPHAN else hubs[hub_i]["name"]
        print(f"Postcode area override: {area} -> {dest} ({n_moved} practices moved)")

    n_orphan = int(oc_weights[oc_is_orphan].sum())

    oc["rep_index"] = oc_rep_idx
    oc["is_orphan"] = oc_is_orphan
    oc["distance_to_hub_km"] = [
        oc_dist[i, oc_rep_idx[i]] if oc_rep_idx[i] >= 0 else oc_min_dist[i] for i in range(len(oc))
    ]

    # Propagate each postcode district's single assignment to every practice in it.
    df = df.merge(oc[["outcode", "rep_index", "is_orphan", "distance_to_hub_km"]], on="outcode", how="left")

    # Recenter only the 2 free hubs on the actual middle (centroid) of their
    # final territory. Leeds/Solihull/Reading stay fixed at their real locations.
    # Names for the free hubs are locked to FREE_HUB_NAMES (see comment above),
    # not recomputed from the centroid, so they stop drifting between runs.
    for i, h in enumerate(hubs):
        mask = df["rep_index"] == i
        h["count"] = int(mask.sum())
        if i not in FIXED_HUB_IDX and h["count"] > 0:
            h["lat"] = float(df.loc[mask, "lat"].mean())
            h["lon"] = float(df.loc[mask, "lon"].mean())
            h["name"] = FREE_HUB_NAMES[i - len(FIXED_HUB_IDX)]

    print("\nFinal territory split:")
    for h in hubs:
        print(f"  {h['name']:30s} ({h['lat']:.4f}, {h['lon']:.4f})  {h['count']} practices")
    print(f"  {'Beyond 200km of any hub (incl. Scotland/NI)':30s} {'':17s}  {n_orphan} practices")

    print("\nLegacy ASM/Area split (informational only, not used to constrain the new split):")
    print(df["Area"].value_counts(dropna=False).to_string())

    print("\nCrosstab: legacy Area vs new rep assignment (counts):")
    df["new_rep"] = df["rep_index"].map(lambda i: hubs[i]["name"] if i >= 0 else "orphan")
    print(pd.crosstab(df["Area"].fillna("(none)"), df["new_rep"]).to_string())

    # Postcode-area code -> official post town name (e.g. "RG" -> "Reading"), for
    # listing which areas each rep covers in the map's legend.
    area_names = json.loads((DATA_DIR / "postcode_area_names.json").read_text())
    for h in hubs:
        h["areas"] = []
    for area, area_df in df[df["rep_index"] >= 0].groupby("area"):
        rep_i = int(area_df["rep_index"].iloc[0])
        hubs[rep_i]["areas"].append({"code": area, "name": area_names.get(area, area)})
    for h in hubs:
        h["areas"].sort(key=lambda a: a["code"])

    map_data = {
        "points": [
            [float(lat), float(lon), int(ri), name, addr]
            for lat, lon, ri, name, addr in zip(
                df["lat"], df["lon"], df["rep_index"],
                df["Practice Name"], df["display_address"].fillna(""),
            )
        ],
        "reps": [
            {"name": h["name"], "lat": h["lat"], "lon": h["lon"], "count": h["count"], "areas": h["areas"]}
            for h in hubs
        ],
        "orphanCount": n_orphan,
    }
    DATA_DIR.mkdir(exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(map_data))
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {OUTPUT_JSON} and {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
