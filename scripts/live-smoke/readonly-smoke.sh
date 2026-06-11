#!/usr/bin/env bash
# readonly-smoke.sh — Proximo READ-ONLY live-smoke wrapper.
#
# Runs pve_node_status, pve_storage_status, pve_storage_content, pve_backup_list,
# and audit_verify against a real Proxmox VE cluster — NO mutations, NO new tokens
# required beyond Datastore.Audit + Sys.Audit.
#
# Required env vars:
#   PROXIMO_API_BASE_URL   e.g. https://pve.example.com:8006/api2/json
#   PROXIMO_NODE           e.g. your-node
#   PROXIMO_VERIFY_TLS     "true" or "false"  (false = accept self-signed cert)
#
# Auth (one of):
#   PROXIMO_TOKEN_PATH     path to a plain file containing the full API token string
#   PROXIMO_TOKEN_FILE     path to an env file that exports the token (auto-detected)
#
# Optional:
#   PYTHON                 override the python interpreter (default: python3)
#
# See README.md for full setup instructions and token creation guidance.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "${SCRIPT_DIR}/lib.sh"

# ---- required env checks ---------------------------------------------------
proximo_require_env PROXIMO_API_BASE_URL PROXIMO_NODE PROXIMO_VERIFY_TLS

# ---- auth ------------------------------------------------------------------
proximo_setup_auth

# ---- python resolution -----------------------------------------------------
proximo_resolve_python
proximo_resolve_pythonpath

# ---- run (no exec — bash must resume so the EXIT trap fires) ---------------
echo ">>> Proximo READ-ONLY smoke (node=${PROXIMO_NODE}; no mutations; token hidden)"
"${PROXIMO_PYTHON}" "${SCRIPT_DIR}/readonly-smoke.py"
# Propagate python exit code; bash continues → EXIT trap shreds the temp file.
exit $?
