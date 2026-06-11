"""TLS verify helper shared by the PVE and PBS backends.

httpx deprecated passing a CA-bundle *path* string to ``verify=``; the documented
replacement is an ``ssl.SSLContext``. ``verify=True``/``verify=False`` (bool) are
unchanged. Both backends send an API-token secret over the wire, so they share one
implementation to keep their TLS behavior identical.
"""

from __future__ import annotations

import ssl


def httpx_verify(value: bool | str) -> bool | ssl.SSLContext:
    """Translate a verify setting into an httpx ``verify=`` value without the deprecated str form.

    - ``bool`` (True/False): passed through unchanged.
    - ``str``: treated as a CA-bundle path and loaded into a default SSL context
      (``cafile=``). The file is read eagerly here, so a bad CA path fails fast at
      backend construction rather than on the first request — the right tradeoff for
      a backend that sends a token secret over the wire.

    Note ``isinstance(True, str)`` is False, so bool values never hit the str branch.
    """
    if isinstance(value, str):
        return ssl.create_default_context(cafile=value)
    return value
