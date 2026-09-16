# verification/ — evidence, runs and the handoff kit

Everything that **proves** something about SmartCLI lives here, separated from everything that **is**
SmartCLI. Nothing in this tree ships: the wheel is built from `smartcli_core` + `smartcli_drive` only
and `MANIFEST.in` prunes this directory from the sdist.

> **Moved here on 2026-09-16** from `D:\Project\SmartCLI-v2-handoff`, `SmartCLI-v2-runs`,
> `SmartCLI-v3-runs` and `SmartCLI-v3-upload`. Documents written before that date that cite those
> absolute paths mean the files now under this directory; nothing was deleted except the four empty
> parent folders.

## What is here

| path | what it is | trust level |
| --- | --- | --- |
| `design/` | — (the v2/v3 design documents live in `kit-v2/docs/`, see below) | — |
| `kit-v2/` | the handoff kit that was sent to a web model for review: `docs/v2`, `docs/v3` (A04_PRODUCTION, EVIDENCE_STANDARD, BENCHMARK_MIN, DIVERGENCE, CROSS_DOMAIN, POSITION_2026Q4, BRIEFS_V3), `briefs/`, `reference/`, `models/`, `site/`, `templates/`, `evidence/`, plus `v3_MANIFEST.json` / `v3_SOURCES.json` / `v3_DELIVERY.json` | design intent — **not** evidence |
| `runs/v2/` | the earlier round's receipts: `T03` (short PTY write), `T04` (SGR), `T05` (cell span), `X2`/`X3` (Windows/POSIX liveness), `A04`/`A04-P` proposals, `final-conformance.json` | evidence, with the commands that produced it |
| `runs/v3/` | this round: `A04/` (A04_PRODUCTION slices + `RECEIPTS.md` + mutation logs + `s5-highwater/` probes), `N1/` (real-transport case JSONs), `W2/` (offline evidence verifier + fixtures), `W3/` (benchmark judge + episodes, incl. the E5/E6 results) | evidence |
| `tools/` | `mutate.py` (the mutation harness that proves a gate can fail), `mutate-v2.py` (its earlier revision, kept for provenance), `conformance.py` (the kit's conformance runner) | tooling |
| `upload/` | the exact package handed to the web model on 2026-09-16 (`01_plan` … `05_verification`, `PROMPT_PASTE_THIS.md`, and `SmartCLI_v3_Upload_2026-09-16.zip` whose sha256 is `536221143a194e7ec5c5e2695b391775c173b8656d9635f75aa83be1c1128dc1`) | artefact of record |

## How to read a receipt

An evidence file is only meaningful with four things, and every receipt here carries them or says
`NOT_RUN`:

1. **what was run** — an absolute path plus the exact command;
2. **what came out** — the command's own output, not a summary;
3. **what it proves** — the evidence level (E1 source, E2 reference model, E3 real core in memory,
   E4 real terminal, E5 end-to-end with a judge, E6 release artefact);
4. **what it does not prove** — limits, unexercised branches, transport caveats.

`runs/v3/A04/RECEIPTS.md` and `runs/v3/W3/last.md` are the two worked examples.

## The evidence levels, and where each was reached

| level | example in this tree |
| --- | --- |
| E3 real core in memory | `runs/v3/A04/` slice tests (injected transports), `runs/v2/T03..T05` |
| E4 real terminal on this host | `runs/v3/N1/case-*.json` (POSIX and ConPTY A/B), `runs/v3/A04/s5-highwater/` |
| E5 end-to-end with a judge | `runs/v3/W3/episodes*/` (three tasks x three tracks x two transports), judged by `W3/judge.py` |
| E6 release artefact | the 0.3.0 → 0.3.2 releases: wheels verified byte-for-byte against their tags |

See `HANDOFF.md` in this directory for what is still open and the exact next commands.
