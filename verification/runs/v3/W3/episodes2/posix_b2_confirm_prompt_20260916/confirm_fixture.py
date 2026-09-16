"""Fixture for B2 on POSIX: ask for confirmation, write only on y."""
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
print(f"Overwrite {target.name}? [y/N] ", end="", flush=True)
line = sys.stdin.readline()
answer = line.strip()[:1].lower()
print(f"ANSWER {answer!r}")
if answer == "y":
    target.write_text("written after confirmation\n", encoding="utf-8")
    print(f"WROTE {target.name} bytes={target.stat().st_size} file_written=True")
else:
    print(f"NO-WRITE {target.name} file_written=False")
print("BYE")
