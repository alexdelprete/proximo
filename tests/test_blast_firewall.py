"""Firewall/network reach engine — pure unit tests (zero API)."""
from __future__ import annotations

from proximo.blast import (
    _port_label,
    _source_breadth,
    compute_apply_lockout,
    compute_firewall_reach,
)


def test_source_breadth_anywhere():
    for s in (None, "", "0.0.0.0/0", "::/0"):
        kind, _ = _source_breadth(s)
        assert kind == "anywhere", s


def test_source_breadth_anywhere_label_is_honest_per_token():
    # the human label must not claim 0.0.0.0/0 when the source was ::/0 (IPv6 anywhere)
    _, v6 = _source_breadth("::/0")
    assert "::/0" in v6 and "0.0.0.0/0" not in v6
    _, v4 = _source_breadth("0.0.0.0/0")
    assert "0.0.0.0/0" in v4
    # empty/None defaults to the widest, family-agnostic label (still leads with 0.0.0.0/0 so the
    # maximal-reach assertions hold) AND names ::/0 so an IPv6 reader is not misled.
    _, empty = _source_breadth(None)
    assert empty.startswith("0.0.0.0/0") and "::/0" in empty


def test_source_breadth_internal():
    for s in ("10.0.0.0/8", "192.168.1.0/24", "172.16.5.4", "127.0.0.1"):
        assert _source_breadth(s)[0] == "internal", s


def test_source_breadth_specific_public():
    assert _source_breadth("203.0.113.5")[0] == "host"
    assert _source_breadth("8.8.8.0/24")[0] == "range"


def test_source_breadth_ipset_alias_is_unknown():
    for s in ("+admins", "dc/trusted", "myalias"):
        assert _source_breadth(s)[0] == "named", s


def test_port_label_known_and_unknown():
    assert "SSH" in _port_label("22") and "22" in _port_label("22")
    assert "8006" in _port_label("8006")
    assert _port_label(None) == "ALL ports"
    assert _port_label("") == "ALL ports"
    assert "8080" in _port_label("8080")
    assert "8000:8100" in _port_label("8000:8100")


def test_port_label_reflects_proto_not_hardcoded_tcp():
    # a udp rule must NOT be narrated as '/tcp' (false content)
    assert "/tcp" not in _port_label("53", "udp")
    assert "udp" in _port_label("53", "udp")
    # tcp / unspecified keeps the conventional /tcp display
    assert "/tcp" in _port_label("22", "tcp")
    assert "/tcp" in _port_label("22", None)


# ---------------------------------------------------------------------------
# compute_firewall_reach — per-rule reach aggregator (A2)
# ---------------------------------------------------------------------------


def test_accept_in_no_source_no_dport_is_maximal_high():
    # The advisor's separating test: empty source + empty dport => MAXIMAL, never benign.
    r = compute_firewall_reach("ACCEPT", "in", source=None, dport=None, proto=None,
                               scope_label="cluster")
    assert r.risk == "high"
    a = r.affected[0]
    assert a["effect"] == "permits" and a["service"] == "ALL ports"
    assert a["from"].startswith("0.0.0.0/0") and a["severity"] == "high"


def test_accept_in_ssh_from_internet_high():
    r = compute_firewall_reach("ACCEPT", "in", source="0.0.0.0/0", dport="22", proto="tcp",
                               scope_label="cluster")
    assert r.risk == "high"
    assert any("SSH" in a["service"] and a["severity"] == "high" for a in r.affected)


def test_accept_in_ssh_from_internal_medium():
    r = compute_firewall_reach("ACCEPT", "in", source="10.0.0.0/8", dport="22", proto="tcp",
                               scope_label="cluster")
    assert any(a["severity"] == "medium" for a in r.affected)
    assert r.risk in ("medium", "high")  # never below medium for an internal mgmt-port open


def test_accept_in_single_host_nonsensitive_low():
    r = compute_firewall_reach("ACCEPT", "in", source="203.0.113.5", dport="8080", proto="tcp",
                               scope_label="cluster")
    assert any(a["severity"] == "low" for a in r.affected)


def test_drop_in_mgmt_port_broad_is_lockout_high():
    r = compute_firewall_reach("DROP", "in", source="0.0.0.0/0", dport="8006", proto="tcp",
                               scope_label="cluster")
    assert r.risk == "high"
    assert any(a["effect"] == "blocks" for a in r.affected)
    assert any("lockout" in line.lower() for line in r.summary_lines)


def test_enable_zero_is_staged_not_permits():
    r = compute_firewall_reach("ACCEPT", "in", source="0.0.0.0/0", dport=None, proto=None,
                               scope_label="cluster", enable=False)
    assert any(a["effect"] == "staged" for a in r.affected)
    assert any("staged" in line.lower() for line in r.summary_lines)
    assert not any(a["effect"] == "permits" for a in r.affected)


def test_ipset_source_conservative_not_low():
    r = compute_firewall_reach("ACCEPT", "in", source="+admins", dport="22", proto="tcp",
                               scope_label="cluster")
    assert all(a["severity"] != "low" for a in r.affected)  # unknown breadth -> not low


def test_out_direction_is_egress_note_lower_severity():
    r = compute_firewall_reach("ACCEPT", "in", source="0.0.0.0/0", dport=None, proto=None,
                               scope_label="cluster")
    out = compute_firewall_reach("ACCEPT", "out", source="0.0.0.0/0", dport=None, proto=None,
                                 scope_label="cluster")
    assert any(a["direction"] == "out" for a in out.affected)
    # egress is materially lower than the inbound-anywhere-all-ports HIGH
    assert out.risk != "high" and r.risk == "high"


def test_out_direction_does_not_narrate_source_as_destination():
    # the engine only holds `source`; an egress rule's destination is `dest` (not passed in v1).
    # The wording must NOT falsely label the source as the egress destination.
    out = compute_firewall_reach("ACCEPT", "out", source="203.0.113.5", dport="443", proto="tcp",
                                 scope_label="cluster")
    egress = next(line for line in out.summary_lines if "outbound" in line.lower())
    assert "203.0.113.5" not in egress  # source must not be narrated as the destination
    assert "egress" in egress.lower()


def test_dport_range_and_list_parsed_not_downgraded():
    rng = compute_firewall_reach("ACCEPT", "in", source="0.0.0.0/0", dport="8000:8100",
                                 proto="tcp", scope_label="cluster")
    lst = compute_firewall_reach("ACCEPT", "in", source="0.0.0.0/0", dport="80,443",
                                 proto="tcp", scope_label="cluster")
    assert any("8000:8100" in a["service"] for a in rng.affected)
    assert any("80,443" in a["service"] for a in lst.affected)
    # anywhere source still forces HIGH regardless of the port form
    assert rng.risk == "high" and lst.risk == "high"


def test_summary_carries_per_rule_reach_disclaimer():
    r = compute_firewall_reach("ACCEPT", "in", source="0.0.0.0/0", dport="22", proto="tcp",
                               scope_label="cluster")
    joined = " ".join(r.summary_lines).lower()
    assert "per-rule" in joined
    # NEVER asserts the cluster is exposed as fact
    assert "your cluster is reachable" not in joined
    assert all(line.lower().startswith("this rule") or "per-rule" in line.lower()
               or line.strip().startswith("->") for line in r.summary_lines)


# ---------------------------------------------------------------------------
# compute_apply_lockout — best-effort mgmt-iface naming (Part B)
# ---------------------------------------------------------------------------


def test_apply_lockout_names_iface_holding_mgmt_ip():
    pending = ["vmbr0"]
    ifaces = [{"iface": "vmbr0", "address": "10.0.0.10"}, {"iface": "vmbr1", "address": "10.0.0.1"}]
    r = compute_apply_lockout(pending, "10.0.0.10", ifaces)
    assert r.risk == "high"
    assert any(a.get("iface") == "vmbr0" for a in r.affected)
    assert any("10.0.0.10" in line for line in r.summary_lines)


def test_apply_lockout_hostname_mgmt_no_match_high_stands():
    r = compute_apply_lockout(["vmbr0"], "pve.example.lan",
                              [{"iface": "vmbr0", "address": "10.0.0.10"}])
    assert r.risk == "high"
    assert any("could not identify" in line.lower() for line in r.summary_lines)
    assert not any(a.get("severity") == "low" for a in r.affected)  # never "no lockout"


def test_apply_lockout_no_iface_addresses_high_stands():
    # mgmt host is an IP but no iface carries an address (read returned addressless ifaces)
    r = compute_apply_lockout(["vmbr0"], "10.0.0.10", [{"iface": "vmbr0"}])
    assert r.risk == "high"
    assert any("could not identify" in line.lower() for line in r.summary_lines)
    assert not any(a.get("severity") == "low" for a in r.affected)


def test_apply_lockout_mgmt_iface_not_pending_high_stands():
    # mgmt iface identified but NOT in the pending set => still HIGH, never "no lockout"
    ifaces = [{"iface": "vmbr0", "address": "10.0.0.10"}, {"iface": "vmbr1", "address": "10.0.0.20"}]
    r = compute_apply_lockout(["vmbr1"], "10.0.0.10", ifaces)
    assert r.risk == "high"
    assert not any(a.get("severity") == "low" for a in r.affected)


def test_apply_lockout_matches_cidr_form_address():
    # PVE often reports address as 'cidr' (e.g. '10.0.0.10/24') — must still match the bare IP
    ifaces = [{"iface": "vmbr0", "cidr": "10.0.0.10/24"}]
    r = compute_apply_lockout(["vmbr0"], "10.0.0.10", ifaces)
    assert any(a.get("iface") == "vmbr0" for a in r.affected)
    assert r.risk == "high"
