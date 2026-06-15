#!/usr/bin/env bash
# fwobjects-smoke.sh — Proximo FIREWALL-OBJECTS-PLANE live-smoke wrapper.
#
# Drives create -> read -> delete of firewall config objects (aliases / ip-sets /
# security-groups) + an options read/PLAN through Proximo's own stack against a real
# Proxmox VE node. Self-cleaning (finally block). Firewall is NEVER enabled; these are
# PASSIVE config objects (no connectivity effect until a rule references them).
# Reversible by construction.
#
# Required env vars:
#   PROXIMO_API_BASE_URL   e.g. https://pve.example.com:8006/api2/json
#   PROXIMO_NODE           e.g. your-node
#   PROXIMO_VERIFY_TLS     "true" or "false"  (nested test cluster is usually "false")
#
# Auth (one of):
#   PROXIMO_TOKEN_PATH     path to a plain file containing the full API token string
#   PROXIMO_TOKEN_FILE     path to an env file that exports the token (auto-detected)
#
# Optional:
#   SMOKE_ALIAS   throwaway alias name           (default: proximo-smoke-alias)
#   SMOKE_IPSET   throwaway ip-set name          (default: proximosmokeset)
#   SMOKE_SG      throwaway security-group name  (default: proximo-smoke-grp)
#   PYTHON        override the python interpreter (default: python3)
#
# NOTE: requires a token with firewall write on /cluster/firewall (Sys.Modify or the
# Tier-1 grant). See README.md for least-privilege token creation.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "${SCRIPT_DIR}/lib.sh"

# ---- required env checks ---------------------------------------------------
proximo_require_env PROXIMO_API_BASE_URL PROXIMO_NODE PROXIMO_VERIFY_TLS

# ---- optional env defaults -------------------------------------------------
export SMOKE_ALIAS="${SMOKE_ALIAS:-proximo-smoke-alias}"
export SMOKE_IPSET="${SMOKE_IPSET:-proximosmokeset}"
export SMOKE_SG="${SMOKE_SG:-proximo-smoke-grp}"

# ---- auth ------------------------------------------------------------------
proximo_setup_auth

# ---- python resolution -----------------------------------------------------
proximo_resolve_python
proximo_resolve_pythonpath

# ---- run (no exec — bash must resume so the EXIT trap fires) ---------------
echo ">>> Proximo FIREWALL-OBJECTS-PLANE smoke (node=${PROXIMO_NODE}; alias/ipset/sg CRUD + options; token hidden)"
echo "    ALIAS=${SMOKE_ALIAS}  IPSET=${SMOKE_IPSET}  SG=${SMOKE_SG}"
"${PROXIMO_PYTHON}" "${SCRIPT_DIR}/fwobjects-smoke.py"
exit $?
