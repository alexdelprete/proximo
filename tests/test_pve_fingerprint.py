"""PVE certificate-fingerprint WIRE-ENFORCEMENT (PROXIMO_FINGERPRINT).

Extends the PBS pin (test_pbs_fingerprint.py) to the PVE ApiBackend: a stock
PVE node serves a cert signed by the per-cluster "PVE Cluster Manager CA", which
no public root trusts — so operators either ship the cluster CA or pin the cert.
Same guarantee as PBS: mismatch closes the socket before the PVEAPIToken header
is sent. Proven on a real TLS handshake, not a mock.
"""

from __future__ import annotations

import datetime
import hashlib
import socket
import ssl
import threading

import httpx
import pytest

from proximo.backends import ApiBackend, ProximoError
from proximo.config import ProximoConfig

_HEX64 = "ab" * 32


def _selfsigned_cert(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pve-test1.lab.local")])
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
                        b"HTTP/1.1 200 OK\r\ncontent-length: 13\r\n"
                        b"content-type: application/json\r\n\r\n{\"data\":null}"
                    )
            except (ssl.SSLError, OSError):
                pass
        except TimeoutError:
            pass
        finally:
            lsock.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return port, t


def _cfg(tmp_path, **kw):
    token = tmp_path / "token"
    token.write_text("root@pam!t=sekrit-test-sentinel\n")
    token.chmod(0o600)  # deploy like production: the config guard refuses group/other-readable tokens
    base = dict(
        api_base_url="https://127.0.0.1:1/api2/json",
        node="pve-test1",
        token_path=str(token),
        verify_tls=False,
        ca_bundle=None,
        fingerprint=None,
    )
    base.update(kw)
    return ProximoConfig(**base)


class TestConstruction:
    def test_fingerprint_alone_is_sufficient(self, tmp_path):
        ApiBackend(_cfg(tmp_path, fingerprint=_HEX64))

    def test_no_fingerprint_no_ca_verify_off_refuses(self, tmp_path):
        with pytest.raises(ProximoError, match="unverified"):
            ApiBackend(_cfg(tmp_path))

    def test_malformed_fingerprint_refused_loudly(self, tmp_path):
        with pytest.raises(ProximoError, match="fingerprint"):
            ApiBackend(_cfg(tmp_path, fingerprint="not-a-hash"))

    def test_refusal_message_mentions_the_fingerprint_option(self, tmp_path):
        with pytest.raises(ProximoError, match="PROXIMO_FINGERPRINT"):
            ApiBackend(_cfg(tmp_path))


class TestPinOnTheWire:
    def test_matching_pin_completes_handshake(self, tmp_path):
        certfile, keyfile, fp = _selfsigned_cert(tmp_path)
        port, t = _one_shot_tls_server(certfile, keyfile)
        api = ApiBackend(_cfg(tmp_path, api_base_url=f"https://127.0.0.1:{port}/api2/json",
                              fingerprint=":".join(fp[i:i + 2].upper() for i in range(0, 64, 2))))
        # A read through the pinned client reaches the server (data=null) — pin matched.
        assert api._get("/version") is None
        t.join(timeout=5)

    def test_wrong_pin_refuses_before_token_sent(self, tmp_path):
        certfile, keyfile, _fp = _selfsigned_cert(tmp_path)
        port, t = _one_shot_tls_server(certfile, keyfile)
        api = ApiBackend(_cfg(tmp_path, api_base_url=f"https://127.0.0.1:{port}/api2/json",
                              fingerprint="00" * 32))
        with pytest.raises(httpx.ConnectError, match="fingerprint"):
            api._get("/version")
        t.join(timeout=5)


class TestConfigParsing:
    def test_from_env_reads_proximo_fingerprint(self, tmp_path, monkeypatch):
        token = tmp_path / "tok"
        token.write_text("root@pam!t=x\n")
        token.chmod(0o600)  # the config guard refuses group/other-readable tokens
        monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://h:8006/api2/json")
        monkeypatch.setenv("PROXIMO_NODE", "n")
        monkeypatch.setenv("PROXIMO_TOKEN_PATH", str(token))
        monkeypatch.setenv("PROXIMO_VERIFY_TLS", "false")
        monkeypatch.setenv("PROXIMO_FINGERPRINT", _HEX64)
        cfg = ProximoConfig.from_env()
        assert cfg.fingerprint == _HEX64

    def test_from_target_reads_fingerprint_field(self):
        cfg = ProximoConfig.from_target({
            "base_url": "https://h:8006/api2/json", "node": "n",
            "token_path": "/x", "verify_tls": False, "fingerprint": _HEX64,
        })
        assert cfg.fingerprint == _HEX64
