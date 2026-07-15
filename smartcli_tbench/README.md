# smartcli-tbench — Terminal-Bench agent adapter

A [Terminal-Bench](https://github.com/laude-institute/terminal-bench) agent that
drives the benchmark's terminal with SmartCLI's **perceive → decide → act → wait →
confirm** loop. It turns "SmartCLI can drive interactive TUIs" into a runnable
benchmark score.

## Why this exists

Terminal-Bench owns the terminal: each task runs in a Docker container and the
harness hands an agent a live `TmuxSession`. The stock `naive` agent is
fire-and-forget — it sends commands and never reads the screen back. SmartCLI's
contribution is the **synchronisation discipline**: after every action, wait until
the screen actually settles / shows a marker / changes before proceeding. Those are
the `wait_stable` / `wait_for` / `wait_any` / `wait_change` primitives, reimplemented
here over `capture_pane()`.

## Layout

| module | what | needs terminal-bench? |
|---|---|---|
| `driver.py` | `TmuxSessionDriver` — the wait primitives over a tmux session | no (duck-typed) |
| `loop.py` | `run_agent_loop` — the loop, parametrised by a `decide_fn` | no |
| `agent.py` | `SmartCliAgent(BaseAgent)` — wires an LLM decider into the loop | **yes** (lazy import) |

`driver.py` and `loop.py` are pure and unit-tested on any OS without Docker or an
LLM (`tests/test_tbench_adapter.py`). Only `SmartCliAgent` needs terminal-bench, and
it imports it lazily — so `import smartcli_tbench` works everywhere; only *using*
the agent requires a TB host.

## Running the benchmark

Terminal-Bench needs **Docker + Linux** — it cannot run on the Windows dev box (no
WSL). Use CI `ubuntu-latest` (see `.github/workflows/bench.yml`) or the Debian box.

```bash
uv tool install terminal-bench   # or: pip install terminal-bench
export PYTHONPATH="$PWD:$PYTHONPATH"

# harness smoke test — no LLM key needed (oracle replays reference solutions):
tb run --agent oracle --dataset-name terminal-bench-core --n-tasks 5

# the scored run (needs an LLM API key + a decide_fn wired into SmartCliAgent):
tb run \
  --agent-import-path "smartcli_tbench.agent:SmartCliAgent" \
  --model anthropic/claude-3-7-latest \
  --dataset-name terminal-bench-core --n-tasks 5
```

The `decide_fn` (the LLM call) is intentionally not bundled — pass `decide_fn=` to
`SmartCliAgent` or override `_make_decider` to plug in your model client. The loop
and wait discipline are the reusable part; the prompting strategy is yours.

## Scope note

Targets **classic** `laude-institute/terminal-bench` (`BaseAgent.perform_task(
instruction, session: TmuxSession)`). The current public leaderboard is
Terminal-Bench 2.0 / Harbor, whose agent interface is different (tool/environment
mediated, no raw tmux handle) — a classic-TB score is real and citable but not
directly comparable to the 2.0 leaderboard. A Harbor port is a separate effort.
