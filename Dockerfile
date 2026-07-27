# SmartCLI — a lean image with the shared core + all three skills, for users who
# want to try the effects and the TUI driver without a local Python setup.
#
#   docker run --rm -it ghcr.io/dwgx/smartcli fx gallery
#   docker run --rm -it ghcr.io/dwgx/smartcli fx play donut --seconds 5
#   docker run --rm -it ghcr.io/dwgx/smartcli ui gallery
#   docker run --rm -it ghcr.io/dwgx/smartcli drive ...   # scripts/tui.py verbs
#   docker run --rm -i  ghcr.io/dwgx/smartcli mcp         # stdio MCP server
#
# POSIX pty backend (stdlib) is used inside the container — no pywinpty needed.
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/dwgx/SmartCLI" \
      org.opencontainers.image.description="SmartCLI — three terminal Agent Skills over one pluggable PTY+pyte core" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    TERM=xterm-256color

WORKDIR /app

# Keep image runtime dependencies aligned with the package/source install.
# pywinpty is Windows-only and its marker skips it in this Linux image.
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared core + the three skills + the entrypoint dispatcher.
COPY smartcli_core/ ./smartcli_core/
COPY skills/ ./skills/
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh

# Make the skills importable/runnable from anywhere.
ENV PYTHONPATH=/app:/app/skills/cmd-art:/app/skills/tui-ui:/app/skills/drive-tui \
    SMARTCLI_ROOT=/app

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["fx", "gallery"]
