"""
Web layers for the Day 18 map.

  buildings.pmtiles  layer "b": d (walk m to the nearest assembly area, -1 = no walkable way), n (route node id),
                     a (assembly area id), p (people, 1 decimal)
  mahalle.geojson    per mahalle: people, people > 500 m, share, assembly areas, m² per person, data gap
  points.geojson     assembly areas: name, mahalle, district, area (null = not in a mapped open space), kind
  tree/{k}.json      the walking tree: for every node used by a building its position and the next node towards the
                     nearest assembly area (p ≥ 0), or the assembly area it reaches (p = −2 − id). Nodes are numbered tile
                     by tile; tree/index.json holds the first id of every tile.
  python pipeline/build_web.py
"""
import json, subprocess, tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

B, W = Path("build"), Path("docs/data")
TILE = 0.02                                   # tree tiles, degrees (~1.7 × 2.2 km)


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    return o


def main():
    g = np.load(B / "graph.npz")
    lonlat, pred, S = g["lonlat"], g["pred"], int(g["S"])
    near = g["near"]
    b = gpd.read_parquet(B / "buildings.parquet")
    pts = gpd.read_parquet(B / "points.parquet")
    n = len(lonlat)

    # ---- walking tree: nodes on the way from every building to its assembly area
    used = np.zeros(n, bool)
    cur = np.unique(b.node.values[np.isfinite(b.d.values)])
    while len(cur):
        cur = cur[~used[cur]]
        used[cur] = True
        nx = pred[cur]
        cur = np.unique(nx[(nx >= 0) & (nx < S)])
    idx = np.nonzero(used)[0]
    tx = np.floor(lonlat[idx, 0] / TILE).astype(int); ty = np.floor(lonlat[idx, 1] / TILE).astype(int)
    key = tx * 100000 + ty
    o = np.lexsort((idx, key)); idx, key = idx[o], key[o]
    newid = np.full(n, -1, dtype=np.int64); newid[idx] = np.arange(len(idx))
    pp = pred[idx]
    root = (pp == S) | (pp < 0)
    pnew = np.where(root, -2 - near[idx], newid[np.clip(pp, 0, n - 1)])
    td = W / "tree"; td.mkdir(parents=True, exist_ok=True)
    for f in td.glob("*.json"):
        f.unlink()
    starts, keys = [], []
    bounds = np.r_[0, np.nonzero(np.diff(key))[0] + 1, len(key)]
    for a, z in zip(bounds[:-1], bounds[1:]):
        k = int(key[a]); keys.append(k); starts.append(int(a))
        ll = np.round(lonlat[idx[a:z]] * 1e5).astype(int)
        (td / f"{k}.json").write_text(json.dumps({"s": int(a), "x": ll[:, 0].tolist(), "y": ll[:, 1].tolist(), "p": pnew[a:z].tolist()}, separators=(",", ":")))
    (td / "index.json").write_text(json.dumps({"s": starts, "k": keys}))
    print(f"tree: {len(idx):,} nodes in {len(keys)} tiles, {sum(f.stat().st_size for f in td.glob('*.json')) / 1e6:.1f} MB")

    # ---- buildings
    b["n"] = np.where(np.isfinite(b.d), newid[b.node.values], -1)
    b4 = b.to_crs(4326)
    with tempfile.TemporaryDirectory() as tmp:
        seq = Path(tmp) / "b.geojsonl"
        with open(seq, "w") as fh:
            for r, geom in zip(b4.itertuples(), shapely.transform(b4.geometry.values, lambda xy: np.round(xy, 6))):
                d = int(round(r.d)) if np.isfinite(r.d) else -1
                pr = {"d": d, "n": int(r.n), "a": int(r.pid), "p": round(float(r.pop), 1)}
                fh.write(json.dumps({"type": "Feature", "properties": pr, "geometry": json.loads(shapely.to_geojson(geom))}, separators=(",", ":")) + "\n")
        subprocess.run(["tippecanoe", "-o", str(W / "buildings.pmtiles"), "--force", "-l", "b", "-Z", "12", "-z", "16",
                        "--drop-densest-as-needed", "--extend-zooms-if-still-dropping", "--no-tile-size-limit",
                        "--simplification=2", "-q", str(seq)], check=True)
    print("buildings.pmtiles", round((W / "buildings.pmtiles").stat().st_size / 1e6, 1), "MB")

    # ---- mahalle, districts, points
    mah = gpd.read_parquet(B / "mahalle.parquet").to_crs(4326)
    mah["geometry"] = mah.geometry.simplify(0.0002)
    cols = ["mid", "mahalle", "district", "pop", "out", "share_out", "n", "area", "area_null", "m2pp", "orph", "gap"]
    m = mah[cols + ["geometry"]].copy()
    for c in ("pop", "out", "orph", "area"):
        m[c] = m[c].round()
    m["share_out"] = m.share_out.round(3); m["m2pp"] = m.m2pp.round(2)
    (W / "mahalle.geojson").write_text(json.dumps(clean(json.loads(m.to_json(drop_id=True))), ensure_ascii=False, separators=(",", ":")))
    dist = gpd.read_parquet(B / "districts.parquet").to_crs(4326)
    dist["geometry"] = dist.geometry.simplify(0.0004)
    (W / "districts.geojson").write_text(dist.to_json(drop_id=True))
    jd = gpd.sjoin(pts[["pid", "geometry"]], gpd.read_parquet(B / "mahalle.parquet")[["mahalle", "district", "geometry"]], predicate="within", how="left") \
        .groupby("pid").first()
    p4 = pts.to_crs(4326)
    feats = []
    for r in p4.itertuples():
        pr = {"i": int(r.pid), "n": r.TOPLANMA_ALAN_AD, "m": jd.mahalle.get(r.pid) or (r.MAHALLE_ADI or "").title(), "dt": jd.district.get(r.pid),
              "a": None if pd.isna(r.area_share) else round(float(r.area_share)), "k": None if pd.isna(r.kind) else r.kind, "w": bool(r.on_network)}
        feats.append({"type": "Feature", "properties": clean(pr), "geometry": {"type": "Point", "coordinates": [round(r.geometry.x, 6), round(r.geometry.y, 6)]}})
    (W / "points.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    s = json.loads((W / "stats.json").read_text())
    s["tree"] = {"nodes": int(len(idx)), "tiles": len(keys), "tile_deg": TILE}
    (W / "stats.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))
    print("web layers written")


if __name__ == "__main__":
    main()
