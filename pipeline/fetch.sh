#!/usr/bin/env bash
# Day 18 · OSM Istanbul extract (Geofabrik) + WorldPop 100 m population. Everything logged.
set -euo pipefail
mkdir -p input build logs
cd input
BBOX=27.95,40.78,29.98,41.60                      # Istanbul province
if [ ! -s istanbul.osm.pbf ]; then
  curl -fsSL --retry 3 -o turkey.osm.pbf https://download.geofabrik.de/europe/turkey-latest.osm.pbf
  ls -la turkey.osm.pbf
  osmium extract -b $BBOX -s smart turkey.osm.pbf -o istanbul.osm.pbf --overwrite
  rm turkey.osm.pbf
fi
osmium fileinfo -e istanbul.osm.pbf | grep -E "Number of|Bounding|timestamp" | head -12 || true
osmium tags-filter istanbul.osm.pbf w/highway -o roads.osm.pbf --overwrite
osmium tags-filter istanbul.osm.pbf w/building r/building -o buildings.osm.pbf --overwrite
osmium tags-filter istanbul.osm.pbf nwr/leisure nwr/landuse=grass,recreation_ground,village_green,meadow,cemetery \
  nwr/amenity=school,college,university,kindergarten,parking nwr/place=square nwr/area:highway=pedestrian \
  w/highway=pedestrian r/type=multipolygon -o open.osm.pbf --overwrite
osmium tags-filter istanbul.osm.pbf r/boundary=administrative -o admin.osm.pbf --overwrite
osmium export buildings.osm.pbf -f geojsonseq -o buildings.geojsonseq --overwrite --geometry-types=polygon -a id
osmium export open.osm.pbf -f geojsonseq -o open.geojsonseq --overwrite --geometry-types=polygon -a id
osmium export admin.osm.pbf -f geojsonseq -o admin.geojsonseq --overwrite --geometry-types=polygon -a id
wc -l *.geojsonseq
# population: WorldPop 2020, constrained to built-up areas, 100 m (3 arc-seconds), persons per cell
if [ ! -s pop.tif ]; then
  for u in https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/TUR/tur_ppp_2020_constrained.tif \
           https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/maxar_v1/TUR/tur_ppp_2020_constrained.tif; do
    if curl -fsSL --retry 3 -o pop_tr.tif "$u"; then echo "population: $u"; break; fi
  done
  ls -la pop_tr.tif
  gdal_translate -q -projwin 27.95 41.60 29.98 40.78 pop_tr.tif pop.tif 2>/dev/null || python - <<'PY'
import rasterio
from rasterio.windows import from_bounds
with rasterio.open("pop_tr.tif") as s:
    w = from_bounds(27.95, 40.78, 29.98, 41.60, s.transform)
    a = s.read(1, window=w); p = s.profile.copy()
    p.update(width=a.shape[1], height=a.shape[0], transform=s.window_transform(w), compress="deflate")
    with rasterio.open("pop.tif", "w", **p) as d:
        d.write(a, 1)
PY
  rm -f pop_tr.tif
fi
python - <<'PY'
import rasterio, numpy as np
with rasterio.open("pop.tif") as s:
    a = s.read(1).astype("float64"); a[a < 0] = 0
    print("population raster", s.shape, s.crs, "sum", round(a.sum()))
PY
