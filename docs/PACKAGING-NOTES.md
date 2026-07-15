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

### Docs site on Read the Docs — READY, one web step to go live

Everything is committed and verified: `mkdocs.yml` (with `exclude_docs` so the
showcase site / i18n / notes aren't treated as pages), `.readthedocs.yaml`
(runs `tools/build_docs.py` in `pre_build`), `docs/requirements.txt`, and
`tools/build_docs.py` (assembles `docs/*.md` from README / the SKILL.md files /
CHANGELOG / knowledge/INDEX at build time, so the site never drifts). Local
`python -m mkdocs build` succeeds.

**To go live (≈1 minute, only you can do the OAuth):**
1. Go to https://readthedocs.org and **Sign up / Log in with GitHub** (this is
   the one-time OAuth authorize step — an API token can't replace it).
2. Click **Import a Project** → the wizard lists your GitHub repos → pick
   **dwgx/SmartCLI** (or "Import Manually" with repo URL
   `https://github.com/dwgx/SmartCLI`).
3. Accept the defaults and **Build** — RTD auto-detects `.readthedocs.yaml`, runs
   `tools/build_docs.py`, then `mkdocs build`. No config to fill in.
4. (Optional) In the RTD project's Admin → set the default version and add the
   docs URL to the GitHub repo's "Website" field.

The showcase site (docs/site/, deployed by `pages.yml`) is separate and
unaffected — this adds a second, reference-docs site.

Local preview: `pip install mkdocs-material && python tools/build_docs.py && python -m mkdocs serve`.

### Coverage badge on Codecov — READY, add one secret

CI's `coverage` job runs `tools/coverage_run.py --xml` and uploads to Codecov
(`codecov/codecov-action@v5`). Codecov's tokenless upload no longer works for
plain pushes (only fork PRs), so it needs the repo upload token.

**To light up the badge (≈2 minutes):**
1. At https://app.codecov.io/github/dwgx (already logged in) open **SmartCLI**
   → **Settings / Configuration** → copy the **CODECOV_TOKEN** (repo upload
   token). If SmartCLI isn't listed, click **"Add new repository" / "Activate"**
   first (public repo, no cost).
2. In GitHub: repo **Settings → Secrets and variables → Actions → New repository
   secret**, name it exactly **`CODECOV_TOKEN`**, paste the value.
3. Re-run CI (push any commit, or Actions → CI → Re-run). The `coverage` job then
   uploads with the token and the README badge fills in (currently ~50% — the
   deterministic subset; see `tools/coverage_run.py`).

Until the secret exists the upload soft-fails (the job is `continue-on-error`),
so CI stays green and the badge just reads "unknown".

### MCP Registry — `server.json` (READY, one ordering caveat)

The drive-tui MCP server (`skills/drive-tui/scripts/mcp_server.py`) can be listed
on the official registry (`registry.modelcontextprotocol.io`), which Smithery /
Glama / MCP.so and the Claude/Cursor/VS Code clients auto-discover — the highest-
leverage free distribution channel for this project. Prepared and committed:
- **`server.json`** (repo root): name `io.github.dwgx/smartcli`, `registryType:
  pypi`, identifier `smartcli-toolkit`. Its `version` must equal the package
  version (a mismatch is the #1 publish failure — keep it in lockstep with the
  6-site bump).
- **PyPI ownership marker**: an `<!-- mcp-name: io.github.dwgx/smartcli -->`
  comment is in `README.md`. The registry verifies ownership by reading this
  string from the **published package's description** (= the README on PyPI).

**Ordering caveat (important):** PyPI verification reads the README of the
*published* release. The marker landed after 0.1.4, so it isn't on PyPI yet.
→ **Publish one more PyPI release first** (so the README-with-marker becomes the
PyPI description), keep `server.json`'s version in step, then register.

**To publish (≈3 minutes, needs a GitHub device-code login only you can do):**
1. Ensure the current PyPI release's description contains the `mcp-name` marker
   (i.e. it shipped after this commit). Bump `server.json` `version` to match.
2. Install the CLI: `brew install mcp-publisher` (or grab the binary from the
   registry's GitHub releases).
3. `mcp-publisher login github` → open the printed URL, enter the device code.
4. `mcp-publisher publish` (run from the repo root, next to `server.json`).
5. Verify: `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.dwgx/smartcli"`.

This can later be automated on tag-push with the "Publish MCP Server" GitHub
Action (composes server.json + publishes via OIDC), matching our existing
tag-push release flow.

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
