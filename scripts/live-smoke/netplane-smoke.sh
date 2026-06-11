#!/usr/bin/env bash
# netplane-smoke.sh — Proximo NETWORK/INFRA-PLANE live-smoke wrapper.
#
# Drives firewall CRUD + pool lifecycle + HA-plan (dry-run) through Proximo's
# own stack against a real Proxmox VE cluster. Self-cleaning (finally block).
# Firewall stays DISABLED throughout; no guest is ever created; no SDN/network
# changes are applied. Reversible by construction.
#
# Required env vars:
#   PROXIMO_API_BASE_URL   e.g. https://pve.example.com:8006/api2/json
#   PROXIMO_NODE           e.g. your-node
#   PROXIMO_VERIFY_TLS     "true" or "false"
#
# Auth (one of):
#   PROXIMO_TOKEN_PATH     path to a plain file containing the full API token string
#   PROXIMO_TOKEN_FILE     path to an env file that exports the token (auto-detected)
#
# Optional:
#   SMOKE_FW_COMMENT       comment tag for throwaway firewall rules (default: proximo-smoke-fwtest)
#   SMOKE_POOL_ID          throwaway pool ID (default: proximo-smoke-throwaway-pool)
#   PYTHON                 override the python interpreter (default: python3)
#
# NOTE: The broader Tier-1 token grant (Pool.Audit + firewall write on /cluster/firewall)
# is required. See README.md.
#
# See README.md for full setup instructions and token creation guidance.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "${SCRIPT_DIR}/lib.sh"

# ---- required env checks ---------------------------------------------------
proximo_require_env PROXIMO_API_BASE_URL PROXIMO_NODE PROXIMO_VERIFY_TLS

# ---- optional env defaults -------------------------------------------------
export SMOKE_FW_COMMENT="${SMOKE_FW_COMMENT:-proximo-smoke-fwtest}"
export SMOKE_POOL_ID="${SMOKE_POOL_ID:-proximo-smoke-throwaway-pool}"

# ---- auth ------------------------------------------------------------------
proximo_setup_auth

# ---- python resolution -----------------------------------------------------
proximo_resolve_python
proximo_resolve_pythonpath

# ---- run (no exec — bash must resume so the EXIT trap fires) ---------------
echo ">>> Proximo NETWORK/INFRA-PLANE smoke (node=${PROXIMO_NODE}; firewall CRUD+pool+HA-plan; token hidden)"
echo "    FW_COMMENT=${SMOKE_FW_COMMENT}  POOL_ID=${SMOKE_POOL_ID}"
"${PROXIMO_PYTHON}" "${SCRIPT_DIR}/netplane-smoke.py"
exit $?
