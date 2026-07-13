#!/usr/bin/env python3
"""_ssh_run.py — minimal password-auth SSH runner (git-bash has no sshpass).

Reads host/user/password from env (SSH_HOST/SSH_USER/SSH_PASS) so the password
never appears in argv or shell history. Runs a command, prints stdout/stderr,
returns the exit status. Also supports `--put local remote` / `--get remote local`
via SFTP. Throwaway helper for the cross-machine recording work; not shipped.
"""
from __future__ import annotations

import os
import sys

import paramiko


def _client():
    host = os.environ["SSH_HOST"]
    user = os.environ["SSH_USER"]
    pw = os.environ["SSH_PASS"]
    port = int(os.environ.get("SSH_PORT", "22"))
    c = paramiko.SSHClient()
    # AutoAddPolicy skips host-key verification (no MITM protection). Acceptable
    # ONLY because this is a throwaway helper for a known LAN host; do not reuse
    # it against untrusted networks without pinning the host key.
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, port=port, username=user, password=pw,
              look_for_keys=False, allow_agent=False, timeout=20)
    return c


def main() -> int:
    args = sys.argv[1:]
    c = _client()
    try:
        if args and args[0] == "--put":
            sftp = c.open_sftp()
            sftp.put(args[1], args[2])
            print(f"put {args[1]} -> {args[2]}")
            sftp.close()
            return 0
        if args and args[0] == "--get":
            sftp = c.open_sftp()
            sftp.get(args[1], args[2])
            print(f"get {args[1]} -> {args[2]}")
            sftp.close()
            return 0
        cmd = " ".join(args) if args else "echo no-command"
        stdin, stdout, stderr = c.exec_command(cmd, timeout=int(os.environ.get("SSH_TIMEOUT", "120")))
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if out:
            sys.stdout.write(out)
        if err:
            sys.stderr.write(err)
        print(f"[exit={rc}]", file=sys.stderr)
        return rc
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
