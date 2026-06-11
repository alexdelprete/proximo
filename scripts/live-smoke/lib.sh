#!/usr/bin/env bash
# lib.sh — shared auth + env-validation helpers for Proximo live-smoke wrappers.
# Source this file; do NOT execute it directly.
#
# DESIGN
# ------
# This library provides two public functions:
#   proximo_require_env   — fail-fast check for required env vars
#   proximo_setup_auth    — resolve the API token from env and wire it into
#                           PROXIMO_TOKEN_PATH via a shred-on-exit tmpfile
#                           (ONLY when the caller doesn't already point
#                            PROXIMO_TOKEN_PATH at an existing file).
#
# SECURITY NOTES
# --------------
# * The token secret is NEVER printed to stdout/stderr.
# * All temp files are created with umask 077 so they are owner-read-only.
# * A `trap '... shred -u ...' EXIT` is registered BEFORE writing the secret.
# * Python is called WITHOUT `exec` so that bash resumes after it exits and
#   the EXIT trap fires — shredding the temp file even on signals or errors.
# * PROXIMO_VERIFY_TLS defaults to empty (no override); callers should set
#   it to "false" explicitly when their PVE uses a self-signed cert.

set -uo pipefail
umask 077

# ---------------------------------------------------------------------------
# proximo_require_env VAR [VAR ...]
#   Print an error and exit 1 if any listed env var is unset or empty.
# ---------------------------------------------------------------------------
proximo_require_env() {
    local missing=0
    for var in "$@"; do
        if [[ -z "${!var:-}" ]]; then
            echo "ERROR: required env var \$$var is unset or empty." >&2
            missing=1
        fi
    done
    if (( missing )); then
        echo "" >&2
        echo "Set the required variables and re-run. See scripts/live-smoke/README.md." >&2
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# proximo_setup_auth
#   Resolves the Proxmox API token and ensures PROXIMO_TOKEN_PATH points to
#   a readable file containing the token string.
#
#   Resolution order (first match wins):
#     1. PROXIMO_TOKEN_PATH already set AND the file exists — use it as-is.
#        (User manages the file; we do not create or shred anything.)
#     2. PROXIMO_TOKEN_FILE set — source that env file, detect the token,
#        write it to a mktemp, register shred trap.
#     3. Neither set — print usage and exit 1.
#
#   After this function returns, PROXIMO_TOKEN_PATH is exported and valid.
# ---------------------------------------------------------------------------
proximo_setup_auth() {
    # Case 1: caller already wired an existing token file
    if [[ -n "${PROXIMO_TOKEN_PATH:-}" && -r "${PROXIMO_TOKEN_PATH}" ]]; then
        echo ">>> auth: using PROXIMO_TOKEN_PATH=${PROXIMO_TOKEN_PATH}"
        export PROXIMO_TOKEN_PATH
        return 0
    fi

    # Case 2: source an env file and auto-detect the token
    if [[ -z "${PROXIMO_TOKEN_FILE:-}" ]]; then
        echo "ERROR: set PROXIMO_TOKEN_PATH (path to a file containing the API token)" >&2
        echo "       OR set PROXIMO_TOKEN_FILE (path to an env file exporting the token)." >&2
        echo "       See scripts/live-smoke/README.md for token format details." >&2
        exit 1
    fi

    if [[ ! -r "${PROXIMO_TOKEN_FILE}" ]]; then
        echo "ERROR: PROXIMO_TOKEN_FILE=${PROXIMO_TOKEN_FILE} is not readable." >&2
        exit 1
    fi

    # Source the env file quietly into a subshell-safe way
    set -a; . "${PROXIMO_TOKEN_FILE}" 2>/dev/null || true; set +a

    # Detect the token string.
    # Pass 1: one variable holds the full USER@REALM!ID=SECRET token.
    local TOK=""
    local n v
    while IFS= read -r n; do
        v="${!n-}"
        if [[ "$v" =~ ^[A-Za-z0-9_.-]+@[a-z]+\![A-Za-z0-9_.-]+=[A-Za-z0-9._-]{8,}$ ]]; then
            TOK="$v"
            break
        fi
    done < <(compgen -v)

    # Pass 2: separate ID var + SECRET var.
    if [[ -z "$TOK" ]]; then
        local ID="" SEC=""
        while IFS= read -r n; do
            v="${!n-}"
            [[ "$v" =~ ^[A-Za-z0-9_.-]+@[a-z]+\![A-Za-z0-9_.-]+$ ]] && ID="$v"
            [[ "$v" =~ ^[A-Za-z0-9._-]{16,}$ ]] && SEC="$v"
        done < <(compgen -v)
        [[ -n "$ID" && -n "$SEC" ]] && TOK="${ID}=${SEC}"
    fi

    if [[ -z "$TOK" ]]; then
        echo "ERROR: could not detect a Proxmox API token in PROXIMO_TOKEN_FILE=${PROXIMO_TOKEN_FILE}." >&2
        echo "       Expected format (one of):" >&2
        echo "         PROXMOX_TOKEN=user@realm!tokenid=<secret>" >&2
        echo "         PROXMOX_TOKEN_ID=user@realm!tokenid   and   PROXMOX_TOKEN_SECRET=<secret>" >&2
        echo "       (Secret masked in file layout below:)" >&2
        sed -E 's/=[[:space:]]*"?([A-Za-z0-9_+/.=-]{16,})"?/=<secret-masked>/g' \
            "${PROXIMO_TOKEN_FILE}" >&2
        exit 1
    fi

    # Write the token to a temp file; register shred-on-exit BEFORE the write.
    local TF
    TF="$(mktemp)"
    # Register cleanup BEFORE writing the secret.
    # NOTE: do NOT use `exec` to launch python later — bash must resume so
    # this trap actually fires. See lib.sh design notes at top of file.
    trap 'shred -u "${TF}" 2>/dev/null || rm -f "${TF}"' EXIT

    printf '%s' "$TOK" > "${TF}"

    export PROXIMO_TOKEN_PATH="${TF}"
    echo ">>> auth: token written to tmpfile (will be shredded on exit)"
}

# ---------------------------------------------------------------------------
# proximo_resolve_python
#   Sets PROXIMO_PYTHON to the python3 interpreter to use.
#   Preference order:
#     $PYTHON if set,
#     python3 if on PATH,
#     python if on PATH.
#   Exits 1 if none found.
# ---------------------------------------------------------------------------
proximo_resolve_python() {
    if [[ -n "${PYTHON:-}" ]]; then
        PROXIMO_PYTHON="${PYTHON}"
    elif command -v python3 &>/dev/null; then
        PROXIMO_PYTHON="python3"
    elif command -v python &>/dev/null; then
        PROXIMO_PYTHON="python"
    else
        echo "ERROR: no python3/python found on PATH. Set PYTHON=/path/to/python3." >&2
        exit 1
    fi
    echo ">>> python: ${PROXIMO_PYTHON}"
}

# ---------------------------------------------------------------------------
# proximo_resolve_pythonpath
#   Exports PYTHONPATH so that `import proximo` finds the package.
#   If proximo is already installed (importable), PYTHONPATH is left alone.
#   Otherwise, we assume the standard layout and add <repo-root>/src.
#   SCRIPT_DIR must be set by the caller to the directory of the wrapper.
# ---------------------------------------------------------------------------
proximo_resolve_pythonpath() {
    # Try installed first (cleanest for end-users who did `pip install proximo`)
    if "${PROXIMO_PYTHON}" -c "import proximo" 2>/dev/null; then
        echo ">>> proximo: found via installed package (no PYTHONPATH needed)"
        return 0
    fi
    # Fall back to repo src layout (two dirs up from scripts/live-smoke/)
    local REPO_ROOT
    REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
    local SRC_DIR="${REPO_ROOT}/src"
    if [[ ! -d "${SRC_DIR}/proximo" ]]; then
        echo "ERROR: proximo not installed and ${SRC_DIR}/proximo not found." >&2
        echo "       Either: pip install proximo   OR run from the repo root." >&2
        exit 1
    fi
    export PYTHONPATH="${SRC_DIR}${PYTHONPATH:+:$PYTHONPATH}"
    echo ">>> proximo: using repo src at ${SRC_DIR}"
}
