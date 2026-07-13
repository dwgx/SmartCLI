<!-- Language: English | [简体中文](docs/i18n/INSTALL.zh-Hans.md) | [繁體中文](docs/i18n/INSTALL.zh-Hant.md) | [日本語](docs/i18n/INSTALL.ja.md) | [한국어](docs/i18n/INSTALL.ko.md) -->

# Installing SmartCLI

SmartCLI is three Agent Skills (`cmd-art`, `drive-tui`, `tui-ui`) over one
pluggable PTY + `pyte` core. There are three ways to get it, from "just drop the
folder in" to a normal pip install. Pick the one that matches how you got the
files.

## TL;DR — drop-in, zero config

Unzip the release and drop the whole repo (or just a single skill folder) into
your AI's skills directory. It self-configures on first use:

- **`cmd-art`** and **`tui-ui`** are pure Python stdlib and fully self-contained.
  They work the moment they are on disk — nothing to install, nothing to wire.
- **`drive-tui`** needs the `smartcli_core` package and the `pyte` library. It
  ships a bundled copy of `smartcli_core` inside `skills/drive-tui/_vendor/`, so
  even a lone `drive-tui` folder finds its core automatically. It locates the
  core in this order: `$SMARTCLI_ROOT` → any parent folder that contains
  `smartcli_core/` → the bundled `_vendor/` → a pip-installed copy.

Check everything is wired up:

```bash
python skills/drive-tui/scripts/tui.py doctor
```

That prints where `smartcli_core` resolved from and whether the runtime deps are
present, with the exact install command if any are missing.

## The three scenarios

### 1. Whole repo (recommended)

Clone or unzip the repo anywhere. All three skills work in place; `drive-tui`
finds `smartcli_core` by walking up to the repo root.

```bash
git clone https://github.com/dwgx/SmartCLI
# or: unzip the release
python skills/drive-tui/scripts/tui.py doctor
```

### 2. A single skill folder, dropped in standalone

Copy just one skill folder (e.g. `skills/drive-tui/`) into your AI's skills
directory. `cmd-art` and `tui-ui` need nothing else. `drive-tui` carries its
`smartcli_core` in `_vendor/`, so keep that subfolder intact and it still works:

```bash
python <dropped-in>/drive-tui/scripts/tui.py doctor
# smartcli_core: .../drive-tui/_vendor
```

### 3. Claude plugin

The repo ships `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`,
so it installs as a plugin bundling all three skills:

```
/plugin marketplace add dwgx/SmartCLI
/plugin install smartcli@smartcli
```

### 4. pip (the shared core as a library)

To use `smartcli_core` as a normal importable library:

```bash
pip install smartcli-toolkit   # import stays: from smartcli_core import PtySession
```

## Dependencies

| Package | Needed by | Auto? |
|---|---|---|
| `pyte` | `drive-tui` core (hard dependency) | reported by `doctor`; install on request |
| `pywinpty` | `drive-tui` on **Windows** only | reported by `doctor`; install on request |
| `pyfiglet`, `Pillow`, `wcwidth` | optional niceties — everything degrades gracefully without them | never required |

`drive-tui` never installs anything behind your back (installing is a network
action). If `pyte`/`pywinpty` are missing it prints the exact command. To let it
install them for you, opt in explicitly:

```bash
python skills/drive-tui/scripts/tui.py --install-deps start --cmd python
# or: set SMARTCLI_AUTO_INSTALL=1
```

Or install everything up front:

```bash
python -m pip install -r requirements.txt              # required
python -m pip install -r requirements-optional.txt     # optional extras
```

## Keeping the vendored core in sync

The `smartcli_core` copy in `skills/drive-tui/_vendor/` is kept byte-identical to
the canonical top-level `smartcli_core/` by a tool + a test:

```bash
python tools/sync_vendor.py          # refresh the vendored copy
python tools/sync_vendor.py --check  # exit 1 if it has drifted (CI/gate)
python tests/test_vendor_sync.py     # the regression lock
```

If you change `smartcli_core/`, run `sync_vendor.py` before committing.

