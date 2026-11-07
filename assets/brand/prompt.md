# 应用图标生成记录

生成方式：内置 imagegen。用户提供的图 2 用作材质与构图参考；宇通官网标识用作品牌形状参考。

官方标识来源：https://www.yutong.global/static/template/pc2025/resource/images/nav_logo2.svg

最终采用：[图标原图](app-logo.png)（宇通标识 + 三个相连的智能体节点）。

原始图案由内置 imagegen 生成。2026-11-06 用户明确选择“用程序精确裁切”，最终 `app-logo.png` 已生成透明通道，白色圆角底座外部完全透明，RGB 图案逐像素保持原样。ICO 和界面缩略图从这份透明 PNG 生成。

初始不透明原图保存在 `app-logo-opaque.png`，分离遮罩保存在 `app-logo-matte.png`。处理步骤与提示词见 [透明边缘处理记录](alpha-processing.md)。

原始图案生成提示词：

```text
Use case: logo-brand. Create ONE finished square desktop application icon for Yutong Agent Teams. The icon must immediately communicate BOTH Yutong Bus and collaboration between multiple AI agents.

Input 1 is the user's style reference: rounded white tile, blue sculptural logo, understated premium finish. Input 2 is the OFFICIAL Yutong emblem: reproduce the exact THREE nested tapered open blue arches shown on the left, with the same proportions. Do not include the YUTONG lettering.

Composition: a pristine white rounded-square app tile, front-facing and almost filling the square canvas, very subtle bevel and extremely restrained soft blue shading. In the upper-middle portion, display the recognizable Yutong three-arch emblem, width approximately 65% of the tile. In the lower portion, integrate EXACTLY THREE small blue rounded-square agent nodes in a compact triangle: left and right nodes slightly higher, middle node slightly lower. Each node has two small white eye dots, communicating AI agents with minimal detail. Connect all three nodes with clean blue paths to form one unmistakably interconnected team. The three agents share the same visual weight; none appears to be a dominant master. Treat the emblem and connected agents as ONE balanced coherent app mark with generous whitespace, no busy decorations. Keep the arches as an intact separate brand symbol above the network; never reshape the arcs into Wi-Fi or add a fourth arch. Elegant saturated Yutong blue, hints of brighter blue highlight, clean white materials, subtle depth only. Highly legible silhouette at 32px, contemporary desktop software quality.

Output: clean high-resolution SQUARE icon on a solid opaque white canvas. No alpha cutout, no transparency, no outdoor photograph, no dark vignette, no gray smudges, no speckled texture. No text, no letters, no slogan, no additional badges or decorative particles. One icon, no presentation mockup or multiple variations.
```
