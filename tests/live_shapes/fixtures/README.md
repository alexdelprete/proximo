# Live-shape characterization fixtures

`pve_real_shapes.json` holds **real Proxmox API response shapes**, captured read-only from a live PVE
and **scrubbed of infra literals** (node/guest names → generic; MACs → dummy; ACL principals →
`userN@pam`; high-entropy fields like `digest`/`smbios1`/`vmgenid` dropped). What's preserved is the
**structure and PVE's serialization quirks** — that's the whole point.

Consumed by `tests/test_live_shapes.py`. These pin the blast engine's API-shape assumptions against
ground truth so a wrong assumption fails the fast suite, not a live cluster. Notably they lock in:

- **PVE omits unset backup-job selection keys** (`pool`/`vmid`/`selMode`) — it does NOT send `null`.
  The `guest_destroy` tri-state coverage resolver depends on this.
- `all` is an int (`1`), `exclude` is a comma-string, disks are `slot: volid`.
- the snapshot list always carries a synthetic `{"name": "current"}` entry that is not a snapshot.

## Re-capturing (e.g. after a PVE major upgrade)

1. `python scripts/live-smoke/capture-shapes.py --out raw.json` (read-only; needs the live-smoke env).
2. **Scrub** `raw.json`: genericize node/guest names, MACs, ACL principals; drop `digest`/`smbios1`/
   `vmgenid`/`meta`/mail fields. Keep the selection-mode and disk-slot serialization verbatim.
3. Diff against `pve_real_shapes.json`. A shape change here means a real assumption to re-verify in
   the engine — update both the fixture and any characterization assertion that moved.

These are **shape-only and point-in-time**: they prove "we parse the real shape," not "the mutation
acts correctly." Live mutate→verify is the `scripts/live-smoke/` harness (Track B of the live-CI scope).
