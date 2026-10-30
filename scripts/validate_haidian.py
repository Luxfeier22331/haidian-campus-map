"""按交接文档的导出要求校验 output/ 下的海淀资产。用法：python scripts/validate_haidian.py
退出码 0 = 通过；1 = 有错误。"""
import json, sys
from pathlib import Path
from shapely.geometry import shape
from shapely.validation import explain_validity

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
LAYERS = {"boundary", "building", "green", "roadp", "sport"}
PLACE_CATS = {"building", "landmark", "gate", "service", "transport"}
errors, warns = [], []


def err(m): errors.append(m)
def warn(m): warns.append(m)


fc = json.loads((OUT / "haidian.geojson").read_text(encoding="utf-8"))
if fc.get("type") != "FeatureCollection":
    err("haidian.geojson 不是 FeatureCollection")
if "crs" in fc:
    err("RFC 7946 不允许 crs 成员")

seen = set()
bbox = [180, 90, -180, -90]
by_layer = {}
for i, f in enumerate(fc["features"]):
    p = f.get("properties") or {}
    lay, fid = p.get("layer"), p.get("fid")
    tag = f"#{i} {lay}:{fid} {p.get('name') or ''}"
    if lay not in LAYERS:
        err(f"{tag} layer 非法")
    if not isinstance(fid, int):
        err(f"{tag} fid 必须是整数")
    if (lay, fid) in seen:
        err(f"{tag} (layer,fid) 重复")
    seen.add((lay, fid))
    by_layer.setdefault(lay, []).append(f)
    g = shape(f["geometry"])
    if not g.is_valid:
        err(f"{tag} 几何无效：{explain_validity(g)}")
    for x, y in (c for part in getattr(g, "geoms", [g]) for c in (part.exterior.coords if hasattr(part, "exterior") else part.coords)):
        if not (115.5 < x < 117.5 and 39.4 < y < 40.6):
            err(f"{tag} 坐标不像北京的 [经度, 纬度]：{x},{y}")
            break
        bbox = [min(bbox[0], x), min(bbox[1], y), max(bbox[2], x), max(bbox[3], y)]
    if hasattr(g, "exterior"):
        cs = list(g.exterior.coords)
        dup = sum(1 for a, b in zip(cs, cs[1:]) if a == b)
        if dup:
            warn(f"{tag} 有 {dup} 个重复节点")
    if lay == "building" and not p.get("name") and p.get("name_status") != "待核":
        err(f"{tag} 无名称但未标记待核")
    if lay == "building" and p.get("name") and not p.get("name_source"):
        err(f"{tag} 有名称但没有名称来源")

if len(by_layer.get("boundary", [])) != 1:
    err("必须正好有 1 个 boundary")
else:
    bnd = shape(by_layer["boundary"][0]["geometry"]).buffer(0.0002)
    for f in by_layer.get("building", []):
        if not bnd.contains(shape(f["geometry"]).centroid):
            warn(f"建筑 {f['properties'].get('name')} (fid {f['properties']['fid']}) 中心在校园边界外")

places = json.loads((OUT / "haidian_places.json").read_text(encoding="utf-8"))["places"]
pids = set()
for pl in places:
    t = f"地点 {pl.get('id')} {pl.get('title')}"
    if not pl.get("id") or pl["id"] in pids:
        err(f"{t} id 为空或重复")
    pids.add(pl.get("id"))
    if pl.get("campus") != "海淀校区":
        err(f"{t} campus 应为 海淀校区")
    if pl.get("category") not in PLACE_CATS:
        err(f"{t} category 非法")
    lng, lat = pl["geojson"]["geometry"]["coordinates"]
    if not (115.5 < lng < 117.5 and 39.4 < lat < 40.6):
        err(f"{t} 坐标顺序或范围错误")
    for ref in pl.get("mapFeatureRefs", []):
        if ref.get("sourceId") != "haidian-campus":
            err(f"{t} sourceId 应为 haidian-campus")
        if (ref.get("layer"), ref.get("fid")) not in seen:
            err(f"{t} 引用的地图要素 {ref} 不存在")

reg = json.loads((OUT / "id_registry.json").read_text(encoding="utf-8"))
for lay, m in reg["layers"].items():
    fids = [v["fid"] for v in m.values()]
    if len(fids) != len(set(fids)):
        err(f"注册表 {lay} 层 fid 重复")

live_file = ROOT / "reference" / "live_places_20261029.json"
if live_file.exists():
    live_ids = {p["id"] for p in json.loads(live_file.read_text(encoding="utf-8"))["places"] if p.get("campus") == "海淀校区"}
    for lost in sorted(live_ids - pids):
        warn(f"线上海淀地点 {lost} 不在新地点目录中，发布后该链接会失效")

print(f"要素 {len(fc['features'])}，地点 {len(places)}，范围 {[round(v, 7) for v in bbox]}")
for w in warns:
    print("警告:", w)
for e in errors:
    print("错误:", e)
print("校验通过" if not errors else f"校验失败：{len(errors)} 个错误")
sys.exit(1 if errors else 0)
