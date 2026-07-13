"""Secret-file permission floor, shared by every loader that reads a secret by path.

One helper, one rule (mirrors ``_tls.py``'s role for TLS parsing): a secret file that
group/other can touch is refused LOUD at config/load time, so a mis-deployed credential
fails before it is ever used. Callers: PVE token + audit HMAC key (``config.py``),
PBS/PMG/PDM credentials (``pbs.py`` / ``pmg.py`` / ``pdm.py``), and the network faces'
bearer tokens + A2A signing key (``webguard.py`` / ``a2a/app.py``).
"""

from __future__ import annotations

import os


def refuse_exposed_secret(path: str, what: str) -> None:
    """Refuse a secret file that group/other can touch (mode & 0o077) — fail LOUD, not silent.

    READ-side floor for secrets referenced by path. Write-side hygiene is already
    0600+O_NOFOLLOW everywhere Proximo *creates* these; this catches the hand-deployed
    file that arrived 0644. Skips: empty path (secret not configured), missing file
    (the call-time read already fails loudly — don't change that), and non-POSIX
    (no meaningful mode bits).
    """
    if not path or os.name != "posix":
        return
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return  # missing/unreadable => the call-time open reports it; perms aren't the story
    if mode & 0o077:
        raise RuntimeError(
            f"{what} {path!r} is group/other-accessible (mode {mode & 0o777:03o}). "
            f"Refusing to start: anything on this box could read the secret. "
            f"Fix: chmod 600 {path}"
        )
