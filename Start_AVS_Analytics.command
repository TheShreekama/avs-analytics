#!/usr/bin/env bash
# macOS double-click launcher. Finder opens this in Terminal.
# Delegates to run_local.sh (creates a local environment on first run).
cd "$(dirname "$0")"
exec ./run_local.sh
