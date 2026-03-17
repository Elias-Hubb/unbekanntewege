import json, re, pandas as pd

def load_location_history(filename: str) -> pd.DataFrame:
    """
    Parse a Google or Apple location history JSON file.
    Returns a deduplicated DataFrame with columns: lat, lon, time (UTC).
    """
    with open(filename) as f:
        data = json.load(f)

    def parse_geo(s):
        nums = re.findall(r"[-\d.]+", str(s).replace("geo:", ""))
        return (float(nums[0]), float(nums[1])) if len(nums) == 2 else None

    points = []

    # ── Google format ──────────────────────────────────────────────────────────
    if isinstance(data, dict) and "semanticSegments" in data:
        print("Detected: Google format")
        for seg in data["semanticSegments"]:
            for pt in seg.get("timelinePath", []):
                coords = parse_geo(pt["point"])
                if coords:
                    points.append({"lat": coords[0], "lon": coords[1], "time": pt["time"]})

            act = seg.get("activity", {})
            for field, tkey in [("start", "startTime"), ("end", "endTime")]:
                raw = act.get(field, {})
                geo = raw.get("latLng", "") if isinstance(raw, dict) else raw
                coords = parse_geo(geo)
                if coords:
                    points.append({"lat": coords[0], "lon": coords[1], "time": seg.get(tkey)})

            vis = seg.get("visit", {})
            geo = vis.get("topCandidate", {}).get("placeLocation", {})
            if isinstance(geo, dict):
                geo = geo.get("latLng", "")
            coords = parse_geo(geo)
            if coords:
                points.append({"lat": coords[0], "lon": coords[1], "time": seg.get("startTime")})

    # ── Apple format ───────────────────────────────────────────────────────────
    elif isinstance(data, list):
        print("Detected: Apple format")
        for seg in data:
            start_time = seg.get("startTime")

            for pt in seg.get("timelinePath", []):
                coords = parse_geo(pt.get("point", ""))
                if not coords:
                    continue
                offset = pt.get("durationMinutesOffsetFromStartTime")
                if offset is not None and start_time is not None:
                    t = pd.Timestamp(start_time, tz="UTC") + pd.Timedelta(minutes=float(offset))
                else:
                    t = start_time
                points.append({"lat": coords[0], "lon": coords[1], "time": t})

            act = seg.get("activity", {})
            for field, tkey in [("start", "startTime"), ("end", "endTime")]:
                coords = parse_geo(act.get(field, ""))
                if coords:
                    points.append({"lat": coords[0], "lon": coords[1], "time": seg.get(tkey)})

            vis = seg.get("visit", {})
            geo = vis.get("topCandidate", {}).get("placeLocation", "")
            coords = parse_geo(geo)
            if coords:
                points.append({"lat": coords[0], "lon": coords[1], "time": start_time})

    else:
        print("❌ Unrecognised format — please share the top-level structure.")
        return pd.DataFrame()

    df = pd.DataFrame(points).drop_duplicates()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    print(f"✓ Extracted {len(df):,} points")
    print(f"  Date range: {df['time'].min().date()} → {df['time'].max().date()}")
    return df

import pickle
from tqdm.notebook import tqdm

def compute_edge_counts(df_city, G, stepsize=1, save_path=None):
    """
    Snap location points to nearest street edges and count visits per segment.
    """

    import osmnx as ox
    import pandas as pd
    import pickle

    df_sample = df_city.iloc[::stepsize].reset_index(drop=True)
    print(f"Snapping {len(df_sample):,} points to streets...")

    # vectorized snapping
    edges = ox.nearest_edges(
        G,
        X=df_sample["lon"],
        Y=df_sample["lat"]
    )

    # edges is a list of (u,v,k)
    edge_counts_series = pd.Series(edges).value_counts()
    edge_counts = edge_counts_series.to_dict()

    print(f"✓ Unique street segments used: {len(edge_counts):,}")

    if save_path:
        with open(save_path, "wb") as f:
            pickle.dump(edge_counts, f)
        print(f"Saved → {save_path}")

    return edge_counts