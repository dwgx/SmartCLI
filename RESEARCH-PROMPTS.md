# RESEARCH-PROMPTS.md — calibrated `/deep-research` anchors

Persists NEXT-STEPS.md task D1: the `/deep-research` anchor list tuned during the
competitive-benchmarking work, so it survives past one session's context. This file
is prompts to run, not answers — do not fill in findings here; if you research one
of these, record the result in HANDOFF.md / NEXT-STEPS.md where the rest of that
work lives, and update this file's "Last checked" line for that anchor.

Positioning these questions must not contradict (HANDOFF §7f): the "pyte semantic
snapshot + wait for stable" pattern is a CROWDED category (pilotty, ht, termscope,
termwright, conch, virtui). SmartCLI's genuinely defensible edges are **native
Windows+POSIX in one library** and **input correctness** (adaptive DECCKM arrows) —
not "semantic not vision", which is table stakes now. A research answer that just
re-confirms the crowded-category framing is not a reason to write a section; only
anchors whose answer plausibly *changes a backlog item* are below.

---

## conch

**Question:** Has conch (or any of the other named crowded-category peers — pilotty,
ht, termscope, termwright, virtui) shipped Windows/ConPTY support, or a wait
primitive SmartCLI doesn't have, since the last time this was checked (the CPR/DSR
auto-answer was conch's "killer feature" and SmartCLI matched it in v0.1.5 — HANDOFF
§9c)? Check conch's repo activity, README, and issue tracker for anything past that.

**Last checked:** 2026-07-15 (CPR parity), positioning re-stated 2026-07-27 (§7f).

**What a good answer changes:**
- If conch (or a peer) now does something SmartCLI doesn't → that becomes a new
  numbered item in HANDOFF §6 OPEN TASKS, ranked by impact/effort like the rest.
- If conch remains POSIX-only / unmaintained → the §7f claim ("native Windows+POSIX
  is the edge") gets re-verified evidence instead of a two-session-old assertion,
  which is what the HN/launch copy leads with (docs/LAUNCH-COPY.md) — worth
  confirming before that copy goes out, not after.
- If nothing has changed either way, this anchor answers nothing and can be dropped
  from future rotations — say so in HANDOFF instead of re-running it unchanged.

---

## terminal-bench / Harbor

**Question:** Has the Harbor leaderboard (`laude-institute/harbor`) published any
scored runs yet, and if so, what agent design do the top entries use for
environments that expose only `environment.exec()` with no `tmux`/`capture_pane`
handle — the same constraint `smartcli_tbench/harbor_agent.py` (HANDOFF §10h) works
around by installing smartcli-toolkit inside the environment and driving it over
`exec`? Is there a reusable pattern (streaming exec, session-reset semantics) that
harbor_agent.py is missing?

**Last checked:** 2026-08-05 (adapter built + `test_harbor_agent.py`, 22 checks,
verified against the real `BaseAgent`; HANDOFF §10h).

**What a good answer changes:**
- If a specific capability gap shows up in top-scoring agents' approach (e.g. how
  they handle a mid-task environment reset) → that's a concrete addition to
  `harbor_agent.py` before it's leaderboard-competitive, not just interface-correct.
- If no scores are public yet → confirms the adapter work is currently blocked
  purely on the owner-gated `decide_fn` + LLM API-key secret (already the stated
  blocker) and there's nothing further to research until that unblocks — say that
  plainly rather than re-researching Harbor's interface, which is already measured.

---

## plotille

**Question:** What plot types does plotille implement (histogram, scatter, heatmap,
axis/tick formatting) that `skills/tui-ui/ui/widgets_ext/braille_chart.py` — currently
one smooth line via Bresenham-into-braille sub-cell raster (HANDOFF-adjacent; see the
module docstring) — does not cover? Are plotille's tick/axis conventions general
enough to reuse, or is its API shaped around a different (streaming figure) model
that wouldn't fit tui-ui's pure-frame-producer contract?

**Last checked:** not yet — `braille_chart.py` was ported from the sub-cell-raster
knowledge note ([[sub-cell-resolution]]), not from a plotille comparison.

**What a good answer changes:**
- If histogram/scatter are cleanly portable as additional pure-frame widgets → that's
  a real widget-count bump (17→N) in `skills/tui-ui`, which means updating every
  `WIDGET_DOCS` site `test_doc_counts.py` gates (README, README-USAGE, CLAUDE.md,
  SKILL.md, 4 i18n READMEs, MACOS-VERIFY.md, 5 site HTML pages) plus a new golden
  frame in `tests/golden/`. Not a small doc edit — worth confirming the port is
  real before starting.
- If plotille's model doesn't fit the frame-producer contract, that's a documented
  "evaluated, doesn't fit" note, not a silent drop — the next AI shouldn't
  re-propose it without knowing why it was already rejected.

---

## TTE (terminaltexteffects)

**Question:** `research/R1-effects-catalog.md` PART C froze TTE's effect list at HEAD
`7a91dd9` (37 effects); three were ported (`text_flyin`/`text_converge`/`text_decrypt`,
v0.1.6). Has TTE added effects since that snapshot, and among the ~34 still unported,
which (if any) compose cleanly onto the primitives already built for the three that
shipped (`_texteffect.py`'s per-char ease-to-target rasterization + the shared
`easing.py` Penner set) versus needing new machinery (TTE's `Path`/`Waypoint`/`Scene`
event system, which SmartCLI does not have)?

**Last checked:** research snapshot 2026-07 (pre-v0.1.6); no re-check since the 3
ports shipped.

**What a good answer changes:**
- A portable effect is a real, contract-tested catalog bump (30→31): it must clear
  `test_fx_contract.py`, move `verify_fx.py` from 38/38 (30 effects + 8 fixed
  checks) to 39/39, and update
  every doc `test_doc_counts.py` gates on the fx count (README, README-USAGE,
  HANDOFF, NEXT-STEPS, CLAUDE.md, 4 i18n READMEs, `skills/cmd-art/SKILL.md`). That's
  the actual cost of "one more effect" here — worth knowing before promising it.
- If nothing left composes cleanly without the Path/Waypoint/Scene machinery, that's
  a decision NOT to build a second effect-authoring model for marginal catalog
  growth — record that as a closed question, not a standing "TODO: port more TTE".

---

## PyPI trusted publishing

**Question:** Does PyPI's Trusted Publishing now support PEP 740 digital
attestations (Sigstore-backed build provenance) as a step beyond bare OIDC, and does
the pinned `pypa/gh-action-pypi-publish@release/v1` action in `.github/workflows/publish.yml`
already emit them, or does it need an explicit input? Trusted Publishing itself is
already live and OIDC-verified (HANDOFF §0, §10g) — this question is specifically
about the newer attestation layer on top of it.

**Last checked:** not yet — `publish.yml`'s OIDC setup predates any attestation
research.

**What a good answer changes:**
- If attestations are opt-in and cheap given OIDC is already wired (the action likely
  needs at most one input flag, no new credential — the whole point of OIDC being
  in place already), that's a genuinely small `publish.yml` edit that adds a
  verifiable provenance signal on the PyPI project page for the next release. Small
  diff, real backlog item, not busywork.
- If it needs infrastructure this project doesn't have (e.g. a separate signing
  identity), that's a "not worth it yet" conclusion — write that down so nobody
  re-opens it as if it were free.

---

## Already benchmarked, not open anchors

pexpect, Textual, and pytest-textual-snapshot were benchmarked during this same
season of work (pexpect: `wait_any` closed the multi-marker gap, HANDOFF §9h;
Textual: `diagnose` CLI ported in v0.1.5, §9c; reactive/declarative layer + color
degrade still an open [M] item per HANDOFF §9f/CONTINUATION PROMPT, not because it's
unresearched but because it's sized and just not built; pytest-textual-snapshot: its
pattern is what `tests/test_golden_frames.py` already implements, HANDOFF §9b). None
of the three currently have an open research question whose answer would change the
backlog — re-running `/deep-research` on them without a new, specific sub-question
would be re-confirming what's already measured. Don't add a section for these unless
a concrete new sub-question shows up.
