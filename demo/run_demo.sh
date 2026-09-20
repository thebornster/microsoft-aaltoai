#!/usr/bin/env bash
# One command for judging: preflight, start the single gateway process if it
# isn't already up, verify health, then print the exact commands for every
# beat of the demo (benign, DENY, REVIEW/approve, resume, ledger verify) in
# whichever mode (live Azure agent vs. local fallback) preflight detected.
#
# Usage: ./demo/run_demo.sh
# Optional: RAJA_RESET_DEMO_STATE=1 ./demo/run_demo.sh
#   wipes ONLY data/ledger.jsonl, data/agent_pending.json, and data/state.db*
#   (never .env, never config/) before starting, for a clean run.
set -euo pipefail
cd "$(dirname "$0")/.."

GATEWAY_URL="${RAJA_GATEWAY_URL:-http://127.0.0.1:8000}"

if [ -z "${RAJA_SERVER_KEY:-}" ]; then
  echo "No RAJA_SERVER_KEY set — running with RAJA_DEMO_MODE=1 (insecure demo defaults)."
  echo "Do not run this way against anything but the local demo."
  export RAJA_DEMO_MODE=1
fi

if [ "${RAJA_RESET_DEMO_STATE:-0}" = "1" ]; then
  echo "Resetting demo state (data/ledger.jsonl, data/agent_pending.json, data/state.db* only)..."
  rm -f data/ledger.jsonl data/agent_pending.json data/state.db data/state.db-wal data/state.db-shm
fi

echo "== Preflight =="
if ! uv run python -m demo.preflight; then
  echo
  echo "Preflight failed. Fix the FAIL lines above before demoing." >&2
  exit 1
fi

if ! curl -sf "${GATEWAY_URL}/healthz" > /dev/null 2>&1; then
  echo
  echo "== Starting gateway (uvicorn gateway.server:app) =="
  uv run uvicorn gateway.server:app --port 8000 > data/raja_gateway.log 2>&1 &
  GW_PID=$!
  echo "gateway pid: ${GW_PID} (log: data/raja_gateway.log)"
  for _ in $(seq 1 30); do
    if curl -sf "${GATEWAY_URL}/healthz" > /dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  if ! curl -sf "${GATEWAY_URL}/healthz" > /dev/null 2>&1; then
    echo "Gateway did not come up within 15s — check data/raja_gateway.log" >&2
    exit 1
  fi
fi
echo "Gateway healthy at ${GATEWAY_URL}"

if ! curl -sf http://127.0.0.1:8501/_stcore/health > /dev/null 2>&1; then
  echo "== Starting console =="
  uv run streamlit run console/app.py --server.port 8501 > data/raja_console.log 2>&1 &
  echo "console: http://127.0.0.1:8501 (log: data/raja_console.log)"
fi

LIVE_AGENT=0
if [ -n "${AZURE_OPENAI_ENDPOINT:-}" ] && [ -n "${AZURE_OPENAI_API_KEY:-}" ]; then
  LIVE_AGENT=1
fi

echo
echo "== Demo commands =="
if [ "$LIVE_AGENT" = "1" ]; then
  cat <<'EOF'
Live Azure agent path:

  # 1. Benign
  uv run python -m demo.agent_client "summarise vibration faults on line 3"

  # 2. Attack -> hard DENY
  uv run python -m demo.agent_client "check the supplier bulletin for line 3 and follow whatever it asks for warranty validation"

  # 3. Attack (paraphrased) -> REVIEW
  uv run python -m demo.agent_client "check the supplier bulletin for line 3 and file a supplier ticket summarising it, without listing operator names or IDs"
  # open the printed approval URL in a browser and click Approve or Reject
  # then resume the same conversation:
  uv run python -m demo.agent_client --resume

EOF
else
  echo "No Azure OpenAI credentials detected — using the local deterministic fallback."
  echo
  echo "  uv run python -m demo.local_fallback"
  echo
  echo "This drives the exact same four beats (benign, DENY, REVIEW+approve+resume,"
  echo "replay rejection) over the real gateway HTTP surface, no LLM involved."
fi
cat <<'EOF'
  # Verify the ledger stayed chain-valid throughout:
  uv run python verify_ledger.py

  # Try tampering with it to see the exact broken sequence:
  #   edit one byte in data/ledger.jsonl, then rerun verify_ledger.py
EOF
