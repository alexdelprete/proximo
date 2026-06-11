"""Append-only, tamper-EVIDENT audit ledger — the PROVE pillar.

Every entry is hash-chained:
    entry_hash = H(prev_hash + canonical(body))
where `body` is the entry minus the chaining fields, and H is either SHA-256 (default) or
HMAC-SHA256 under an operator key (opt-in — see below). Altering, inserting, reordering, or removing
any *interior* entry breaks the chain, and verify() pinpoints the first break. **Tail operations** —
deleting the last entry, appending a forged entry, or wiping the file — are NOT caught by a forward
walk alone; pass `verify(expected_head=...)` with a head() value you pinned off-box to detect them.

Keyed mode (opt-in, set ``PROXIMO_AUDIT_KEY_PATH``):
    With a key, entry_hash = HMAC-SHA256(key, prev_hash + canonical(body)) and each entry carries
    ``"alg": "hmac-sha256"``. An attacker who can write the log but cannot read the key cannot forge a
    valid forward rewrite. A keyed ledger **requires every entry to be keyed** — an unkeyed entry is
    treated as a downgrade and FAILS verification (the entry's own ``alg`` tag is never trusted; the
    ledger's key configuration is authoritative). You therefore cannot mix modes in one log — start a
    fresh log to enable keying.

    Honest threat model: a same-user attacker who can write the 0600 log can often read the 0600 key
    too — so keying is a *marginal* hardening, **not** a substitute for an off-box head() anchor, which
    remains the strong guarantee. Use both.

Tamper-EVIDENT, not tamper-PROOF: anyone with write access (and, in keyed mode, the key) can rewrite the
chain from a point forward. Detection is the guarantee, not prevention.

Secrets are never written here — callers pass only non-sensitive detail.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

GENESIS_HASH = "0" * 64
_KEY_ALG = "hmac-sha256"
# Fields excluded from the hashed `body`. `alg` is a transparency marker, NOT a trusted input: verify()
# decides keyed-vs-unkeyed from the ledger's own key, so a tampered `alg` can't downgrade the check.
_CHAIN_FIELDS = ("prev_hash", "entry_hash", "alg")


def _canonical(body: dict[str, Any]) -> bytes:
    # Deterministic, order-independent serialization for hashing.
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash(body: dict[str, Any], prev_hash: str, key: bytes | None = None) -> str:
    msg = prev_hash.encode("ascii") + _canonical(body)
    if key is not None:
        return hmac.new(key, msg, hashlib.sha256).hexdigest()
    # Identical bytes to the historical two-update form: sha256(prev || canonical(body)).
    return hashlib.sha256(msg).hexdigest()


def load_or_create_key(path: str) -> bytes:
    """Load the audit HMAC key from `path` (stored as hex), generating a 32-byte key at 0600 if absent.

    Fail-closed on an empty or non-hex key file. See the module docstring for the (honest, marginal)
    threat model — keying is not a substitute for an off-box head() anchor.
    """
    path = os.path.expanduser(path)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if not os.path.exists(path):
        # Generate + publish ATOMICALLY: write a 0600 temp in the same dir, then os.link it into place.
        # The key file is therefore never observable half-written/empty by a racing process — the loser
        # of the link race reads the winner's key (single-key guarantee).
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".audit-key-")
        try:
            os.fchmod(fd, 0o600)
            os.write(fd, (secrets.token_bytes(32).hex() + "\n").encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(tmp, path)  # atomic; raises if another process already created the key
        except FileExistsError:
            pass
        finally:
            os.unlink(tmp)
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        raise ValueError(f"audit key file {path} is empty — refusing an empty key (fail-closed)")
    try:
        key = bytes.fromhex(text)
    except ValueError as e:
        raise ValueError(f"audit key file {path} is not valid hex: {e}") from e
    if len(key) < 32:
        raise ValueError(f"audit key file {path} is too short ({len(key)} bytes; need >=32) — fail-closed")
    return key


@dataclass(frozen=True)
class LedgerVerification:
    ok: bool
    entries: int
    broken_at: int | None = None  # 1-based line number of the first bad entry
    reason: str | None = None


class AuditLedger:
    """Hash-chained, flock-guarded, append-only audit ledger (JSON lines).

    Pass `key` (bytes) to chain with HMAC-SHA256 instead of bare SHA-256 (opt-in keyed mode). A given
    log file must be all-keyed or all-unkeyed for its whole life — see the module docstring.
    """

    def __init__(self, path: str, *, key: bytes | None = None):
        self.path = path
        self.key = key
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    @property
    def keyed(self) -> bool:
        return self.key is not None

    @staticmethod
    def _last_hash(f) -> str:
        # O(n) tail scan. Audit volume is low; optimize to a cached head if it ever isn't.
        prev = GENESIS_HASH
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                prev = json.loads(line)["entry_hash"]
            except (json.JSONDecodeError, KeyError):
                continue
        return prev

    def record(self, action: str, *, target: str, mutation: bool = False,
               outcome: str = "ok", detail: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {
            "ts": datetime.now(UTC).isoformat(),
            "action": action,
            "target": target,
            "mutation": mutation,
            "outcome": outcome,
            "detail": detail or {},
        }
        # Hold an exclusive lock across read-prev + append so the chain stays consistent under concurrency.
        # Owner-only on creation: entries carry command/SQL detail, so the umask default is too open.
        # (Applies at creation only — an existing file keeps whatever mode the operator set.)
        with open(self.path, "a+", encoding="utf-8",
                  opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                prev = self._last_hash(f)
                entry = {**body, "prev_hash": prev, "entry_hash": _hash(body, prev, self.key)}
                if self.key is not None:
                    entry["alg"] = _KEY_ALG
                f.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return entry

    def head(self) -> str:
        """Latest entry_hash (GENESIS if empty). Anchor this off-box for true tamper-resistance."""
        if not os.path.exists(self.path):
            return GENESIS_HASH
        with open(self.path, encoding="utf-8") as f:
            return self._last_hash(f)

    def verify(self, expected_head: str | None = None) -> LedgerVerification:
        """Walk the chain; report the first break.

        Catches interior alteration / insertion / removal / reorder on its own. A keyed ledger also
        catches a *downgrade* (a keyed entry rewritten without the HMAC), because keyed-vs-unkeyed is
        decided by this ledger's key — never by the entry's own `alg` tag. To also catch tail
        truncation, a forged tail-append, or a full file replacement, pass `expected_head` — the head()
        value you pinned off-box; verify fails if the chain's final hash doesn't match it.
        """
        prev = GENESIS_HASH
        count = 0
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for lineno, raw in enumerate(f, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        return LedgerVerification(False, count, lineno, "unparseable line")
                    if not isinstance(entry, dict):
                        return LedgerVerification(False, count, lineno, "non-object line")
                    if entry.get("prev_hash") != prev:
                        return LedgerVerification(
                            False, count, lineno, "prev_hash mismatch (entry inserted, removed, or reordered)"
                        )
                    body = {k: v for k, v in entry.items() if k not in _CHAIN_FIELDS}
                    entry_alg = entry.get("alg")
                    if self.key is not None:
                        # Keyed ledger: EVERY entry must be keyed. A non-keyed entry is a downgrade —
                        # reject it (do not let the attacker-controlled `alg` choose the algorithm).
                        if entry_alg != _KEY_ALG:
                            return LedgerVerification(
                                False, count, lineno,
                                "expected an HMAC-keyed entry but found none (possible downgrade)",
                            )
                        expected = _hash(body, prev, self.key)
                    else:
                        # Unkeyed ledger: a keyed entry can't be verified without the key — say so.
                        if entry_alg == _KEY_ALG:
                            return LedgerVerification(
                                False, count, lineno, "chain is HMAC-keyed but verify() has no key"
                            )
                        if entry_alg is not None:
                            return LedgerVerification(
                                False, count, lineno, f"unknown chain alg {entry_alg!r}"
                            )
                        expected = _hash(body, prev, None)
                    if not hmac.compare_digest(expected, entry.get("entry_hash") or ""):
                        return LedgerVerification(False, count, lineno, "entry_hash mismatch (entry altered)")
                    prev = entry["entry_hash"]
                    count += 1
        # Tail truncation / forged append / full wipe are invisible to a forward walk — only an
        # off-box anchor can catch them.
        if expected_head is not None and prev != expected_head:
            return LedgerVerification(False, count, None, "head mismatch (tail truncated/appended or file replaced)")
        return LedgerVerification(ok=True, entries=count)
