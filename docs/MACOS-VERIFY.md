# macOS verification runbook

**Status: NOT yet verified on macOS.** This is the one platform SmartCLI has never
run on. The specific unknown is the **BSD pty EOF path** — macOS uses a BSD-derived
`pty.fork()` whose EOF/`read()` semantics on a closed child differ subtly from
Linux's, and `PosixPtyBackend` has only been exercised on Debian.

This runbook is what to run once you open the Mac and give me SSH (or run it
yourself). It is ordered, **serial**, and respects the repo spawn red-line: one PTY
at a time, verify zero residue between heavy steps, never fan out real processes.

---

## 0. Connection + environment (you do this once)

On the Mac:
```sh
# a) make sure Python 3.11+ and git are present
python3 --version        # need >= 3.9; 3.11/3.12 ideal
git --version

# b) enable Remote Login so SSH works:  System Settings -> General -> Sharing
#    -> Remote Login = ON. Note the `user@host` it shows.
```

Then tell me the `user@host` (or add it to your `~/.ssh/config` as e.g.
`Host dwgx-mac`), and I connect the same way I use `dwgx-home-cloud`.

## 1. Get the code + deps into an isolated venv (no system pollution)

```sh
cd ~
git clone https://github.com/dwgx/SmartCLI smartcli-macverify || \
  (cd smartcli-macverify && git pull)
cd smartcli-macverify
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt      # pywinpty line is skipped on macOS by marker
python -c "import pyte; print('pyte OK')"
```

## 2. The core POSIX backend sandbox — THE key test (BSD pty EOF path)

This is the single most important check: it drives real programs through
`PosixPtyBackend` (`pty.fork()`), exercises spawn / read / write / resize / EOF,
the perceive stack, DECCKM SS3 arrows (#5), and zombie-free terminate (#6).

```sh
python tests/_sandbox_posix_backend.py ; echo "exit=$?"
```
- **exit 0 = the BSD pty path works.** Read the printed `PASS/KNOWN` lines.
- Watch specifically for: the EOF line after the child exits (does `read()` return
  cleanly, or hang/raise on macOS?), the `terminate()` reap (no `<defunct>`), and
  the ncurses arrow probe reading `Up` as `KEY_UP` (SS3 path).
- If it hangs on the EOF read, that's the BSD difference we're hunting — capture
  the traceback / where it stalls and stop; do not retry in a loop.
```

## 3. Deterministic suite (safe, no interactive PTY)

```sh
PYTHONIOENCODING=utf-8 python tests/test_fx_contract.py     # 30 effects x sizes
PYTHONIOENCODING=utf-8 python tests/_readme_literal.py
( cd skills/tui-ui && python self_test.py && python -m ui widgets )   # 15 widgets
( cd skills/cmd-art && python -m fx list )                            # 30 effects
python skills/tui-ui/ui/box_junction.py
```
All should exit 0 and are pure/deterministic — fine to run together.

## 4. ONE live drive-tui smoke (serial; close before anything else)

Verifies the daemon's `start_new_session` detach + real drive on macOS. Do this
ALONE — one PTY, then close + confirm zero residue.

```sh
T=skills/drive-tui/scripts/tui.py
SID=$(python $T start --cmd "python3" --cols 80 --rows 24); echo "sid=$SID"
python $T wait-regex --id $SID ">>> " --timeout-ms 15000
python $T send-line --id $SID "print(6*7)"
python $T snapshot --id $SID          # expect to see 42
python $T close --id $SID
python $T list                        # MUST be empty (zero residue)
```
Also test the Ctrl-C path (POSIX should interrupt cleanly, unlike Windows ConPTY):
start another session running `python3`, `send-line "import time; time.sleep(30)"`,
`keys C-c`, snapshot (should show KeyboardInterrupt), close, `list` empty.

## 5. Optional: real tmux launchers (only if tmux is installed)

`skills/cmd-art/tmux/*.sh` have never run on a real tmux host. If `brew install
tmux` is acceptable:
```sh
tmux -V
sh skills/cmd-art/tmux/fx-popup.sh    # inspect, don't leave sessions running
tmux kill-server                       # clean up
```

## 6. Report back — what I'll update on green

If §2 + §4 pass on macOS, these become true and I'll update them (with the run as
evidence, not an assertion):
- `README.md` "verified on Debian 13 + Windows/ConPTY. macOS ... not yet verified"
  → add macOS.
- `HANDOFF.md` §6/§7 "STILL UNVERIFIED: macOS (BSD pty EOF path)" → verified.
- `skills/drive-tui/references/LIMITATIONS.md` → move the macOS caveat to resolved.
- The CI matrix's `macos-latest` leg already covers the deterministic + POSIX
  sandbox parts automatically going forward.

**If anything fails:** capture the exact output, DON'T loop-retry (red-line), and I
diagnose the root cause before changing code. `smartcli_core` is DO-NOT-MODIFY
except with real-run-path verification + adversarial review — a macOS fix qualifies,
but only with the failing output in hand.
