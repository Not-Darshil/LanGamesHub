#!/usr/bin/env bash
# Regenerate pinned Python requirements (run on the internet-connected dev PC).
#   requirements.txt          universal lock (macOS/Linux dev and Windows host)
#   requirements-windows.txt  exact set the Windows host installs from the wheelhouse
#   requirements-dev.txt      test tools, constrained to the runtime pins
set -euo pipefail
cd "$(dirname "$0")/../backend"
uv pip compile requirements.in --universal --python-version 3.11 -o requirements.txt
uv pip compile requirements.in --python-version 3.11 \
  --python-platform x86_64-pc-windows-msvc -c requirements.txt -o requirements-windows.txt
uv pip compile requirements-dev.in --universal --python-version 3.11 -o requirements-dev.txt
