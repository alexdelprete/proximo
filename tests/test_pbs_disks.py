"""TDD tests for the PBS disk-admin plane (Wave 2d, full-surface campaign) — fully mocked, no
live PBS.

Mirrors test_pbs_node.py's style (fake `_get`/`_post`/`_put`/`_delete` recorder) and
test_node_lifecycle.py's style (validator-rejection + plan-factory risk/blast-radius asserts).

Covers: validators (whole-disk vs disk-or-partition, datastore name, zpool name, devices CSV,
filesystem/raidlevel/compression enums, ashift range); backend functions for all 10 ops (5 read,
5 mutation); plan factories (risk ratings — ALL mutations RISK_HIGH, mirroring
node_lifecycle.py's PVE disk-admin ratings exactly; blast-radius/no-undo wording); the two
confirmed schema gaps named in the module docstring (no lvm/lvmthin backends; no zfs delete).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from proximo.backends import ProximoError
from proximo.pbs_disks import (
    _check_ashift,
    _check_compression,
    _check_devices_csv,
    _check_filesystem,
    _check_pbs_datastore_name,
    _check_pbs_disk_or_partition,
    _check_pbs_wholedisk,
    _check_pbs_zpool_name,
    _check_raidlevel,
    disk_directory_create,
    disk_directory_delete,
    disk_directory_list,
    disk_initgpt,
    disk_smart,
    disk_wipe,
    disk_zfs_create,
    disk_zfs_get,
    disk_zfs_list,
    disks_list,
    plan_disk_directory_create,
    plan_disk_directory_delete,
    plan_disk_initgpt,
    plan_disk_wipe,
    plan_disk_zfs_create,
)
from proximo.planning import RISK_HIGH

# ---------------------------------------------------------------------------
# Fake API
# ---------------------------------------------------------------------------

def _api(get_return=None) -> SimpleNamespace:
    """Minimal PBS API fake recording the LAST _get/_post/_put/_delete call."""
    seen: dict = {}

    def fake_get(path, params=None):
        seen["get_path"] = path
        seen["get_params"] = params
        return get_return

    def fake_post(path, data=None):
        seen["post_path"] = path
        seen["post_data"] = data
        return "UPID:localhost:00000001:00000000:00000000:disk:sda:root@pam:"

    def fake_put(path, data=None):
        seen["put_path"] = path
        seen["put_data"] = data
        return "UPID:localhost:00000001:00000000:00000000:disk:sda:root@pam:"

    def fake_delete(path, params=None):
        seen["delete_path"] = path
        seen["delete_params"] = params
        return None

    return SimpleNamespace(
        _get=fake_get, _post=fake_post, _put=fake_put, _delete=fake_delete, seen=seen,
    )


# ---------------------------------------------------------------------------
# Module structure — the schema gaps named in the module docstring
# ---------------------------------------------------------------------------

def test_module_docstring_names_the_lvm_gap_and_zfs_delete_gap():
    import proximo.pbs_disks as m
    doc = m.__doc__ or ""
    assert "lvm" in doc.lower()
    assert "delete" in doc.lower()


def test_no_lvm_or_lvmthin_functions_exist():
    """PBS's live schema has NO /nodes/{node}/disks/lvm* path at all."""
    import proximo.pbs_disks as m
    for bad in ("disk_lvm_list", "disk_lvm_create", "disk_lvmthin_list", "disk_lvmthin_create"):
        assert not hasattr(m, bad), f"{bad} should not exist — PBS has no lvm/lvmthin disk API"


def test_no_zfs_delete_function_exists():
    """PBS's live schema has NO DELETE /nodes/{node}/disks/zfs/{name} — nothing to build."""
    import proximo.pbs_disks as m
    assert not hasattr(m, "disk_zfs_delete")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckPbsWholedisk:
    def test_valid_ata_scsi_virtio(self):
        for d in ("sda", "hda", "vda", "xvda"):
            assert _check_pbs_wholedisk(d) == d

    def test_valid_nvme(self):
        assert _check_pbs_wholedisk("nvme0n1") == "nvme0n1"

    def test_rejects_dev_prefix(self):
        """PBS disk names are BARE /sys/block/<name> basenames — unlike PVE's /dev/... form."""
        with pytest.raises(ProximoError):
            _check_pbs_wholedisk("/dev/sda")

    def test_rejects_partition_suffix(self):
        """Whole-disk validator rejects a trailing partition number (that's wipedisk-only)."""
        with pytest.raises(ProximoError):
            _check_pbs_wholedisk("sda1")

    def test_rejects_traversal(self):
        with pytest.raises(ProximoError):
            _check_pbs_wholedisk("../etc/passwd")

    def test_rejects_trailing_newline(self):
        with pytest.raises(ProximoError):
            _check_pbs_wholedisk("sda\n")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_pbs_wholedisk("")


class TestCheckPbsDiskOrPartition:
    def test_valid_whole_disk(self):
        assert _check_pbs_disk_or_partition("sda") == "sda"
        assert _check_pbs_disk_or_partition("nvme0n1") == "nvme0n1"

    def test_valid_partition(self):
        assert _check_pbs_disk_or_partition("sda1") == "sda1"
        assert _check_pbs_disk_or_partition("nvme0n1p1") == "nvme0n1p1"

    def test_rejects_dev_prefix(self):
        with pytest.raises(ProximoError):
            _check_pbs_disk_or_partition("/dev/sda1")

    def test_rejects_traversal(self):
        with pytest.raises(ProximoError):
            _check_pbs_disk_or_partition("..")

    def test_rejects_trailing_newline(self):
        with pytest.raises(ProximoError):
            _check_pbs_disk_or_partition("sda1\n")


class TestCheckPbsDatastoreName:
    def test_valid(self):
        assert _check_pbs_datastore_name("tank") == "tank"
        assert _check_pbs_datastore_name("data-01") == "data-01"

    def test_rejects_too_short(self):
        with pytest.raises(ProximoError):
            _check_pbs_datastore_name("ab")

    def test_rejects_too_long(self):
        with pytest.raises(ProximoError):
            _check_pbs_datastore_name("a" * 33)

    def test_rejects_leading_hyphen(self):
        with pytest.raises(ProximoError):
            _check_pbs_datastore_name("-bad")

    def test_rejects_trailing_newline(self):
        with pytest.raises(ProximoError):
            _check_pbs_datastore_name("tank\n")


class TestCheckPbsZpoolName:
    def test_valid(self):
        assert _check_pbs_zpool_name("tank") == "tank"

    def test_rejects_leading_digit(self):
        """Zpool-name pattern (GET /disks/zfs/{name}) requires a LETTER start, unlike the
        datastore-name pattern (POST create) which allows alnum/underscore start."""
        with pytest.raises(ProximoError):
            _check_pbs_zpool_name("1tank")

    def test_rejects_trailing_newline(self):
        with pytest.raises(ProximoError):
            _check_pbs_zpool_name("tank\n")

    def test_rejects_single_char(self):
        with pytest.raises(ProximoError):
            _check_pbs_zpool_name("t")


class TestCheckDevicesCsv:
    def test_valid_single(self):
        assert _check_devices_csv("sda") == "sda"

    def test_valid_multi(self):
        assert _check_devices_csv("sda,sdb,sdc") == "sda,sdb,sdc"

    def test_rejects_dev_prefixed_item(self):
        with pytest.raises(ProximoError):
            _check_devices_csv("sda,/dev/sdb")

    def test_rejects_empty_segment(self):
        with pytest.raises(ProximoError):
            _check_devices_csv("sda,,sdb")

    def test_rejects_empty_string(self):
        with pytest.raises(ProximoError):
            _check_devices_csv("")


class TestCheckFilesystem:
    def test_valid(self):
        assert _check_filesystem("ext4") == "ext4"
        assert _check_filesystem("xfs") == "xfs"

    def test_rejects_unknown(self):
        with pytest.raises(ProximoError):
            _check_filesystem("btrfs")


class TestCheckRaidlevel:
    def test_valid(self):
        for r in ("single", "mirror", "raid10", "raidz", "raidz2", "raidz3"):
            assert _check_raidlevel(r) == r

    def test_rejects_pve_only_draid(self):
        """dRAID is PVE-only — PBS's raidlevel enum has no draid/draid2/draid3."""
        with pytest.raises(ProximoError):
            _check_raidlevel("draid")


class TestCheckCompression:
    def test_valid(self):
        for c in ("gzip", "lz4", "lzjb", "zle", "zstd", "on", "off"):
            assert _check_compression(c) == c

    def test_rejects_unknown(self):
        with pytest.raises(ProximoError):
            _check_compression("brotli")


class TestCheckAshift:
    def test_valid_range(self):
        assert _check_ashift(9) == 9
        assert _check_ashift(12) == 12
        assert _check_ashift(16) == 16

    def test_rejects_below_min(self):
        with pytest.raises(ProximoError):
            _check_ashift(8)

    def test_rejects_above_max(self):
        with pytest.raises(ProximoError):
            _check_ashift(17)


# ---------------------------------------------------------------------------
# Backend functions — reads
# ---------------------------------------------------------------------------

class TestDisksList:
    def test_path_defaults_localhost(self):
        api = _api(get_return=[{"name": "sda"}])
        result = disks_list(api)
        assert api.seen["get_path"] == "/nodes/localhost/disks/list"
        assert result == [{"name": "sda"}]

    def test_forwards_filters(self):
        api = _api(get_return=[])
        disks_list(api, include_partitions=True, skipsmart=True, usage_type="unused")
        assert api.seen["get_params"] == {
            "include-partitions": True, "skipsmart": True, "usage-type": "unused",
        }

    def test_returns_empty_list_on_none(self):
        api = _api(get_return=None)
        assert disks_list(api) == []


class TestDiskSmart:
    def test_minimal(self):
        api = _api(get_return={"status": "passed"})
        result = disk_smart(api, "sda")
        assert api.seen["get_path"] == "/nodes/localhost/disks/smart"
        assert api.seen["get_params"] == {"disk": "sda"}
        assert result == {"status": "passed"}

    def test_healthonly_forwarded(self):
        api = _api(get_return={})
        disk_smart(api, "sda", healthonly=True)
        assert api.seen["get_params"] == {"disk": "sda", "healthonly": True}

    def test_rejects_invalid_disk(self):
        api = _api()
        with pytest.raises(ProximoError):
            disk_smart(api, "/dev/sda")


class TestDiskDirectoryList:
    def test_path(self):
        api = _api(get_return=[])
        disk_directory_list(api)
        assert api.seen["get_path"] == "/nodes/localhost/disks/directory"


class TestDiskZfsList:
    def test_path(self):
        api = _api(get_return=[])
        disk_zfs_list(api)
        assert api.seen["get_path"] == "/nodes/localhost/disks/zfs"


class TestDiskZfsGet:
    def test_path(self):
        api = _api(get_return={"name": "tank"})
        result = disk_zfs_get(api, "tank")
        assert api.seen["get_path"] == "/nodes/localhost/disks/zfs/tank"
        assert result == {"name": "tank"}

    def test_rejects_leading_digit_name(self):
        api = _api()
        with pytest.raises(ProximoError):
            disk_zfs_get(api, "1tank")


# ---------------------------------------------------------------------------
# Backend functions — mutations
# ---------------------------------------------------------------------------

class TestDiskWipe:
    def test_body_and_verb(self):
        api = _api()
        disk_wipe(api, "sda")
        assert api.seen["put_path"] == "/nodes/localhost/disks/wipedisk"
        assert api.seen["put_data"] == {"disk": "sda"}

    def test_accepts_partition(self):
        api = _api()
        disk_wipe(api, "sda1")
        assert api.seen["put_data"] == {"disk": "sda1"}

    def test_rejects_dev_prefix(self):
        api = _api()
        with pytest.raises(ProximoError):
            disk_wipe(api, "/dev/sda")


class TestDiskInitgpt:
    def test_body_and_verb(self):
        api = _api()
        disk_initgpt(api, "sda")
        assert api.seen["post_path"] == "/nodes/localhost/disks/initgpt"
        assert api.seen["post_data"] == {"disk": "sda"}

    def test_uuid_forwarded(self):
        api = _api()
        disk_initgpt(api, "sda", uuid="12345678-1234-1234-1234-123456789012")
        assert api.seen["post_data"] == {
            "disk": "sda", "uuid": "12345678-1234-1234-1234-123456789012",
        }

    def test_rejects_partition(self):
        """initgpt is whole-disk only — no partition suffix allowed (unlike wipedisk)."""
        api = _api()
        with pytest.raises(ProximoError):
            disk_initgpt(api, "sda1")


class TestDiskDirectoryCreate:
    def test_minimal_body(self):
        api = _api()
        disk_directory_create(api, "sda", "tank")
        assert api.seen["post_path"] == "/nodes/localhost/disks/directory"
        assert api.seen["post_data"] == {"disk": "sda", "name": "tank"}

    def test_full_options(self):
        api = _api()
        disk_directory_create(
            api, "sda", "tank", filesystem="xfs",
            add_datastore=True, removable_datastore=True,
        )
        assert api.seen["post_data"] == {
            "disk": "sda", "name": "tank", "filesystem": "xfs",
            "add-datastore": True, "removable-datastore": True,
        }

    def test_rejects_bad_filesystem(self):
        api = _api()
        with pytest.raises(ProximoError):
            disk_directory_create(api, "sda", "tank", filesystem="btrfs")


class TestDiskDirectoryDelete:
    def test_path_no_params(self):
        """No cleanup-disks/cleanup-config on PBS — nothing but the path."""
        api = _api()
        result = disk_directory_delete(api, "tank")
        assert api.seen["delete_path"] == "/nodes/localhost/disks/directory/tank"
        assert result is None


class TestDiskZfsCreate:
    def test_minimal_body(self):
        api = _api()
        disk_zfs_create(api, "sda,sdb", "tank", "mirror")
        assert api.seen["post_path"] == "/nodes/localhost/disks/zfs"
        assert api.seen["post_data"] == {
            "devices": "sda,sdb", "name": "tank", "raidlevel": "mirror",
        }

    def test_full_options(self):
        api = _api()
        disk_zfs_create(
            api, "sda,sdb", "tank", "mirror",
            ashift=13, compression="lz4", add_datastore=True,
        )
        assert api.seen["post_data"] == {
            "devices": "sda,sdb", "name": "tank", "raidlevel": "mirror",
            "ashift": 13, "compression": "lz4", "add-datastore": True,
        }

    def test_rejects_bad_raidlevel(self):
        api = _api()
        with pytest.raises(ProximoError):
            disk_zfs_create(api, "sda,sdb", "tank", "draid")


# ---------------------------------------------------------------------------
# Plan factories — all mutations are RISK_HIGH (mirrors node_lifecycle.py's PVE disk-admin
# ratings exactly: every disk-consuming/formatting/wiping op is HIGH, no undo).
# ---------------------------------------------------------------------------

class TestPlanDiskWipe:
    def test_risk_high(self):
        p = plan_disk_wipe("sda")
        assert p.risk == RISK_HIGH

    def test_no_undo_and_destroys_wording(self):
        p = plan_disk_wipe("sda")
        assert "no undo" in p.note.lower() or "irreversible" in p.note.lower()
        assert any("destr" in b.lower() for b in p.blast_radius)

    def test_names_disk(self):
        p = plan_disk_wipe("sda")
        assert "sda" in p.target or "sda" in p.change

    def test_invalid_disk_raises(self):
        with pytest.raises(ProximoError):
            plan_disk_wipe("/dev/sda")


class TestPlanDiskInitgpt:
    def test_risk_high(self):
        p = plan_disk_initgpt("sda")
        assert p.risk == RISK_HIGH

    def test_overwrites_partition_table_wording(self):
        p = plan_disk_initgpt("sda")
        assert "partition table" in p.change.lower()


class TestPlanDiskDirectoryCreate:
    def test_risk_high(self):
        p = plan_disk_directory_create("sda", "tank")
        assert p.risk == RISK_HIGH

    def test_formats_disk_wording(self):
        p = plan_disk_directory_create("sda", "tank")
        assert any("format" in b.lower() for b in p.blast_radius)

    def test_disk_and_name_named(self):
        p = plan_disk_directory_create("sda", "tank")
        blob = p.target + p.change + " ".join(p.blast_radius)
        assert "sda" in blob
        assert "tank" in blob


class TestPlanDiskDirectoryDelete:
    def test_risk_high(self):
        p = plan_disk_directory_delete("tank")
        assert p.risk == RISK_HIGH

    def test_no_cleanup_option_disclosed(self):
        """Honest disclosure: PBS's directory-delete has NO cleanup-disks flag — the underlying
        disk data always persists, unmanaged, after this call (unlike PVE's optional wipe)."""
        p = plan_disk_directory_delete("tank")
        blob = (p.note or "") + " ".join(p.blast_radius)
        assert "persist" in blob.lower() or "unmanaged" in blob.lower()


class TestPlanDiskZfsCreate:
    def test_risk_high(self):
        p = plan_disk_zfs_create("sda,sdb", "tank", "mirror")
        assert p.risk == RISK_HIGH

    def test_formats_disks_wording(self):
        p = plan_disk_zfs_create("sda,sdb", "tank", "mirror")
        assert any("format" in b.lower() for b in p.blast_radius)

    def test_devices_named(self):
        p = plan_disk_zfs_create("sda,sdb", "tank", "mirror")
        blob = p.target + p.change + " ".join(p.blast_radius)
        assert "sda" in blob
        assert "tank" in blob

    def test_invalid_raidlevel_raises(self):
        with pytest.raises(ProximoError):
            plan_disk_zfs_create("sda,sdb", "tank", "draid")
