"""Proximo Ceph plane — PVE core observability + flags (Wave 6a) + services lifecycle (Wave 6b)
+ OSD (Wave 6c), 2026-07-16 full-surface campaign, `.scratch/2026-07-15-full-surface-campaign.md`
"Wave 6 decomposition (Ceph — PVE)".

Endpoints, Wave 6a (13 tools — 11 read, 2 mutation):

  GET  /cluster/ceph/status                              — pve_ceph_status       (read)
  GET  /cluster/ceph/metadata[?scope=]                    — pve_ceph_metadata     (read; ADVERSARIAL)
  GET  /cluster/ceph/flags                                — pve_ceph_flags_list  (read)
  GET  /cluster/ceph/flags/{flag}                         — pve_ceph_flag_get    (read)
  PUT  /cluster/ceph/flags                                — pve_ceph_flags_set   (MUTATION, MEDIUM, async UPID)
  PUT  /cluster/ceph/flags/{flag}                          — pve_ceph_flag_set    (MUTATION, MEDIUM, sync null)
  GET  /nodes/{node}/ceph/cfg/db                          — pve_ceph_cfg_db      (read)
  GET  /nodes/{node}/ceph/cfg/raw                         — pve_ceph_cfg_raw     (read)
  GET  /nodes/{node}/ceph/cfg/value?config-keys=          — pve_ceph_cfg_value   (read)
  GET  /nodes/{node}/ceph/crush                            — pve_ceph_crush       (read)
  GET  /nodes/{node}/ceph/log[?limit=][&start=]           — pve_ceph_log         (read; ADVERSARIAL)
  GET  /nodes/{node}/ceph/rules                            — pve_ceph_rules       (read)
  GET  /nodes/{node}/ceph/cmd-safety?action=&service=&id= — pve_ceph_cmd_safety  (read)

Endpoints, Wave 6b — services lifecycle (13 tools — 3 read, 10 mutation):

  GET    /nodes/{node}/ceph/mon              — pve_ceph_mon_list       (read; ADVERSARIAL)
  POST   /nodes/{node}/ceph/mon/{monid}      — pve_ceph_mon_create     (MUTATION, MEDIUM, async UPID)
  DELETE /nodes/{node}/ceph/mon/{monid}      — pve_ceph_mon_destroy    (MUTATION, HIGH, async UPID)
  GET    /nodes/{node}/ceph/mgr              — pve_ceph_mgr_list       (read; ADVERSARIAL)
  POST   /nodes/{node}/ceph/mgr/{id}         — pve_ceph_mgr_create     (MUTATION, MEDIUM, async UPID)
  DELETE /nodes/{node}/ceph/mgr/{id}         — pve_ceph_mgr_destroy    (MUTATION, HIGH, async UPID)
  GET    /nodes/{node}/ceph/mds              — pve_ceph_mds_list       (read; ADVERSARIAL)
  POST   /nodes/{node}/ceph/mds/{name}       — pve_ceph_mds_create     (MUTATION, MEDIUM, async UPID)
  DELETE /nodes/{node}/ceph/mds/{name}       — pve_ceph_mds_destroy    (MUTATION, HIGH, async UPID)
  POST   /nodes/{node}/ceph/init             — pve_ceph_init           (MUTATION, MEDIUM, sync null)
  POST   /nodes/{node}/ceph/start            — pve_ceph_service_start  (MUTATION, MEDIUM, async UPID)
  POST   /nodes/{node}/ceph/stop             — pve_ceph_service_stop   (MUTATION, HIGH, async UPID)
  POST   /nodes/{node}/ceph/restart          — pve_ceph_service_restart (MUTATION, MEDIUM, async UPID)

Endpoints, Wave 6c — OSD (8 tools — 3 read, 5 mutation):

  GET    /nodes/{node}/ceph/osd                    — pve_ceph_osd_tree      (read; ADVERSARIAL)
  GET    /nodes/{node}/ceph/osd/{osdid}/lv-info    — pve_ceph_osd_lv_info   (read; REVIEWED_TRUSTED)
  GET    /nodes/{node}/ceph/osd/{osdid}/metadata   — pve_ceph_osd_metadata  (read; ADVERSARIAL)
  POST   /nodes/{node}/ceph/osd                    — pve_ceph_osd_create    (MUTATION, HIGH, async UPID)
  DELETE /nodes/{node}/ceph/osd/{osdid}            — pve_ceph_osd_destroy   (MUTATION, HIGH, async UPID)
  POST   /nodes/{node}/ceph/osd/{osdid}/in         — pve_ceph_osd_in        (MUTATION, MEDIUM, sync null)
  POST   /nodes/{node}/ceph/osd/{osdid}/out        — pve_ceph_osd_out       (MUTATION, MEDIUM, sync null)
  POST   /nodes/{node}/ceph/osd/{osdid}/scrub      — pve_ceph_osd_scrub     (MUTATION, LOW, sync null)

Endpoints, Wave 6d — pools + CephFS (8 tools — 3 read, 5 mutation; CLOSES Wave 6):

  GET    /nodes/{node}/ceph/pool                     — pve_ceph_pool_list    (read; ADVERSARIAL)
  GET    /nodes/{node}/ceph/pool/{name}/status[?verbose=] — pve_ceph_pool_status (read; ADVERSARIAL)
  POST   /nodes/{node}/ceph/pool                     — pve_ceph_pool_create  (MUTATION, MEDIUM, async UPID)
  PUT    /nodes/{node}/ceph/pool/{name}               — pve_ceph_pool_set    (MUTATION, MEDIUM, async UPID)
  DELETE /nodes/{node}/ceph/pool/{name}               — pve_ceph_pool_destroy (MUTATION, HIGH, async UPID)
  GET    /nodes/{node}/ceph/fs                        — pve_ceph_fs_list     (read; ADVERSARIAL)
  POST   /nodes/{node}/ceph/fs/{name}                 — pve_ceph_fs_create   (MUTATION, MEDIUM, async UPID)
  DELETE /nodes/{node}/ceph/fs/{name}                 — pve_ceph_fs_destroy  (MUTATION, HIGH, async UPID)

Schema truth: `.scratch/api-schemas-2026-07-15/wave6-pve-ceph-schema.json` (37 paths, 48
methods, extracted from the live PVE apidoc pulled 2026-07-15). NONE of these 42 tools are
live-verified yet — no Ceph cluster exists in the sealed vmbr1 lab today; every backend method
(`backends.py`) carries its own Smoke-confirm comment. This module holds the mutation plan
factories only (the 20 reads across all four waves have no plan — mirrors `apt.py`).

**`/nodes/{node}/ceph/status` is a DOCUMENTED alias** of `/cluster/ceph/status` (schema:
"cluster-wide and identical … node-level alias exists for operator convenience"). Proximo builds
ONLY the cluster form (`pve_ceph_status`) — the node alias is intentionally not built (the 5d
gc path-alias precedent: one tool per distinct wire call, not one per URL).

**UNDO HONESTY:** nothing on this plane is PVE-snapshottable — no rollback primitive exists
(same class as firewall/SDN/ACL). `pve_ceph_flags_set`/`pve_ceph_flag_set` CAPTURE-or-declare
the prior flag state into the plan; revert is "re-apply the captured values with this same
tool," never an automatic rollback.

**Risk:** both mutations are RISK_MEDIUM — flag semantics vary per flag: `pause` halts ALL
client I/O to the cluster; `noout`/`noscrub`/etc. are routine maintenance toggles. The docstring
carries this honesty line verbatim rather than implying a single uniform blast radius.

**cmd-safety is ADVISORY, never a gate** (schema: "Heuristical check"). `pve_ceph_cmd_safety`
is built here as a standalone read tool in this chunk; wiring it in as cited evidence inside a
mon/mds/osd destroy/stop plan is chunk 6b/6c's job (those plans don't exist yet in 6a) — when
they land, an unreachable cmd-safety check must degrade to an honest "cmd-safety unavailable:
<err>" line, never a fabricated `safe=true`, and never block plan rendering (fail-open by
design: a plan must still render when Ceph itself is unhealthy).

**Taint — argued, not asserted (Wave 6a adversarial review Finding 2, 2026-07-16):**

- **`pve_ceph_log` is ADVERSARIAL** (`taint.ADVERSARIAL_TOOLS`) — free-text log lines (`{n, t}`),
  Sys.Syslog-channel content, same rationale as `pve_node_journal`/`pve_node_syslog`. Not a
  contested call.
- **`pve_ceph_metadata` is ADVERSARIAL** (reclassified by the Wave 6a review; it shipped
  REVIEWED_TRUSTED originally, which didn't survive challenge). The schema types every
  per-instance mon/mgr/mds entry `"additionalProperties": 1` — an explicitly OPEN shape, not a
  closed structured record — and the documented fields include `hostname`, `addr`/`addrs`, and
  `name`, all **self-reported by each daemon at registration**, not typed in by the operator. The
  counter-argument for REVIEWED_TRUSTED would be: unlike a remote PBS (a genuinely separate
  administrative domain), Ceph mon/mgr/mds/osd daemons are part of the SAME cluster the operator
  already administers — if an attacker has compromised one badly enough to forge its `hostname`,
  they already hold a much stronger lever (arbitrary `ceph.conf`/mon-command access) than a
  spoofed metadata string. That's a real distinction, but `taint.py`'s own controlling rule is
  that **classification is by CONTENT CHANNEL, not by who chose (or already controls) the
  target** — the same rule that lands `pbs_s3_list_buckets`/`pbs_remote_scan` in
  `ADVERSARIAL_TOOLS` despite their own targets being operator-configured/same-domain too. A
  rogue or compromised daemon controls `hostname`/`addr`/`name` the same way a compromised remote
  PBS controls its store names/comments — "whoever controls it controls these bytes" — aggregated
  across every node in the cluster into the calling agent's context, unfiltered. Bias
  conservative per taint.py's own stated policy: classify as adversarial when unsure.
- **`pve_ceph_status` STAYS REVIEWED_TRUSTED** — argued, not just asserted, despite its own vague
  `{"type": "object"}` schema shape (zero documented properties; the module's own Smoke-confirm
  note above concedes the shape isn't live-verified). The distinguishing fact is the SAME
  same-admin-domain point raised above for metadata, but here it actually carries the
  classification: `ceph status`/`ceph -s` is a structured cluster-health SUMMARY (health/monmap/
  osdmap/pgmap), template-generated by ceph-mgr — a same-admin-domain daemon the operator already
  trusts to report cluster state, not an open per-instance registry of individually-addressable
  daemon-controlled strings. The free-text/open channels on THIS plane are `pve_ceph_log`
  (explicit free text) and `pve_ceph_metadata` (open per-instance self-report) — both classified
  ADVERSARIAL above; `pve_ceph_status` carries neither shape.
- `pve_ceph_cmd_safety`'s `status` field ("human-readable status message from Ceph") is the same
  class of daemon-generated advisory prose, but unlike metadata's open per-instance map it's a
  single bounded field describing ONE specific stop/destroy check the caller itself requested
  (action+service+id), and the tool is documented ADVISORY-ONLY — never a gate — so even a
  maximally hostile `status` string cannot do more than mis-describe a check result the caller
  must not act on unverified anyway. REVIEWED_TRUSTED stands.
- `flags-list`/`flag-get`/`cfg_db`/`cfg_raw`/`cfg_value`/`crush`/`rules` are closed-shape,
  operator-authored structured data (`cfg_raw`/`cfg_db` carry ceph.conf content — matches the
  `pbs_node_config_get` config-read precedent) -> REVIEWED_TRUSTED, uncontested. Both mutations
  (`flags_set`/`flag_set`) return either an opaque UPID or null — no content channel at all.

---

**Wave 6b — services lifecycle (2026-07-16).** Extends the module above; nothing in Wave 6a
changes. New: `pve_ceph_{mon,mgr,mds}_list`, `pve_ceph_{mon,mgr,mds}_{create,destroy}`,
`pve_ceph_init`, `pve_ceph_service_{start,stop,restart}`.

**Build nuance — the id path segment resolves the "default: nodename" locally.** The live schema
lists `monid` (mon POST), `id` (mgr POST), and `name` (mds POST) as `"optional": 1` params with
`"default": "nodename"` — but each is ALSO the URL path segment (`/nodes/{node}/ceph/mon/{monid}`
etc.), which cannot itself be "omitted" from an HTTP request. The flat api-viewer schema documents
path segments and true body/query params identically inside one `parameters` block, so this
"optional with a default" only makes sense as documentation for whoever constructs the request:
the CALLER (us) must resolve monid/id/name to the nodename before building the URL when the
caller passed none. `backends.py`'s `_ceph_daemon_target()` does this once, shared by all three
CREATE methods. DESTROY (DELETE) declares no `optional`/`default` on the same param at all — it
is genuinely required there (PVE cannot guess which existing instance to destroy).

**`mgr_id` avoids shadowing the `id` builtin** (the schema's own param name) — same rename
precedent as Wave 6a's `cmd-safety` `id` -> `service_id`. `mon`/`mds` don't need the rename
(`monid`/`name` are already non-shadowing).

**cmd-safety citation matrix (fail-open ADVISORY, never a gate — Wave 6a's own posture, now
actually wired in as promised):**

- `mon_destroy` — YES: `action=destroy, service=mon, id=<monid>` (mon is in the cmd-safety enum
  `{osd, mon, mds}`).
- `mds_destroy` — YES: `action=destroy, service=mds, id=<name>` (mds is in the enum).
- `mgr_destroy` — **NO.** The plan states plainly "no upstream cmd-safety check exists for mgr":
  cmd-safety's service enum is `{osd, mon, mds}` — mgr was never in it; inventing a check would
  fabricate coverage that doesn't exist upstream.
- `service_stop` — CONDITIONAL: cited only when `service` parses to a `mon.<id>`/`mds.<id>`/
  `osd.<id>` shape (kind in the enum AND a specific instance id present). A bare kind (`mon`, no
  id), `ceph`/`ceph.target`, or `mgr` has no single instance for cmd-safety to evaluate — the
  plan states "no cmd-safety check available" rather than guessing an id.
- `mon_create`/`mgr_create`/`mds_create`/`init`/`service_start`/`service_restart` — NO.
  cmd-safety only covers `stop`/`destroy` actions (schema enum) — start/restart/create have no
  upstream heuristic to cite.

Every citation attempt is wrapped in try/except: an unreachable/erroring cmd-safety call
degrades to `"cmd-safety unavailable: <ExceptionType>: <msg>"` in the plan's blast_radius, NEVER
blocks the plan, and NEVER fabricates `safe=true`. `_cmd_safety_note()` below is the shared helper.

**CAPTURE-or-declare (the 6a flags precedent, extended):** `mon_create`/`mon_destroy`,
`mgr_create`/`mgr_destroy`, `mds_create`/`mds_destroy` each best-effort read the matching
`ceph_{mon,mgr,mds}_list()` and look up the target id by `name` — a successful read that simply
finds no match degrades to `current={}` (honest — e.g. a create's target doesn't exist yet), not
a failure; only a raised exception on the read itself sets `complete=False`. `pve_ceph_init` gets
NO capture (mirrors `plan_apt_update_refresh`'s own "no meaningful current state to snapshot"
posture — there is no single "current init state" resource to read). `service_{start,stop,
restart}` also get no capture — there is no durable "is `ceph.target` currently running" read
built on this plane to snapshot from.

**Taint — mon/mgr/mds LIST tools are ADVERSARIAL, extending the Wave 6a review's metadata
reasoning (not narrowing it):** `pve_ceph_mon_list`/`pve_ceph_mgr_list`/`pve_ceph_mds_list`
return per-instance `name`/`host`/`addr`/`ceph_version` fields — the SAME daemon-self-reported
identity strings that made `pve_ceph_metadata` ADVERSARIAL in the Wave 6a review, just sliced by
service type instead of aggregated across all four. The counter-argument (closed-shape: these
schemas name every field explicitly, no `additionalProperties: 1` the way metadata's per-instance
entries do) is real and was weighed — but the controlling rule stays `taint.py`'s own: "channel,
not by who chose the target." A rogue/compromised mon/mgr/mds daemon controls `addr`/`host`/
`name` in the per-type list the identical way it controls those same fields inside the aggregated
metadata view — the JSON container shape (open vs. closed) changes how PVE happens to present the
bytes, not who authored them. Classifying the list view REVIEWED_TRUSTED while the aggregate view
stays ADVERSARIAL would be an inconsistent channel call for functionally identical content, and
`taint.py`'s own HONEST LIMITS section states the tie-break explicitly: "bias conservative...
classify as adversarial when unsure." All 10 mutations (create/destroy/init/service_*) stay
REVIEWED_TRUSTED — each returns only an opaque UPID or null, no content channel at all (same
reasoning as `flags_set`/`flag_set`).

**Taint fix (Wave 6b adversarial review Finding 1, post-review):** the 6 mon/mgr/mds
create/destroy plan factories' CAPTURE reads call `api.ceph_{mon,mgr,mds}_list()` directly — the
SAME ADVERSARIAL-classified content the paragraph above argues for, but reached WITHOUT going
through the wrapped read tool or `_audited()`, so it originally bypassed taint marking and ledger
provenance-stamping entirely. Fixed by routing every one of those 6 CAPTURE reads through
`taint.capture_adversarial_current()` — the shared helper marks the sticky taint marker (when
taint tracking is enabled) and stamps the captured entry landing in `Plan.current` (and therefore
the ledger's "planned" entry, which writes `Plan.current` verbatim) with the same
`{"untrusted": True, "content_trust": "adversarial"}` annotation `_audited()` applies. See
`taint.py`'s `capture_adversarial_current` docstring for the full mechanism.

**UNDO honesty (unchanged from Wave 6a):** no rollback primitive on this plane. `mon_destroy`
reverts via a fresh `mon_create` with the same `monid` — a NEW monitor, not a byte-for-byte
restore of the destroyed one's internal state — and every mutation docstring says so plainly.

**Risk (per the campaign brief, `.scratch/2026-07-15-full-surface-campaign.md` "Wave 6
decomposition"):** `init`/`mon_create`/`mgr_create`/`mds_create`/`service_start`/
`service_restart` = RISK_MEDIUM. `mon_destroy`/`mgr_destroy`/`mds_destroy`/`service_stop` =
RISK_HIGH (quorum/metadata-service loss for the destroys; `service_stop` halts live storage
daemons).

---

**Wave 6c — OSD (2026-07-16).** Extends the module above; nothing in Wave 6a/6b changes. New:
`pve_ceph_osd_tree`, `pve_ceph_osd_lv_info`, `pve_ceph_osd_metadata`, `pve_ceph_osd_create`,
`pve_ceph_osd_destroy`, `pve_ceph_osd_in`, `pve_ceph_osd_out`, `pve_ceph_osd_scrub`.

**osdid=0 is a VALID id (the falsy-id lesson, Wave 6b Finding 2, applied to a numeric id).**
Every osdid check in this chunk (`_check_ceph_osdid` in backends.py, `_find_osd_in_tree` below)
uses isinstance+equality, NEVER truthiness — `osdid=0` (the first OSD ever created) must never
be mistaken for "missing" anywhere on this plane.

**Taint — argued per tool, extending the established channel rule:**

- **`pve_ceph_osd_tree` is ADVERSARIAL.** The schema types the ENTIRE nested CRUSH-bucket
  response `additionalProperties: 1` (open, untyped) — an even more extreme "cannot statically
  say what's in here" shape than `pve_ceph_metadata`'s own per-instance open map — and its
  documented per-node properties (status/weight/in/usage/latencies/...) are daemon-self-reported
  telemetry flowing back through the same monitor-cluster channel that made metadata/mon-list/
  mgr-list/mds-list ADVERSARIAL. Not a contested call.
- **`pve_ceph_osd_metadata` is ADVERSARIAL.** Its `osd{}` sub-object carries `hostname`/
  `back_addr`/`front_addr`/`hb_back_addr`/`hb_front_addr` — literally the SAME daemon-self-
  reported identity/address field SET that made the aggregated `pve_ceph_metadata` ADVERSARIAL
  in Wave 6a. This is that exact channel's single-OSD drill-down (the same relationship
  `pve_ceph_mon_list`/etc. bore to the aggregate metadata view in Wave 6b), not a fresh judgment
  call.
- **`pve_ceph_osd_lv_info` STAYS REVIEWED_TRUSTED — argued, not defaulted, against the two
  precedents above.** Its schema is CLOSED-shape (no `additionalProperties: 1` — every field
  named: `creation_time`/`lv_name`/`lv_path`/`lv_size`/`lv_uuid`/`vg_name`). The CHANNEL differs
  on the axis `taint.py`'s own rule actually cares about: this content is sourced from a LOCAL
  `lvs` shell-out on the SAME host administering the OSD, not a cross-daemon network self-report
  exchanged at cluster registration. The counter-argument (an attacker who has already forged a
  rogue LV to poison `lv_name`/`vg_name` controls those bytes the same way a rogue daemon
  controls `hostname`) does not survive on TWO independent grounds, not one (Wave 6c review
  strengthening, 2026-07-16 — the "requires root" ground alone doesn't rule out a non-root daemon
  writing malicious data through some other channel; this second ground is the sharper, more
  load-bearing one): (1) forging local LVM metadata on a host already REQUIRES root/host-level
  compromise on that specific node — a materially stronger foothold than a compromised/rogue
  MON/MGR/MDS/OSD daemon merely joining the cluster with a leaked cephx key (the threat model
  that drove metadata/list/osd_tree/osd_metadata ADVERSARIAL); (2) even granting some non-root
  compromise, `lv_name`/`vg_name` are not operator-typed or daemon-rewritable free strings in the
  first place — `ceph-volume lvm create/prepare` auto-generates them as UUID-derived identifiers
  (e.g. `ceph-<uuid>`/`osd-block-<uuid>`) at OSD-creation time, and the running `ceph-osd` daemon
  does not rewrite them during normal operation, so a routinely-compromised (non-root) OSD daemon
  process cannot steer an arbitrary string into these fields just by being compromised — a root
  escalation is the only lever that reaches them at all. This lands `pve_ceph_osd_lv_info` in the
  SAME class as `cfg_raw`/`cfg_db` (Wave 6a's local-config-read precedent), not the
  registration-handshake class above. Reviewer challenge welcome, per the same posture Wave 6a
  extended to `cfg_raw`/`cfg_db`.
- The 5 mutations (`osd_create`/`osd_destroy`/`osd_in`/`osd_out`/`osd_scrub`) all stay
  REVIEWED_TRUSTED — each returns only an opaque UPID or null, no content channel at all (same
  reasoning as every prior mutation on this plane).

**CAPTURE-or-declare + the nested-tree extension:** `osd_destroy`/`osd_in`/`osd_out` each
best-effort read the CRUSH tree (`pve_ceph_osd_tree`, ADVERSARIAL) and look up the target osdid's
leaf entry — through `taint.capture_adversarial_current`, exactly like Wave 6b's mon/mgr/mds
factories, so the SAME taint-marking/ledger-provenance-stamping applies. The tree is a NESTED
structure (root -> children -> ... -> leaves), not a flat list, so the helper's default flat-list
`key`-equality lookup doesn't fit — `capture_adversarial_current` was extended (compatibly; every
Wave 6b caller is byte-for-byte unchanged) with an optional `finder=` callable; `_find_osd_in_tree`
below is passed as that `finder`. A successful read with no matching leaf degrades to
`current={}` (honest — e.g. the OSD may already be gone), not a failure; only a raised exception
on the read itself sets `complete=False`. `osd_create` gets NO capture — it creates a BRAND-NEW
OSD, nothing existing to snapshot (mirrors `plan_apt_update_refresh`'s own "no capture" posture).
`osd_scrub` also gets no capture — scrubbing isn't a durable state to snapshot (mirrors
`plan_ceph_service_start`'s own "nothing to capture" posture).

**cmd-safety citation matrix, extended:**

- `osd_destroy` — YES: `action=destroy, service=osd, id=str(osdid)` (osd is in the cmd-safety
  enum `{osd, mon, mds}`; `service_id` is typed string on that endpoint, so `osdid` is stringified
  for the call).
- `osd_in`/`osd_out` — **NO for BOTH.** cmd-safety's `action` enum is `{stop, destroy}` — neither
  'in' nor 'out' is either one: 'in'/'out' toggle CRUSH acting-set membership without stopping the
  OSD daemon or destroying anything. Both plans state this plainly rather than guessing or
  fabricating coverage (mirrors `mgr_destroy`'s own honest "no check exists" posture from Wave 6b,
  applied here to an action-enum mismatch instead of a service-enum one).
- `osd_create`/`osd_scrub` — NO. cmd-safety only covers `stop`/`destroy` actions; create/scrub
  have no upstream heuristic to cite (same reasoning as `mon_create`/`init`/`service_start` in
  Wave 6b).

**`osd_create`'s device-path validation is a deliberate, stricter-than-schema choice, Ceph-scoped
(Wave 6c review Finding 1, MAJOR, 2026-07-16 fix)** (see `backends.ceph_osd_create`'s docstring):
`dev`/`db_dev`/`wal_dev` are validated with `_check_ceph_osd_dev` — a Ceph-scoped WIDENING of the
shared `_check_disk` block-device-path validator PVE's node-disks plane uses, NOT a loosening of
`_check_disk` itself (`node_disk_wipe`/`node_disk_initgpt` keep relying on its stricter shape).
THIS schema declares no format/pattern for any of the three params, but a stricter-than-schema
tightening for the single highest-risk mutation on this whole plane (a malformed device string
here formats real hardware) is still worth doing — the first-shipped version simply reused
`_check_disk` verbatim and was too strict for its own highest-risk mutation: its
`[a-zA-Z0-9/_-]` charset rejected real-world, PVE-documented, commonly-recommended stable device
paths (e.g. `/dev/disk/by-id/nvme-eui.<hex>`, `/dev/disk/by-path/pci-<bus>:<dev>.<fn>-...`) that
are specifically relevant here (`osds-per-device`'s own description: "Only useful for fast NVMe
devices") and that operators reach for on THIS plane precisely to avoid `/dev/sdX` renumbering.
`_check_ceph_osd_dev` widens the charset to admit `.`, `:`, `+`, `=` (still a conservative
WHITELIST — whitespace/backslashes/shell metacharacters stay excluded by construction) while
keeping the `/dev/` prefix requirement and the `..`-traversal check. `crush_device_class` stays
unvalidated (free-form label, no schema pattern — mirrors `mon_address`'s own "no regex given,
don't invent one" posture). `db_dev_size` REQUIRES `db_dev`;
`wal_dev_size` REQUIRES `wal_dev` (both schema `"requires"`, enforced client-side exactly like
Wave 6b's `cluster_network` requires `network`). `osds-per-device`'s "mutually exclusive with
db_dev/wal_dev" is PROSE in the schema's own param description, not a formal requires/conflicts
field — enforced here anyway (fail fast locally rather than a guaranteed upstream rejection),
flagged explicitly since it's a step beyond the literal schema constraints.

**UNDO honesty (unchanged):** no rollback primitive on this plane. `osd_destroy` reverts via a
fresh `osd_create` — a NEW OSD with a DIFFERENT id and no data continuity, not a byte-for-byte
restore. `osd_create` itself does not return the new OSD's id synchronously (only a worker-task
UPID) — the id is only discoverable afterward via `pve_ceph_osd_tree`.

**Risk:** `osd_create`/`osd_destroy` = RISK_HIGH (consumes/formats a device; destroys an OSD —
data-durability risk). `osd_in`/`osd_out` = RISK_MEDIUM (both trigger data rebalance/recovery,
just in opposite directions). `osd_scrub` = RISK_LOW (no logical state change; a deep scrub is
I/O-heavy while it runs, but that is a performance concern, not a state-change one).

---

**Wave 6d — pools + CephFS (2026-07-16, CLOSES Wave 6).** Extends the module above; nothing in
Wave 6a/6b/6c changes. New: `pve_ceph_pool_list`, `pve_ceph_pool_status`, `pve_ceph_pool_create`,
`pve_ceph_pool_set`, `pve_ceph_pool_destroy`, `pve_ceph_fs_list`, `pve_ceph_fs_create`,
`pve_ceph_fs_destroy`. The per-pool `GET /pool/{name}` and the per-item directory-index GETs are
pure child-link stubs (schema: "Pool index."/"Directory index.") — NOT built, per the campaign
brief's own "5 directory stubs" disposition list; the real per-pool read is
`GET .../pool/{name}/status`.

**Schema divergences worth flagging (build-time findings, not defects):**

- **Wire param-name inconsistency between pool and fs, same wave, same upstream author (PVE,
  not Proximo) — verified against the raw schema JSON, not assumed:** pool create/destroy use
  UNDERSCORE param names (`add_storages`, `remove_ecprofile`, `remove_storages`); fs
  create/destroy use HYPHENATED param names (`add-storage`, `remove-pools`, `remove-storages`).
  `backends.py`'s wire-body dict keys match each endpoint's OWN literal wire name exactly —
  Python-side kwargs stay underscore-named throughout for both, per this codebase's own
  convention; only the WIRE body differs.
- **`crush_rule` is two different types depending on direction — but ONLY for `pool_list`, not
  `pool_status` (corrected, Wave 6d review Finding 2, 2026-07-17: the original claim blanketed
  both under "the READ side," which is wrong for one of the two — verified against the raw
  schema JSON, not assumed).** `pve_ceph_pool_list`'s `crush_rule` really is the numeric CRUSH
  rule id (`crush_rule: integer`, title "Crush Rule") plus a separate human-readable
  `crush_rule_name: string`. `pve_ceph_pool_status`'s `crush_rule` is ALREADY a string
  (`crush_rule: string`, title "Crush Rule Name" — the identical title `pool_create`/`pool_set`
  use for their own write-side param) and carries no separate `crush_rule_name` field at all — it
  matches the write side exactly, no round-trip hazard exists for `pool_status`. Only
  `pve_ceph_pool_list`'s read value diverges from what `pve_ceph_pool_create`/`pve_ceph_pool_set`
  accept; docstrings say so explicitly, scoped to `pool_list` alone, so a caller doesn't try to
  round-trip THAT read value straight back into a write call.
- **`pg_num_min` is upper-bounded ONLY** (schema: `maximum: 32768`, no `minimum` key at all — the
  live typetext is literally `<integer> (-N - 32768)`), unlike `pg_num`/`min_size`/`size` which
  are bounded both ways. `_check_ceph_pool_upper_bound` (backends.py) validates accordingly — a
  new one-sided validator, not a reuse of `_check_ceph_init_bound` (which requires both a lo and
  a hi).
- **`erasure-coding` is PVE's own propertyString wire format**
  (`k=<int>,m=<int>[,device-class=<class>][,failure-domain=<domain>][,profile=<profile>]`) —
  Proximo does NOT invent a nested-object param for this one field on this one endpoint; the
  caller passes the SAME string PVE's own tooling would send, and
  `_check_ceph_pool_erasure_coding` (backends.py) validates it by PARSING (required k>=2/m>=1,
  closed field set, no duplicates) before passing the original string through unchanged.
  `failure-domain`'s own schema default ('host') and `device-class`/`profile`'s optionality are
  left to PVE server-side — Proximo does not second-guess them.
- **`pve_ceph_fs_create`'s `name` schema-defaults to the FIXED LITERAL `'cephfs'`** — a
  DIFFERENT default-resolution shape than Wave 6b's mon/mgr/mds `default: nodename` (there, the
  id resolves to the CALLER'S node name; here it resolves to a hardcoded string). Both are
  client-side-resolved for the identical mechanical reason (the id/name is ALSO the URL path
  segment and cannot itself be "omitted" from an HTTP request) — `_check_ceph_fs_name_or_default`
  (backends.py) is the Wave 6d analog of `_ceph_daemon_target`.

**Taint — REVERSED post-ship (Wave 6d review Finding 1, 2026-07-17; the ruling below is the
CORRECTED final state, superseding what shipped originally — see `.scratch/sdd/wave-6d-report.md`
"Fixes applied (post-review)" for the strike-and-correct on the original claim):**

- **`pve_ceph_pool_list`/`pve_ceph_pool_status`/`pve_ceph_fs_list` are ADVERSARIAL**
  (`taint.ADVERSARIAL_TOOLS`) — this chunk originally shipped them REVIEWED_TRUSTED, arguing
  every field was either operator-chosen config or a cluster-computed summary, the same class
  that keeps `pve_ceph_status` REVIEWED_TRUSTED. That argument didn't survive challenge on three
  grounds:
  1. **The closest, most damaging precedent in this same codebase was never engaged.**
     `taint.py`'s own `ADVERSARIAL_TOOLS` already classifies `pve_list_guests`/
     `pve_cluster_resources`/`pve_snapshot_list` ADVERSARIAL with the stated reason
     "operator-set, but free-text fields a guest/attacker can shape." `pool_name` (POST
     `.../pool`) and CephFS `name` (POST `.../fs/{name}`) both validate against the pattern
     `^[^:/\\s]+$` ONLY — no length cap at all (unlike Wave 6b's mds `name`, which carries
     `maxLength: 200`) — and are creatable by ANY cephx-capable client holding mon caps, not only
     through Proximo's own `pool_create`/`fs_create`; Ceph itself also auto-creates pools with no
     operator action at all (`device_health_metrics`, `.mgr`). That is structurally identical to
     the VM/CT/snapshot-name precedent, which this chunk's original argument never mentioned.
  2. **`application_metadata` is a third channel the original operator-chosen/cluster-computed
     dichotomy never covered.** It's populated by `ceph osd pool application set <pool> <app>
     <key> <value>` — a raw Ceph admin command entirely OUTSIDE `pve_ceph_pool_create`/
     `pve_ceph_pool_set` (neither exposes an application-metadata key/value parameter at all).
     Proximo mediates neither the write nor any cluster-computed derivation of it — it is neither
     "operator-chosen through this surface" nor "cluster-computed," the two buckets the original
     argument relied on exhaustively.
  3. **Two of the original argument's own supporting schema citations were false, verified by
     parsing the raw schema JSON directly, not visual read.** The original text claimed
     `application_metadata`/`autoscale_status` "ARE schema-open (`additionalProperties: 1`, ...
     same as metadata's per-instance entries)" and that `pve_ceph_fs_list` "is narrower still — no
     `additionalProperties: 1` sub-object anywhere." Both are backwards:
     `pool_list.returns.items`, `pool_list.returns.items.properties.application_metadata`/
     `.autoscale_status`, and `pool_status.returns` (top level) carry NO `additionalProperties`
     key at all; the ONLY `"additionalProperties": 1` anywhere in the schema's pool/fs section
     sits at line 904, on `pve_ceph_fs_list`'s OWN per-entry object
     (`GET /nodes/{node}/ceph/fs` returns.items) — i.e. **fs_list's own entry is the schema-open
     one**, the exact inverse of what shipped. Given `pve_ceph_metadata`'s own precedent (this
     module's Wave 6a section: `additionalProperties: 1` on a per-instance entry is material
     evidence toward ADVERSARIAL, "an explicitly OPEN shape, not a closed structured record") —
     the identical marker `fs_list` carries and was claimed not to.

  Corrected verdict for all three: bias conservative per `taint.py`'s own stated policy ("classify
  as adversarial when unsure"). `pool_name`/`name` are attacker-shapeable free-text fields set
  through a channel Proximo doesn't fully control (a rogue cephx client, or Ceph's own
  auto-creation), landing them the same way `pve_list_guests`/`pve_snapshot_list` already landed;
  `application_metadata` is externally-authored content over an operator-configured channel (the
  `pbs_s3_list_buckets`/`pbs_remote_scan` shape, not the `pve_ceph_status` shape); and `fs_list`'s
  own schema-open marker cuts the same direction `pve_ceph_metadata` already established.
- The 5 mutations (`pool_create`/`pool_set`/`pool_destroy`/`fs_create`/`fs_destroy`) stay
  REVIEWED_TRUSTED — each returns only an opaque UPID, no content channel at all (same reasoning
  as every prior mutation on this plane). Unaffected by the reversal above.

**CAPTURE-or-declare — through `taint.capture_adversarial_current` (corrected, Wave 6d review
Finding 1 fix):** since `pve_ceph_pool_list`/`pve_ceph_pool_status`/`pve_ceph_fs_list` are
ADVERSARIAL by the ruling above, all 5 mutations' CAPTURE reads (`pool_create`/`pool_destroy`
read `ceph_pool_list()`; `fs_create`/`fs_destroy` read `ceph_fs_list()`; `pool_set` reads
`ceph_pool_status(name)`) were rewired from a plain try/except onto
`taint.capture_adversarial_current` — the SAME fix Wave 6b's own review applied to the mon/mgr/mds
create/destroy factories, reopened here for a different plane (exactly the gap the Wave 6d
review's Finding 1 called out in advance: "the CAPTURE wiring in five plan factories needs to
change ... exactly the compound the review brief called out"). `pool_create`/`pool_destroy` pass
`key="pool_name"` (the default lookup's `key=` param, since the pool entry's match field isn't
named `name`); `fs_create`/`fs_destroy` use the default `key="name"` unchanged. `pool_set` is the
first caller whose CAPTURE source (`ceph_pool_status`) returns a single dict, not a list — its
`finder` returns that dict verbatim (ignoring `match_id`) instead of searching a collection,
closer to what "revert by reapplying the captured current values" actually needs (the full
current settings object, not a list-entry fragment), the same reasoning `plan_ceph_flag_set`
already applies by reading `ceph_flag_get` directly instead of scanning `ceph_flags_list` (that
source stays REVIEWED_TRUSTED, so it keeps its own plain try/except — unaffected by this fix). A
successful read with no match (pool_create/pool_destroy/fs_create/fs_destroy) degrades to
`current={}` (expected for a create; honest-but-gone for a destroy), NOT a failure — only a
raised exception on the read itself sets `complete=False`. All 5 factories now take a required
keyword-only `audit_dir: str` param (threaded from `tools/pve_ceph.py`'s wrappers via
`os.path.dirname(audit.path)`, the same computation `_audited()` already uses), mirroring the
Wave 6b/6c mon/mgr/mds/osd factories' own shape exactly.

**cmd-safety does NOT cover this plane at all:** cmd-safety's `service` enum is
`{osd, mon, mds}` — it covers NONE of pool or filesystem. Every plan below states this plainly
(the Wave 6b `mgr_destroy` honesty precedent, applied here to an entire plane instead of one
service type) rather than inventing a check or silently omitting the point.

**`pool_destroy`'s `force` is NEVER defaulted on** — forwarded to the wire ONLY when the caller
explicitly sets it (schema: "destroys pool even if in use"), mirroring `osd_destroy`'s `cleanup`
precedent exactly.

**UNDO honesty:** nothing on this plane is PVE-snapshottable — no rollback primitive exists (same
class as every other Ceph mutation). `pool_destroy`/`fs_destroy` are UNRECOVERABLE via the API:
recreating a pool/filesystem with the SAME name does NOT restore the destroyed data (a fresh
empty pool/fs, not a byte-for-byte restore) — the same honesty `osd_destroy` already carries for
OSD data. `pool_set` reverts by re-applying the captured prior settings with this same tool
(mirrors `flag_set`).

**Risk:** `pool_create`/`fs_create` = RISK_MEDIUM (new capacity/service, no existing data at
stake). `pool_set` = RISK_MEDIUM (a `pg_num` change triggers cluster rebalance — docstring says
so plainly). `pool_destroy`/`fs_destroy` = RISK_HIGH (irreversibly destroys the pool/filesystem
and, depending on flags, the underlying data too).
"""

from __future__ import annotations

from typing import Any

from .backends import (
    _CEPH_CMD_SAFETY_SERVICES,
    ProximoError,
    _check_ceph_bounded_int,
    _check_ceph_daemon_id,
    _check_ceph_flag,
    _check_ceph_fs_name_or_default,
    _check_ceph_init_bound,
    _check_ceph_init_network,
    _check_ceph_osd_dev,
    _check_ceph_osd_int_min,
    _check_ceph_osd_min,
    _check_ceph_osdid,
    _check_ceph_pool_application,
    _check_ceph_pool_autoscale_mode,
    _check_ceph_pool_erasure_coding,
    _check_ceph_pool_or_fs_name,
    _check_ceph_pool_ratio,
    _check_ceph_pool_target_size,
    _check_ceph_pool_upper_bound,
    _check_ceph_service,
    _check_node,
)
from .planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM, Plan
from .taint import capture_adversarial_current


def plan_ceph_flags_set(api: Any, changes: dict) -> Plan:
    """Plan for pve_ceph_flags_set — bulk set/unset multiple Ceph flags at once.

    `changes` keys are already WIRE flag names (translated by tools/pve_ceph.py's
    `_ceph_flags_changes` from the tool's individual python-named params), values are the
    booleans to apply. CAPTURE-or-declare: reads current flag values via GET /cluster/ceph/flags
    (best-effort) — a successful read simply degrades to whatever subset of `changes` it could
    match (an absent/mismatched name just isn't in `current`); only a raised exception on the
    read itself sets complete=False.

    Wave 6a review Finding 1: every flag param defaults to None (tri-state), so a zero-kwarg
    call produces changes == {}. Nothing downstream would otherwise reject that — PVE still
    runs a real worker task for a PUT that changes nothing. Refuse it here, before _plan()
    records anything, mirroring the "at least one field" guard idiom every sibling bulk-update
    tool already enforces (sdn_zone_update/sdn_vnet_update/sdn_subnet_update in network.py,
    ha_rule_update in cluster_ops.py, pool_update(delete=True) in tasks_pools.py).
    """
    if not changes:
        raise ProximoError("pve_ceph_flags_set requires at least one flag to set or unset")
    for k in changes:
        _check_ceph_flag(k)
    current: dict = {}
    complete = True
    note_capture = ""
    try:
        result = api.ceph_flags_list() or []
        current = {f.get("name"): f.get("value") for f in result if f.get("name") in changes}
    except Exception:
        complete = False
        note_capture = " Could not capture current flag state — no guided revert available."
    pause_note = (
        " WARNING: setting 'pause' halts ALL client I/O to the cluster."
        if changes.get("pause") is True else ""
    )
    return Plan(
        action="pve_ceph_flags_set",
        target="cluster/ceph/flags",
        change=f"set/unset Ceph flags in bulk: {changes}",
        current=current,
        blast_radius=[
            "cluster-wide Ceph flag state — flag semantics vary per flag ('pause' halts ALL "
            "client I/O; 'noout'/'noscrub'/etc. are routine maintenance toggles)." + pause_note
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["changes cluster-wide Ceph behavior flags — semantics vary per flag"],
        complete=complete,
        note=(
            "Revert by re-applying the captured current values with pve_ceph_flags_set."
            + note_capture
        ),
    )


def plan_ceph_flag_set(api: Any, flag: str, value: bool) -> Plan:
    """Plan for pve_ceph_flag_set — set/clear a single Ceph flag (synchronous, unlike the bulk
    PUT above).

    CAPTURE-or-declare: reads the flag's current value via GET /cluster/ceph/flags/{flag}
    (best-effort); only a raised exception on the read itself sets complete=False.
    """
    _check_ceph_flag(flag)
    current: dict = {}
    complete = True
    note_capture = ""
    try:
        current = {"value": api.ceph_flag_get(flag)}
    except Exception:
        complete = False
        note_capture = " Could not capture current flag state — no guided revert available."
    pause_note = " WARNING: 'pause' halts ALL client I/O to the cluster." if flag == "pause" else ""
    return Plan(
        action="pve_ceph_flag_set",
        target=f"cluster/ceph/flags/{flag}",
        change=f"set Ceph flag {flag!r} to {value}",
        current=current,
        blast_radius=[f"cluster-wide Ceph flag {flag!r} -> {value}." + pause_note],
        risk=RISK_MEDIUM,
        risk_reasons=[f"changes cluster-wide Ceph flag {flag!r} — semantics vary per flag"],
        complete=complete,
        note=(
            f"Revert by calling pve_ceph_flag_set(flag={flag!r}, value=<captured current>)."
            + note_capture
        ),
    )


# === Wave 6b — services lifecycle ===========================================================


def _cmd_safety_note(api: Any, action: str, service: str, service_id: str, node: str | None) -> str:
    """Fail-open ADVISORY citation of GET /nodes/{node}/ceph/cmd-safety, for a destroy/stop
    plan's blast_radius. NEVER a gate: an unreachable/erroring check degrades to an honest
    "cmd-safety unavailable" line, never blocks the plan from rendering, never fabricates
    safe=true (mirrors this module's own cmd-safety honesty line from Wave 6a)."""
    try:
        result = api.ceph_cmd_safety(action, service, service_id, node) or {}
        safe = result.get("safe")
        status = result.get("status")
        if safe is None:
            return "cmd-safety advisory: Ceph returned no safety verdict for this check."
        detail = f" ({status})" if status else ""
        return (
            f"cmd-safety advisory: Ceph reports safe={safe}{detail} for {action} {service} "
            f"{service_id!r} — ADVISORY ONLY, verify yourself before proceeding."
        )
    except Exception as e:
        return f"cmd-safety unavailable: {type(e).__name__}: {e}"


def _parse_ceph_service(service: str) -> tuple[str, str | None]:
    """Split a validated ceph service string ('mon.pve1', 'ceph.target', 'osd.3', 'mgr', ...)
    into (kind, id_or_None) — used to decide whether a cmd-safety citation is even possible for
    pve_ceph_service_stop (it needs a specific mon/mds/osd instance id, not just a bare kind)."""
    if "." in service:
        kind, _, sid = service.partition(".")
        return kind, sid
    return service, None


def plan_ceph_mon_create(
    api: Any, node: str | None = None, monid: str | None = None, mon_address: str | None = None,
    *, audit_dir: str,
) -> Plan:
    """Plan for pve_ceph_mon_create — create a Ceph Monitor (auto-creates a Manager too if this
    is the FIRST monitor in the cluster, per schema truth).

    `monid` defaults to the nodename when omitted via the SHARED `api._ceph_daemon_target()`
    helper (the id is a REQUIRED URL path segment even though the schema lists it "optional,
    default: nodename"; see this module's docstring "Build nuance" section) — the plan factory no
    longer duplicates that resolution inline (Wave 6b adversarial review Nit).

    CAPTURE-or-declare: reads current monitors via GET /nodes/{node}/ceph/mon (best-effort,
    through `taint.capture_adversarial_current` — the same taint-marking/provenance-stamping
    `_audited()` applies to a live call of the ADVERSARIAL-classified pve_ceph_mon_list, since
    this read bypasses that tool/wiring entirely) and looks up monid's existing entry; a
    successful read with no match degrades to current={} (the monitor doesn't exist yet —
    expected for a create), not a failure — only a raised exception on the read itself sets
    complete=False. `audit_dir` is the audit ledger's directory (see server.py's `_audited`),
    required so the taint marker can be written when taint tracking is enabled.
    """
    n, mid = api._ceph_daemon_target(node, monid, "monid")
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_mon_list", lambda: api.ceph_mon_list(node), mid
    )
    note_capture = (
        "" if complete else " Could not capture current monitor list — no guided revert available."
    )
    change = f"create Ceph monitor {mid!r} on node {n}"
    if mon_address is not None:
        change += f" (mon-address={mon_address!r})"
    return Plan(
        action="pve_ceph_mon_create",
        target=f"{n}/ceph/mon/{mid}",
        change=change,
        current=current,
        blast_radius=[
            f"adds monitor {mid!r} to the cluster monmap — extends quorum membership. Auto-"
            "creates a Manager too if this is the FIRST monitor in the cluster (schema truth)."
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["adds a new Ceph monitor daemon — extends cluster quorum membership"],
        complete=complete,
        note=(
            f"No rollback primitive on this plane — revert by calling "
            f"pve_ceph_mon_destroy(monid={mid!r})." + note_capture
        ),
    )


def plan_ceph_mon_destroy(api: Any, monid: str, node: str | None = None, *, audit_dir: str) -> Plan:
    """Plan for pve_ceph_mon_destroy — destroy a Ceph Monitor. PVE refuses to remove the LAST
    monitor of the cluster (schema truth); does not destroy any Manager on the same node.

    CAPTURE-or-declare: reads current monitors via GET /nodes/{node}/ceph/mon (best-effort,
    through `taint.capture_adversarial_current` — see plan_ceph_mon_create's docstring for the
    taint-marking/provenance-stamping rationale) and looks up monid's existing entry; a
    successful read with no match degrades to current={} (honest — the monitor may already be
    gone), not a failure. cmd-safety citation: fail-open ADVISORY evidence (action=destroy,
    service=mon) via _cmd_safety_note — never a gate. `audit_dir` is the audit ledger's directory,
    required so the taint marker can be written when taint tracking is enabled.
    """
    _check_node(node)
    mid = _check_ceph_daemon_id(monid, "monid")
    n = node or api.config.node
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_mon_list", lambda: api.ceph_mon_list(node), mid
    )
    note_capture = (
        "" if complete else " Could not capture current monitor list — no guided revert available."
    )
    return Plan(
        action="pve_ceph_mon_destroy",
        target=f"{n}/ceph/mon/{mid}",
        change=f"destroy Ceph monitor {mid!r} on node {n}",
        current=current,
        blast_radius=[
            f"removes monitor {mid!r} from the cluster monmap — reduces quorum membership. PVE "
            "refuses to remove the LAST monitor of the cluster; does not destroy any Manager on "
            "the same node (schema truth).",
            _cmd_safety_note(api, "destroy", "mon", mid, node),
        ],
        risk=RISK_HIGH,
        risk_reasons=["destroys a Ceph monitor daemon — quorum-loss risk if too few monitors remain"],
        complete=complete,
        note=(
            "No rollback primitive on this plane — recreate with pve_ceph_mon_create (a NEW "
            "monitor, not a byte-for-byte restore of this one's internal state)." + note_capture
        ),
    )


def plan_ceph_mgr_create(
    api: Any, node: str | None = None, mgr_id: str | None = None, *, audit_dir: str
) -> Plan:
    """Plan for pve_ceph_mgr_create — create a Ceph Manager.

    `mgr_id` defaults to the nodename when omitted via the SHARED `api._ceph_daemon_target()`
    helper (same "Build nuance" as mon_create above; no longer duplicated inline — Wave 6b
    adversarial review Nit). CAPTURE-or-declare: reads current managers via GET
    /nodes/{node}/ceph/mgr (best-effort, through `taint.capture_adversarial_current` — see
    plan_ceph_mon_create's docstring for the taint-marking/provenance-stamping rationale); a
    successful read with no match degrades to current={} (expected for a create), not a failure.
    `audit_dir` is the audit ledger's directory, required so the taint marker can be written when
    taint tracking is enabled.
    """
    n, mid = api._ceph_daemon_target(node, mgr_id, "mgr id")
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_mgr_list", lambda: api.ceph_mgr_list(node), mid
    )
    note_capture = (
        "" if complete else " Could not capture current manager list — no guided revert available."
    )
    return Plan(
        action="pve_ceph_mgr_create",
        target=f"{n}/ceph/mgr/{mid}",
        change=f"create Ceph manager {mid!r} on node {n}",
        current=current,
        blast_radius=[
            f"adds manager {mid!r} on node {n} — provides cluster monitoring/orchestration "
            "modules (dashboard, balancer, etc.)."
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["adds a new Ceph manager daemon"],
        complete=complete,
        note=(
            f"No rollback primitive on this plane — revert by calling "
            f"pve_ceph_mgr_destroy(mgr_id={mid!r})." + note_capture
        ),
    )


def plan_ceph_mgr_destroy(api: Any, mgr_id: str, node: str | None = None, *, audit_dir: str) -> Plan:
    """Plan for pve_ceph_mgr_destroy — destroy a Ceph Manager.

    CAPTURE-or-declare: reads current managers via GET /nodes/{node}/ceph/mgr (best-effort,
    through `taint.capture_adversarial_current` — see plan_ceph_mon_create's docstring for the
    taint-marking/provenance-stamping rationale). NO cmd-safety citation: cmd-safety's service
    enum is {osd, mon, mds} — mgr was never in it, so the plan states plainly that no upstream
    heuristic safety check exists, rather than inventing one or silently omitting the point.
    `audit_dir` is the audit ledger's directory, required so the taint marker can be written when
    taint tracking is enabled.
    """
    _check_node(node)
    mid = _check_ceph_daemon_id(mgr_id, "mgr id")
    n = node or api.config.node
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_mgr_list", lambda: api.ceph_mgr_list(node), mid
    )
    note_capture = (
        "" if complete else " Could not capture current manager list — no guided revert available."
    )
    return Plan(
        action="pve_ceph_mgr_destroy",
        target=f"{n}/ceph/mgr/{mid}",
        change=f"destroy Ceph manager {mid!r} on node {n}",
        current=current,
        blast_radius=[
            f"removes manager {mid!r} — if it was the ACTIVE manager, a standby (if any) takes "
            "over; with none, cluster monitoring/orchestration modules go dark until a manager "
            "is recreated.",
            "no upstream cmd-safety check exists for mgr (cmd-safety's service enum is "
            "{osd, mon, mds} only).",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            "destroys a Ceph manager daemon — no upstream heuristic safety check available for "
            "this service type"
        ],
        complete=complete,
        note=(
            "No rollback primitive on this plane — recreate with pve_ceph_mgr_create (a NEW "
            "manager, not a byte-for-byte restore of this one's internal state)." + note_capture
        ),
    )


def plan_ceph_mds_create(
    api: Any, node: str | None = None, name: str | None = None, hotstandby: bool | None = None,
    *, audit_dir: str,
) -> Plan:
    """Plan for pve_ceph_mds_create — create a Ceph Metadata Server (MDS).

    `name` defaults to the nodename when omitted via the SHARED `api._ceph_daemon_target()`
    helper (same "Build nuance" as mon_create above; no longer duplicated inline — Wave 6b
    adversarial review Nit). `hotstandby`=True has the daemon poll+replay an active MDS's log for
    faster failover, at the cost of more idle resources (schema default False). CAPTURE-or-
    declare: reads current MDSes via GET /nodes/{node}/ceph/mds (best-effort, through
    `taint.capture_adversarial_current` — see plan_ceph_mon_create's docstring for the
    taint-marking/provenance-stamping rationale); a successful read with no match degrades to
    current={} (expected for a create), not a failure. `audit_dir` is the audit ledger's
    directory, required so the taint marker can be written when taint tracking is enabled.
    """
    n, nm = api._ceph_daemon_target(node, name, "mds name")
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_mds_list", lambda: api.ceph_mds_list(node), nm
    )
    note_capture = (
        "" if complete else " Could not capture current MDS list — no guided revert available."
    )
    change = f"create Ceph MDS {nm!r} on node {n}"
    if hotstandby:
        change += " (hotstandby=True)"
    return Plan(
        action="pve_ceph_mds_create",
        target=f"{n}/ceph/mds/{nm}",
        change=change,
        current=current,
        blast_radius=[
            f"adds MDS {nm!r} on node {n} — serves (or stands by for) CephFS metadata; needed "
            "for any CephFS filesystem to be usable."
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["adds a new Ceph metadata-server daemon"],
        complete=complete,
        note=(
            f"No rollback primitive on this plane — revert by calling "
            f"pve_ceph_mds_destroy(name={nm!r})." + note_capture
        ),
    )


def plan_ceph_mds_destroy(api: Any, name: str, node: str | None = None, *, audit_dir: str) -> Plan:
    """Plan for pve_ceph_mds_destroy — destroy a Ceph Metadata Server.

    CAPTURE-or-declare: reads current MDSes via GET /nodes/{node}/ceph/mds (best-effort, through
    `taint.capture_adversarial_current` — see plan_ceph_mon_create's docstring for the
    taint-marking/provenance-stamping rationale). cmd-safety citation: fail-open ADVISORY
    evidence (action=destroy, service=mds) via _cmd_safety_note — never a gate. `audit_dir` is the
    audit ledger's directory, required so the taint marker can be written when taint tracking is
    enabled.
    """
    _check_node(node)
    nm = _check_ceph_daemon_id(name, "mds name")
    n = node or api.config.node
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_mds_list", lambda: api.ceph_mds_list(node), nm
    )
    note_capture = (
        "" if complete else " Could not capture current MDS list — no guided revert available."
    )
    return Plan(
        action="pve_ceph_mds_destroy",
        target=f"{n}/ceph/mds/{nm}",
        change=f"destroy Ceph MDS {nm!r} on node {n}",
        current=current,
        blast_radius=[
            f"removes MDS {nm!r} — any CephFS rank it was actively serving fails over to a "
            "standby if one exists, else that filesystem's metadata becomes unavailable.",
            _cmd_safety_note(api, "destroy", "mds", nm, node),
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            "destroys a Ceph metadata-server daemon — CephFS availability risk if no standby exists"
        ],
        complete=complete,
        note=(
            "No rollback primitive on this plane — recreate with pve_ceph_mds_create (a NEW "
            "daemon, not a byte-for-byte restore of this one's internal state)." + note_capture
        ),
    )


def plan_ceph_init(
    api: Any,
    node: str | None = None,
    cluster_network: str | None = None,
    disable_cephx: bool | None = None,
    min_size: int | None = None,
    network: str | None = None,
    pg_bits: int | None = None,
    size: int | None = None,
) -> Plan:
    """Plan for pve_ceph_init — create the initial Ceph default configuration + symlinks.

    IDEMPOTENT on re-call (schema truth): if a [global] section already exists in ceph.conf, the
    existing fsid/auth/pool defaults are preserved and most parameters are silently ignored. No
    CAPTURE: there is no meaningful "current Ceph init state" to snapshot for a guided revert
    (mirrors plan_apt_update_refresh's own "no capture" posture, apt.py) — idempotent re-call is
    itself the safety net.
    """
    _check_node(node)
    n = node or api.config.node
    if cluster_network is not None and network is None:
        raise ProximoError(
            "pve_ceph_init: cluster_network requires network to also be set (schema: "
            "'requires': 'network')"
        )
    min_size = _check_ceph_init_bound(min_size, "min_size", 1, 7)
    size = _check_ceph_init_bound(size, "size", 1, 7)
    pg_bits = _check_ceph_init_bound(pg_bits, "pg_bits", 6, 14)
    cluster_network = _check_ceph_init_network(cluster_network, "cluster-network")
    network = _check_ceph_init_network(network, "network")
    options = {
        k: v for k, v in {
            "cluster-network": cluster_network, "disable_cephx": disable_cephx,
            "min_size": min_size, "network": network, "pg_bits": pg_bits, "size": size,
        }.items() if v is not None
    }
    return Plan(
        action="pve_ceph_init",
        target=f"{n}/ceph/init",
        change=(
            f"initialize Ceph default configuration on node {n}"
            + (f" with {options}" if options else "")
        ),
        current={},
        blast_radius=[
            "creates the initial ceph.conf [global] section + symlinks on this node. IDEMPOTENT: "
            "if a [global] section already exists, the existing fsid/auth/pool defaults are "
            "preserved and most parameters here are silently ignored (schema truth) — this is "
            "NOT guaranteed to apply the options above on a re-call."
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "one-time cluster-bootstrap step — on the FIRST real call it establishes the fsid/"
            "auth/pool defaults for the whole cluster; harmless (silently ignored) to re-run after"
        ],
        complete=True,
        note=(
            "No CAPTURE possible — no 'current Ceph init state' read exists; idempotent re-call "
            "is itself the safety net. No rollback primitive on this plane."
        ),
    )


def plan_ceph_service_start(api: Any, node: str | None = None, service: str | None = None) -> Plan:
    """Plan for pve_ceph_service_start — start Ceph service(s) (systemd unit(s) matching
    `service`, default 'ceph.target'). No CAPTURE: no durable "is this unit currently running"
    read exists on this plane to snapshot from.
    """
    _check_node(node)
    n = node or api.config.node
    svc = _check_ceph_service(service) if service is not None else "ceph.target"
    return Plan(
        action="pve_ceph_service_start",
        target=f"{n}/ceph/start:{svc}",
        change=f"start Ceph service {svc!r} on node {n}",
        current={},
        blast_radius=[f"starts the {svc!r} systemd unit(s) on node {n}."],
        risk=RISK_MEDIUM,
        risk_reasons=["starts Ceph storage daemon(s) on this node"],
        complete=True,
        note=(
            "No rollback primitive on this plane — revert with pve_ceph_service_stop for the "
            "same service target."
        ),
    )


def plan_ceph_service_stop(api: Any, node: str | None = None, service: str | None = None) -> Plan:
    """Plan for pve_ceph_service_stop — stop Ceph service(s). RISK_HIGH: halts I/O for the
    targeted storage daemon(s). cmd-safety citation: fail-open ADVISORY evidence (action=stop)
    cited ONLY when `service` parses to a mon/mds/osd-shaped kind WITH a specific instance id
    (cmd-safety needs exactly that to evaluate) — a bare kind, 'ceph'/'ceph.target', or 'mgr' has
    no single instance for cmd-safety to check, and the plan states that honestly rather than
    guessing an id or fabricating coverage. No CAPTURE: no durable "is this unit currently
    running" read exists on this plane to snapshot from.
    """
    _check_node(node)
    n = node or api.config.node
    svc = _check_ceph_service(service) if service is not None else "ceph.target"
    kind, sid = _parse_ceph_service(svc)
    if kind in _CEPH_CMD_SAFETY_SERVICES and sid:
        safety_note = _cmd_safety_note(api, "stop", kind, sid, node)
    else:
        safety_note = (
            f"no cmd-safety check available for service {svc!r} — cmd-safety needs a specific "
            "mon/mds/osd instance id to evaluate; a bare kind, 'ceph'/'ceph.target', or 'mgr' "
            "has none."
        )
    return Plan(
        action="pve_ceph_service_stop",
        target=f"{n}/ceph/stop:{svc}",
        change=f"stop Ceph service {svc!r} on node {n}",
        current={},
        blast_radius=[
            f"halts the {svc!r} systemd unit(s) on node {n} — storage daemons stop serving I/O "
            "while stopped.",
            safety_note,
        ],
        risk=RISK_HIGH,
        risk_reasons=["stops Ceph storage daemon(s) — halts I/O they were serving"],
        complete=True,
        note=(
            "No rollback primitive on this plane — revert with pve_ceph_service_start for the "
            "same service target."
        ),
    )


def plan_ceph_service_restart(
    api: Any, node: str | None = None, service: str | None = None
) -> Plan:
    """Plan for pve_ceph_service_restart — restart Ceph service(s). No CAPTURE: no durable
    "is this unit currently running" read exists on this plane to snapshot from.
    """
    _check_node(node)
    n = node or api.config.node
    svc = _check_ceph_service(service) if service is not None else "ceph.target"
    return Plan(
        action="pve_ceph_service_restart",
        target=f"{n}/ceph/restart:{svc}",
        change=f"restart Ceph service {svc!r} on node {n}",
        current={},
        blast_radius=[
            f"restarts the {svc!r} systemd unit(s) on node {n} — brief I/O interruption while "
            "the daemon(s) cycle."
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["restarts Ceph storage daemon(s) — brief interruption while cycling"],
        complete=True,
        note="No rollback primitive on this plane — restart is not revertible; re-restart if needed.",
    )


# === Wave 6c — OSD ============================================================================


def _find_osd_in_tree(tree: Any, osdid: int) -> dict:
    """Walk GET /nodes/{node}/ceph/osd's nested CRUSH-bucket response (root -> children -> ...
    recursively) for the leaf whose 'id' equals `osdid` — an EQUALITY check, never a truthiness
    check, so osdid=0 (the first OSD ever created) is never mistaken for "missing" (the Wave 6b
    falsy-id lesson, applied to a numeric id here instead of a string one). Returns {} if `tree`
    is falsy/malformed or no matching leaf exists — NEVER raises (mirrors
    capture_adversarial_current's own "no match -> current={}, not a failure" contract). Passed
    as `taint.capture_adversarial_current`'s `finder=` kwarg — see that function's Wave 6c
    extension docstring for why a `finder` was needed at all: the flat-list `key`-equality
    default doesn't fit this nested shape."""
    if not isinstance(tree, dict):
        return {}
    root = tree.get("root")
    if not isinstance(root, dict):
        return {}
    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if node.get("id") == osdid:
            return node
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(children)
    return {}


def plan_ceph_osd_create(
    api: Any,
    dev: str,
    node: str | None = None,
    crush_device_class: str | None = None,
    db_dev: str | None = None,
    db_dev_size: float | None = None,
    wal_dev: str | None = None,
    wal_dev_size: float | None = None,
    encrypted: bool | None = None,
    osds_per_device: int | None = None,
) -> Plan:
    """Plan for pve_ceph_osd_create — create a new Ceph OSD, consuming+formatting `dev`.

    No CAPTURE: this creates a BRAND-NEW OSD — there is nothing existing to snapshot for a
    guided revert (mirrors plan_apt_update_refresh's own "no meaningful current state" posture,
    apt.py). Validates the schema's `requires` constraints client-side (db_dev_size requires
    db_dev; wal_dev_size requires wal_dev) plus the schema's PROSE-only "mutually exclusive with
    db_dev/wal_dev" note for osds_per_device (not a formal requires/conflicts field, enforced
    anyway to fail fast locally instead of a guaranteed upstream rejection — see this module's
    docstring "osd_create's device-path validation" section).
    """
    _check_node(node)
    n = node or api.config.node
    dev = _check_ceph_osd_dev(dev)
    if db_dev_size is not None and db_dev is None:
        raise ProximoError(
            "pve_ceph_osd_create: db_dev_size requires db_dev to also be set (schema: "
            "'requires': 'db_dev')"
        )
    if wal_dev_size is not None and wal_dev is None:
        raise ProximoError(
            "pve_ceph_osd_create: wal_dev_size requires wal_dev to also be set (schema: "
            "'requires': 'wal_dev')"
        )
    if osds_per_device is not None and (db_dev is not None or wal_dev is not None):
        raise ProximoError(
            "pve_ceph_osd_create: osds_per_device is mutually exclusive with db_dev/wal_dev "
            "(schema param description, not a formal requires/conflicts field)"
        )
    if db_dev is not None:
        db_dev = _check_ceph_osd_dev(db_dev)
    if wal_dev is not None:
        wal_dev = _check_ceph_osd_dev(wal_dev)
    db_dev_size = _check_ceph_osd_min(db_dev_size, "db_dev_size", 1)
    wal_dev_size = _check_ceph_osd_min(wal_dev_size, "wal_dev_size", 0.5)
    osds_per_device = _check_ceph_osd_int_min(osds_per_device, "osds-per-device", 1)
    extras = []
    if db_dev is not None:
        extras.append(
            f"db_dev={db_dev!r}"
            + (f" (db_dev_size={db_dev_size})" if db_dev_size is not None else "")
        )
    if wal_dev is not None:
        extras.append(
            f"wal_dev={wal_dev!r}"
            + (f" (wal_dev_size={wal_dev_size})" if wal_dev_size is not None else "")
        )
    if crush_device_class is not None:
        extras.append(f"crush_device_class={crush_device_class!r}")
    if encrypted:
        extras.append("encrypted=True")
    if osds_per_device is not None:
        extras.append(f"osds_per_device={osds_per_device}")
    change = f"create a new Ceph OSD on {dev!r} on node {n}"
    if extras:
        change += " (" + ", ".join(extras) + ")"
    dedicated_note = (
        f" db_dev={db_dev!r}/wal_dev={wal_dev!r} are ALSO consumed for dedicated block.db/"
        "block.wal." if (db_dev or wal_dev) else ""
    )
    encrypted_note = " Encryption (LUKS/dm-crypt) is applied." if encrypted else ""
    return Plan(
        action="pve_ceph_osd_create",
        target=f"{n}/ceph/osd:{dev}",
        change=change,
        current={},
        blast_radius=[
            f"consumes and REFORMATS {dev!r} as a new Ceph OSD (BlueStore) — ALL existing data "
            f"on the device is destroyed." + dedicated_note + encrypted_note,
            "the new OSD's id is NOT returned by this call (only a worker-task UPID) — read "
            "pve_ceph_osd_tree once the task completes to discover the assigned id.",
        ],
        risk=RISK_HIGH,
        risk_reasons=[
            "consumes and formats a block device as a new Ceph OSD — irreversibly destroys "
            "existing data on it"
        ],
        complete=True,
        note=(
            "No CAPTURE possible — this creates a brand-new OSD, nothing existing to snapshot "
            "(mirrors plan_apt_update_refresh's own 'no capture' posture). No rollback primitive "
            "on this plane — revert by destroying the new OSD with pve_ceph_osd_destroy once its "
            "id is known."
        ),
    )


def plan_ceph_osd_destroy(
    api: Any, osdid: int, node: str | None = None, cleanup: bool | None = None,
    *, audit_dir: str,
) -> Plan:
    """Plan for pve_ceph_osd_destroy — destroy an OSD. `cleanup=True` also zaps the underlying
    LVs (schema truth — see backends.ceph_osd_destroy's docstring).

    CAPTURE-or-declare: reads the OSD CRUSH tree via GET /nodes/{node}/ceph/osd (best-effort,
    through `taint.capture_adversarial_current` with a `finder=` — the tree is a NESTED CRUSH
    bucket structure, not a flat list, so the helper's default flat-list key-equality lookup
    doesn't fit; `_find_osd_in_tree` walks it instead) and looks up osdid's leaf entry; a
    successful read with no match degrades to current={} (honest — the OSD may already be gone),
    not a failure. cmd-safety citation: fail-open ADVISORY evidence (action=destroy, service=osd)
    via _cmd_safety_note — never a gate. `audit_dir` is the audit ledger's directory, required so
    the taint marker can be written when taint tracking is enabled.
    """
    _check_node(node)
    osdid = _check_ceph_osdid(osdid)
    n = node or api.config.node
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_osd_tree", lambda: api.ceph_osd_tree(node), osdid,
        finder=_find_osd_in_tree,
    )
    note_capture = (
        "" if complete else " Could not capture current OSD tree state — no guided revert available."
    )
    return Plan(
        action="pve_ceph_osd_destroy",
        target=f"{n}/ceph/osd/{osdid}",
        change=f"destroy Ceph OSD {osdid} on node {n}" + (" (cleanup=True)" if cleanup else ""),
        current=current,
        blast_radius=[
            f"removes OSD {osdid} from the cluster — data it held is recovered/rebalanced onto "
            "remaining OSDs (may already have been triggered by a prior 'out'). cleanup=True "
            "ALSO destroys the underlying logical volumes (ceph-volume lvm zap --destroy + "
            "pvremove) and wipes leftover journal/block.db/block.wal partitions; without it, "
            "the LVs/partitions are left intact for inspection (schema truth).",
            _cmd_safety_note(api, "destroy", "osd", str(osdid), node),
        ],
        risk=RISK_HIGH,
        risk_reasons=["destroys a Ceph OSD — data-durability risk if too few replicas/OSDs remain"],
        complete=complete,
        note=(
            "No rollback primitive on this plane — recreate with pve_ceph_osd_create (a NEW OSD, "
            "different id, not a byte-for-byte restore of this one's data)." + note_capture
        ),
    )


def plan_ceph_osd_in(api: Any, osdid: int, node: str | None = None, *, audit_dir: str) -> Plan:
    """Plan for pve_ceph_osd_in — mark an OSD 'in' (rejoins the CRUSH acting set; data
    rebalances BACK onto it). Runs SYNCHRONOUSLY (schema: returns null).

    CAPTURE-or-declare: reads the OSD CRUSH tree (best-effort, through
    `taint.capture_adversarial_current` + `_find_osd_in_tree` — see plan_ceph_osd_destroy's
    docstring for the nested-tree rationale). No cmd-safety citation: cmd-safety's action enum
    is {stop, destroy} — 'in' is neither (it doesn't stop a daemon or destroy anything), so no
    upstream heuristic exists for it; the plan states this plainly rather than guessing.
    `audit_dir` is the audit ledger's directory, required so the taint marker can be written when
    taint tracking is enabled.
    """
    _check_node(node)
    osdid = _check_ceph_osdid(osdid)
    n = node or api.config.node
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_osd_tree", lambda: api.ceph_osd_tree(node), osdid,
        finder=_find_osd_in_tree,
    )
    note_capture = (
        "" if complete else " Could not capture current OSD tree state — no guided revert available."
    )
    return Plan(
        action="pve_ceph_osd_in",
        target=f"{n}/ceph/osd/{osdid}/in",
        change=f"mark Ceph OSD {osdid} IN on node {n}",
        current=current,
        blast_radius=[
            f"OSD {osdid} rejoins the CRUSH acting set — Ceph rebalances data BACK onto it. No "
            "upstream cmd-safety check exists for the 'in' action (cmd-safety's action enum is "
            "{stop, destroy} only).",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["marks an OSD back in — triggers data rebalance onto it"],
        complete=complete,
        note=(
            f"No rollback primitive on this plane — revert with pve_ceph_osd_out(osdid={osdid})."
            + note_capture
        ),
    )


def plan_ceph_osd_out(api: Any, osdid: int, node: str | None = None, *, audit_dir: str) -> Plan:
    """Plan for pve_ceph_osd_out — mark an OSD 'out' (excluded from the CRUSH acting set;
    triggers data rebalance/recovery AWAY from it). Runs SYNCHRONOUSLY (schema: returns null).

    CAPTURE-or-declare: reads the OSD CRUSH tree (best-effort, through
    `taint.capture_adversarial_current` + `_find_osd_in_tree` — see plan_ceph_osd_destroy's
    docstring for the nested-tree rationale). No cmd-safety citation: cmd-safety's action enum is
    {stop, destroy} — 'out' is NEITHER (it doesn't stop the OSD daemon or destroy anything; the
    daemon keeps running, just excluded from the acting set), so no upstream heuristic exists for
    it — the plan states this plainly rather than guessing or fabricating coverage.
    `audit_dir` is the audit ledger's directory, required so the taint marker can be written when
    taint tracking is enabled.
    """
    _check_node(node)
    osdid = _check_ceph_osdid(osdid)
    n = node or api.config.node
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_osd_tree", lambda: api.ceph_osd_tree(node), osdid,
        finder=_find_osd_in_tree,
    )
    note_capture = (
        "" if complete else " Could not capture current OSD tree state — no guided revert available."
    )
    return Plan(
        action="pve_ceph_osd_out",
        target=f"{n}/ceph/osd/{osdid}/out",
        change=f"mark Ceph OSD {osdid} OUT on node {n}",
        current=current,
        blast_radius=[
            f"OSD {osdid} is excluded from the CRUSH acting set — Ceph triggers data rebalance/"
            "recovery AWAY from it onto remaining OSDs. No upstream cmd-safety check exists for "
            "the 'out' action (cmd-safety's action enum is {stop, destroy} only — 'out' neither "
            "stops the daemon nor destroys anything).",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["marks an OSD out — triggers data rebalance/recovery away from it"],
        complete=complete,
        note=(
            f"No rollback primitive on this plane — revert with pve_ceph_osd_in(osdid={osdid})."
            + note_capture
        ),
    )


def plan_ceph_osd_scrub(
    api: Any, osdid: int, node: str | None = None, deep: bool | None = None
) -> Plan:
    """Plan for pve_ceph_osd_scrub — instruct an OSD to scrub (light, or deep when deep=True).
    Runs SYNCHRONOUSLY (schema: returns null). RISK_LOW: no logical state change; a deep scrub
    is I/O-heavy while it runs. No CAPTURE: scrubbing isn't a durable state to snapshot (mirrors
    plan_ceph_service_start's own "nothing to capture" posture).
    """
    _check_node(node)
    osdid = _check_ceph_osdid(osdid)
    n = node or api.config.node
    kind = "deep scrub" if deep else "scrub"
    io_note = (
        "a DEEP scrub reads every object's full data and is I/O-heavy while it runs."
        if deep else "a light scrub checks metadata only and is comparatively cheap."
    )
    return Plan(
        action="pve_ceph_osd_scrub",
        target=f"{n}/ceph/osd/{osdid}/scrub",
        change=f"instruct Ceph OSD {osdid} to {kind} on node {n}",
        current={},
        blast_radius=[f"instructs OSD {osdid} to {kind} — no logical state change; " + io_note],
        risk=RISK_LOW,
        risk_reasons=["read-verification pass on an OSD — no logical state change"],
        complete=True,
        note="No CAPTURE / no rollback primitive — scrubbing isn't a durable state to revert.",
    )


# === Wave 6d — pools + CephFS (CLOSES Wave 6) ===============================================


def plan_ceph_pool_create(
    api: Any,
    name: str,
    node: str | None = None,
    add_storages: bool | None = None,
    application: str | None = None,
    crush_rule: str | None = None,
    erasure_coding: str | None = None,
    min_size: int | None = None,
    pg_autoscale_mode: str | None = None,
    pg_num: int | None = None,
    pg_num_min: int | None = None,
    size: int | None = None,
    target_size: str | None = None,
    target_size_ratio: float | None = None,
    *,
    audit_dir: str,
) -> Plan:
    """Plan for pve_ceph_pool_create — create a Ceph pool.

    CAPTURE-or-declare: reads current pools via GET /nodes/{node}/ceph/pool (best-effort, through
    `taint.capture_adversarial_current` — `pve_ceph_pool_list` is ADVERSARIAL, reversed from
    REVIEWED_TRUSTED by the Wave 6d review; see this module's Wave 6d Taint section) and looks up
    `name`'s existing entry (`key="pool_name"`, the pool entry's own match field); a successful
    read with no match degrades to current={} (expected — the pool doesn't exist yet), not a
    failure — only a raised exception on the read itself sets complete=False. `erasure_coding` is
    PVE's own propertyString wire format, validated by parsing (see
    backends._check_ceph_pool_erasure_coding). `audit_dir` is the audit ledger's directory (see
    server.py's `_audited`), required so the taint marker can be written when taint tracking is
    enabled.
    """
    name = _check_ceph_pool_or_fs_name(name, "pool name")
    n = node or api.config.node
    if application is not None:
        application = _check_ceph_pool_application(application)
    if erasure_coding is not None:
        erasure_coding = _check_ceph_pool_erasure_coding(erasure_coding)
    min_size = _check_ceph_bounded_int(min_size, "pool min_size", 1, 7)
    size = _check_ceph_bounded_int(size, "pool size", 1, 7)
    pg_num = _check_ceph_bounded_int(pg_num, "pool pg_num", 1, 32768)
    pg_num_min = _check_ceph_pool_upper_bound(pg_num_min, "pg_num_min", 32768)
    if pg_autoscale_mode is not None:
        pg_autoscale_mode = _check_ceph_pool_autoscale_mode(pg_autoscale_mode)
    if target_size is not None:
        target_size = _check_ceph_pool_target_size(target_size)
    target_size_ratio = _check_ceph_pool_ratio(target_size_ratio)
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_pool_list", lambda: api.ceph_pool_list(node), name,
        key="pool_name",
    )
    note_capture = (
        "" if complete else " Could not capture current pool list — no guided revert available."
    )
    extras = []
    if application is not None:
        extras.append(f"application={application!r}")
    if erasure_coding is not None:
        extras.append(f"erasure-coding={erasure_coding!r}")
    if crush_rule is not None:
        extras.append(f"crush_rule={crush_rule!r}")
    change = f"create Ceph pool {name!r} on node {n}"
    if extras:
        change += " (" + ", ".join(extras) + ")"
    return Plan(
        action="pve_ceph_pool_create",
        target=f"{n}/ceph/pool:{name}",
        change=change,
        current=current,
        blast_radius=[
            f"creates a new Ceph pool {name!r} — consumes cluster capacity per its "
            "size/pg_num settings. No upstream cmd-safety check exists for pool creation "
            "(cmd-safety's service enum is {osd, mon, mds} only — covers neither pool nor "
            "filesystem)."
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["creates a new Ceph pool — consumes cluster capacity"],
        complete=complete,
        note=(
            f"No rollback primitive on this plane — revert by calling "
            f"pve_ceph_pool_destroy(name={name!r})." + note_capture
        ),
    )


def _identity_finder(result: Any, _match_id: Any) -> dict | None:
    """`finder=` for a CAPTURE source whose read() already returns the single target object
    directly (not a list to search) — `plan_ceph_pool_set`'s `ceph_pool_status(name)` read is the
    first caller. Returns `result` unchanged (ignoring `match_id` entirely) when it's a dict, else
    None (normalized by `capture_adversarial_current` to the same current={} "no match" shape as
    every other CAPTURE source — never raises)."""
    return dict(result) if isinstance(result, dict) else None


def plan_ceph_pool_set(
    api: Any,
    name: str,
    node: str | None = None,
    application: str | None = None,
    crush_rule: str | None = None,
    min_size: int | None = None,
    pg_autoscale_mode: str | None = None,
    pg_num: int | None = None,
    pg_num_min: int | None = None,
    size: int | None = None,
    target_size: str | None = None,
    target_size_ratio: float | None = None,
    *,
    audit_dir: str,
) -> Plan:
    """Plan for pve_ceph_pool_set — change an existing pool's settings.

    At-least-one-field guard (the 6a `flags_set` lesson — this is a bulk-optional-field
    mutation): refuses BEFORE any read or `_plan()` recording if every settable field is
    omitted. CAPTURE-or-declare: reads the pool's CURRENT settings via GET
    /nodes/{node}/ceph/pool/{name}/status (best-effort, through
    `taint.capture_adversarial_current` — `pve_ceph_pool_status` is ADVERSARIAL, reversed from
    REVIEWED_TRUSTED by the Wave 6d review; see this module's Wave 6d Taint section), using
    `_identity_finder` since this source's read() already returns the single target object
    (not a list to search); only a raised exception on the read itself sets complete=False. No
    add_storages/erasure-coding here — PUT doesn't accept either (create-only per schema).
    `audit_dir` is the audit ledger's directory, required so the taint marker can be written when
    taint tracking is enabled.
    """
    name = _check_ceph_pool_or_fs_name(name, "pool name")
    n = node or api.config.node
    if (application is None and crush_rule is None and min_size is None
            and pg_autoscale_mode is None and pg_num is None and pg_num_min is None
            and size is None and target_size is None and target_size_ratio is None):
        raise ProximoError("pve_ceph_pool_set requires at least one field to change")
    if application is not None:
        application = _check_ceph_pool_application(application)
    min_size = _check_ceph_bounded_int(min_size, "pool min_size", 1, 7)
    size = _check_ceph_bounded_int(size, "pool size", 1, 7)
    pg_num = _check_ceph_bounded_int(pg_num, "pool pg_num", 1, 32768)
    pg_num_min = _check_ceph_pool_upper_bound(pg_num_min, "pg_num_min", 32768)
    if pg_autoscale_mode is not None:
        pg_autoscale_mode = _check_ceph_pool_autoscale_mode(pg_autoscale_mode)
    if target_size is not None:
        target_size = _check_ceph_pool_target_size(target_size)
    target_size_ratio = _check_ceph_pool_ratio(target_size_ratio)
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_pool_status", lambda: api.ceph_pool_status(name, node), name,
        finder=_identity_finder,
    )
    note_capture = (
        "" if complete else " Could not capture current pool settings — no guided revert available."
    )
    changes = {
        k: v for k, v in {
            "application": application, "crush_rule": crush_rule, "min_size": min_size,
            "pg_autoscale_mode": pg_autoscale_mode, "pg_num": pg_num, "pg_num_min": pg_num_min,
            "size": size, "target_size": target_size, "target_size_ratio": target_size_ratio,
        }.items() if v is not None
    }
    pg_num_note = (
        " WARNING: a pg_num change triggers cluster rebalance." if "pg_num" in changes else ""
    )
    return Plan(
        action="pve_ceph_pool_set",
        target=f"{n}/ceph/pool/{name}",
        change=f"change Ceph pool {name!r} settings on node {n}: {changes}",
        current=current,
        blast_radius=[
            f"changes pool {name!r}'s settings." + pg_num_note + " No upstream cmd-safety "
            "check exists for pool changes (cmd-safety's service enum is {osd, mon, mds} only)."
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["changes an existing Ceph pool's settings — a pg_num change rebalances data"],
        complete=complete,
        note=(
            "Revert by re-applying the captured current settings with pve_ceph_pool_set."
            + note_capture
        ),
    )


def plan_ceph_pool_destroy(
    api: Any,
    name: str,
    node: str | None = None,
    force: bool | None = None,
    remove_ecprofile: bool | None = None,
    remove_storages: bool | None = None,
    *,
    audit_dir: str,
) -> Plan:
    """Plan for pve_ceph_pool_destroy — destroy a Ceph pool. UNRECOVERABLE via the API: a
    recreated pool with the same name is a fresh EMPTY pool, not a restore.

    `force` is NEVER defaulted on — forwarded only when the caller explicitly sets it (schema:
    "destroys pool even if in use"). CAPTURE-or-declare: reads current pools via GET
    /nodes/{node}/ceph/pool (best-effort, through `taint.capture_adversarial_current` —
    `pve_ceph_pool_list` is ADVERSARIAL, reversed from REVIEWED_TRUSTED by the Wave 6d review; see
    this module's Wave 6d Taint section) and looks up `name`'s existing entry (`key="pool_name"`);
    a successful read with no match degrades to current={} (honest — the pool may already be
    gone), not a failure. No cmd-safety citation: cmd-safety's service enum is {osd, mon, mds} —
    pool was never in it. `audit_dir` is the audit ledger's directory, required so the taint
    marker can be written when taint tracking is enabled.
    """
    name = _check_ceph_pool_or_fs_name(name, "pool name")
    n = node or api.config.node
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_pool_list", lambda: api.ceph_pool_list(node), name,
        key="pool_name",
    )
    note_capture = (
        "" if complete else " Could not capture current pool list — no guided revert available."
    )
    force_note = (
        " force=True: destroys the pool EVEN IF IN USE (schema truth)." if force else ""
    )
    return Plan(
        action="pve_ceph_pool_destroy",
        target=f"{n}/ceph/pool/{name}",
        change=f"destroy Ceph pool {name!r} on node {n}",
        current=current,
        blast_radius=[
            f"destroys pool {name!r} and ALL data stored in it — UNRECOVERABLE via the API."
            + force_note,
            "no upstream cmd-safety check exists for pool destroy (cmd-safety's service enum "
            "is {osd, mon, mds} only).",
        ],
        risk=RISK_HIGH,
        risk_reasons=["destroys a Ceph pool and all data stored in it — irreversible via the API"],
        complete=complete,
        note=(
            "No rollback primitive on this plane — recreating a pool with the SAME name is a "
            "fresh EMPTY pool, not a restore of the destroyed data." + note_capture
        ),
    )


def plan_ceph_fs_create(
    api: Any,
    node: str | None = None,
    name: str | None = None,
    add_storage: bool | None = None,
    pg_num: int | None = None,
    *,
    audit_dir: str,
) -> Plan:
    """Plan for pve_ceph_fs_create — create a Ceph filesystem. `name` schema-defaults to the
    FIXED LITERAL 'cephfs' when omitted, resolved client-side (see
    backends._check_ceph_fs_name_or_default — name is ALSO the URL path segment).

    CAPTURE-or-declare: reads current filesystems via GET /nodes/{node}/ceph/fs (best-effort,
    through `taint.capture_adversarial_current` — `pve_ceph_fs_list` is ADVERSARIAL, reversed from
    REVIEWED_TRUSTED by the Wave 6d review; see this module's Wave 6d Taint section) and looks up
    the resolved name's existing entry; a successful read with no match degrades to current={}
    (expected — the filesystem doesn't exist yet), not a failure. `audit_dir` is the audit
    ledger's directory, required so the taint marker can be written when taint tracking is
    enabled.
    """
    nm = _check_ceph_fs_name_or_default(name)
    n = node or api.config.node
    pg_num = _check_ceph_bounded_int(pg_num, "fs pg_num", 8, 32768)
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_fs_list", lambda: api.ceph_fs_list(node), nm,
    )
    note_capture = (
        "" if complete else
        " Could not capture current filesystem list — no guided revert available."
    )
    change = f"create Ceph filesystem {nm!r} on node {n}"
    if pg_num is not None:
        change += f" (pg_num={pg_num})"
    return Plan(
        action="pve_ceph_fs_create",
        target=f"{n}/ceph/fs:{nm}",
        change=change,
        current=current,
        blast_radius=[
            f"creates CephFS {nm!r} — allocates a new metadata pool + data pool (pg_num "
            "backing the data pool; the metadata pool uses a quarter of it, per schema truth). "
            "Requires at least one MDS to actually serve it (pve_ceph_mds_create). No upstream "
            "cmd-safety check exists for filesystem creation."
        ],
        risk=RISK_MEDIUM,
        risk_reasons=["creates a new CephFS filesystem — allocates new metadata/data pools"],
        complete=complete,
        note=(
            f"No rollback primitive on this plane — revert by calling "
            f"pve_ceph_fs_destroy(name={nm!r})." + note_capture
        ),
    )


def plan_ceph_fs_destroy(
    api: Any,
    name: str,
    node: str | None = None,
    remove_pools: bool | None = None,
    remove_storages: bool | None = None,
    *,
    audit_dir: str,
) -> Plan:
    """Plan for pve_ceph_fs_destroy — destroy a Ceph filesystem. Refuses upstream while a
    'cephfs' PVE storage entry still references it and is not disabled, UNLESS remove_storages
    is set (schema truth) — UNRECOVERABLE via the API otherwise.

    CAPTURE-or-declare: reads current filesystems via GET /nodes/{node}/ceph/fs (best-effort,
    through `taint.capture_adversarial_current` — `pve_ceph_fs_list` is ADVERSARIAL, reversed from
    REVIEWED_TRUSTED by the Wave 6d review; see this module's Wave 6d Taint section) and looks up
    `name`'s existing entry; a successful read with no match degrades to current={} (honest — the
    filesystem may already be gone), not a failure. No cmd-safety citation: cmd-safety's service
    enum is {osd, mon, mds} — filesystem was never in it. `audit_dir` is the audit ledger's
    directory, required so the taint marker can be written when taint tracking is enabled.
    """
    name = _check_ceph_pool_or_fs_name(name, "fs name")
    n = node or api.config.node
    current, complete = capture_adversarial_current(
        audit_dir, "pve_ceph_fs_list", lambda: api.ceph_fs_list(node), name,
    )
    note_capture = (
        "" if complete else
        " Could not capture current filesystem list — no guided revert available."
    )
    refusal_note = (
        "" if remove_storages else
        " Refuses upstream while a 'cephfs' PVE storage entry still references this filesystem "
        "and is not disabled (schema truth) — set remove_storages=True to remove those storage "
        "entries too."
    )
    pools_note = (
        " remove_pools=True ALSO destroys the underlying metadata and data pools." if remove_pools
        else ""
    )
    return Plan(
        action="pve_ceph_fs_destroy",
        target=f"{n}/ceph/fs/{name}",
        change=f"destroy Ceph filesystem {name!r} on node {n}",
        current=current,
        blast_radius=[
            f"destroys CephFS {name!r} — UNRECOVERABLE via the API." + refusal_note + pools_note,
            "no upstream cmd-safety check exists for filesystem destroy (cmd-safety's service "
            "enum is {osd, mon, mds} only).",
        ],
        risk=RISK_HIGH,
        risk_reasons=["destroys a CephFS filesystem — irreversible via the API"],
        complete=complete,
        note=(
            "No rollback primitive on this plane — recreating a filesystem with the SAME name "
            "is a fresh EMPTY filesystem, not a restore." + note_capture
        ),
    )
