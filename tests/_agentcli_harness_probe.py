"""AGENTCLI control-plane harness probe.

Runs the local synthetic agent scenarios only. It does not call external model
providers and does not require API keys.
"""
from __future__ import annotations

import subprocess
import sys


cmd = [sys.executable, "tools/agentcli/validate_agentcli.py", "--no-screenshots"]
raise SystemExit(subprocess.call(cmd))
