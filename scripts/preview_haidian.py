"""用 Campus Web 的配色规则把 output/haidian.geojson 画成 output/preview.png，便于人工检查。"""
import json, math
from pathlib import Path
from shapely.geometry import shape
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findSystemFonts

ROOT = Path(__file__).resolve().parent.parent
cjk = [f for f in findSystemFonts() if any(k in f for k in ("NotoSansCJK", "msyh", "simhei", "simsun", "SourceHan"))]
fp = FontProperties(fname=cjk[0]) if cjk else None
BC = {"教学科研": "#6688a8", "住宿生活": "#df8b77", "餐饮": "#75a879", "公共文化": "#d0ae58", "医疗服务": "#59a8a1",
      "商业服务": "#ad82aa", "校园设施": "#93a1a8", "出入口安保": "#c9844f", "体育场地": "#4eae5b", "综合/待核": "#a6a09a"}


def sport_color(p):
    if p.get("surface") == "track-infield":
        return "#4eae5b"
    return {"田径场": "#c77963", "篮球场": "#76bfc9", "排球场": "#76bfc9", "网球场": "#76bfc9"}.get(p.get("name"), "#4eae5b")


def fill(ax, g, fc, ec="none", z=1, lw=0.5, holes=True):
    from matplotlib.path import Path as MPath
    from matplotlib.patches import PathPatch
    for p in getattr(g, "geoms", [g]):
        verts, codes = [], []
        for ring in [p.exterior, *p.interiors]:
            cs = list(ring.coords)
            verts += cs
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(cs) - 2) + [MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts, codes), fc=fc, ec=ec, lw=lw, zorder=z))


F = json.loads((ROOT / "output" / "haidian.geojson").read_text(encoding="utf-8"))["features"]
fig, ax = plt.subplots(figsize=(13, 13))
ax.set_facecolor("#f7f9f8")
for f in F:
    p, g, L = f["properties"], shape(f["geometry"]), f["properties"]["layer"]
    if L == "green":
        fill(ax, g, "#e1f2d6" if p.get("surface") == "base" else "#c6e4b2", z=1)
    elif L == "roadp":
        fill(ax, g, "#d3d8d4", "#75827a", 2, 0.6)
    elif L == "sport":
        fill(ax, g, sport_color(p), "#555", 3, 0.3)
    elif L == "building":
        fill(ax, g, BC.get(p.get("category"), "#a6a09a"), "#555", 4, 0.5)
        if p.get("name"):
            ax.text(g.centroid.x, g.centroid.y, p["name"], fontproperties=fp, fontsize=5.5, ha="center", va="center", zorder=6)
    elif L == "boundary":
        ax.plot(*g.exterior.xy, "k-", lw=1.5, zorder=5)
ax.autoscale_view()
ax.set_aspect(1 / math.cos(math.radians(39.95)))
fig.savefig(ROOT / "output" / "preview.png", dpi=85, bbox_inches="tight")
print("output/preview.png")
