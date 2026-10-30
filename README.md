# 中央民族大学海淀校区地图

海淀校区地图的导出脚本、成品数据和审阅网页。

**在线查看：<https://luxfeier22331.github.io/haidian-campus-map/>**

审阅网页是一个单文件页面（`index.html`，与 `output/haidian_map.html` 相同），不依赖外部资源，可以缩放、搜索地点、点击建筑查看详情。名称待核的建筑用虚线框标出。

## 仓库内容

| 位置 | 内容 |
|---|---|
| `index.html` | 审阅网页（GitHub Pages 首页） |
| `output/haidian.geojson` | 地图几何成品，EPSG:4326，RFC 7946，图层 `boundary` / `building` / `green` / `roadp` / `sport` |
| `output/haidian_places.json` | 海淀地点目录，结构与 Campus Web 的 places.json 一致 |
| `output/id_registry.json` | 稳定 ID 注册表（地图要素 fid、地点 id），发布后不再改变 |
| `output/haidian_meta.json` | 校区范围、要素数、sha256 |
| `output/preview.png` | 静态预览图 |
| `scripts/` | 导出、校验、预览、生成审阅网页的脚本 |
| `review/` | 每一轮修改的审核记录 |
| `交接文档.md`、`工作区说明.md` | 本地工作流程（引用的 `qgis/` 源数据没有上传） |

制图源数据（QGIS 项目和 GeoPackage）不在仓库里，所以 `scripts/` 不能直接在仓库里重新导出。

## 更新流程

在本地工作区（含 `qgis/minzu_campus.gpkg`）依次运行：

```
python scripts/export_haidian.py
python scripts/validate_haidian.py
python scripts/preview_haidian.py
python scripts/build_viewer.py
```

把 `output/` 里的文件复制到仓库，再把 `output/haidian_map.html` 复制成 `index.html` 后提交，Pages 会自动更新。

## 数据来源与许可

- 部分建筑、道路、运动场几何来自 © OpenStreetMap contributors，按 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) 提供。含 OSM 几何的 GeoJSON 及其衍生数据同样适用 ODbL。
- 其余几何为人工描绘，建筑名称经人工核对。
- 高德地图只作为人工描图参照，仓库中不含高德瓦片或数据。
