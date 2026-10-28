#!/usr/bin/env sh
# EditVideo Agent setup for Linux/macOS (core runtime). Vision/temporal GPU extras: see README.
# Needs Python 3.11+, Node.js 22+, FFmpeg/FFprobe on PATH. Untested on macOS; report issues.
set -eu
cd "$(dirname "$0")"
# a slow mirror is retried instead of failing the install
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-60}" PIP_RETRIES="${PIP_RETRIES:-5}"
ROOT="$(pwd)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { echo "Python 3.11 or newer is required" >&2; exit 1; }
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
(cd engines && npm ci --no-audit --no-fund)
# Remotion's headless Chrome (~120 MB), once: otherwise the first renders each start the download and can time out
(cd engines && node --input-type=module -e "const r = await import('@remotion/renderer'); await r.ensureBrowser(); console.log('Remotion browser ready')")
if [ "${1:-}" = "--voice" ]; then  # optional offline Vietnamese narration (Piper, GPL-3.0, separate process)
  .venv/bin/python -m pip install -r requirements.voice.txt
  .venv/bin/python scripts/setup_voice.py --whisper
fi
if [ ! -f .mcp.json ]; then
  cat > .mcp.json <<EOF
{
  "mcpServers": {
    "editvideo": {
      "type": "stdio",
      "command": "$ROOT/.venv/bin/python",
      "args": ["$ROOT/run.py"],
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
EOF
fi
echo "EditVideo Agent ready. Configure your AI client with .mcp.json."
