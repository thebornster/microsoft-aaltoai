#!/usr/bin/env bash
# Populate the deployed Raja dashboard with the complete four-beat proof:
# ALLOW, hard DENY, URL-mode REVIEW/approval/resume, and replay rejection.
#
# Usage:
#   RAJA_DEMO_SECRET='the deployment approval secret' ./demo/run_deployed_demo.sh
# Optional:
#   RAJA_GATEWAY_URL='https://...' RAJA_DEMO_SECRET='...' ./demo/run_deployed_demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."

GATEWAY_URL="${RAJA_GATEWAY_URL:-https://raja-gateway.proudsea-6cbc91b7.swedencentral.azurecontainerapps.io}"

if [ -z "${RAJA_DEMO_SECRET:-}" ]; then
  echo "RAJA_DEMO_SECRET is required: it is the approval secret configured on Azure." >&2
  echo "If you no longer have it, rotate it with the Azure command in DEPLOY.md." >&2
  exit 1
fi

echo "Checking deployed gateway: ${GATEWAY_URL}"
curl --fail --silent --show-error "${GATEWAY_URL}/healthz" >/dev/null
echo "Gateway healthy. Running the deterministic HTTP demo..."
RAJA_GATEWAY_URL="${GATEWAY_URL}" uv run python -m demo.local_fallback
echo
echo "Open the live evidence view:"
echo "  ${GATEWAY_URL}/dashboard"
