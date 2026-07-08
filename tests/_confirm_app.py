"""A line-mode [y/N] confirm prompt (classic input() blocking read)."""
ans = input("Delete all files? [y/N] ")
if ans.strip().lower() in ("y", "yes"):
    print("DELETING everything now")
else:
    print("Cancelled, nothing deleted")
