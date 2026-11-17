"""
Day 18 · NULL · Istanbul: earthquake assembly areas on the map, out of reach on foot.

1. Walk network from OpenStreetMap: every highway a person can walk along (streets with or without sidewalks, paths,
   steps, squares), without motorways and ways tagged foot=no / access=private.
2. Assembly areas: IBB open data (5,599 points). Each point is joined to the OSM open space it sits in (park, square,
   school yard, pitch …) to estimate its area; the dataset itself has no area or capacity field (NULL).
   Entrances: network nodes on / just inside the edge of that open space, else the nearest node to the point.
3. Walking distance from every network node to its nearest assembly area: one Dijkstra from a virtual source
   connected to all entrances (scipy). The predecessor tree is kept for the web map (route from any building).
4. Buildings (OSM) take the distance of their nearest node + the straight walk to it.
5. People: WorldPop 2020 (100 m, constrained) shared out to the residential-looking buildings in each cell by
   footprint area; cells with people but no OSM building are kept as "people without a mapped building".
6. Mahalle (OSM admin_level 8) and district (6) statistics; data gaps are kept apart from poor access.

  python pipeline/analyse.py
"""
import json, math, time
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
import osmium
import rasterio
from pyproj import Transformer
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

IN, B, W = Path("input"), Path("build"), Path("docs/data")
CRS = 32635                                   # UTM 35N, metres
LIMIT = 6000.0                                # follow the walk up to 6 km
WALK_KMH = 4.5
NOT_WALK = {"motorway", "motorway_link", "construction", "proposed", "abandoned", "raceway", "bus_guideway", "escape",
            "razed", "disused", "platform", "corridor", "elevator", "via_ferrata", "no"}
NON_RES = {"industrial", "warehouse", "commercial", "retail", "office", "mosque", "church", "synagogue", "religious",
           "school", "university", "college", "kindergarten", "hospital", "public", "civic", "government", "train_station",
           "transportation", "garage", "garages", "parking", "shed", "roof", "hut", "cabin", "service", "stadium",
           "sports_hall", "sports_centre", "greenhouse", "barn", "farm_auxiliary", "stable", "ruins", "construction",
           "kiosk", "toilets", "transformer_tower", "water_tower", "silo", "storage_tank", "bunker", "tent", "carport",
           "factory", "manufacture", "hangar", "fuel", "power", "substation", "military", "castle", "tower", "bridge"}
OPEN_KEYS = ("leisure", "landuse", "amenity", "place", "area:highway", "highway")
OPEN_OK = {"leisure": {"park", "garden", "playground", "pitch", "recreation_ground", "sports_centre", "stadium", "common", "dog_park",
                       "fitness_station", "schoolyard", "track", "picnic_site"},
           "landuse": {"grass", "recreation_ground", "village_green", "meadow"},
           "amenity": {"school", "college", "university", "kindergarten", "parking"},
           "place": {"square"}, "area:highway": None, "highway": {"pedestrian"}}


def is_open(p):
    for k, ok in OPEN_OK.items():
        v = p.get(k)
        if isinstance(v, str) and (ok is None or v in ok):
            return True
    return False
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.0f} s]", *a, flush=True)


# ------------------------------------------------------------------ 1 · walk network
class Ways(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.u, self.v, self.ids, self.xy = [], [], {}, []

    def nid(self, n):
        k = n.ref
        i = self.ids.get(k)
        if i is None:
            i = self.ids[k] = len(self.xy)
            self.xy.append((n.lon, n.lat))
        return i

    def way(self, w):
        t = w.tags
        hw = t.get("highway")
        if not hw or hw in NOT_WALK or t.get("foot") in ("no", "private") or t.get("access") in ("no", "private") and t.get("foot") not in ("yes", "designated", "permissive"):
            return
        if t.get("area") == "yes" and hw != "pedestrian":
            return
        prev = None
        for n in w.nodes:
            if not n.location.valid():
                prev = None; continue
            i = self.nid(n)
            if prev is not None and prev != i:
                self.u.append(prev); self.v.append(i)
            prev = i


def network():
    h = Ways()
    h.apply_file(str(IN / "roads.osm.pbf"), locations=True)
    lonlat = np.array(h.xy, dtype="float64")
    tr = Transformer.from_crs(4326, CRS, always_xy=True)
    x, y = tr.transform(lonlat[:, 0], lonlat[:, 1])
    xy = np.c_[x, y]
    u, v = np.array(h.u), np.array(h.v)
    w = np.hypot(*(xy[u] - xy[v]).T)
    log(f"walk network: {len(xy):,} nodes, {len(u):,} segments, {w.sum() / 1000:,.0f} km")
    return lonlat, xy, u, v, w


# ------------------------------------------------------------------ helpers
def read_seq(p, keep=None):
    feats = []
    with open(p) as f:
        for line in f:
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            o = json.loads(line)
            pr = o.get("properties") or {}
            if keep and not keep(pr):
                continue
            feats.append((shapely.geometry.shape(o["geometry"]), pr))
    g = gpd.GeoDataFrame([p for _, p in feats], geometry=[g for g, _ in feats], crs=4326)
    return g


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    return o


def main():
    B.mkdir(exist_ok=True); W.mkdir(parents=True, exist_ok=True)
    st = {}
    # admin areas ------------------------------------------------------------
    adm = read_seq(IN / "admin.geojsonseq", lambda p: p.get("boundary") == "administrative" and p.get("admin_level") in ("4", "6", "8"))
    adm = adm.to_crs(CRS)
    adm["geometry"] = shapely.make_valid(adm.geometry.values)
    dist = adm[adm.admin_level == "6"].copy()
    mah = adm[adm.admin_level == "8"].copy()
    # Istanbul = the districts that hold IBB assembly areas (the bbox also cuts into Kocaeli and Tekirdağ)
    ibb = gpd.read_file("data/ibb_toplanma_alanlari.geojson").to_crs(CRS)
    cnt = gpd.sjoin(ibb[["geometry"]], dist[["geometry"]], predicate="within").groupby("index_right").size()
    dist = dist.loc[cnt.index[cnt >= 5]]
    city = shapely.union_all(dist.geometry.values).buffer(30)
    mah = mah[mah.geometry.representative_point().within(city)]
    log(f"Istanbul: {len(dist)} districts with IBB assembly areas")
    dist = dist[["name", "geometry"]].rename(columns={"name": "district"}).reset_index(drop=True)
    mah = mah[["name", "geometry"]].rename(columns={"name": "mahalle"}).reset_index(drop=True)
    mah["district"] = gpd.sjoin(gpd.GeoDataFrame(geometry=mah.geometry.representative_point(), crs=CRS), dist, predicate="within", how="left") \
        .groupby(level=0).district.first().reindex(mah.index)
    mah["mid"] = np.arange(len(mah))
    log(f"{len(dist)} districts, {len(mah)} mahalle (OSM admin_level 6 / 8)")

    # network ----------------------------------------------------------------
    lonlat, xy, u, v, w = network()
    n = len(xy)

    # assembly areas -----------------------------------------------------------
    pts = gpd.read_file("data/ibb_toplanma_alanlari.geojson").to_crs(CRS)
    pts["pid"] = np.arange(len(pts))
    log(f"assembly areas: {len(pts):,}; empty fields:", {c: int(pts[c].isna().sum()) for c in pts.columns if c != "geometry"})
    op = read_seq(IN / "open.geojsonseq", is_open).to_crs(CRS)
    op["geometry"] = shapely.make_valid(op.geometry.values)
    op = op[op.geometry.area.between(80, 2_000_000)].reset_index(drop=True)
    def kind(r):
        for k, ok in OPEN_OK.items():
            v = r.get(k)
            if isinstance(v, str) and (ok is None or v in ok):
                return f"{k}={v}"
        return "open"
    op["kind"] = [kind(r) for r in op.to_dict("records")]
    op["area"] = op.geometry.area
    # point → smallest open space containing it, else nearest within 25 m
    j = gpd.sjoin(pts[["pid", "geometry"]], op[["kind", "area", "geometry"]], predicate="within", how="left")
    j = j.sort_values("area").groupby("pid").first()
    miss = j.index[j.area.isna()]
    if len(miss):
        jn = gpd.sjoin_nearest(pts.loc[pts.pid.isin(miss), ["pid", "geometry"]], op[["kind", "area", "geometry"]], max_distance=25, how="left")
        jn = jn.sort_values("area").groupby("pid").first()
        j.loc[jn.index, ["index_right", "kind", "area"]] = jn[["index_right", "kind", "area"]].values
    pts["oi"] = j.index_right.reindex(pts.pid).values
    pts["kind"] = j.kind.reindex(pts.pid).values
    pts["area"] = j.area.reindex(pts.pid).values
    # a big park shared by several points: share its area between them
    share = pts.groupby("oi").pid.transform("count")
    pts["area_share"] = pts.area / share
    log(f"points inside a mapped open space: {pts.area.notna().sum():,} of {len(pts):,}; kinds:", pts.kind.value_counts().head(8).to_dict())

    # entrances ----------------------------------------------------------------
    tree = cKDTree(xy)
    src_node, src_pid, src_off = [], [], []
    for r in pts.itertuples():
        if not pd.isna(r.oi):
            poly = op.geometry[int(r.oi)]
            edge = poly.boundary.buffer(12).union(poly) if poly.area < 300_000 else poly.boundary.buffer(12)
            x0, y0, x1, y1 = edge.bounds
            cand = tree.query_ball_point([(x0 + x1) / 2, (y0 + y1) / 2], math.hypot(x1 - x0, y1 - y0) / 2 + 1)
            cand = [c for c in cand if edge.contains(shapely.Point(xy[c]))]
            if cand:
                src_node += cand; src_pid += [r.pid] * len(cand); src_off += [0.0] * len(cand)
                continue
        d, c = tree.query([r.geometry.x, r.geometry.y])
        if d <= 150:
            src_node.append(int(c)); src_pid.append(r.pid); src_off.append(float(d))
    src_node, src_pid, src_off = np.array(src_node), np.array(src_pid), np.array(src_off)
    reach = np.zeros(len(pts), bool); reach[np.unique(src_pid)] = True
    pts["on_network"] = reach
    log(f"entrances: {len(src_node):,} nodes for {reach.sum():,} points; {(~reach).sum()} points > 150 m from any walkable way")
    # one entrance per node: the closest point's
    o = np.lexsort((src_off, src_node)); keep = np.r_[True, src_node[o][1:] != src_node[o][:-1]]
    src_node, src_pid, src_off = src_node[o][keep], src_pid[o][keep], src_off[o][keep]

    # Dijkstra from a virtual source ---------------------------------------------------
    S = n
    rows = np.r_[u, v, np.full(len(src_node), S)]; cols = np.r_[v, u, src_node]; wts = np.r_[w, w, src_off + 1e-3]
    G = coo_matrix((wts, (rows, cols)), shape=(n + 1, n + 1)).tocsr()
    dist_n, pred = dijkstra(G, directed=True, indices=S, return_predecessors=True, limit=LIMIT)
    dist_n, pred = dist_n[:n], pred[:n]
    root_pid = np.full(n, -1, dtype=np.int64); root_pid[src_node] = src_pid
    # nearest assembly area of every node: walk the tree outward in order of distance
    near = root_pid.copy()
    order = np.argsort(dist_n); order = order[np.isfinite(dist_n[order])]
    pl = pred.tolist(); nl = near.tolist()
    for i in order.tolist():
        q = pl[i]
        if 0 <= q < S:
            nl[i] = nl[q]
    near_pid = np.where(np.isfinite(dist_n), np.array(nl), -1)
    log(f"Dijkstra done: {np.isfinite(dist_n).sum():,} nodes reached within {LIMIT / 1000:.0f} km; median {np.nanmedian(np.where(np.isfinite(dist_n), dist_n, np.nan)):.0f} m")

    # buildings ----------------------------------------------------------------------
    b = read_seq(IN / "buildings.geojsonseq").to_crs(CRS)
    b = b[b.geometry.notna() & ~b.geometry.is_empty].reset_index(drop=True)
    b["area"] = b.geometry.area
    b = b[b.area >= 15].reset_index(drop=True)
    if city is not None:
        b = b[b.geometry.representative_point().within(city)].reset_index(drop=True)
    btype = b["building"].fillna("yes").astype(str)
    b["res"] = ~btype.isin(NON_RES) & b.get("amenity", pd.Series(index=b.index, dtype=object)).isna() & (b.area < 20_000)
    c = b.geometry.representative_point()
    cx, cy = c.x.values, c.y.values
    dd, nn = tree.query(np.c_[cx, cy])
    b["node"] = nn
    b["snap"] = dd
    b["d"] = np.where(dd <= 250, dist_n[nn] + dd, np.inf)
    b["pid"] = np.where(np.isfinite(b.d), near_pid[nn], -1)
    log(f"buildings: {len(b):,} ({b.res.sum():,} residential-looking); snapped > 250 m: {(dd > 250).sum():,}")

    # people -----------------------------------------------------------------------------
    with rasterio.open(IN / "pop.tif") as s:
        pop = s.read(1).astype("float64"); pop[pop < 0] = 0; ptr = s.transform
    tr4 = Transformer.from_crs(CRS, 4326, always_xy=True)
    lon, lat = tr4.transform(cx, cy)
    col = ((np.array(lon) - ptr.c) / ptr.a).astype(int); row = ((np.array(lat) - ptr.f) / ptr.e).astype(int)
    ok = (col >= 0) & (row >= 0) & (col < pop.shape[1]) & (row < pop.shape[0])
    cell = np.where(ok, row * pop.shape[1] + col, -1)
    wgt = np.where(b.res, b.area, 0.0)
    cw = np.bincount(cell[cell >= 0], weights=wgt[cell >= 0], minlength=pop.size)
    b["pop"] = np.where((cell >= 0) & (wgt > 0), pop.ravel()[np.maximum(cell, 0)] * wgt / np.maximum(cw[np.maximum(cell, 0)], 1e-9), 0.0)
    # people in cells with no residential building in OSM
    rr, cc = np.nonzero(pop > 0)
    fl = rr * pop.shape[1] + cc
    orphan = pop.ravel()[fl] * (cw[fl] <= 0)
    oxl, oyl = ptr.c + (cc + 0.5) * ptr.a, ptr.f + (rr + 0.5) * ptr.e
    ox, oy = Transformer.from_crs(4326, CRS, always_xy=True).transform(oxl, oyl)
    m_or = orphan > 0
    orph = gpd.GeoDataFrame({"pop": orphan[m_or]}, geometry=gpd.points_from_xy(np.array(ox)[m_or], np.array(oy)[m_or]), crs=CRS)
    if city is not None:
        orph = orph[orph.within(city)]
    od, on = tree.query(np.c_[orph.geometry.x, orph.geometry.y])
    orph["d"] = np.where(od <= 250, dist_n[on] + od, np.inf)
    P_b, P_o = b["pop"].sum(), orph["pop"].sum()
    log(f"people: {P_b + P_o:,.0f} in Istanbul (WorldPop 2020); {P_b:,.0f} in OSM buildings, {P_o:,.0f} ({P_o / (P_b + P_o):.1%}) in cells without a mapped home")

    # stats --------------------------------------------------------------------------------
    def share(dv, pv, lim):
        pv = np.asarray(pv); dv = np.asarray(dv)
        return float(pv[dv > lim].sum() / max(pv.sum(), 1))
    allp = np.r_[b["pop"].values, orph["pop"].values]; alld = np.r_[b.d.values, orph.d.values]
    st["people"] = round(float(allp.sum()))
    st["share_over"] = {str(L): round(share(alld, allp, L), 4) for L in (250, 500, 1000, 2000)}
    st["people_over_500"] = round(float(allp[alld > 500].sum()))
    wsort = np.argsort(alld); cum = np.cumsum(allp[wsort]); st["median_walk_person_m"] = round(float(alld[wsort][np.searchsorted(cum, cum[-1] / 2)]))
    st["points"] = {"total": int(len(pts)), "in_open_space": int(pts.area.notna().sum()), "area_null": int(pts.area.isna().sum()),
                    "off_network": int((~pts.on_network).sum()), "kinds": pts.kind.value_counts().head(10).to_dict(),
                    "fields_empty": {c: int(pts[c].isna().sum()) for c in ("SE_ANNO_CAD_DATA", "KIMLIKNO") if c in pts},
                    "area_m2_known": round(float(pts.area_share.sum()))}
    st["buildings"] = {"total": int(len(b)), "residential": int(b.res.sum()), "people_in_cells_without_buildings": round(float(P_o))}
    log("headline:", json.dumps({k: st[k] for k in ("people", "share_over", "people_over_500", "median_walk_person_m")}))

    # per mahalle --------------------------------------------------------------------
    bc = gpd.GeoDataFrame({"pop": b["pop"].values, "d": b.d.values}, geometry=gpd.points_from_xy(cx, cy), crs=CRS)
    allpts = pd.concat([bc, orph[["pop", "d", "geometry"]].assign(orphan=1)], ignore_index=True)
    allpts["orphan"] = allpts.orphan.fillna(0)
    jm = gpd.sjoin(allpts, mah[["mid", "geometry"]], predicate="within", how="left")
    jm = jm[jm.mid.notna()]
    jm["out"] = jm["pop"] * (jm.d > 500); jm["orph"] = jm["pop"] * jm.orphan
    agg = jm.groupby("mid").agg(pop=("pop", "sum"), out=("out", "sum"), orph=("orph", "sum"))
    pm = gpd.sjoin(pts[["pid", "area_share", "geometry"]], mah[["mid", "geometry"]], predicate="within", how="left")
    pa = pm.groupby("mid").agg(n=("pid", "count"), area=("area_share", "sum"), area_null=("area_share", lambda s: int(s.isna().sum())))
    mah = mah.join(agg, on="mid").join(pa, on="mid")
    for k in ("pop", "out", "orph", "n", "area", "area_null"):
        mah[k] = mah[k].fillna(0)
    mah["share_out"] = mah.out / mah["pop"].where(mah["pop"] > 0)
    mah["m2pp"] = mah.area / mah["pop"].where(mah["pop"] > 0)
    # data gap: most of the people live in cells where OSM has no home
    mah["gap"] = (mah.orph / mah["pop"].where(mah["pop"] > 0) > 0.5) & (mah["pop"] > 300)
    log(f"mahalle: {len(mah)}, with people {int((mah['pop'] > 300).sum())}, data gap {int(mah.gap.sum())}, "
        f"no assembly area at all {int(((mah.n == 0) & (mah['pop'] > 300)).sum())}")
    good = mah[(mah["pop"] > 1000) & ~mah.gap]
    st["worst_mahalle"] = good.sort_values("out", ascending=False).head(15)[["mahalle", "district", "pop", "out", "share_out", "n"]].round(3).to_dict("records")
    st["worst_share"] = good[good["pop"] > 3000].sort_values("share_out", ascending=False).head(15)[["mahalle", "district", "pop", "out", "share_out", "n"]].round(3).to_dict("records")
    # districts
    jd = gpd.sjoin(allpts, dist[["district", "geometry"]], predicate="within", how="left")
    jd["out"] = jd["pop"] * (jd.d > 500)
    dg = jd.groupby("district").agg(pop=("pop", "sum"), out=("out", "sum"))
    dp = gpd.sjoin(pts[["pid", "geometry"]], dist, predicate="within").groupby("district").pid.count()
    dg["n"] = dp.reindex(dg.index).fillna(0); dg["share_out"] = dg.out / dg["pop"]
    st["districts"] = dg.sort_values("share_out", ascending=False).round(3).reset_index().to_dict("records")

    # save for the web / film ------------------------------------------------------------
    b[["node", "d", "pid", "pop", "res", "snap", "geometry"]].assign(osm=b["@id"] if "@id" in b else None).to_parquet(B / "buildings.parquet")
    mah.to_parquet(B / "mahalle.parquet"); dist.to_parquet(B / "districts.parquet")
    pts.drop(columns=[c for c in ("SE_ANNO_CAD_DATA",) if c in pts]).to_parquet(B / "points.parquet")
    orph.to_parquet(B / "orphans.parquet")
    np.savez_compressed(B / "graph.npz", lonlat=lonlat, xy=xy, u=u, v=v, dist=dist_n, pred=pred, near=near_pid, S=S)
    (W / "stats.json").write_text(json.dumps(clean(st), ensure_ascii=False, indent=1, allow_nan=False))
    log("saved")


if __name__ == "__main__":
    main()
