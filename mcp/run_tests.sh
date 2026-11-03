#!/bin/bash
# Run the MCP server tests.
#   ./run_tests.sh           unit tests only (fast, no network, no real data)
#   ./run_tests.sh --smoke   unit tests, then call the tool on the real RSEc data
#                            (first run downloads ~58 MB into ./data and loads it)

set -euo pipefail
cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "ERROR: uv is not installed (https://docs.astral.sh/uv/)"; exit 1; }

SMOKE=0
case "${1:-}" in
  "") ;;
  --smoke) SMOKE=1 ;;
  *) echo "Usage: $0 [--smoke]"; exit 2 ;;
esac

echo "=== Installing dependencies ==="
uv sync --quiet

echo "=== Unit tests ==="
uv run pytest -q

if [ "$SMOKE" -eq 1 ]; then
  echo ""
  echo "=== Smoke test: tools exposed by the server ==="
  uv run fastmcp list server.py
  echo ""
  echo "=== Smoke test: list_software_with_biotools_ids on the real data ==="
  uv run fastmcp call server.py list_software_with_biotools_ids limit=3
fi

echo ""
echo "=== All tests passed ==="
