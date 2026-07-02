"""Off-box PROVE anchor — automated ledger-head pinning for tail-attack detection.

The PROVE ledger's forward hash-chain walk (``audit.py``) catches interior tampering — reorder,
insert, alter, remove of a *middle* entry — but is BLIND to TAIL operations: truncating the last
N entries, wiping the file wholesale, or forging an appended tail all leave a chain that verifies
clean on its own. The documented strong guarantee is to pin the ledger ``head()`` OFF-BOX and pass
it back as ``expected_head`` (see ``AuditLedger.verify``). Today that pin is a manual copy-paste;
this module automates it.

An :class:`AnchorSink` publishes the current head to an off-box destination and fetches the last
pinned head back, so on startup the live ledger is verified against the anchor with no operator
action. This is the SMALLEST FIRST SLICE: only :class:`FileSink` (write the head as JSON to a file —
e.g. an NFS mount or object store that Proximo can write-but-not-rewrite) plus config-load auto-pin
and on-demand export from ``audit_verify``. HTTP / syslog / journal sinks and a background export
thread are deliberate later extensions.

HONESTY — where the guarantee actually rests. The anchor removes the manual step; it does NOT add
cryptography. Its entire value depends on the sink being **less-compromisable than this box**: a
separate host or an append-only / write-protected store, monitored independently. An attacker who
can rewrite the sink can supply any head and defeat the anchor. Proximo cannot prove the sink's own
integrity — that is the operator's job. Detection, not prevention, remains the guarantee.

FAIL-CLOSED. A configured sink is a declared dependency. If it is unreachable — a missing
destination directory, an unreadable/corrupt anchor file, or a malformed pinned head — the sink
raises :class:`AnchorError`, and the config layer turns that into a hard refusal to start. A
configured-but-unreachable anchor means tail-attack detection is silently gone, so we fail loud,
never skip. Only an unambiguous "sink reachable but empty" (a legit first run) reads as ``None``.

POINT-IN-TIME LIMIT (inherent, same as a manual ``PROXIMO_AUDIT_EXPECTED_HEAD``). The pin is ONE
hash: verifying the live ledger against it catches a ledger that DIVERGED or went BACKWARDS
(truncation / wipe / fork), but a ledger that legitimately grew FORWARD past the pin also fails the
equality check. So the anchor is at its strongest as a startup / at-rest check (ledger == last
export before any new appends).

ANTI-POISONING RULE (the security invariant — see ``server.audit_verify``). The on-demand export
advances the pin ONLY on a first run (no pin yet) or when the live head is UNCHANGED from the pin —
it NEVER overwrites an existing pin once the head has MOVED. That is deliberate: auto-advancing the
pin on every verify (the naive design) lets a verify that just DETECTED a truncation re-pin the
anchor to the tampered head, making the attack permanently invisible after the next restart. So
advancing the pin past a moved head is the operator's DELIBERATE act, never a silent side-effect of
a verify. A moved head is surfaced as ``anchor_hint`` — using the pinned vs live entry COUNT to say
whether the ledger grew FORWARD (benign stale-pin lag; re-pin when confirmed) or went BACKWARD (a
truncation/wipe signal to investigate). Walking the chain to confirm a forward advance is genuine
(the old pin still appears as an interior hash) is a deliberate later extension; until then the pin
stays put and the count-direction hint keeps a routine op from reading as tampering.
"""

from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod

from .audit import looks_like_head

# Sink types recognized by build_anchor_sink(). The slice ships "file"; the enum is the seam the
# later HTTP/syslog/journal sinks slot into. "none" (and "") = disabled.
_KNOWN_SINKS = frozenset({"none", "file"})


class AnchorError(Exception):
    """Publishing to, or fetching from, the off-box anchor sink failed.

    Raised on any unreachable / corrupt / malformed-pin condition. The config layer maps this to a
    fail-closed startup refusal; the on-demand export path maps it to a refused ``audit_verify``.
    """


class AnchorSink(ABC):
    """Publish and fetch audit-ledger heads off-box. See the module docstring for the trust model."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short sink identifier surfaced in ``audit_verify`` output (e.g. ``"file"``)."""

    @abstractmethod
    def publish(self, head: str, ts: str, node: str, ledger_path: str,
                entries: int | None = None) -> None:
        """Write ``head`` (+ provenance, incl. the ledger ``entries`` count) to the sink,
        overwriting any prior pin. Idempotent.

        Raises :class:`AnchorError` on any I/O failure — never a silent no-op.
        """

    @abstractmethod
    def last_pin(self) -> dict | None:
        """Return the most recent pinned payload (``{head, ts, node, ledger_path, entries?}``), or
        ``None`` if the sink is reachable but empty (a legit first run).

        Raises :class:`AnchorError` if the sink is unreachable or its stored pin is corrupt /
        malformed. ``None`` is reserved for the unambiguous first-run case (fail-closed elsewhere).
        """

    def last_head(self) -> str | None:
        """The most recent pinned head, or ``None`` on a legit first run. Delegates to
        :meth:`last_pin` so every sink shares one read/validate path."""
        pin = self.last_pin()
        return pin["head"] if pin else None


class FileSink(AnchorSink):
    """Pin the ledger head to a file — the portable slice sink.

    The file is meant to live OFF-BOX (an NFS/SMB mount, an object-store gateway, a synced path)
    where this box can write the latest head but cannot rewrite history. Locally it is also handy
    for testing. The head is stored as a small JSON object ``{"head", "ts", "node", "ledger_path"}``
    and written atomically (temp file + ``os.replace``) so a reader never sees a half-written pin.
    """

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    @property
    def name(self) -> str:
        return "file"

    def publish(self, head: str, ts: str, node: str, ledger_path: str,
                entries: int | None = None) -> None:
        payload: dict = {"head": head, "ts": ts, "node": node, "ledger_path": ledger_path}
        if entries is not None:
            payload["entries"] = entries
        directory = os.path.dirname(self.path) or "."
        tmp: str | None = None
        try:
            # Atomic publish: write a temp file in the destination dir, fsync, then rename over the
            # anchor. mkstemp raises (OSError) if `directory` is missing — that is the fail-closed
            # "destination unreachable" signal, wrapped as AnchorError below.
            fd, tmp = tempfile.mkstemp(dir=directory, prefix=".proximo-anchor-")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            tmp = None  # renamed away; nothing to clean up
        except (OSError, ValueError) as e:
            raise AnchorError(
                f"file anchor sink: cannot publish head to {self.path!r}: {e}"
            ) from e
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def last_pin(self) -> dict | None:
        try:
            with open(self.path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            # File absent. If its parent dir exists, the sink is reachable but empty => first run.
            # If the parent dir is GONE, the sink is unreachable/misconfigured => fail closed.
            parent = os.path.dirname(self.path) or "."
            if os.path.isdir(parent):
                return None
            raise AnchorError(
                f"file anchor sink: destination directory {parent!r} does not exist "
                f"(configured but unreachable — fail closed)"
            ) from None
        except (OSError, ValueError) as e:
            raise AnchorError(f"file anchor sink: cannot read {self.path!r}: {e}") from e
        try:
            payload = json.loads(text)
            head = payload["head"]
        except (ValueError, KeyError, TypeError) as e:
            raise AnchorError(
                f"file anchor sink: {self.path!r} is corrupt or missing a 'head' field: {e}"
            ) from e
        if not isinstance(head, str) or not looks_like_head(head):
            raise AnchorError(
                f"file anchor sink: pinned head in {self.path!r} is malformed "
                f"(expected a 64-char hex head() value) — treat as sink corruption/tamper"
            )
        return payload


def build_anchor_sink(sink_type: str, file_path: str | None) -> AnchorSink | None:
    """Instantiate the configured anchor sink, or ``None`` when disabled (``"none"``/``""``).

    Raises ``RuntimeError`` (a config error) on an unknown sink type, or a ``"file"`` sink with no
    path — a misconfigured anchor must fail loud at load, not silently disable tail-attack
    detection. Reaching the sink (fetching ``last_head()``) is the caller's fail-closed step.
    """
    sink = (sink_type or "none").strip().lower()
    if sink in ("", "none"):
        return None
    if sink not in _KNOWN_SINKS:
        raise RuntimeError(
            f"PROXIMO_AUDIT_ANCHOR_SINK={sink!r} is not a recognized sink "
            f"(this slice supports: 'none', 'file')"
        )
    # sink == "file"
    if not file_path or not file_path.strip():
        raise RuntimeError(
            "PROXIMO_AUDIT_ANCHOR_SINK=file requires PROXIMO_AUDIT_ANCHOR_FILE_PATH "
            "(the off-box file to pin the ledger head to)"
        )
    return FileSink(file_path.strip())
