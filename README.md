# NULL · On the map, out of reach — Istanbul's earthquake assembly areas

**#30DayMapChallenge 2026 · Day 18 · NULL · Istanbul**

🌍 **Live map:** https://barisparlatangiller.github.io/30DMC26-D18-NULL-Istanbul-Assembly-Access/ · all maps: https://barisparlatangiller.github.io/

Istanbul lists 5,599 earthquake assembly areas. This map measures the **walk** from every building to the nearest one,
along OpenStreetMap streets and paths, and shows what the data leaves out. Tap a building to see its route.

## Findings

- **1 in 4 residents (24.7 %), about 3.9 million people**, live more than a 500 m walk from the nearest assembly area. Median walk: about 280 m.
- Districts with the largest share beyond 500 m: Silivri 69 %, Başakşehir 68 %, Şile 63 %, Arnavutköy 61 %. Lowest: Güngören 2 %, Gaziosmanpaşa 5 %, Fatih 6 %.
- The data's own NULL: the official list has **no area and no capacity** for any of the 5,599 points; 1,926 do not lie in any mapped
  open space, so even their size is unknown. 57 neighbourhoods with residents have no assembly area inside their borders.
- In 309 neighbourhoods most residents live where OSM has no buildings: hatched on the map as a data gap, not a result.

## Method

1. Walk network: OSM highways a pedestrian can use (no motorways, no foot=no / access=private), 51,600 km (`pipeline/analyse.py`).
2. Entrances: if a point lies in a mapped park, square, school yard, pitch …, every network node on its edge counts as an
   entrance; otherwise the nearest node (≤ 150 m).
3. One multi-source Dijkstra (scipy) gives every node its walk to the nearest assembly area and the next step on the way.
   That tree is cut into small tiles (`docs/data/tree/`) so the site can draw the route from any building.
4. People: WorldPop 2020 (100 m, constrained) shared out to the residential OSM buildings in each cell by footprint area;
   cells without a mapped home keep their people at the cell centre.
5. Istanbul = the 39 districts holding IBB assembly areas.

## Data & licences

Acil Durum Toplanma Alanları © İBB Açık Veri Portalı · © OpenStreetMap contributors (ODbL, Geofabrik extract) ·
WorldPop (2020), CC BY 4.0. Barış Parlatangiller · built with AI assistance (Claude, Anthropic) · code MIT.
