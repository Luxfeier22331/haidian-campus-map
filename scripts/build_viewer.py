"""把 output/ 中的地图和地点目录打包成一个可直接打开、可发给别人的网页：output/haidian_map.html。
运动场按 QGIS 原样显示：另外从 qgis/minzu_campus.gpkg 读取塑胶场地底板和场地标线（这两层不进 haidian.geojson）。
用法：python scripts/build_viewer.py（在 export_haidian.py 之后运行）"""
import json, datetime, sys
from pathlib import Path
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_haidian as E


def js(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def overlay():
    feats = []
    for r in E.load("areas"):
        if r.get("category") == "塑胶场地":
            for p in E.polys(E.to_wgs(r["geom"])):
                feats.append({"type": "Feature", "properties": {"kind": "pad"}, "geometry": mapping(E.r7(p))})
    for r in E.load("markings"):
        if r["geom"] is not None:
            feats.append({"type": "Feature", "properties": {"kind": "marking"}, "geometry": mapping(E.r7(E.to_wgs(r["geom"])))})
    return {"type": "FeatureCollection", "features": feats}


geo = json.loads((OUT / "haidian.geojson").read_text(encoding="utf-8"))
places = json.loads((OUT / "haidian_places.json").read_text(encoding="utf-8"))["places"]
meta = {"date": datetime.date.today().isoformat()}
tpl = (ROOT / "scripts" / "viewer_template.html").read_text(encoding="utf-8")
html = (tpl.replace("__GEO__", js(geo)).replace("__OVERLAY__", js(overlay()))
        .replace("__PLACES__", js(places)).replace("__META__", js(meta)))
(OUT / "haidian_map.html").write_text(html, encoding="utf-8")
print(f"output/haidian_map.html  {len(html) // 1024} KB")
