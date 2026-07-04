"""PMG + PDM certificate-fingerprint WIRE-ENFORCEMENT.

Completes cert pinning across all four Proxmox surfaces (PVE + PBS already covered
in test_pve_fingerprint / test_pbs_fingerprint). Same guarantee: an exact-cert
SHA-256 match on the handshake replaces CA/hostname validation for a self-signed
PMG/PDM, and a mismatch closes the socket before credentials/token are sent.
Proven on a real TLS handshake, not a mock.
"""

from __future__ import annotations

import datetime
import hashlib
import socket
import ssl
import threading

import httpx
import pytest

from proximo.backends import ProximoError
from proximo.pdm import PdmBackend, PdmConfig
from proximo.pmg import PmgBackend, PmgConfig

_HEX64 = "ab" * 32


def _selfsigned_cert(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "surface.lab.local")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .sign(key, hashes.SHA256())
    )
    certfile, keyfile = tmp_path / "c.pem", tmp_path / "k.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    fp = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return str(certfile), str(keyfile), fp


def _one_shot_tls_server(certfile, keyfile):
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
                    tls.sendall(b"HTTP/1.1 200 OK\r\ncontent-length: 13\r\n"
                                b"content-type: application/json\r\n\r\n{\"data\":null}")
            except (ssl.SSLError, OSError):
                pass
        except TimeoutError:
            pass
        finally:
            lsock.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return port, t


def _pmg(tmp_path, **kw):
    secret = tmp_path / "pw"
    secret.write_text("sekrit-test-sentinel\n")
    base = dict(base_url="https://127.0.0.1:1/api2/json", password_path=str(secret),
                verify_tls=False, ca_bundle=None, fingerprint=None)
    base.update(kw)
    return PmgConfig(**base)


def _pdm(tmp_path, **kw):
    secret = tmp_path / "tok"
    secret.write_text("tid:sekrit-test-sentinel\n")
    base = dict(base_url="https://127.0.0.1:1/api2/json", token_path=str(secret),
                verify_tls=False, ca_bundle=None, fingerprint=None)
    base.update(kw)
    return PdmConfig(**base)


# (label, backend_cls, cfg_factory) — one row per surface, shared assertions below.
SURFACES = [
    ("pmg", PmgBackend, _pmg),
    ("pdm", PdmBackend, _pdm),
]


@pytest.mark.parametrize("label,Backend,mkcfg", SURFACES)
class TestConstruction:
    def test_fingerprint_alone_is_sufficient(self, label, Backend, mkcfg, tmp_path):
        Backend(mkcfg(tmp_path, fingerprint=_HEX64))

    def test_no_fingerprint_no_ca_verify_off_refuses(self, label, Backend, mkcfg, tmp_path):
        with pytest.raises(ProximoError, match="unverified"):
            Backend(mkcfg(tmp_path))

    def test_malformed_fingerprint_refused_loudly(self, label, Backend, mkcfg, tmp_path):
        with pytest.raises(ProximoError, match="fingerprint"):
            Backend(mkcfg(tmp_path, fingerprint="not-a-hash"))

    def test_refusal_message_names_the_fingerprint_env(self, label, Backend, mkcfg, tmp_path):
        with pytest.raises(ProximoError, match="FINGERPRINT"):
            Backend(mkcfg(tmp_path))


@pytest.mark.parametrize("label,Backend,mkcfg", SURFACES)
class TestWrongPinRefuses:
    def test_wrong_pin_refuses_before_creds_sent(self, label, Backend, mkcfg, tmp_path):
        certfile, keyfile, _fp = _selfsigned_cert(tmp_path)
        port, t = _one_shot_tls_server(certfile, keyfile)
        api = Backend(mkcfg(tmp_path, base_url=f"https://127.0.0.1:{port}/api2/json",
                            fingerprint="00" * 32))
        with pytest.raises(httpx.ConnectError, match="fingerprint"):
            api._get("/version")
        t.join(timeout=5)


def _colon_pin(fp: str) -> str:
    return ":".join(fp[i:i + 2].upper() for i in range(0, 64, 2))


class TestMatchingPinReachesServer:
    """A matching pin lets the request through. PDM is token-auth (one GET); PMG does a
    ticket-login POST first, so its server must answer both requests on the kept-alive
    connection and return a valid ticket."""

    def test_pdm_matching_pin(self, tmp_path):
        certfile, keyfile, fp = _selfsigned_cert(tmp_path)
        port, t = _one_shot_tls_server(certfile, keyfile)
        api = PdmBackend(_pdm(tmp_path, base_url=f"https://127.0.0.1:{port}/api2/json",
                              fingerprint=_colon_pin(fp)))
        assert api._get("/version") is None
        t.join(timeout=5)

    def test_pmg_matching_pin_builds_pinned_client(self, tmp_path):
        # PMG's ticket-login round-trip makes a mock GET brittle (httpx pools connections
        # differently across login+GET); the real "matching pin connects" evidence is the
        # live-lab proof against pmg-test. Here, assert the pin is actually wired into the
        # client's TLS context (not silently ignored) — the wire refusal test covers enforcement.
        from proximo._tls import _FingerprintPinnedContext
        _, _, fp = _selfsigned_cert(tmp_path)
        api = PmgBackend(_pmg(tmp_path, fingerprint=_colon_pin(fp)))
        ctx = api._client._transport._pool._ssl_context
        assert isinstance(ctx, _FingerprintPinnedContext)
        assert ctx._pin == fp  # normalized lowercase, no colons


class TestConfigParsing:
    def test_pmg_from_env(self, tmp_path, monkeypatch):
        pw = tmp_path / "pw"
        pw.write_text("x\n")
        monkeypatch.setenv("PROXIMO_PMG_BASE_URL", "https://h:8006/api2/json")
        monkeypatch.setenv("PROXIMO_PMG_PASSWORD_PATH", str(pw))
        monkeypatch.setenv("PROXIMO_PMG_VERIFY_TLS", "false")
        monkeypatch.setenv("PROXIMO_PMG_FINGERPRINT", _HEX64)
        assert PmgConfig.from_env().fingerprint == _HEX64

    def test_pmg_from_target(self):
        cfg = PmgConfig.from_target({"base_url": "https://h/api2/json",
                                     "password_path": "/x", "verify_tls": False,
                                     "fingerprint": _HEX64})
        assert cfg.fingerprint == _HEX64

    def test_pdm_from_env(self, tmp_path, monkeypatch):
        tok = tmp_path / "tok"
        tok.write_text("x\n")
        monkeypatch.setenv("PROXIMO_PDM_BASE_URL", "https://h:8443/api2/json")
        monkeypatch.setenv("PROXIMO_PDM_TOKEN_PATH", str(tok))
        monkeypatch.setenv("PROXIMO_PDM_VERIFY_TLS", "false")
        monkeypatch.setenv("PROXIMO_PDM_FINGERPRINT", _HEX64)
        assert PdmConfig.from_env().fingerprint == _HEX64

    def test_pdm_from_target(self):
        cfg = PdmConfig.from_target({"base_url": "https://h/api2/json",
                                     "token_path": "/x", "verify_tls": False,
                                     "fingerprint": _HEX64})
        assert cfg.fingerprint == _HEX64
