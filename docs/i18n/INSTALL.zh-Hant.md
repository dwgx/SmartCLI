<!-- Language: [English](../../INSTALL.md) | [简体中文](INSTALL.zh-Hans.md) | 繁體中文 | [日本語](INSTALL.ja.md) | [한국어](INSTALL.ko.md) -->

# 安裝 SmartCLI

SmartCLI 是三個 Agent Skills（`cmd-art`、`drive-tui`、`tui-ui`），全都建構在同一套可插拔的 PTY + `pyte` 核心之上。取得它的方式有三種，從「直接把資料夾丟進去」到一般的 pip 安裝都有，挑一個符合你拿到檔案方式的做法即可。

## TL;DR — 免設定，丟進去就能用

解壓縮 release，把整個 repo（或單獨一個 skill 資料夾）丟進你 AI 的 skills 目錄。第一次使用時它就會自動完成設定：

- **`cmd-art`** 與 **`tui-ui`** 是純 Python 標準函式庫、完全自給自足。只要檔案就位就能運作，不用安裝，也不用做任何串接。
- **`drive-tui`** 需要 `smartcli_core` 套件與 `pyte` 函式庫。它在 `skills/drive-tui/_vendor/` 內附帶了一份 `smartcli_core` 的複本，所以即使只有單獨一個 `drive-tui` 資料夾，也能自動找到它的核心。它依這個順序定位核心：`$SMARTCLI_ROOT` → 任何含有 `smartcli_core/` 的上層資料夾 → 隨附的 `_vendor/` → pip 安裝的複本。

確認一切都串接妥當：

```bash
python skills/drive-tui/scripts/tui.py doctor
```

這會印出 `smartcli_core` 是從哪裡解析而來、以及執行期相依套件是否齊備；若有缺少，還會附上確切的安裝指令。

## 三種情境

### 1. 整個 repo（建議）

把 repo clone 或解壓縮到任何地方。三個 skill 都能就地運作；`drive-tui` 會往上走到 repo 根目錄來找到 `smartcli_core`。

```bash
git clone https://github.com/dwgx/SmartCLI
# or: unzip the release
python skills/drive-tui/scripts/tui.py doctor
```

### 2. 單獨丟進去的一個 skill 資料夾

只複製其中一個 skill 資料夾（例如 `skills/drive-tui/`）到你 AI 的 skills 目錄。`cmd-art` 與 `tui-ui` 不需要任何其他東西。`drive-tui` 把它的 `smartcli_core` 帶在 `_vendor/` 裡，所以只要保持那個子資料夾完整，它照樣能運作：

```bash
python <dropped-in>/drive-tui/scripts/tui.py doctor
# smartcli_core: .../drive-tui/_vendor
```

### 3. Claude 外掛

repo 隨附了 `.claude-plugin/plugin.json` 與 `.claude-plugin/marketplace.json`，因此可以當成一個外掛安裝，把三個 skill 全部打包在一起：

```
/plugin marketplace add dwgx/SmartCLI
/plugin install smartcli@smartcli
```

### 4. pip（把共用核心當函式庫）

若要把 `smartcli_core` 當成一般可 import 的函式庫使用：

```bash
pip install smartcli-toolkit   # import stays: from smartcli_core import PtySession
```

## 相依套件

| 套件 | 由誰需要 | 自動？ |
|---|---|---|
| `pyte` | `drive-tui` 核心（硬相依） | 由 `doctor` 回報；經要求才安裝 |
| `pywinpty` | 僅 **Windows** 上的 `drive-tui` | 由 `doctor` 回報；經要求才安裝 |
| `pyfiglet`、`Pillow`、`wcwidth` | 選用的加分項 — 沒有它們一切也會優雅降級 | 從不強制 |

`drive-tui` 絕不會在你背後偷裝任何東西（安裝是一種網路動作）。若缺少 `pyte`/`pywinpty`，它會印出確切的指令。若要讓它替你安裝，請明確選擇加入：

```bash
python skills/drive-tui/scripts/tui.py --install-deps start --cmd python
# or: set SMARTCLI_AUTO_INSTALL=1
```

或者一開始就全部裝好：

```bash
python -m pip install -r requirements.txt              # required
python -m pip install -r requirements-optional.txt     # optional extras
```

## 讓隨附的核心保持同步

`skills/drive-tui/_vendor/` 內的 `smartcli_core` 複本，會靠一支工具加一項測試，與最上層正規的 `smartcli_core/` 保持位元組完全一致：

```bash
python tools/sync_vendor.py          # refresh the vendored copy
python tools/sync_vendor.py --check  # exit 1 if it has drifted (CI/gate)
python tests/test_vendor_sync.py     # the regression lock
```

若你更動了 `smartcli_core/`，請在 commit 前先執行 `sync_vendor.py`。
