# Packaging & distribution — status and the human-only steps

A single reference for every distribution channel: what's live, what's prepared
(config committed, waiting on an account/PR only you can do), and the exact step
that unblocks each. Nothing here needs me to have your credentials.

## Live now
| Channel | Status | Notes |
|---|---|---|
| **PyPI** | ✅ live | `pip install smartcli-toolkit` (import stays `smartcli_core`). Auto-publish via OIDC works — see below. |
| **GitHub repo / Releases / Pages** | ✅ live | showcase site auto-deploys from `docs/site/**` via `pages.yml`. |
| **Claude plugin marketplace** | ✅ live | `/plugin marketplace add dwgx/SmartCLI`. |
| **skillhu.bz** | ✅ live | all 3 skills. |

## Auto-runs on GitHub Actions (no account needed — done)
| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | push/PR | Windows + Linux + macOS matrix; deterministic tests + POSIX sandbox. |
| `publish.yml` | tag `v*` | PyPI OIDC publish. **Verified working** (run 29245353129). |
| `docker.yml` | push main / tag | builds + pushes `ghcr.io/dwgx/smartcli` via built-in token. |
| `codeql.yml` | push/PR/weekly | static security scan. |
| `lint.yml` | push/PR | ruff + mypy (advisory). |
| `release-drafter.yml` | push/PR | drafts grouped release notes. |
| `pages.yml` | push `docs/site/**` | showcase site. |

## Prepared — needs a human step (only you can do)

### PyPI release (already working, for reference)
Bump the version in all six places (pyproject, `smartcli_core/__init__`,
`skills/cmd-art/fx/__init__`, the 3 `skills/*/SKILL.md`, `marketplace.json`),
commit, then:
```sh
git tag v0.1.3 && git push origin v0.1.3     # publish.yml auto-uploads via OIDC
```

### TestPyPI (rehearsal channel) — `.github/workflows/publish-testpypi.yml`
One-time: register at test.pypi.org, add a Trusted Publisher (repo **`SmartCLI`**,
workflow **`publish-testpypi.yml`**, environment **`testpypi`**), create a
`testpypi` GitHub Environment. Then a `v0.1.3rc1` tag rehearses the full publish.

### GHCR image visibility
The image publishes automatically, but GHCR packages start **private**. To make it
public: GitHub → your profile → Packages → `smartcli` → Package settings → change
visibility to Public. (One-time.)

### Docs site — `mkdocs.yml`
Prepared. To go live pick ONE:
- **Read the Docs:** sign in at readthedocs.org → Import Project → connect
  `dwgx/SmartCLI`. Add `.readthedocs.yaml` (starter below) to pin the build.
- **GitHub Pages (mkdocs):** `pip install mkdocs-material && mkdocs gh-deploy` —
  but Pages is already used by the showcase site, so move/subpath it first.

The `nav:` in `mkdocs.yml` references `docs/*.md` stubs that don't exist yet.
Simplest fix at build time (copies the real docs in):
```sh
mkdir -p docs && cp README.md docs/index.md && cp README-USAGE.md docs/usage.md
cp skills/cmd-art/SKILL.md docs/skills-cmd-art.md
cp skills/drive-tui/SKILL.md docs/skills-drive-tui.md
cp skills/tui-ui/SKILL.md docs/skills-tui-ui.md
cp knowledge/INDEX.md docs/knowledge.md && cp CHANGELOG.md docs/changelog.md
```

Starter `.readthedocs.yaml`:
```yaml
version: 2
build:
  os: ubuntu-24.04
  tools: {python: "3.12"}
mkdocs:
  configuration: mkdocs.yml
python:
  install:
    - requirements: docs/requirements.txt   # mkdocs-material
```

### conda-forge — `packaging/conda-forge/recipe/meta.yaml`
Draft ready. Fill the sdist `sha256` (command in the file header), copy into a fork
of `conda-forge/staged-recipes` under `recipes/smartcli-toolkit/`, open a PR. A
conda-forge maintainer reviews; on merge a feedstock is auto-created and their bot
bumps future versions.

### Homebrew — `packaging/homebrew/smartcli-toolkit.rb`
Draft ready. Fastest path is your own tap: create `dwgx/homebrew-tap`, put the file
at `Formula/smartcli-toolkit.rb`, fill the two `sha256` values (commands in header),
then `brew install dwgx/tap/smartcli-toolkit`.

## macOS verification
See `docs/MACOS-VERIFY.md` — the runbook for the one unverified platform (BSD pty
EOF path). CI's `macos-latest` leg now covers the deterministic + POSIX-sandbox
parts automatically; the runbook is for the interactive drive smoke you do over SSH.

## Launch / discoverability (owner-posts, copy is ready)
`docs/LAUNCH-COPY.md` has ready-to-paste copy for Show HN, Reddit, X, awesome-list
PRs, and the skill communities. Those are human-posted on your timing.
