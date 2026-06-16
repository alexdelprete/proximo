"""Firewall reach — independent-redteam follow-ups (under-flag closures).

Two real under-flags the independent redteam surfaced:
  1. VNC (5900-5999) was absent from sensitivity — a VNC-open from a narrow source rated 'low'.
  2. A service-NAME dport (e.g. "ssh") returned not-sensitive (benign) — the spec says an
     unrecognized form must NOT be downgraded to benign.
"""
from __future__ import annotations

from proximo.blast import _port_is_sensitive, _port_label, compute_firewall_reach


def test_vnc_port_is_sensitive_and_labelled():
    assert _port_is_sensitive("5901") is True          # VNC display :1
    assert _port_is_sensitive("5999") is True
    assert "VNC" in _port_label("5901")
    # boundary: 5899 / 6000 are NOT VNC
    assert _port_is_sensitive("6000") is False


def test_vnc_range_member_trips_sensitivity():
    assert _port_is_sensitive("5900:5910") is True     # range overlapping VNC
    assert _port_is_sensitive("80,5905") is True        # list with a VNC port


def test_service_name_dport_not_downgraded_to_benign():
    assert _port_is_sensitive("ssh") is True            # known sensitive service name
    assert _port_is_sensitive("vnc") is True
    assert _port_is_sensitive("rdp") is True
    # an UNRECOGNIZED service name must be conservative (never benign), per the spec
    assert _port_is_sensitive("some-unknown-svc") is True
    # but a plain list of genuinely non-sensitive numeric ports stays not-sensitive
    assert _port_is_sensitive("80,443") is False


def test_vnc_from_single_host_is_not_low():
    # VNC is admin-grade remote desktop — from a single host it must be at least MEDIUM, not low.
    r = compute_firewall_reach("ACCEPT", "in", source="203.0.113.5", dport="5901", proto="tcp",
                               scope_label="cluster")
    assert all(a["severity"] != "low" for a in r.affected)


def test_named_service_from_single_host_is_not_low():
    r = compute_firewall_reach("ACCEPT", "in", source="203.0.113.5", dport="ssh", proto="tcp",
                               scope_label="cluster")
    assert all(a["severity"] != "low" for a in r.affected)
