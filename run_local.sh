#!/usr/bin/env bash
# ============================================================================
#  AVS Migration Analytics - local launcher (macOS / Linux)
#
#  Sets up a self-contained virtual environment on first run, then starts the
#  dashboard at http://localhost:8501 and opens your browser.
#
#  Requires Python 3.10+ on PATH. Everything else is installed locally into
#  ./.venv ; no data ever leaves your machine.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

PORT="${AVS_PORT:-8501}"
URL="http://localhost:${PORT}"
VENV=".venv"
PY="python3"

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "ERROR: Python 3 is not installed or not on PATH." >&2
    exit 1
fi

# Create venv + install deps once (marker file avoids re-installing every run).
if [ ! -f "${VENV}/.deps_installed" ]; then
    echo "==> First run: creating local environment (one-time, ~1-2 min)…"
    "$PY" -m venv "$VENV"
    # shellcheck disable=SC1091
    source "${VENV}/bin/activate"
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    touch "${VENV}/.deps_installed"
else
    # shellcheck disable=SC1091
    source "${VENV}/bin/activate"
fi

echo ""
echo "  ============================================================"
echo "    AVS Migration Analytics"
echo "    Opening ${URL} in your browser…"
echo "    (Keep this terminal open. Press Ctrl+C to stop.)"
echo "  ============================================================"
echo ""

# Open the browser shortly after the server boots.
( sleep 5
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  fi ) >/dev/null 2>&1 &

exec python -m streamlit run Home.py \
    --server.port "$PORT" \
    --server.address localhost \
    --server.headless true \
    --browser.gatherUsageStats false
