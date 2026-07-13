<!-- Language: [English](../../INSTALL.md) | 简体中文 | [繁體中文](INSTALL.zh-Hant.md) | [日本語](INSTALL.ja.md) | [한국어](INSTALL.ko.md) -->

# 安装 SmartCLI

SmartCLI 是构建在一套可插拔 PTY + `pyte` 内核之上的三个 Agent Skill（`cmd-art`、`drive-tui`、`tui-ui`）。它有三种获取方式，从「把文件夹直接丢进去」到常规的 pip 安装都行。根据你拿到文件的方式，挑对应的一种即可。

## 一句话版 —— 即放即用，零配置

解压发行包，把整个仓库（或者单个 skill 文件夹）丢进你 AI 的 skills 目录。它会在首次使用时自动完成配置：

- **`cmd-art`** 和 **`tui-ui`** 是纯 Python 标准库实现，完全自包含。只要文件落到磁盘上就能用 —— 无需安装，也无需接线。
- **`drive-tui`** 需要 `smartcli_core` 包和 `pyte` 库。它在 `skills/drive-tui/_vendor/` 里内置了一份 `smartcli_core` 副本，所以即便只有孤零零一个 `drive-tui` 文件夹，也能自动找到它的内核。它按以下顺序定位内核：`$SMARTCLI_ROOT` → 任意包含 `smartcli_core/` 的上层文件夹 → 内置的 `_vendor/` → pip 安装的副本。

检查一切是否接通：

```bash
python skills/drive-tui/scripts/tui.py doctor
```

它会打印出 `smartcli_core` 是从哪里解析到的、运行时依赖是否齐全，如果缺了哪个还会给出确切的安装命令。

## 三种场景

### 1. 整个仓库（推荐）

把仓库克隆或解压到任意位置。三个 skill 都能就地工作；`drive-tui` 会一路向上走到仓库根目录来找到 `smartcli_core`。

```bash
git clone https://github.com/dwgx/SmartCLI
# or: unzip the release
python skills/drive-tui/scripts/tui.py doctor
```

### 2. 单个 skill 文件夹，独立丢进去

只复制一个 skill 文件夹（例如 `skills/drive-tui/`）进你 AI 的 skills 目录。`cmd-art` 和 `tui-ui` 不需要任何别的东西。`drive-tui` 在 `_vendor/` 里自带 `smartcli_core`，所以只要保持那个子文件夹完整，它照样能工作：

```bash
python <dropped-in>/drive-tui/scripts/tui.py doctor
# smartcli_core: .../drive-tui/_vendor
```

### 3. Claude 插件

仓库随附了 `.claude-plugin/plugin.json` 和 `.claude-plugin/marketplace.json`，因此它可以作为一个打包了全部三个 skill 的插件来安装：

```
/plugin marketplace add dwgx/SmartCLI
/plugin install smartcli@smartcli
```

### 4. pip（把共享内核当作库用）

要把 `smartcli_core` 当作一个普通的可导入库来用：

```bash
pip install smartcli-toolkit   # import stays: from smartcli_core import PtySession
```

## 依赖

| 包 | 谁需要它 | 自动？ |
|---|---|---|
| `pyte` | `drive-tui` 内核（硬依赖） | 由 `doctor` 报告；按需安装 |
| `pywinpty` | 仅 **Windows** 上的 `drive-tui` | 由 `doctor` 报告；按需安装 |
| `pyfiglet`、`Pillow`、`wcwidth` | 可选的锦上添花 —— 没有它们一切都会优雅降级 | 从不必需 |

`drive-tui` 绝不会背着你偷偷安装任何东西（安装是一种网络行为）。如果 `pyte`/`pywinpty` 缺失，它会打印出确切的命令。若想让它替你安装，请显式选择开启：

```bash
python skills/drive-tui/scripts/tui.py --install-deps start --cmd python
# or: set SMARTCLI_AUTO_INSTALL=1
```

或者一次性把所有东西都装好：

```bash
python -m pip install -r requirements.txt              # required
python -m pip install -r requirements-optional.txt     # optional extras
```

## 保持内置内核同步

`skills/drive-tui/_vendor/` 里的 `smartcli_core` 副本，靠一个工具加一个测试，与顶层规范的 `smartcli_core/` 保持逐字节一致：

```bash
python tools/sync_vendor.py          # refresh the vendored copy
python tools/sync_vendor.py --check  # exit 1 if it has drifted (CI/gate)
python tests/test_vendor_sync.py     # the regression lock
```

如果你改动了 `smartcli_core/`，提交前请先运行 `sync_vendor.py`。
