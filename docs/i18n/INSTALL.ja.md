<!-- Language: [English](../../INSTALL.md) | [简体中文](INSTALL.zh-Hans.md) | [繁體中文](INSTALL.zh-Hant.md) | 日本語 | [한국어](INSTALL.ko.md) -->

# SmartCLI のインストール

SmartCLI は、プラグイン可能な PTY + `pyte` コアの上に構築された 3 つの Agent Skill（`cmd-art`、`drive-tui`、`tui-ui`）です。導入方法は「フォルダをそのまま置くだけ」から通常の pip インストールまで 3 通りあります。ファイルをどのように入手したかに合わせて選んでください。

## TL;DR — 設定不要、置くだけ

リリースを展開し、リポジトリ全体（あるいは単一のスキルフォルダだけ）を AI のスキルディレクトリに置いてください。初回利用時に自動で設定されます。

- **`cmd-art`** と **`tui-ui`** は純粋な Python 標準ライブラリのみで完結しています。ディスク上に置いた時点で動作し、インストールも設定も不要です。
- **`drive-tui`** には `smartcli_core` パッケージと `pyte` ライブラリが必要です。`skills/drive-tui/_vendor/` の中に `smartcli_core` の同梱コピーを持っているため、`drive-tui` フォルダ単体でもコアを自動的に見つけます。コアの探索順序は次のとおりです。`$SMARTCLI_ROOT` → `smartcli_core/` を含む親フォルダ → 同梱の `_vendor/` → pip でインストールされたコピー。

すべてが正しくセットアップされているか確認します。

```bash
python skills/drive-tui/scripts/tui.py doctor
```

このコマンドは、`smartcli_core` がどこから解決されたか、ランタイム依存がそろっているかを表示し、不足しているものがあれば正確なインストールコマンドも示します。

## 3 つのシナリオ

### 1. リポジトリ全体（推奨）

任意の場所にリポジトリをクローンまたは展開します。3 つのスキルはすべてその場で動作し、`drive-tui` はリポジトリのルートまで遡って `smartcli_core` を見つけます。

```bash
git clone https://github.com/dwgx/SmartCLI
# or: unzip the release
python skills/drive-tui/scripts/tui.py doctor
```

### 2. 単一のスキルフォルダを単独で配置

スキルフォルダを 1 つだけ（例: `skills/drive-tui/`）AI のスキルディレクトリにコピーします。`cmd-art` と `tui-ui` は他に何も必要としません。`drive-tui` は `_vendor/` に `smartcli_core` を同梱しているため、そのサブフォルダをそのまま残しておけば単体でも動作します。

```bash
python <dropped-in>/drive-tui/scripts/tui.py doctor
# smartcli_core: .../drive-tui/_vendor
```

### 3. Claude プラグイン

リポジトリには `.claude-plugin/plugin.json` と `.claude-plugin/marketplace.json` が同梱されているため、3 つのスキルすべてをまとめたプラグインとしてインストールできます。

```
/plugin marketplace add dwgx/SmartCLI
/plugin install smartcli@smartcli
```

### 4. pip（共有コアをライブラリとして）

`smartcli_core` を通常の import 可能なライブラリとして使うには、次のようにします。

```bash
pip install smartcli-toolkit   # import stays: from smartcli_core import PtySession
```

## 依存関係

| パッケージ | 必要とする対象 | 自動？ |
|---|---|---|
| `pyte` | `drive-tui` コア（必須の依存） | `doctor` が報告；要求に応じてインストール |
| `pywinpty` | **Windows** 上の `drive-tui` のみ | `doctor` が報告；要求に応じてインストール |
| `pyfiglet`、`Pillow`、`wcwidth` | 任意の便利機能 — なくてもすべて適切にフォールバックします | 一切不要 |

`drive-tui` があなたの知らないところで何かをインストールすることは決してありません（インストールはネットワーク操作だからです）。`pyte`/`pywinpty` が不足している場合は正確なコマンドを表示します。`drive-tui` にインストールを任せたい場合は、明示的にオプトインしてください。

```bash
python skills/drive-tui/scripts/tui.py --install-deps start --cmd python
# or: set SMARTCLI_AUTO_INSTALL=1
```

あるいは、すべてを事前にインストールしておくこともできます。

```bash
python -m pip install -r requirements.txt              # required
python -m pip install -r requirements-optional.txt     # optional extras
```

## 同梱コアを同期させておく

`skills/drive-tui/_vendor/` 内の `smartcli_core` のコピーは、ツールとテストによって、正規のトップレベル `smartcli_core/` とバイト単位で同一に保たれています。

```bash
python tools/sync_vendor.py          # refresh the vendored copy
python tools/sync_vendor.py --check  # exit 1 if it has drifted (CI/gate)
python tests/test_vendor_sync.py     # the regression lock
```

`smartcli_core/` を変更した場合は、コミットする前に `sync_vendor.py` を実行してください。
