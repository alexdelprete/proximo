#!/usr/bin/env bash
# phase1-smoke.sh — Proximo Phase-1 MUTATE live-smoke wrapper.
#
# Drives create/clone/backup/restore/delete through Proximo's own stack against
# a real Proxmox VE node using THROWAWAY VMIDs in a dedicated pool. Self-cleaning
# (try/finally in Python). Requires broader token privileges than readonly.
#
# Required env vars:
#   PROXIMO_API_BASE_URL   e.g. https://pve.example.com:8006/api2/json
#   PROXIMO_NODE           e.g. your-node
#   PROXIMO_VERIFY_TLS     "true" or "false"
#   SMOKE_STORE            storage ID for backups, e.g. your-backup-storage
#
# Auth (one of):
#   PROXIMO_TOKEN_PATH     path to a plain file containing the full API token string
#   PROXIMO_TOKEN_FILE     path to an env file that exports the token (auto-detected)
#
# Optional:
#   SMOKE_POOL             pool to create throwaway VMs in (default: proximo-smoke-throwaway)
#   SMOKE_VMID             base VMID for the throwaway triplet (default: 9900)
#                          Three consecutive IDs are used: BASE, BASE+1, BASE+2.
#                          Choose IDs well above your highest production VMID.
#   PROXIMO_CT_ALLOWLIST   comma-separated CTID allowlist for Proximo (default: matches SMOKE_VMID)
#   PYTHON                 override the python interpreter (default: python3)
#
# WARNING: This smoke performs REAL (reversible, self-cleaning) mutations on your
# Proxmox host. Run only against a dedicated test or dev cluster, or with IDs and
# storage confirmed safe for throwaway use.
#
# See README.md for full setup instructions and token creation guidance.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "${SCRIPT_DIR}/lib.sh"

# ---- required env checks ---------------------------------------------------
proximo_require_env PROXIMO_API_BASE_URL PROXIMO_NODE PROXIMO_VERIFY_TLS SMOKE_STORE

# ---- optional env defaults -------------------------------------------------
export SMOKE_POOL="${SMOKE_POOL:-proximo-smoke-throwaway}"
export SMOKE_VMID="${SMOKE_VMID:-9900}"
# Default the CT allowlist to the throwaway VMID range so no hardcoded IDs ship.
export PROXIMO_CT_ALLOWLIST="${PROXIMO_CT_ALLOWLIST:-${SMOKE_VMID},$((SMOKE_VMID+1)),$((SMOKE_VMID+2))}"

# ---- auth ------------------------------------------------------------------
proximo_setup_auth

# ---- python resolution -----------------------------------------------------
proximo_resolve_python
proximo_resolve_pythonpath

# ---- run (no exec — bash must resume so the EXIT trap fires) ---------------
echo ">>> Proximo Phase-1 MUTATE smoke (node=${PROXIMO_NODE}, pool=${SMOKE_POOL}, base-vmid=${SMOKE_VMID}; token hidden)"
echo "    SMOKE_STORE=${SMOKE_STORE}  CT_ALLOWLIST=${PROXIMO_CT_ALLOWLIST}"
"${PROXIMO_PYTHON}" "${SCRIPT_DIR}/phase1-smoke.py"
exit $?
