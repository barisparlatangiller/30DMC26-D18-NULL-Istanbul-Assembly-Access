"""
Day 18 film for LinkedIn (1080×1350, ~23 s, top view): Istanbul's streets light up outward from its 5,599 assembly
areas as the walking distance grows; everything beyond 500 m stays NULL; then a close-up of the neighbourhood with
the most people out of reach, with the walking routes drawn from its buildings, and the missing data.

  python pipeline/film.py
Output  build/video/day18_istanbul_null_assembly.mp4 · build/video/cover.png · build/video/still_*.png
"""
import json, math, subprocess, time
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pyproj import Transformer

B, OUT = Path("build"), Path("build/video")
W, H, FPS = 1080, 1350, 24
MAP_Y, MAP_H = 230, 980
BG = (20, 21, 24)
STREET0 = (58, 60, 66)
INK, INK2, ACC = (240, 236, 228), (165, 160, 150), (226, 140, 92)
BRK = [250, 500, 1000, 2000]
COL = np.array([(95, 168, 160), (156, 195, 160), (226, 194, 124), (217, 138, 78), (179, 71, 58)], float)
NULLC = np.array((179, 71, 58), float)
CRS = 32635


def font(size, bold=False):
    for name in (["Inter:bold", "DejaVu Sans:bold"] if bold else ["Inter", "DejaVu Sans"]):
        f = subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True, text=True).stdout.strip()
        if f:
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def ease(u):
    u = min(1, max(0, u))
    return u * u * (3 - 2 * u)


def cls(d):
    return np.digitize(d, BRK)


class View:
    def __init__(self, cx, cy, span):
        self.x0, self.y1, self.px = cx - span / 2, cy + MAP_H * span / W / 2, span / W

    def xy(self, x, y):
        return (np.asarray(x) - self.x0) / self.px, (self.y1 - np.asarray(y)) / self.px


def raster_lines(view, X, u, v, val, width=1):
    """min value of the segments over each pixel (segments drawn from high to low value)"""
    img = Image.new("F", (W, MAP_H), float("inf"))
    d = ImageDraw.Draw(img)
    px, py = view.xy(X[:, 0], X[:, 1])
    m = ((px[u] > -50) | (px[v] > -50)) & ((px[u] < W + 50) | (px[v] < W + 50)) & ((py[u] > -50) | (py[v] > -50)) & ((py[u] < MAP_H + 50) | (py[v] < MAP_H + 50))
    idx = np.nonzero(m)[0]
    idx = idx[np.argsort(-val[idx])]
    for k in idx.tolist():
        d.line([(px[u[k]], py[u[k]]), (px[v[k]], py[v[k]])], fill=float(val[k]), width=width)
    return np.asarray(img)


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    fr = OUT / "frames"; fr.mkdir(exist_ok=True)
    for f in fr.glob("*.jpg"):
        f.unlink()
    g = np.load(B / "graph.npz")
    X, u, v, dist, pred, S = g["xy"], g["u"], g["v"], g["dist"], g["pred"], int(g["S"])
    ev = np.where(np.isfinite(dist[u]) & np.isfinite(dist[v]), (dist[u] + dist[v]) / 2, 1e9)
    b = gpd.read_parquet(B / "buildings.parquet")
    pts = gpd.read_parquet(B / "points.parquet")
    mah = gpd.read_parquet(B / "mahalle.parquet")
    st = json.loads(Path("docs/data/stats.json").read_text())
    F = {k: font(*a) for k, a in {"eye": (22, True), "t1": (46, True), "t2": (30, False), "big": (84, True), "mid": (34, True),
                                  "sm": (24, False), "lab": (22, True), "foot": (19, False)}.items()}

    # ---- city view
    tr = Transformer.from_crs(4326, CRS, always_xy=True)
    cx, cy = tr.transform(28.985, 41.035)
    city = View(cx, cy, 64000.0)
    Dst = raster_lines(city, X, u, v, ev, 1)
    log = lambda *a: print(f"[{time.time() - t0:5.0f} s]", *a, flush=True)
    log("city street raster")
    street = np.isfinite(Dst)
    ppx, ppy = city.xy(pts.geometry.x.values, pts.geometry.y.values)
    bc = b.geometry.representative_point()
    bx, by = city.xy(bc.x.values, bc.y.values)
    ok = (bx >= 0) & (by >= 0) & (bx < W) & (by < MAP_H) & (b["pop"].values > 0)
    pop_px = np.zeros((MAP_H, W)); out_px = np.zeros((MAP_H, W))
    np.add.at(pop_px, (by[ok].astype(int), bx[ok].astype(int)), b["pop"].values[ok])
    far = ok & (b.d.values > 500)
    np.add.at(out_px, (by[far].astype(int), bx[far].astype(int)), b["pop"].values[far])
    nullmask = np.asarray(Image.fromarray(((out_px > 0) * 255).astype("uint8")).filter(ImageFilter.MaxFilter(3))) > 0

    # ---- close-up: the mahalle with most people beyond 500 m (no data gap)
    wm = st.get("worst_mahalle") or []
    target = wm[0] if wm else None
    mrow = mah[(mah.mahalle == target["mahalle"]) & (mah.district == target["district"])].iloc[0] if target else mah.sort_values("out").iloc[-1]
    mc = mrow.geometry.representative_point()
    x0m, y0m, x1m, y1m = mrow.geometry.bounds
    span_z = max(2200.0, (x1m - x0m) * 1.5, (y1m - y0m) * 1.5 * W / MAP_H)
    zoom = View(mc.x, mc.y, span_z)
    Dz = raster_lines(zoom, X, u, v, ev, 2)
    zb = b[b.intersects(shapely.box(zoom.x0, zoom.y1 - MAP_H * zoom.px, zoom.x0 + W * zoom.px, zoom.y1))]
    bimg = Image.new("RGB", (W, MAP_H), BG); bd = ImageDraw.Draw(bimg)
    for geom, d in zip(zb.geometry.values, zb.d.values):
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        c = tuple(int(x) for x in (COL[cls(d)] if np.isfinite(d) else (90, 85, 80)))
        for p in polys:
            xs, ys = zoom.xy(*np.asarray(p.exterior.coords).T)
            bd.polygon(list(zip(xs, ys)), fill=c)
    bz = np.asarray(bimg).astype(float)
    # routes from the farthest residential buildings in the mahalle
    inm = zb[zb.within(mrow.geometry) & zb.res & np.isfinite(zb.d)]
    sample = inm.sort_values("d", ascending=False)
    picks, used = [], []
    for r in sample.itertuples():
        c = r.geometry.representative_point()
        if all(math.hypot(c.x - a, c.y - bb) > span_z / 7 for a, bb in used):
            used.append((c.x, c.y)); picks.append(r)
        if len(picks) == 6:
            break
    routes = []
    for r in picks:
        c = r.geometry.representative_point(); path = [(c.x, c.y)]; k = int(r.node); guard = 0
        while 0 <= k < S and guard < 20000:
            path.append(tuple(X[k])); k = int(pred[k]); guard += 1
        routes.append((np.array(path), float(r.d)))
    zpx, zpy = zoom.xy(pts.geometry.x.values, pts.geometry.y.values)
    zin = (zpx > -20) & (zpy > -20) & (zpx < W + 20) & (zpy < MAP_H + 20)
    zhollow = pts.area_share.isna().values[zin]
    mline = mrow.geometry.boundary if mrow.geometry.geom_type == "Polygon" else max(mrow.geometry.geoms, key=lambda g: g.area).boundary
    if mline.geom_type == "MultiLineString":
        mline = max(mline.geoms, key=lambda g: g.length)
    log(f"close-up: {mrow.mahalle} ({mrow.district}), {len(zb)} buildings, {len(routes)} routes")

    so = st["share_over"]; p500 = st["people_over_500"]
    pts_total = st["points"]["total"]

    def colour_streets(D, t, dim=False):
        img = np.zeros((MAP_H, W, 3)); img[:] = BG
        s = np.isfinite(D)
        img[s] = STREET0
        lit = s & (D <= t)
        img[lit] = COL[cls(D[lit])]
        if dim:
            img[lit] = img[lit] * 0.45 + np.array(BG) * 0.55
        return img

    def compose(mapimg, title, sub=None, eyebrow=True, overlay=None, big=None):
        im = Image.new("RGB", (W, H), BG)
        im.paste(Image.fromarray(np.clip(mapimg, 0, 255).astype("uint8")), (0, MAP_Y))
        d = ImageDraw.Draw(im)
        if eyebrow:
            d.text((48, 36), "#30DAYMAPCHALLENGE · DAY 18 · NULL · ISTANBUL", font=F["eye"], fill=ACC)
        d.text((48, 76), title, font=F["t1"], fill=INK)
        if sub:
            d.text((48, 140), sub, font=F["t2"], fill=INK2)
        if big:
            d.rounded_rectangle([40, MAP_Y + MAP_H - 220, W - 40, MAP_Y + MAP_H - 30], 26, fill=(28, 29, 33))
            d.text((72, MAP_Y + MAP_H - 205), big[0], font=F["big"], fill=tuple(int(x) for x in NULLC))
            d.text((72, MAP_Y + MAP_H - 105), big[1], font=F["sm"], fill=INK)
            if len(big) > 2:
                d.text((72, MAP_Y + MAP_H - 72), big[2], font=F["sm"], fill=INK2)
        ly = MAP_Y + MAP_H + 26
        for i, lb in enumerate(["< 250 m", "250–500", "0.5–1 km", "1–2 km", "> 2 km"]):
            x = 48 + i * 168
            d.rounded_rectangle([x, ly, x + 22, ly + 16], 4, fill=tuple(int(c) for c in COL[i])); d.text((x + 30, ly - 4), lb, font=F["foot"], fill=INK2)
        d.text((48, ly + 28), "walk to the nearest assembly area, on OSM streets", font=F["foot"], fill=INK2)
        d.ellipse([W - 400, ly + 32, W - 386, ly + 46], fill=INK); d.text((W - 378, ly + 28), "assembly area", font=F["foot"], fill=INK2)
        d.ellipse([W - 220, ly + 32, W - 206, ly + 46], outline=INK, width=2); d.text((W - 198, ly + 28), "size: NULL", font=F["foot"], fill=INK2)
        d.text((48, H - 34), "Assembly areas © İBB Açık Veri · © OpenStreetMap contributors · WorldPop 2020 · B. Parlatangiller", font=F["foot"], fill=(110, 106, 100))
        if overlay:
            overlay(d)
        return im

    def dots(img, px, py, r=1.0, col=(226, 222, 214), hollow=None):
        im = Image.fromarray(np.clip(img, 0, 255).astype("uint8")); d = ImageDraw.Draw(im)
        for i, (x, y) in enumerate(zip(px, py)):
            if hollow is not None and hollow[i]:
                d.ellipse([x - r - 1, y - r - 1, x + r + 1, y + r + 1], outline=col, width=2)
            else:
                d.ellipse([x - r, y - r, x + r, y + r], fill=col)
        return np.asarray(im).astype(float)

    n = 0
    def save(im):
        nonlocal n
        im.save(fr / f"f{n:04d}.jpg", quality=92); n += 1

    base0 = colour_streets(Dst, -1)
    # 1 · streets
    for k in range(int(FPS * 1.6)):
        a = ease(k / (FPS * 1.2))
        img = np.array(BG, float) * (1 - a) + base0 * a
        save(compose(img, f"Istanbul has {pts_total:,} earthquake", "assembly areas. How far is the walk?"))
    # 2 · dots
    order = np.argsort(np.random.default_rng(1).random(len(ppx)))
    for k in range(int(FPS * 1.8)):
        m = order[: int(len(order) * ease(k / (FPS * 1.4)))]
        save(compose(dots(base0, ppx[m], ppy[m], 1.1), f"Istanbul has {pts_total:,} earthquake", "assembly areas. How far is the walk?"))

    # 3 · the walk grows
    NG = int(FPS * 5.0)
    for k in range(NG):
        t = 2200 * ease(k / (NG - 1)) ** 1.1
        img = dots(colour_streets(Dst, t), ppx, ppy, 0.9)
        lab = f"{t:,.0f} m" if t < 1000 else f"{t / 1000:.1f} km"
        save(compose(img, "Walking along real streets", f"from every assembly area outward: {lab}"))
    full = dots(colour_streets(Dst, 1e9), ppx, ppy, 0.9)
    # 4 · NULL beyond 500 m
    NN = int(FPS * 3.6)
    for k in range(NN):
        a = ease(k / (FPS * 1.0))
        img = colour_streets(Dst, 500, dim=True)
        img = full * (1 - a) + img * a
        glow = nullmask[..., None] * NULLC
        img = np.where(nullmask[..., None], img * (1 - a) + glow * a, img)
        img = dots(img, ppx, ppy, 0.8, col=(200, 196, 188))
        save(compose(img, "Beyond 500 m: NULL", "homes more than a 7-minute walk away",
                     big=(f"{so['500'] * 100:.0f}% of residents", f"about {p500 / 1e6:.1f} million people live more than", "a 500 m walk from the nearest assembly area") if k > FPS * 0.8 else None))
    nullimg = img
    # 5 · close-up with routes
    zstreet = colour_streets(Dz, 1e9) * 0.55 + np.array(BG) * 0.45
    zimg = np.where((bz != BG).any(axis=2)[..., None], bz, zstreet)
    for k in range(int(FPS * 1.0)):                                     # fade
        a = ease(k / (FPS * 1.0))
        save(compose(nullimg * (1 - a) + zimg * a, f"{mrow.mahalle}, {mrow.district}", f"{target['share_out'] * 100:.0f}% of {target['pop']:,.0f} residents beyond 500 m" if target else ""))
    NR = int(FPS * 4.2)
    for k in range(NR):
        a = ease(k / (FPS * 3.0))
        im = Image.fromarray(np.clip(zimg, 0, 255).astype("uint8")); d = ImageDraw.Draw(im)
        for x, y, hol in zip(zpx[zin], zpy[zin], zhollow):
            if hol:
                d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=INK, width=2)
            else:
                d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=INK, outline=BG, width=1)
        mxs, mys = zoom.xy(*np.asarray(mline.coords).T)
        d.line(list(zip(mxs, mys)), fill=(240, 236, 228), width=2)
        boxes = []
        for path, dd in routes:
            pxs, pys = zoom.xy(path[:, 0], path[:, 1])
            m = max(2, int(len(pxs) * a))
            c = tuple(int(x) for x in COL[cls(dd)])
            d.line(list(zip(pxs[:m], pys[:m])), fill=(255, 255, 255), width=8, joint="curve")
            d.line(list(zip(pxs[:m], pys[:m])), fill=c, width=4, joint="curve")
            d.ellipse([pxs[0] - 6, pys[0] - 6, pxs[0] + 6, pys[0] + 6], fill=c, outline=(255, 255, 255), width=2)
            if a >= 1:
                t = f"{dd:,.0f} m · {max(1, round(dd / 75))} min"; tw = d.textlength(t, font=F["lab"])
                x, y = pxs[0] + 10, pys[0] - 30
                if x + tw > W - 10:
                    x = pxs[0] - 10 - tw
                for _ in range(8):
                    if not any(x < bx1 and x + tw > bx0 and y < by1 and y + 28 > by0 for bx0, by0, bx1, by1 in boxes):
                        break
                    y += 30
                boxes.append((x, y, x + tw, y + 28))
                d.text((x, y), t, font=F["lab"], fill=INK, stroke_width=3, stroke_fill=BG)
        far_d = max((r[1] for r in routes), default=0)
        save(compose(np.asarray(im).astype(float), f"{mrow.mahalle}, {mrow.district}",
                     f"the farthest homes walk {far_d / 1000:.1f} km, about {round(far_d / 75)} minutes"))
    routeimg = np.asarray(im).astype(float)
    if True:
        compose(routeimg, f"{mrow.mahalle}, {mrow.district}", f"the farthest homes walk {far_d / 1000:.1f} km, about {round(far_d / 75)} minutes").save(OUT / "still_closeup.png")
    # 6 · the data's own NULL
    an = st["points"]["area_null"]
    for k in range(int(FPS * 3.0)):
        def ov(d):
            a = min(1, k / (FPS * 0.5))
            d.rounded_rectangle([40, MAP_Y + 40, W - 40, MAP_Y + 300], 26, fill=(28, 29, 33))
            d.text((72, MAP_Y + 62), "And the data itself:", font=F["mid"], fill=INK)
            d.text((72, MAP_Y + 118), f"area: NULL · capacity: NULL", font=F["big"] if False else F["mid"], fill=tuple(int(x) for x in NULLC))
            d.text((72, MAP_Y + 170), f"for all {pts_total:,} assembly areas in the official list.", font=F["sm"], fill=INK)
            d.text((72, MAP_Y + 210), f"{an:,} are not in any mapped park or square:", font=F["sm"], fill=INK2)
            d.text((72, MAP_Y + 244), "their size is unknown even from OpenStreetMap.", font=F["sm"], fill=INK2)
        save(compose(routeimg, f"{mrow.mahalle}, {mrow.district}", "how many people can each area hold?", overlay=ov))
    # 7 · outro
    for k in range(int(FPS * 3.6)):
        def ov(d):
            d.rounded_rectangle([40, MAP_Y + 120, W - 40, MAP_Y + 820], 28, fill=(28, 29, 33))
            d.text((W // 2, MAP_Y + 170), "Istanbul · walking to safety", font=F["sm"], fill=INK2, anchor="ma")
            d.text((W // 2, MAP_Y + 230), f"{p500 / 1e6:.1f} million", font=F["big"], fill=tuple(int(x) for x in NULLC), anchor="ma")
            d.text((W // 2, MAP_Y + 330), "residents live more than a 500 m walk", font=F["sm"], fill=INK, anchor="ma")
            d.text((W // 2, MAP_Y + 364), "from their nearest assembly area", font=F["sm"], fill=INK, anchor="ma")
            d.text((W // 2, MAP_Y + 450), f"{pts_total:,} areas listed · size and capacity: NULL", font=F["lab"], fill=INK2, anchor="ma")
            d.text((W // 2, MAP_Y + 560), "Tap your building:", font=F["mid"], fill=INK, anchor="ma")
            d.text((W // 2, MAP_Y + 610), "your route, your minutes", font=F["mid"], fill=INK, anchor="ma")
            d.text((W // 2, MAP_Y + 720), "barisparlatangiller.github.io", font=F["lab"], fill=ACC, anchor="ma")
        a = ease(k / (FPS * 0.6))
        save(compose(nullimg * (1 - 0.6 * a) + np.array(BG) * 0.6 * a, "NULL · on the map, out of reach", None, overlay=ov if k > 4 else None))
    compose(nullimg * 0.4 + np.array(BG) * 0.6, "NULL · on the map, out of reach", None, overlay=ov).save(OUT / "outro.png")
    compose(nullimg, "Beyond 500 m: NULL", "homes more than a 7-minute walk away",
            big=(f"{so['500'] * 100:.0f}% of residents", f"about {p500 / 1e6:.1f} million people live more than", "a 500 m walk from the nearest assembly area")).save(OUT / "cover.png")
    compose(full, "Walking along real streets", "from every assembly area outward").save(OUT / "still_walk.png")
    out = OUT / "day18_istanbul_null_assembly.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(fr / "f%04d.jpg"), "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "21", "-profile:v", "main", "-pix_fmt", "yuv420p", "-color_range", "tv", "-tag:v", "avc1", "-movflags", "+faststart", str(out)], check=True)
    log(f"film: {n} frames, {n / FPS:.1f} s, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
