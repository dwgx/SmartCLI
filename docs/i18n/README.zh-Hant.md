<!-- Language: [English](../../README.md) | [简体中文](README.zh-Hans.md) | 繁體中文 | [日本語](README.ja.md) | [한국어](README.ko.md) -->

# SmartCLI

*閱讀語言：[English](../../README.md) · [简体中文](README.zh-Hans.md) · **繁體中文** · [日本語](README.ja.md) · [한국어](README.ko.md)*

**驅動、感知並渲染終端機的本地 Python 工具組 — 三個 agent 技能，建構於單一可插拔的 PTY + `pyte` 核心之上。**

[![PyPI](https://img.shields.io/pypi/v/smartcli-toolkit?color=orange)](https://pypi.org/project/smartcli-toolkit/)
[![Python](https://img.shields.io/pypi/pyversions/smartcli-toolkit?color=blue)](https://pypi.org/project/smartcli-toolkit/)
[![CI](https://github.com/dwgx/SmartCLI/actions/workflows/ci.yml/badge.svg)](https://github.com/dwgx/SmartCLI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/pypi/l/smartcli-toolkit?color=green)](../../LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/smartcli-toolkit?color=blueviolet)](https://pypi.org/project/smartcli-toolkit/)
[![Skills: 3](https://img.shields.io/badge/skills-3-purple)](#features)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#安裝)

## 是什麼、為什麼

SmartCLI 是一個為終端機工作打造的工作區，而這些工作 agent 與人都會做：**驅動**互動式終端機程式、**感知**畫面實際顯示的內容，以及把視覺與版面**渲染**回終端機。它建構於單一共用、可插拔的 PTY 後端，再加上 `pyte` 畫面模型 — 之所以選這個做法而非截圖／視覺辨識，是為了讓單一的結構化畫面模型能同時餵給感知（讀取畫面）與渲染（繪製畫面）兩端。PTY 這一層刻意**不**綁定 tmux：本地開發在 Windows 上透過 ConPTY（`pywinpty`）執行，而目標程式則可在別處跑在 POSIX pty 或 tmux 之下。三個技能座落在這個核心之上，每一個都是能從 checkout 原地執行的獨立工具。

CI 會跑 Windows + Linux + macOS 三平台矩陣：POSIX pty 後端在 Linux 與 macOS 上皆已驗證，本地開發則在 Windows 11、Python 3.14.6、`pyte` + `pywinpty` / ConPTY 上驗證。尚未接上真正的 `tmux`，因此截圖報告會誠實地標記為 `pyte-simulation`，而非真正的 tmux 擷取。

## 驅動真實的 TUI

SmartCLI 驅動 **lazygit** —— 一個真正的全螢幕 curses 程式 —— 走過它的
感知 → 行動 → 確認迴圈：它讀取 `pyte` 的儲存格網格（哪一列被選取、alt-screen
的差異），用方向鍵移動、打開某次 commit 的 diff，並將某個分支高亮。這是在
Linux 容器裡驅動實際程式所擷取的，而非腳本模擬。像 pexpect 那樣的位元組串流
比對器無法感知「哪一列被高亮」；畫面模型可以。

<p align="center">
  <img src="../../showcase/drive-lazygit.gif" alt="SmartCLI 驅動 lazygit" width="700">
</p>

> 誠實的範圍說明：CI 會跑 Windows + Linux + macOS 三平台矩陣。POSIX pty 後端
> （spawn／read／drive／resize／zombie-free terminate）在 CI 中已於 Linux 與 macOS
> 上驗證；互動式的 DECCKM/SS3 方向鍵探針在 CI runner 上會被略過，仍需在真實主機上
> 跑一次。真正的 tmux 尚未驗證 —— 參見
> [`skills/drive-tui/references/LIMITATIONS.md`](../../skills/drive-tui/references/LIMITATIONS.md)。

## 螢幕截圖

一小組 `cmd-art` 效果的展示藝廊，透過 `fx` 引擎渲染。以下任一效果都可以用 `python -m fx play <name>` 重現（參見 [Quickstart](#quickstart)）。

| | | |
|:---:|:---:|:---:|
| ![donut](../../showcase/donut.png) | ![fire](../../showcase/fire.png) | ![plasma](../../showcase/plasma.png) |
| **donut** | **fire** | **plasma** |
| ![rain](../../showcase/rain.png) | ![starfield](../../showcase/starfield.png) | ![tunnel](../../showcase/tunnel.png) |
| **rain** | **starfield** | **tunnel** |

## 安裝

**主要方式 — 從 PyPI 安裝：**

```bash
pip install smartcli-toolkit
```

> **發佈名稱與匯入名稱：** PyPI 上的發佈名稱是 `smartcli-toolkit`
> （`smartcli` / `smart-cli` 這兩個名稱已被佔用或封鎖），但可匯入的
> 套件是 `smartcli_core`。所以在 `pip install smartcli-toolkit` 之後，你仍然
> 是寫 `from smartcli_core import PtySession`。

**替代方式 — 從原始碼 checkout 重現完整的開發環境：**

```bash
git clone https://github.com/dwgx/SmartCLI SmartCLI
cd SmartCLI
python -m pip install -r requirements.txt
```

`requirements.txt` 只會拉進兩個必要的執行期相依套件：`pyte`（所有平台）與
`pywinpty`（僅限 Windows — marker 會在 POSIX 上略過它，POSIX 改用標準函式庫的 `pty`
後端）。從 checkout，`pip install .` 會安裝同一個可匯入的
`smartcli_core` 套件。

誠實的範圍說明：`pip install smartcli-toolkit` 會安裝乾淨、可匯入的 `smartcli_core`
套件以及它必要的相依套件。它**不會**搬移那三個技能 — 那些技能是透過各自的進入點
（`python -m fx`、`python -m ui`、
`skills/drive-tui/scripts/tui.py`）原地執行，正如 Quickstart 所示。這是刻意設計的；
參見 [`pyproject.toml`](../../pyproject.toml) 頂端的說明。

**選用的額外套件**（真正的 FIGlet 字型、點陣影像、權威的儲存格寬度 — 缺少時
全都會優雅地退回標準函式庫的備援）：

```bash
python -m pip install -r requirements-optional.txt
# or, from the checkout, via pyproject extras:
pip install ".[all]"        # pyfiglet + Pillow + wcwidth
pip install ".[art]"        # pyfiglet only
pip install ".[image]"      # Pillow only  (also: the PNG screenshot harness needs it)
pip install ".[width]"      # wcwidth only
```

**Windows 注意事項：** 在執行任何技能前先設定 UTF-8 輸出，讓框線繪製字元與 CJK
字符能乾淨地編碼（這些 CLI 也會自動重設 stdout，但保險起見還是設定一下）：

```powershell
set PYTHONIOENCODING=utf-8
```

在開發機（Windows 11、CPython 3.14.6）上已驗證的相依套件版本：`pyte` 0.8.2、
`pywinpty` 3.0.5、`pyfiglet` 1.0.4、`Pillow` 12.2.0、`wcwidth` 0.8.1。

## Quickstart

### cmd-art — 終端機視覺效果

```bash
cd skills/cmd-art
python -m fx list                          # list all 30 effects
python -m fx play donut --seconds 5        # play one effect (bounded)
python -m fx gallery                       # one frame of each effect
python -m fx show --seq "donut:fire:3,plasma::3"
```

### tui-ui — 儲存格精確的終端機 UI

```bash
cd skills/tui-ui
python -m ui widgets                       # list all 17 widgets
python -m ui gallery --width 100 --height 30
python -m ui demo table --width 80 --height 12 --theme dashboard
```

### drive-tui — 感知並驅動互動式程式

持續連線的 CLI（狀態會在多次 shell 呼叫之間保留）：

```bash
python skills/drive-tui/scripts/tui.py start --cmd "python" --cols 80 --rows 24
python skills/drive-tui/scripts/tui.py wait-regex --id <SID> ">>> " --timeout-ms 15000
python skills/drive-tui/scripts/tui.py send-line --id <SID> "print(6*7)"
python skills/drive-tui/scripts/tui.py snapshot --id <SID>
python skills/drive-tui/scripts/tui.py close --id <SID>
```

### 作為函式庫使用

共用核心可以直接匯入：

```python
import sys
from smartcli_core import PtySession

s = PtySession()
s.start([sys.executable, "-q"])
s.wait_for(r">>> ")            # readiness sync, never a blind sleep
print(s.snapshot().to_text())  # pyte-backed structured screen
s.close()
```

完整的指令參考、截圖／AGENTCLI 測試工具，以及回歸測試套件，
請參見 **[`README-USAGE.md`](../../README-USAGE.md)**。

## Features

**`cmd-art`**（`skills/cmd-art`）— 一套「活範本」效果引擎：`Effect` ABC +
`@register` 裝飾器 + 自動探索。橫跨 **8 種主題**（mono、fire、
ocean、synthwave、viridis、pastel、matrix-green、rainbow）的 **30 種效果**（donut、solarsystem、fire、plasma、rain、
starfield、tunnel、text3d、cube、sphere、boids、life、fireworks、sparkle、decrypt、
gradient_text、banner_scroll、image2ascii、typewriter、julia、mandelbrot、perlin、flames、water、nebula、text_flyin、text_converge、text_decrypt、spectrum_bars、cbonsai）。這些效果是純粹的畫格
產生器；`play` 預設有時間界限，且一定會還原終端機狀態。

**`tui-ui`**（`skills/tui-ui`）— 一套類 web 的終端機版面引擎，輸出對 tmux 安全的
ANSI 畫格（只有 SGR 色彩序列 + 換行；沒有游標移動、沒有 alt-screen）。建構在真正的**引擎**之上的 **15 種
widget**（badge、banner、braille_chart、card、gradient_rule、kv、meter、panel、
progress、radial_glow、rule、slider_track、table、tabs、tree）：
`field.py`（shader 合成器）、`raster.py`（子儲存格 half/quad/braille 像素）、
`box_junction.py`（邊緣代數框線接合）、`color_model.py`（誠實的 truecolor → 256 →
16 → mono 降階）。對 CJK／emoji／ZWJ 做到顯示儲存格精確，讓欄位永遠不會失去對齊。

**`drive-tui`**（`skills/drive-tui`）— 透過 PTY 驅動互動式終端機程式（REPL、
選單、pager、y/N 提示、精靈），採用
感知 → 決策 → 動作 → 等待 → 確認的迴圈，絕不盲目 sleep。一個輕薄的 CLI
（`scripts/tui.py`）提供持續的分離式連線與一次性的 `run` 模式，並附帶
一套可匯入的模式函式庫，內含 **8 種 recipe**（repl、menu_select、pager、search_filter、
confirm、form、progress、wizard），能對畫面做 `classify()` 並加以 `drive()`。

**共用核心**（`smartcli_core`）— 可插拔的 PTY 後端 + `pyte` 畫面模型 +
語意 snapshot + readiness sync（`pty_backend / screen_model / snapshot / readiness /
session`）。這是三個技能底下那個可重用、可匯入的基礎。

**知識圖譜**（`knowledge/`）— 一個由 122 篇筆記組成的 wiki-link 圖譜，收錄精確的渲染
公式、ANSI 序列與實測常數，每篇筆記都附有出處與交叉連結。
參見 [`knowledge/INDEX.md`](../../knowledge/INDEX.md)。

## 專案結構

```text
SmartCLI/
  smartcli_core/           shared PTY + pyte engine (importable package)
  skills/cmd-art/          fx effect package and CLI (30 effects, 8 themes)
  skills/drive-tui/        TUI pattern library and PTY driver CLI (8 recipes)
  skills/tui-ui/           terminal UI layout engine and widgets (17 widgets)
  tools/screenshot/        pyte -> PNG smoke-test harness
  tools/agentcli/          agent-CLI control validation harness
  knowledge/               122-note knowledge graph (see knowledge/INDEX.md)
  showcase/                rendered effect PNGs (see Screenshots)
  tests/                   direct script-style regressions
  research/                archived first-pass research notes
```

## 文件

- **[`README-USAGE.md`](../../README-USAGE.md)** — 完整的使用速查表：每一個技能、
  截圖與 AGENTCLI 測試工具，以及回歸測試指令。
- **[`knowledge/INDEX.md`](../../knowledge/INDEX.md)** — 122 篇筆記的知識圖譜。
- **[`AGENTCLI-VALIDATION.md`](../../AGENTCLI-VALIDATION.md)** — agent-CLI 控制測試矩陣。
- **[`CHANGELOG.md`](../../CHANGELOG.md)** — 版本發佈歷史。

## 授權

MIT — 參見 [LICENSE](../../LICENSE)。
