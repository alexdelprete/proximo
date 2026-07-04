"""PBS certificate-fingerprint WIRE-ENFORCEMENT (v0.14.x hardening).

The pin is proven on a real TLS handshake, not a mock: each wire test generates a
self-signed cert (the exact shape a stock PBS box serves), runs a one-shot TLS server
on 127.0.0.1, and connects through the pinned context. Match → handshake completes.
Mismatch → the connection is refused at the socket layer, before one byte of HTTP
(the token header) leaves the client.
"""

from __future__ import annotations

import datetime
import hashlib
import socket
import ssl
import threading

import httpx
import pytest

from proximo._tls import fingerprint_pinned_context, normalize_fingerprint
from proximo.backends import ProximoError
from proximo.pbs import PbsBackend, PbsConfig

# ---------------------------------------------------------------------------
# normalize_fingerprint — shape validation (fail-closed on garble)
# ---------------------------------------------------------------------------

_HEX64 = "ab" * 32  # 64 hex chars


class TestNormalizeFingerprint:
    def test_plain_hex_lowercased_passthrough(self):
        assert normalize_fingerprint(_HEX64) == _HEX64

    def test_colon_separated_uppercase_pbs_gui_form(self):
        # The PBS GUI shows AA:BB:...:FF — the form operators will paste.
        colons = ":".join(["AB"] * 32)
        assert normalize_fingerprint(colons) == _HEX64

    def test_whitespace_stripped(self):
        assert normalize_fingerprint(f"  {_HEX64}\n") == _HEX64

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "ab:cd",  # too short
            "zz" * 32,  # not hex
            "ab" * 31,  # 62 chars
            "ab" * 33,  # 66 chars
            "sha256:" + "ab" * 32,  # scheme prefix not accepted — paste the bare hash
        ],
    )
    def test_garbled_shapes_refused(self, bad):
        with pytest.raises(ValueError):
            normalize_fingerprint(bad)


# ---------------------------------------------------------------------------
# Real-wire pin enforcement
# ---------------------------------------------------------------------------


def _selfsigned_cert(tmp_path):
    """Generate a self-signed cert+key (stock-PBS shape); return (certfile, keyfile, sha256hex)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pbs.test-lab.example")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .sign(key, hashes.SHA256())
    )
    certfile = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    fp = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return str(certfile), str(keyfile), fp


def _one_shot_tls_server(certfile, keyfile):
    """Accept ONE TLS connection, answer a minimal HTTP response, exit. Returns (port, thread)."""
    srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    srv_ctx.load_cert_chain(certfile, keyfile)
    lsock = socket.socket()
    lsock.bind(("127.0.0.1", 0))
    lsock.listen(1)
    lsock.settimeout(5)
    port = lsock.getsockname()[1]

    def serve():
        try:
            raw, _ = lsock.accept()
            raw.settimeout(5)
            try:
                with srv_ctx.wrap_socket(raw, server_side=True) as tls:
                    tls.recv(4096)
                    tls.sendall(
                        b"HTTP/1.1 200 OK\r\ncontent-length: 11\r\n"
                        b"content-type: application/json\r\n\r\n{\"data\":[]}"
                    )
            except (ssl.SSLError, OSError):
                pass  # client aborted the handshake (mismatch case) — expected
        except TimeoutError:
            pass
        finally:
            lsock.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return port, t


class TestPinOnTheWire:
    def test_matching_pin_completes_handshake(self, tmp_path):
        certfile, keyfile, fp = _selfsigned_cert(tmp_path)
        port, t = _one_shot_tls_server(certfile, keyfile)
        ctx = fingerprint_pinned_context(fp)
        with httpx.Client(verify=ctx) as client:
            r = client.get(f"https://127.0.0.1:{port}/")
        assert r.status_code == 200
        t.join(timeout=5)

    def test_wrong_pin_refuses_before_http(self, tmp_path):
        certfile, keyfile, _fp = _selfsigned_cert(tmp_path)
        port, t = _one_shot_tls_server(certfile, keyfile)
        ctx = fingerprint_pinned_context("00" * 32)  # deliberately wrong
        with httpx.Client(verify=ctx) as client:
            with pytest.raises(httpx.ConnectError, match="fingerprint"):
                client.get(f"https://127.0.0.1:{port}/")
        t.join(timeout=5)

    def test_pinned_backend_end_to_end(self, tmp_path):
        """PbsBackend with ONLY a fingerprint (no CA, verify off) reaches a matching server."""
        certfile, keyfile, fp = _selfsigned_cert(tmp_path)
        port, t = _one_shot_tls_server(certfile, keyfile)
        token = tmp_path / "token"
        token.write_text("backup@pbs!t:sekrit-test-sentinel\n")
        cfg = PbsConfig(
            base_url=f"https://127.0.0.1:{port}/api2/json",
            token_path=str(token),
            verify_tls=False,
            ca_bundle=None,
            fingerprint=":".join(fp[i : i + 2].upper() for i in range(0, 64, 2)),
        )
        api = PbsBackend(cfg)
        assert api._get("/admin/datastore") == []
        t.join(timeout=5)


# ---------------------------------------------------------------------------
# Backend construction semantics
# ---------------------------------------------------------------------------


class TestBackendConstruction:
    def _cfg(self, tmp_path, **kw):
        token = tmp_path / "token"
        token.write_text("backup@pbs!t:sekrit-test-sentinel\n")
        base = dict(
            base_url="https://pbs.example.invalid:8007/api2/json",
            token_path=str(token),
            verify_tls=False,
            ca_bundle=None,
            fingerprint=None,
        )
        base.update(kw)
        return PbsConfig(**base)

    def test_fingerprint_alone_is_sufficient_verification(self, tmp_path):
        # Pin substitutes for CA validation (the PBS-client idiom) — no refusal.
        PbsBackend(self._cfg(tmp_path, fingerprint=_HEX64))

    def test_no_fingerprint_no_ca_verify_off_still_refuses(self, tmp_path):
        with pytest.raises(ProximoError, match="unverified"):
            PbsBackend(self._cfg(tmp_path))

    def test_malformed_fingerprint_refused_loudly_at_construction(self, tmp_path):
        with pytest.raises(ProximoError, match="fingerprint"):
            PbsBackend(self._cfg(tmp_path, fingerprint="not-a-hash"))

    def test_refusal_message_now_mentions_the_fingerprint_option(self, tmp_path):
        with pytest.raises(ProximoError, match="PROXIMO_PBS_FINGERPRINT"):
            PbsBackend(self._cfg(tmp_path))
