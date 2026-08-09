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
| **MCP Registry** | ✅ live | `io.github.dwgx/smartcli` on `registry.modelcontextprotocol.io` (published 2026-07-15). Re-publish is **automated**: publish.yml's `publish-mcp` job runs after a successful PyPI tag publish, via OIDC with a pinned, checksum-verified `mcp-publisher`. The manual flow below is kept only as a fallback. |
| **Read the Docs** | ✅ live | https://smartcli.readthedocs.io/ — built from `.readthedocs.yaml` + `mkdocs.yml`, with `tools/build_docs.py` assembling the pages in `pre_build`. Separate from the GitHub Pages showcase. |

## Auto-runs on GitHub Actions (no account needed — done)
| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | push/PR | Windows + Linux + macOS × py3.10/3.14: deterministic tests + POSIX sandbox, plus the bounded `drive-smoke` (real-PTY probes, 3 OS), `package` (wheel + `server.json` schema + version-site + clean-venv install/uvx) and `coverage` jobs. |
| `publish.yml` | tag `v*` | PyPI OIDC publish (**verified working**, run 29245353129), then the `publish-mcp` job re-publishes `server.json` to the MCP Registry via OIDC. |
| `publish-testpypi.yml` | tag `v*rc*` / dispatch | TestPyPI rehearsal publish (OIDC). |
| `docker.yml` | push main / tag | builds + pushes `ghcr.io/dwgx/smartcli` via built-in token. |
| `codeql.yml` | push/PR/weekly | static security scan. |
| `lint.yml` | push/PR | ruff correctness subset (E9,F63,F7,F82) + mypy **block**; full ruff / format check advisory. |
| `release-drafter.yml` | push/PR | drafts grouped release notes. |
| `pages.yml` | push `docs/site/**` | showcase site. |
| `bench.yml` | dispatch | Terminal-Bench oracle smoke + scored subset (scored runs need an LLM API-key secret). |

## Prepared — needs a human step (only you can do)

### PyPI release (already working, for reference)
Bump the version in all **ten** places — `pyproject.toml`,
`smartcli_core/__init__.py`, `skills/cmd-art/fx/__init__.py`, the 3
`skills/*/SKILL.md`, `.claude-plugin/marketplace.json`,
`.claude-plugin/plugin.json`, `skills/drive-tui/_vendor/smartcli_core/__init__.py`
and **both** `server.json` fields (top-level + `packages[0].version`) — then
re-sync and gate before tagging:
```sh
python tools/sync_vendor.py
python tests/test_vendor_sync.py     # vendored copy byte-identical
python tests/test_version_sync.py    # all ten sites agree
git tag vX.Y.Z && git push origin vX.Y.Z   # publish.yml: PyPI + MCP Registry via OIDC
```

### TestPyPI (rehearsal channel) — OPTIONAL, deliberately not set up
**This is not a gap. Do not treat it as unfinished work.** It was listed here for
long enough to look like a to-do, so here is the reasoning instead.

TestPyPI exists because a PyPI version number is permanent — you cannot delete and
re-upload one — so it gives you somewhere disposable to check that a package really
builds, installs and imports. Every one of those checks already happens without it:

- CI's `package` job builds the wheel, installs it into a clean venv and runs it
  through `uvx` on every push.
- Before the v0.2.3 tag, the built artifacts were checked with `twine check`,
  installed into a clean venv, and the release's headline fix was exercised through
  the installed package against a real PTY. After the tag, the same was repeated
  from PyPI itself.
- Production OIDC publishing is **verified working** — v0.2.3 went out that way with
  all three publish jobs green.

So the only thing TestPyPI would add is rehearsing the *upload step* against a
throwaway index, which matters if you later rewrite `publish.yml` and don't want to
burn a real version number finding a mistake. Worth doing then; not worth an account
and a Trusted Publisher setup now.

If that day comes, the workflow is already written and needs four one-time steps:
register at test.pypi.org, add a Trusted Publisher (project `smartcli-toolkit`, owner
`dwgx`, repo **`SmartCLI`** — the GitHub repo name, not the dist name, which is the
mismatch that broke the production setup originally — workflow
`publish-testpypi.yml`, environment `testpypi`), create a `testpypi` GitHub
Environment, then dispatch it.

### GHCR image visibility
The image publishes automatically, but GHCR packages start **private**. To make it
public: GitHub → your profile → Packages → `smartcli` → Package settings → change
visibility to Public. (One-time.)

### Docs site on Read the Docs — ✅ LIVE at https://smartcli.readthedocs.io/

RTD builds from `.readthedocs.yaml` + `mkdocs.yml`, running `tools/build_docs.py`
in `pre_build` to assemble the `docs/*.md` stubs. No further setup needed.

### Coverage badge on Codecov

CI's `coverage` job runs `tools/coverage_run.py --xml` and uploads to Codecov
(`codecov/codecov-action@v5`). The job is `continue-on-error` (advisory) so CI
stays green regardless. It uses `CODECOV_TOKEN` if that secret is configured;
without it, uploads succeed via tokenless mode for public repos but the token
makes it more reliable.

To configure: Codecov → SmartCLI → Settings → copy **CODECOV_TOKEN** → GitHub
repo Settings → Secrets → add it. The badge currently shows ~50% on the
deterministic subset; see `tools/coverage_run.py`.

### MCP Registry — ✅ LIVE (`io.github.dwgx/smartcli`)

The MCP listing at `registry.modelcontextprotocol.io` is live (published
2026-07-15). Re-publishing on every release is **automated**: `publish.yml`'s
`publish-mcp` job runs after a successful PyPI tag push, using GitHub OIDC with
a pinned, sha256-verified `mcp-publisher` (no manual device-login step).

**Manual fallback** (if the OIDC job fails):
1. `brew install mcp-publisher` (or binary from the registry GitHub releases).
2. `mcp-publisher login github` → device code.
3. `mcp-publisher publish` (from repo root next to `server.json`).
4. Verify: `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.dwgx/smartcli"`.

This can later be automated on tag-push with the "Publish MCP Server" GitHub
Action (composes server.json + publishes via OIDC), matching our existing
tag-push release flow.

### conda-forge — `packaging/conda-forge/recipe/meta.yaml`
**OPTIONAL — a genuinely different distribution channel, so the only reason to do it
is "I want conda users to reach the package". It is not unfinished work.** The recipe
is finished: calibrated to 0.2.3, sha256 filled and verified (matches PyPI's own
recorded digest), the three `test:` commands run against a real install of that
version and pass, deps / `requires-python` / `noarch` all agree with pyproject.

If you ever want it live, the whole step is: fork `conda-forge/staged-recipes`, copy
`packaging/conda-forge/recipe/meta.yaml` to `recipes/smartcli-toolkit/meta.yaml`, open
a PR. Two notes so it goes smoothly:
1. conda-forge prefers more than one `recipe-maintainers` entry; the recipe lists only
   `dwgx`. Either add someone who agrees, or submit with one and answer the
   reviewer's question.
2. Their bot takes over future version bumps once merged, so this is a one-time
   submission, not an ongoing chore.

### Homebrew — `packaging/homebrew/smartcli-toolkit.rb`
**Do not open a homebrew-core PR.** Verdict recorded 2026-08-09 in the formula
header: `mcp` has been a required dependency since 0.2.0, and its transitive
closure is ~30 packages including Rust-compiled `pydantic-core` and `rpds-py`.
Homebrew forces `--no-binary=:all:`, so every `brew install` would compile those
from source — minutes of build for something `pip install smartcli-toolkit` does
in seconds. That is a worse experience than the channel we already ship on, and a
formula nobody can maintain cheaply.

The sdist and `pyte` sha256 values in the draft are now **real and verified**
against the published 0.2.3 sdist (previously all-zero placeholders), so if you
ever do want a personal tap the file is honest: create `dwgx/homebrew-tap`, put it
at `Formula/smartcli-toolkit.rb`, and regenerate the remaining `resource` stanzas
with `brew update-python-resources` — the draft only vendors `pyte` today.

## macOS verification
See `docs/MACOS-VERIFY.md` — the runbook for the one unverified platform (BSD pty
EOF path). CI's `macos-latest` leg now covers the deterministic + POSIX-sandbox
parts automatically; the runbook is for the interactive drive smoke you do over SSH.

## Launch / discoverability (owner-posts, copy is ready)
`docs/LAUNCH-COPY.md` has ready-to-paste copy for Show HN, Reddit, X, awesome-list
PRs, and the skill communities. Those are human-posted on your timing.
