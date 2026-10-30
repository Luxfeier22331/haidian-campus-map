"""由导出的地图要素生成海淀地点目录（结构与线上 places.json 中的 place 一致）。

地点 ID 规则：已定稿的 ID 写在 id_registry.json 的 "places" 中（与线上同名的沿用线上 ID，其余为英文意译），
改名不会改变 ID。新增地点首次导出时由名称拼音临时生成 `haidian-xxx`，发布前请在注册表里改成英文意译。
"""
import re
from shapely.geometry import shape

try:
    from pypinyin import lazy_pinyin
except ImportError:  # 没装 pypinyin 时退化为 fid
    lazy_pinyin = None

CAMPUS = "海淀校区"
SOURCE_ID = "haidian-campus"
NAME_REF = "campus-map:private-source:haidian-qgis-draft"


def slug(name, fallback):
    if lazy_pinyin:
        s = "-".join(lazy_pinyin(name))
        s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        if s:
            return "haidian-" + s
    return f"haidian-{fallback}"


def tags_for(props, name):
    cat = props.get("category", "")
    t = []
    if "食堂" in name or cat == "餐饮":
        t += ["食堂", "生活"]
    elif "公寓" in name or "宿舍" in name or cat == "住宿生活":
        t += ["宿舍" if "学生" in name else "公寓", "生活"]
    elif "教学" in name or cat == "教学科研":
        t += ["教学", "上课"]
    elif cat == "医疗服务":
        t += ["医疗", "门诊"]
    elif cat == "公共文化":
        t += ["文化", "地标"]
    elif cat == "商业服务":
        t += ["商业", "服务"]
    elif cat == "体育场地":
        t += ["运动", "体育馆"]
    elif cat in ("校园设施", "出入口安保"):
        t += ["办事", "服务"]
    else:
        t += ["办公"]
    return t + ["海淀"]


def place_category(layer, props, name):
    if layer == "sport" or props.get("category") == "体育场地":
        return "landmark"
    if props.get("category") == "医疗服务":
        return "service"
    if props.get("category") == "公共文化" and any(k in name for k in ("礼堂", "剧院", "博物馆", "美术馆")):
        return "landmark"
    return "building"


def build(feats, poi_rows, to_wgs, reg):
    ids = reg.setdefault("places", {})
    used = set(ids.values())
    out = []

    def pid_for(key, name, fallback):
        if key in ids:
            return ids[key]
        base = slug(name, fallback)
        pid, n = base, 2
        while pid in used:
            pid = f"{base}-{n}"
            n += 1
        ids[key] = pid
        used.add(pid)
        return pid

    def add(key, title, layer, props, geom, category, tags, desc, extra=None, refs=True):
        pid = pid_for(key, title, f"{layer}-{props.get('fid', 'x')}")
        pt = geom.representative_point() if geom.geom_type != "Point" else geom
        rows = list(extra or [])
        p = {
            "accessNote": None,
            "additionalProperties": rows,
            "campus": CAMPUS,
            "category": category,
            "description": desc,
            "geojson": {
                "geometry": {"coordinates": [round(pt.x, 7), round(pt.y, 7)], "type": "Point"},
                "properties": {"category": category, "placeId": pid, "title": title},
                "type": "Feature",
            },
            "id": pid,
            "sourceRefs": [NAME_REF, f"campus-map:projection:{pid}"],
            "tags": tags,
            "title": title,
        }
        if refs:
            p["mapFeatureRefs"] = [{"fid": props["fid"], "layer": layer, "sourceId": SOURCE_ID}]
        out.append(p)

    # 建筑：只收已核对名称的
    for props, g in feats:
        if props["layer"] != "building" or not props.get("name"):
            continue
        name = props["name"]
        extra = []
        if props.get("floor"):
            extra.append({"label": "楼层", "value": f"{props['floor']}层"})
        extra += [
            {"label": "地图分类", "value": props.get("category", "")},
            {"label": "名称状态", "value": props.get("name_status", "")},
            {"label": "名称来源", "value": props.get("name_source", "")},
        ]
        add(f"building:{props['fid']}", name, "building", props, g,
            place_category("building", props, name), tags_for(props, name),
            f"海淀校区{name}。", extra)

    # 运动场：同名场地合并为一个地点，引用所有要素
    groups = {}
    for props, g in feats:
        if props["layer"] == "sport" and props.get("name"):
            groups.setdefault(props["name"], []).append((props, g))
    for name, items in groups.items():
        from shapely.ops import unary_union
        g = unary_union([x[1] for x in items])
        key = f"sport-group:{name}"
        pid = pid_for(key, name, f"sport-{items[0][0]['fid']}")
        pt = g.representative_point()
        out.append({
            "accessNote": None,
            "additionalProperties": [{"label": "场地数量", "value": f"{len(items)}块"}],
            "campus": CAMPUS,
            "category": "landmark",
            "description": f"海淀校区{name}" + (f"，共{len(items)}块。" if len(items) > 1 else "。"),
            "geojson": {"geometry": {"coordinates": [round(pt.x, 7), round(pt.y, 7)], "type": "Point"},
                        "properties": {"category": "landmark", "placeId": pid, "title": name}, "type": "Feature"},
            "id": pid,
            "mapFeatureRefs": [{"fid": p["fid"], "layer": "sport", "sourceId": SOURCE_ID} for p, _ in items],
            "sourceRefs": [NAME_REF, f"campus-map:projection:{pid}"],
            "tags": ["运动", name.replace("场", ""), "海淀"],
            "title": name,
        })

    # 兴趣点：点位置，无地图要素引用
    for r in poi_rows:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        g = to_wgs(r["geom"])
        cat = "service"
        tags = ["服务", "海淀"]
        extra = []
        if r.get("type") == "bank":
            tags = ["银行", "服务", "海淀"]
        elif r.get("type") == "gate":
            cat = "gate"
            tags = ["出入口", "交通", "海淀"]
        add(f"poi:{r['fid']}", name, "poi", {"fid": r["fid"]}, g, cat, tags,
            f"海淀校区{name}。", extra, refs=False)
    return out
