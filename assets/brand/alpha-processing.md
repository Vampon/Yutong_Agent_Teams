# 透明边缘处理记录

日期：2026-11-06。用户明确选择“用程序精确裁切”。

最终产物：`app-logo.png`，1254 × 1254 RGBA。宇通三重拱形、三个协作节点和白色圆角底座保持原有 RGB 像素，仅重新计算外部透明区域。

1. 原图另存为 `app-logo-opaque.png`。
2. 内置 imagegen 生成外部洋红色的分离遮罩 `app-logo-matte.png`，提示词见下方。
3. `python scripts/prepare-icon-alpha.py` 从分离遮罩提取透明通道，保留中央圆角底座的连通区域及抗锯齿边缘，原始图案提供全部 RGB 像素。
4. `scripts/build-icons.ps1` 生成界面 PNG 和 9 种尺寸的 Windows ICO。程序分发无需 Pillow；Pillow 仅用于重新处理原图。

验证：原图与最终图 RGB 完全相同；圆角底座内部完全不透明；ICO 所有尺寸的四角 alpha 都为 0。深浅背景预览见 `docs/screenshots/fixes-icon-backgrounds.png`，数值记录见 `docs/evidence/fixes-icon-alpha.json`。

分离遮罩提示词（内置 imagegen，非透明输出）：

```text
Production cutout preparation. Edit only the BACKGROUND OUTSIDE the rounded-square white tile in the supplied application icon. Replace the entire outside canvas with one perfectly flat saturated MAGENTA color (#ff00ff), including all four corners. Keep the whole white rounded-square tile COMPLETELY OPAQUE and keep all internal art exactly unchanged: three Yutong blue arches and three connected blue robot nodes, same shape, same positions, same original colors. A single perfectly smooth rounded-square outer boundary separates magenta outside from the fully opaque white/light-blue tile inside. No shadows, white specks or haze outside the tile. This magenta background is an intermediate separation matte, not part of the design. Preserve the original icon composition. No alpha transparency in this intermediate image.
```
