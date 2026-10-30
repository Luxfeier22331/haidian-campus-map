"""把 QGIS 底稿 (qgis/minzu_campus.gpkg, GCJ-02) 导出为 Campus Web 海淀地图资产草稿 (WGS84)。

用法（任意装了 Python 3 + shapely 的环境，或 QGIS 自带的 Python）：
    python scripts/export_haidian.py
输出：
    output/haidian.geojson        地图几何（layer = boundary/building/green/roadp/sport）
    output/haidian_places.json    海淀地点目录（与线上 places.json 的 place 结构一致）
    output/id_registry.json       稳定 ID 注册表（feature fid ↔ 源要素）
运行前请关闭 QGIS。
"""
import json, math, sqlite3, struct, sys, hashlib
from pathlib import Path
from shapely import wkb
from shapely.geometry import mapping, shape, Polygon, MultiPolygon, LineString, MultiLineString, Point
from shapely.ops import transform, unary_union
from shapely.validation import make_valid

ROOT = Path(__file__).resolve().parent.parent
GPKG = ROOT / "qgis" / "minzu_campus.gpkg"
OUT = ROOT / "output"
REGISTRY = OUT / "id_registry.json"
SOURCE_ID = "haidian-campus"

# ---------------- GCJ-02 -> WGS84 ----------------
_A = 6378245.0
_EE = 0.00669342162296594323


def _tlat(x, y):
    r = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    r += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return r


def _tlng(x, y):
    r = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    r += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return r


def wgs84_to_gcj02(lng, lat):
    dlat = _tlat(lng - 105.0, lat - 35.0)
    dlng = _tlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = 1 - _EE * math.sin(radlat) ** 2
    sq = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sq) * math.pi)
    dlng = (dlng * 180.0) / (_A / sq * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng, lat):
    wlng, wlat = lng, lat
    for _ in range(20):
        glng, glat = wgs84_to_gcj02(wlng, wlat)
        dlng, dlat = glng - lng, glat - lat
        wlng, wlat = wlng - dlng, wlat - dlat
        if abs(dlng) < 1e-10 and abs(dlat) < 1e-10:
            break
    return wlng, wlat


def to_wgs(g):
    return transform(lambda x, y, z=None: gcj02_to_wgs84(x, y), g)


# ---------------- 读取 GeoPackage ----------------
def parse_gpkg_geom(blob):
    if blob is None:
        return None
    env = (blob[3] >> 1) & 7
    n = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]
    return wkb.loads(bytes(blob[8 + n:]))


def load(table):
    con = sqlite3.connect(f"file:{GPKG}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(f'select * from "{table}" order by fid')]
    con.close()
    for r in rows:
        r["geom"] = parse_gpkg_geom(r["geom"])
    return rows


# ---------------- 几何整理 ----------------
def r7(g):
    return transform(lambda x, y, z=None: (round(x, 7), round(y, 7)), g)


def polys(g):
    g = make_valid(g)
    if g.geom_type == "Polygon":
        return [g]
    return [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon" and p.area > 0]


def orient_ccw(p):
    from shapely.geometry.polygon import orient
    return orient(p, sign=1.0)


# 本地米制，用于给道路线加宽成面
LAT0 = 39.95
KX = 111320 * math.cos(math.radians(LAT0))
KY = 110540


def to_m(g):
    return transform(lambda x, y, z=None: ((x - 116.3) * KX, (y - LAT0) * KY), g)


def from_m(g):
    return transform(lambda x, y, z=None: (x / KX + 116.3, y / KY + LAT0), g)


ROAD_WIDTH_M = {"residential": 7.0, "service": 5.0, "footway": 3.0, "path": 2.0}

# ---------------- 稳定 ID ----------------
def load_registry():
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {"note": "fid 一旦分配就不再改变；删除要素时保留记录并标记 retired。", "layers": {}}


def assign_fid(reg, layer, source_key, start):
    lay = reg["layers"].setdefault(layer, {})
    if source_key in lay:
        lay[source_key]["retired"] = False
        return lay[source_key]["fid"]
    used = {v["fid"] for v in lay.values()}
    fid = max(used | {start - 1}) + 1
    lay[source_key] = {"fid": fid, "retired": False}
    return fid


def source_key(table, row):
    osm = (row.get("osm_id") or "").strip()
    return f"osm:{osm}" if osm else f"gpkg:{table}:{row['fid']}"


# ---------------- 名称来源说明 ----------------
NAME_SOURCE = "QGIS 海淀底稿（参照高德地图人工描绘），用户 lux 人工核对"
NAME_STATUS_OK = "已人工核对"
NAME_STATUS_TODO = "待核"


def building_props(r, fid):
    name = (r.get("name") or "").strip() or None
    cat = r.get("category") or "综合/待核"
    osm = (r.get("osm_id") or "").strip()
    p = {
        "fid": fid,
        "layer": "building",
        "category": cat,
        "geometry_source": f"OpenStreetMap {osm}（GCJ-02 描图校正后转 WGS84）" if osm else "QGIS 手绘（参照高德地图描图，GCJ-02 转 WGS84）",
    }
    if r.get("floors"):
        p["floor"] = int(r["floors"])
    if name:
        p["name"] = name
        p["name_source"] = NAME_SOURCE
        p["name_status"] = NAME_STATUS_OK
    else:
        p["name_status"] = NAME_STATUS_TODO
        p["name_note"] = "名称未确认，按规范不填写正式名称。"
    if osm:
        p["osm_id"] = osm
    return p


# 塑胶场地底板不导出：Campus Web 的样式没有对应配色，会显示成大块绿色并盖住球场；只保留在 QGIS 底稿中。
SPORT_CATS = {"田径场", "足球场", "球场", "运动场"}
# MapLibre 按要素顺序绘制同一 fill 图层：跑道在下，内场其次，其余场地在上
SPORT_ORDER = {"田径场": 0, "足球场": 1, "运动场": 2, "球场": 3}


def main():
    OUT.mkdir(exist_ok=True)
    reg = load_registry()
    for lay in reg["layers"].values():
        for v in lay.values():
            v["retired"] = True
    feats = []
    report = {"warnings": []}

    # boundary
    b = load("campus_boundary")
    for r in b:
        for p in polys(to_wgs(r["geom"])):
            fid = assign_fid(reg, "boundary", source_key("campus_boundary", r), 1)
            feats.append(({"fid": fid, "layer": "boundary", "name": "校园边界"}, p))
    campus = unary_union([to_wgs(r["geom"]) for r in b])

    # green: 绿地底图 + 草坪
    areas = load("areas")
    for r in areas:
        cat = r.get("category")
        if cat not in ("绿地底图", "草坪"):
            continue
        for i, p in enumerate(polys(to_wgs(r["geom"]))):
            key = source_key("areas", r) + (f"#{i}" if i else "")
            fid = assign_fid(reg, "green", key, 1)
            props = {"fid": fid, "layer": "green", "surface": "base" if cat == "绿地底图" else "lawn"}
            if r.get("name") and cat != "绿地底图":
                props["name"] = r["name"]
            feats.append((props, p))

    # sport
    for r in sorted(areas, key=lambda r: (SPORT_ORDER.get(r.get("category"), 9), 0 if r["fid"] == 7 else 1, r["fid"])):
        cat = r.get("category")
        if cat not in SPORT_CATS:
            continue
        name = (r.get("name") or "").strip() or None
        for i, p in enumerate(polys(to_wgs(r["geom"]))):
            key = source_key("areas", r) + (f"#{i}" if i else "")
            fid = assign_fid(reg, "sport", key, 1)
            props = {"fid": fid, "layer": "sport", "sport_category": cat}
            if r["fid"] == 7 or name == "田径场内场":
                props["surface"] = "track-infield"
                name = None
                props["name_note"] = "田径场内场，与跑道共用位置；不单独显示名称。"
            if name:
                props["name"] = "田径场" if cat == "田径场" else name
            if r.get("marking"):
                props["marking"] = r["marking"]
            if (r.get("osm_id") or "").strip():
                props["osm_id"] = r["osm_id"].strip()
            feats.append((props, p))

    # roads -> polygons (roadp)，按真实宽度加宽后合并
    roads = load("roads")
    road_m = []
    for r in roads:
        w = ROAD_WIDTH_M.get(r.get("type") or "", 4.0)
        road_m.append(to_m(to_wgs(r["geom"])).buffer(w / 2, cap_style=1, join_style=1))
    road_union = from_m(unary_union(road_m).simplify(0.2))
    for i, p in enumerate(polys(road_union)):
        fid = assign_fid(reg, "roadp", f"roads-union#{i}", 1)
        feats.append(({"fid": fid, "layer": "roadp"}, p))

    # buildings
    for r in load("buildings"):
        ps = polys(to_wgs(r["geom"]))
        if not ps:
            report["warnings"].append(f"建筑 gpkg fid={r['fid']} 几何为空，已跳过")
            continue
        fid = assign_fid(reg, "building", source_key("buildings", r), 1)
        g = ps[0] if len(ps) == 1 else MultiPolygon(ps)
        if len(ps) > 1:
            g = max(ps, key=lambda q: q.area)
            report["warnings"].append(f"建筑 {r.get('name')} (gpkg fid={r['fid']}) 有 {len(ps)} 个部件，只保留最大的一个")
        feats.append((building_props(r, fid), g))

    # ---------- 写 GeoJSON ----------
    out_feats = []
    for props, g in feats:
        g = r7(orient_ccw(g) if g.geom_type == "Polygon" else g)
        out_feats.append({"type": "Feature", "properties": props, "geometry": mapping(g)})
    fc = {"type": "FeatureCollection", "features": out_feats}
    txt = json.dumps(fc, ensure_ascii=False, separators=(",", ":"))
    (OUT / "haidian.geojson").write_text(txt, encoding="utf-8")

    minx, miny, maxx, maxy = campus.bounds
    meta = {
        "campus": "haidian",
        "name": "海淀校区",
        "bounds": [round(minx, 7), round(miny, 7), round(maxx, 7), round(maxy, 7)],
        "sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
        "feature_counts": {},
        "attribution": "© OpenStreetMap contributors（ODbL 1.0）",
        "crs": "EPSG:4326 / RFC 7946 [longitude, latitude]",
        "warnings": report["warnings"],
    }
    for props, _ in feats:
        meta["feature_counts"][props["layer"]] = meta["feature_counts"].get(props["layer"], 0) + 1
    (OUT / "haidian_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 地点目录 ----------
    import build_places
    places = build_places.build(feats, load("poi"), to_wgs, reg)
    extra_file = ROOT / "data" / "live_only_places.json"
    if extra_file.exists():
        have = {p["id"] for p in places}
        for p in json.loads(extra_file.read_text(encoding="utf-8"))["places"]:
            if p["id"] in have:
                raise SystemExit(f"data/live_only_places.json 中的 {p['id']} 已由底稿生成，请从该文件删除")
            places.append(p)
    (OUT / "haidian_places.json").write_text(json.dumps({"places": places}, ensure_ascii=False, indent=2), encoding="utf-8")

    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("bounds", "feature_counts", "warnings")}, ensure_ascii=False, indent=2))
    print(f"places: {len(places)}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
