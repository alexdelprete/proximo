"""Storage / ISO / template operation tests — fully mocked, no live Proxmox.

Covers: URL construction, parameter mapping (including the checksum-algorithm hyphen key),
volid URL-encoding, traversal rejection, content-type validation, plan risk escalation,
and default-node resolution via api.config.node.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.config import ProximoConfig
from proximo.storage import (
    RISK_HIGH,
    RISK_MEDIUM,
    content_delete,
    plan_content_delete,
    plan_storage_download,
    storage_content,
    storage_download_url,
    storage_status,
)

# ---------------------------------------------------------------------------
# Minimal config + fake api helpers (mirror test_backends.py style)
# ---------------------------------------------------------------------------

class _FakeApi:
    """Thin stand-in that records the last _get/_post/_delete call."""

    def __init__(self, node: str = "pve"):
        # Give the api object a config.node so default-node resolution works identically to ApiBackend.
        self.config = ProximoConfig(
            api_base_url="https://x:8006/api2/json",
            node=node,
            token_path="/run/x",
            ct_allowlist=frozenset({"*"}),
        )
        self.last_get: str | None = None
        self.last_post: tuple | None = None   # (path, data)
        self.last_delete: tuple | None = None  # (path,)

    def _get(self, path: str):
        self.last_get = path
        return []

    def _post(self, path: str, data: dict | None = None):
        self.last_post = (path, data)
        return "UPID:pve:00001:0:0:taskid:download:root@pam:"

    def _delete(self, path: str, params: dict | None = None):
        self.last_delete = (path,)
        return "UPID:pve:00002:0:0:taskid:delete:root@pam:"


# ---------------------------------------------------------------------------
# storage_content
# ---------------------------------------------------------------------------

def test_storage_content_builds_correct_url():
    api = _FakeApi()
    storage_content(api, "local")
    assert api.last_get == "/nodes/pve/storage/local/content"


def test_storage_content_uses_explicit_node():
    api = _FakeApi()
    storage_content(api, "local", node="node2")
    assert api.last_get == "/nodes/node2/storage/local/content"


def test_storage_content_with_node_none_falls_back_to_config_node():
    api = _FakeApi(node="mynode")
    storage_content(api, "local", node=None)
    assert api.last_get == "/nodes/mynode/storage/local/content"


def test_storage_content_appends_content_filter_iso():
    api = _FakeApi()
    storage_content(api, "local", content="iso")
    assert api.last_get == "/nodes/pve/storage/local/content?content=iso"


def test_storage_content_appends_content_filter_backup():
    api = _FakeApi()
    storage_content(api, "local", content="backup")
    assert api.last_get == "/nodes/pve/storage/local/content?content=backup"


def test_storage_content_rejects_invalid_content_filter():
    api = _FakeApi()
    with pytest.raises(ProximoError, match="invalid content filter"):
        storage_content(api, "local", content="disk")


def test_storage_content_rejects_bad_storage_id():
    api = _FakeApi()
    with pytest.raises(ProximoError, match="invalid storage id"):
        storage_content(api, "local/../../etc")


def test_storage_content_rejects_bad_node():
    api = _FakeApi()
    with pytest.raises(ProximoError):
        storage_content(api, "local", node="bad node!")


def test_storage_content_returns_list_on_none_response():
    api = _FakeApi()
    # _get returning None (empty pool) should yield [] not None
    api._get = lambda path: None  # type: ignore[method-assign]
    result = storage_content(api, "local")
    assert result == []


# ---------------------------------------------------------------------------
# storage_status
# ---------------------------------------------------------------------------

def test_storage_status_builds_correct_url():
    api = _FakeApi()
    storage_status(api, "local")
    assert api.last_get == "/nodes/pve/storage/local/status"


def test_storage_status_uses_explicit_node():
    api = _FakeApi()
    storage_status(api, "cifs-backup", node="node3")
    assert api.last_get == "/nodes/node3/storage/cifs-backup/status"


def test_storage_status_rejects_bad_storage_id():
    api = _FakeApi()
    with pytest.raises(ProximoError, match="invalid storage id"):
        storage_status(api, "bad storage!")


def test_storage_status_returns_dict_on_none_response():
    api = _FakeApi()
    api._get = lambda path: None  # type: ignore[method-assign]
    result = storage_status(api, "local")
    assert result == {}


# ---------------------------------------------------------------------------
# storage_download_url
# ---------------------------------------------------------------------------

def test_storage_download_url_builds_correct_path():
    api = _FakeApi()
    storage_download_url(api, "local", "iso", "https://example.com/debian.iso", "debian.iso")
    path, _ = api.last_post
    assert path == "/nodes/pve/storage/local/download-url"


def test_storage_download_url_maps_required_params():
    api = _FakeApi()
    storage_download_url(api, "local", "iso", "https://example.com/debian.iso", "debian.iso")
    _, data = api.last_post
    assert data["content"] == "iso"
    assert data["url"] == "https://example.com/debian.iso"
    assert data["filename"] == "debian.iso"


def test_storage_download_url_omits_checksum_when_not_given():
    api = _FakeApi()
    storage_download_url(api, "local", "iso", "https://x.com/f.iso", "f.iso")
    _, data = api.last_post
    assert "checksum" not in data
    assert "checksum-algorithm" not in data


def test_storage_download_url_includes_checksum_with_hyphen_key():
    """The PVE body key is 'checksum-algorithm' (hyphen), NOT 'checksum_algorithm' (underscore)."""
    api = _FakeApi()
    storage_download_url(
        api, "local", "iso", "https://x.com/f.iso", "f.iso",
        checksum="abcdef1234", checksum_algorithm="sha256",
    )
    _, data = api.last_post
    assert data["checksum"] == "abcdef1234"
    assert "checksum-algorithm" in data, "body key must use a hyphen, not underscore"
    assert data["checksum-algorithm"] == "sha256"
    assert "checksum_algorithm" not in data


def test_storage_download_url_vztmpl_content_type():
    api = _FakeApi()
    storage_download_url(api, "local", "vztmpl", "https://x.com/t.tar.zst", "t.tar.zst")
    _, data = api.last_post
    assert data["content"] == "vztmpl"


def test_storage_download_url_rejects_invalid_content_type():
    api = _FakeApi()
    with pytest.raises(ProximoError, match="invalid download content type"):
        storage_download_url(api, "local", "backup", "https://x.com/f.vma", "f.vma")


def test_storage_download_url_rejects_bad_storage_id():
    api = _FakeApi()
    with pytest.raises(ProximoError, match="invalid storage id"):
        storage_download_url(api, "bad/id", "iso", "https://x.com/f.iso", "f.iso")


def test_storage_download_url_uses_explicit_node():
    api = _FakeApi()
    storage_download_url(api, "local", "iso", "https://x.com/f.iso", "f.iso", node="node4")
    path, _ = api.last_post
    assert "/nodes/node4/" in path


def test_storage_download_url_returns_upid():
    api = _FakeApi()
    upid = storage_download_url(api, "local", "iso", "https://x.com/f.iso", "f.iso")
    assert upid.startswith("UPID:")


# ---------------------------------------------------------------------------
# content_delete
# ---------------------------------------------------------------------------

def test_content_delete_url_encodes_volid():
    """colons and slashes in volid must be percent-encoded in the path segment."""
    api = _FakeApi()
    content_delete(api, "local", "local:iso/debian-12.iso")
    (path,) = api.last_delete
    assert "local%3Aiso%2Fdebian-12.iso" in path


def test_content_delete_builds_correct_path_structure():
    api = _FakeApi()
    content_delete(api, "local", "local:iso/debian-12.iso")
    (path,) = api.last_delete
    # Path must include /content/ segment before the encoded volid
    assert path.startswith("/nodes/pve/storage/local/content/")


def test_content_delete_uses_explicit_node():
    api = _FakeApi()
    content_delete(api, "local", "local:iso/f.iso", node="node5")
    (path,) = api.last_delete
    assert path.startswith("/nodes/node5/")


def test_content_delete_rejects_traversal_in_volid_dots():
    api = _FakeApi()
    with pytest.raises(ProximoError, match="traversal"):
        content_delete(api, "local", "local:iso/../../../etc/passwd")


def test_content_delete_rejects_volid_without_colon():
    api = _FakeApi()
    with pytest.raises(ProximoError, match="invalid volid"):
        content_delete(api, "local", "nodisk-image")


def test_content_delete_rejects_volid_with_spaces():
    api = _FakeApi()
    with pytest.raises(ProximoError, match="invalid volid"):
        content_delete(api, "local", "local:iso/bad file.iso")


def test_content_delete_rejects_bad_storage_id():
    api = _FakeApi()
    with pytest.raises(ProximoError, match="invalid storage id"):
        content_delete(api, "local/../etc", "local:iso/f.iso")


def test_content_delete_rejects_bad_node():
    api = _FakeApi()
    with pytest.raises(ProximoError):
        content_delete(api, "local", "local:iso/f.iso", node="bad node\n")


def test_content_delete_backup_volid_is_reachable():
    """backup volids (vzdump-* pattern) must pass validation — they're valid volid shapes."""
    api = _FakeApi()
    # Should not raise — validation + encoding succeeds
    content_delete(api, "local", "local:backup/vzdump-lxc-105-2026_06_08.tar.zst")
    (path,) = api.last_delete
    assert "local%3Abackup%2Fvzdump-lxc-105-2026_06_08.tar.zst" in path


# ---------------------------------------------------------------------------
# plan_storage_download
# ---------------------------------------------------------------------------

def test_plan_storage_download_is_medium():
    p = plan_storage_download("local", "iso", "https://x.com/f.iso", "f.iso")
    assert p.risk == RISK_MEDIUM


def test_plan_storage_download_action():
    p = plan_storage_download("local", "iso", "https://x.com/f.iso", "f.iso")
    assert p.action == "pve_storage_download"


def test_plan_storage_download_blast_radius_names_url_and_storage():
    p = plan_storage_download("local", "iso", "https://x.com/f.iso", "f.iso")
    blast = " ".join(p.blast_radius)
    assert "https://x.com/f.iso" in blast
    assert "local" in blast
    assert "f.iso" in blast


def test_plan_storage_download_note_discloses_network_fetch():
    p = plan_storage_download("local", "iso", "https://x.com/f.iso", "f.iso")
    assert p.note  # must carry a honesty disclaimer
    combined = (p.note + " ".join(p.risk_reasons)).lower()
    assert "operator" in combined or "trusted" in combined or "url" in combined


def test_plan_storage_download_current_is_empty():
    p = plan_storage_download("local", "iso", "https://x.com/f.iso", "f.iso")
    assert p.current == {}


def test_plan_storage_download_target_includes_storage():
    p = plan_storage_download("mystore", "iso", "https://x.com/f.iso", "f.iso")
    assert "mystore" in p.target


# ---------------------------------------------------------------------------
# plan_content_delete
# ---------------------------------------------------------------------------

def _content_api():
    """Empty-cluster fake: the in-use-disk scan finds no guest → base risk preserved."""
    from types import SimpleNamespace

    def _get(path):
        if path == "/cluster/resources":
            return []
        return {}

    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_get)


def test_plan_content_delete_iso_is_medium():
    p = plan_content_delete(_content_api(), "local", "local:iso/debian-12.iso")
    assert p.risk == RISK_MEDIUM


def test_plan_content_delete_vztmpl_is_medium():
    p = plan_content_delete(_content_api(), "local", "local:vztmpl/ubuntu-22.04-standard.tar.zst")
    assert p.risk == RISK_MEDIUM


def test_plan_content_delete_vzdump_volid_escalates_to_high():
    p = plan_content_delete(_content_api(), "local", "local:backup/vzdump-lxc-105-2026_06_08.tar.zst")
    assert p.risk == RISK_HIGH


def test_plan_content_delete_backup_path_segment_escalates_to_high():
    p = plan_content_delete(_content_api(), "cifs", "cifs:backup/somearchive.vma.lzo")
    assert p.risk == RISK_HIGH


def test_plan_content_delete_high_reason_names_backup_irreversibility():
    p = plan_content_delete(_content_api(), "local", "local:backup/vzdump-lxc-105-2026_06_08.tar.zst")
    combined = " ".join(p.risk_reasons).lower()
    assert "backup" in combined
    assert "restore" in combined or "cannot" in combined


def test_plan_content_delete_blast_radius_names_volid():
    volid = "local:iso/myos.iso"
    p = plan_content_delete(_content_api(), "local", volid)
    blast = " ".join(p.blast_radius)
    assert volid in blast


def test_plan_content_delete_action():
    p = plan_content_delete(_content_api(), "local", "local:iso/f.iso")
    assert p.action == "pve_content_delete"


def test_plan_content_delete_current_is_empty():
    p = plan_content_delete(_content_api(), "local", "local:iso/f.iso")
    assert p.current == {}


def test_plan_content_delete_target_includes_storage():
    p = plan_content_delete(_content_api(), "mystore", "mystore:iso/f.iso")
    assert "mystore" in p.target


# ── REGRESSION: redteam fixes (2026-06-08) ────────────────────────────────────

def test_storage_download_rejects_path_in_filename():
    from proximo.storage import storage_download_url
    # filename check raises before the api is touched -> a dummy api is fine
    with pytest.raises(ProximoError, match="invalid filename"):
        storage_download_url(None, "local", "iso", "https://x/y.iso", "../evil.iso")


def test_storage_check_volid_rejects_empty_segment():
    from proximo.storage import _check_volid
    with pytest.raises(ProximoError):
        _check_volid("local:iso//x.iso")


def test_plan_content_delete_in_use_disk_escalates_and_names_guest():
    """Deleting a volume that is an ACTIVE guest disk → escalated to HIGH + the guest named."""
    from types import SimpleNamespace

    def _get(path):
        if path == "/cluster/resources":
            return [{"vmid": "101", "type": "qemu", "node": "pve", "name": "web"}]
        if path.endswith("/config"):
            return {"scsi0": "local-lvm:vm-101-disk-0,size=8G", "bootdisk": "scsi0"}
        return {}

    api = SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_get)
    p = plan_content_delete(api, "local-lvm", "local-lvm:vm-101-disk-0")
    assert p.risk == RISK_HIGH
    assert any(a["vmid"] == "101" for a in p.affected)
