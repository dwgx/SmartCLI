# 终端渲染第一性原理 — tui-ui 的理论内核

> 这不是又一组 widget。这是所有 widget 都必须建立其上的底层模型。
> 任何新效果/组件先问:它是哪个原语的组合？不能回答就说明还没理解到位。

## 公理:终端 = 离散字符栅格

一块 `cols × rows` 的网格。每格是一个 `Cell = (glyph, fg, bg, attrs)`。
**没有像素、没有连续坐标**——一切最终塌缩成整格。人类做终端图形的所有技巧，
都是在"如何用离散格子逼近连续视觉"这一个问题上做文章。

## 四个底层原语（skill 内核）

### 1. CellField — 万物皆着色器场
任何可渲染的东西本质是一个纯函数（片元着色器）：
```
S(x, y, t) -> Sample(glyph, fg, bg, alpha)
```
- `x,y` 格坐标，`t` 时间相位。
- ripple / glow / gradient / plasma / fire / 扫描线 —— **全是不同的 S**，
  不是各写各的 widget。引擎负责采样每格、alpha 合成、run-length 序列化。
- 组合是场的代数：`over(A,B)`、`add`、`mask`、空间变换（平移/缩放）。

**几何真理（最重要的一条）**：字符格 高≈2×宽，所以 `ASPECT = 2.0`。
任何"各向同性/圆/等距"的度量必须校正 y：
```
dist(x,y, ox,oy) = sqrt( (x-ox)^2 + ((y-oy) * ASPECT)^2 )
angle(...)       = atan2( (y-oy)*ASPECT , x-ox )
```
参考选择器的 ripple 中 `((row-2)*2)^2` 就是这条。忽略它 → 圆变竖条（我犯过）。

内核自带的 field 词汇（每个都只是一个 S，~10 行）：
- `Ripple(origin, wavelength, travel, palette)`：`d=dist; if d>travel: none; r=(d-travel)%λ; a=(1+cos(2π r/λ))/2; level=round(a·(n-1))`
- `RadialGlow(center, radius, ramp)`：`i=1-(d/R)^2`（quadratic）clamp0。
- `LinearGradient(stops, axis)`：沿轴插值。
- `Plasma(t)`：sin 之和。`Noise/Fire`：缓冲迭代。

### 2. SubcellRaster — 亚格分辨率（平滑的来源）
整格只有 cols×rows 分辨率 → 永远 blocky。用特殊字形编码子像素：
- 半块 `▀`(上)`▄`(下)+ fg/bg 双色 → **1×2 像素/格**。
- 四分块 `▘▝▖▗▀▄▌▐█…` → **2×2**。
- 盲文 `U+2800..U+28FF`（8 点位）→ **2×4**（最高密度，画曲线/图）。
一个 W×H 网格 = 最高 `W·2 × H·4` 的像素缓冲。
流程：渲染进 SubcellRaster（真像素）→ downsample 成对应字形 + 颜色 →
写回 Cell。图片、平滑圆、抗锯齿曲线、迷你图都走这条。
**这是"像网页一样平滑"缺的那块——不能只用整格背景色。**

### 3. BoxJunction — 结构是连接代数
边框/表格/树不该手摆 `─│┌┐`。每格记 4 条边的权重：
```
edge[N,E,S,W] ∈ {0:无, 1:细, 2:粗, 3:双}
```
glyph = 纯查表 `LOOKUP[(n,e,s,w)]`（Unicode box-drawing 全集）。
两条线交叉 → 自动出 `┼`；细碰粗 → `┿`。任意布局的边框都自动接上，
表格分隔、树枝、圆角面板全部从同一张表长出来。

### 4. ColorModel — 诚实的颜色与对齐
- truecolor `\x1b[38;2;r;g;bm` / bg `48;2`；attrs bold/dim/reverse。
- **诚实降级**：truecolor→256（6×6×6+灰阶最近邻）→16→mono（按亮度阈值选字符）。
  声明支持某档就必须真降级，不能假装。
- **宽度对齐**：`wcwidth` —— CJK/emoji 占 2 格，宽字后跟 cont 空格，
  否则整行列错位（表格、对齐全废）。
- 序列化：仅在样式变化时发 SGR（run-length），行尾 reset。tmux 安全（只 SGR+换行）。
  **行分隔用 CRLF**（终端 LF 只下移不回列；harness 已把 \n→\r\n）。

## 一切如何组合（验证内核是否成立的试金石）
- 渐变实线分隔 = `LinearGradient` field 采一行。
- ultracode 发光 = `Ripple` field washes 面板，白字 over 之上。
- 平滑进度条/迷你图 = `SubcellRaster`。
- 面板/表格/树 = `BoxJunction` + 内容 field。
- **effort 选择器 = 布局(labelStarts/trianglePositions) + Ripple field + 文本 over。**
  它只是内核的一次组合 + 一份 ~12 行的 field 定义，不是一个 bespoke 脚本。

如果一个新需求不能表达成「上面某几个原语的组合」，先扩原语，别再写死 widget。

## See also（知识图谱 twin）
本文在 SmartCLI 知识图谱里的对应节点：`D:/Project/SmartCLI/knowledge/INDEX.md`
- 图谱 twin：[[rendering-model]]（四原语内核）。
- 基础：[[cell-grid-model]] · [[ansi-sgr-color]] · [[terminal-cell-aspect-ratio]] · [[sub-cell-resolution]] · [[flicker-free-rendering]]。
- 布局：[[box-model-on-cell-grid]] · [[fractional-space-distribution]] · [[box-drawing-glyphs]]。
- 具体 field 公式：`knowledge/effects/`（如 [[plasma]]）、`knowledge/color-type/`（[[color-interpolation]] · [[hsv-cycling-lolcat]]）。
- 复刻 case：[[effort-selector]]（effort = 布局 + Ripple field + 文本 over）。
