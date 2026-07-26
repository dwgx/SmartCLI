#!/bin/sh
# Dispatch the first arg to the right skill CLI so the image is friendly:
#   fx ...     -> cmd-art  (python -m fx)
#   ui ...     -> tui-ui   (python -m ui)
#   drive ...  -> drive-tui (scripts/tui.py)
#   mcp         -> drive-tui stdio MCP server
# Anything else runs verbatim (so `docker run ... python -c ...` still works).
set -e
cmd="${1:-fx}"
case "$cmd" in
  fx)
    shift
    exec python -m fx "$@"
    ;;
  ui)
    shift
    exec python -m ui "$@"
    ;;
  drive)
    shift
    exec python /app/skills/drive-tui/scripts/tui.py "$@"
    ;;
  mcp)
    shift
    exec python /app/skills/drive-tui/scripts/mcp_server.py "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
