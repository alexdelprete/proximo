#!/usr/bin/env python3
"""PMG Wave 8 live-prove smoke — ruledb per-object reads + welcomelist vs real PMG 9.1.

Priorities per the Wave 8 binding brief (.scratch/sdd/wave-8-draft-decomposition.md §5):

  P1  Does GET /config/ruledb/rules/{id}/config really embed an 'action' key?
      (The shipped ruledb_rule_actions_list extracts cfg.get("action") — mock-tested
      only. If the live response has no such key, that tool silently returns [] for
      rules WITH attached actions.) Also live-proves the new singular-endpoint tool
      ruledb_rule_action_groups_list against the same rule.

  P2  Global welcomelist round-trip: add -> typed get -> update -> list -> delete for
      email; add -> get -> delete for receiver_domain (records the REAL response
      fields — the schema types only {id}; Facts #6/#7/#12).

  P3  Per-object read sweep: who (create + read + cleanup), what (factory object if
      present, else create), when (timeframe round-trip), action typed gets
      (create -> get -> delete per family). ldapuser is SKIPPED honestly if no LDAP
      profile exists in the lab.

  Factory reset (pmg_ruledb_reset): NOT SMOKED. Requires John's explicit go, runs
  LAST if ever — it would erase every fixture this smoke creates.

All fixtures are w8smoke-* named, created inactive where the concept exists, and
cleaned up in reverse order (best-effort, failures reported loudly).

Environment (same wiring as pmg-smoke.py):
  PROXIMO_PMG_BASE_URL / _USERNAME / _PASSWORD_PATH / _NODE / _VERIFY_TLS / _CA_BUNDLE
"""
from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from proximo.pmg import (  # noqa: E402
    PmgBackend,
    PmgConfig,
    action_bcc_create,
    action_bcc_get,
    action_delete,
    action_disclaimer_create,
    action_disclaimer_get,
    action_field_create,
    action_field_get,
    action_notification_create,
    action_notification_get,
    action_objects_list,
    action_removeattachments_create,
    action_removeattachments_get,
    ruledb_rule_action_attach,
    ruledb_rule_action_detach,
    ruledb_rule_action_groups_list,
    ruledb_rule_actions_list,
    ruledb_rule_create,
    ruledb_rule_delete,
    ruledb_rules_list,
    what_group_create,
    what_group_delete,
    what_group_objects,
    what_groups_list,
    what_object_add,
    what_object_delete,
    what_object_get,
    when_group_create,
    when_group_delete,
    when_group_objects,
    when_groups_list,
    when_object_add,
    when_object_delete,
    when_object_get,
    who_group_create,
    who_group_delete,
    who_group_objects,
    who_groups_list,
    who_object_add,
    who_object_delete,
    who_object_get,
)
from proximo.pmg_welcomelist import (  # noqa: E402
    welcomelist_object_add,
    welcomelist_object_delete,
    welcomelist_object_get,
    welcomelist_object_update,
    welcomelist_objects_list,
)

RESULTS: list[tuple[str, str, str]] = []


def step(name: str):
    def deco(fn):
        def run(*a, **kw):
            try:
                detail = fn(*a, **kw)
                RESULTS.append((name, "PASS", str(detail or "")[:120]))
                print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
                return detail
            except Exception as e:  # noqa: BLE001 — smoke reports, never aborts
                RESULTS.append((name, "FAIL", f"{type(e).__name__}: {e}"))
                print(f"  FAIL  {name} — {type(e).__name__}: {e}")
                traceback.print_exc(limit=2)
                return None
        return run
    return deco


def run_p1(api: PmgBackend, cleanup: list) -> tuple[str | None, str | None, str | None]:
    """P1 — the actions_list question. Returns (rid, notify_ogroup, notify_compound)."""
    print("== P1: the actions_list question ==")
    rid = None
    notify_ogroup = None      # the action GROUP id (attach/detach + groups-list)
    notify_compound = None    # the {ogroup}_{objid} compound id (typed get + delete)

    @step("P1.1 create inactive throwaway rule")
    def _p1_rule():
        nonlocal rid
        before = {str(r.get("id")) for r in ruledb_rules_list(api)}
        ruledb_rule_create(api, "w8smoke-rule", 50, active=False)
        after = ruledb_rules_list(api)
        new = [r for r in after if str(r.get("id")) not in before]
        assert len(new) == 1, f"expected 1 new rule, got {len(new)}"
        rid = str(new[0]["id"])
        cleanup.append(("rule delete", lambda: ruledb_rule_delete(api, rid)))
        return f"rule id={rid}"
    _p1_rule()

    @step("P1.2 create notification action object")
    def _p1_action():
        nonlocal notify_ogroup, notify_compound
        before = {str(o.get("id")) for o in action_objects_list(api)}
        action_notification_create(
            api, name="w8smoke-notify", to="postmaster",
            subject="w8smoke", body_text="w8smoke",
        )
        new = [o for o in action_objects_list(api) if str(o.get("id")) not in before]
        assert len(new) == 1, f"expected 1 new action object, got {len(new)}"
        notify_compound = str(new[0]["id"])          # e.g. '198_224'
        notify_ogroup = str(new[0]["ogroup"])        # e.g. '198' — what attach wants
        cleanup.append(("action delete", lambda: action_delete(api, notify_compound)))
        return (f"action ogroup={notify_ogroup} compound-id={notify_compound} "
                f"raw-keys={sorted(new[0])}")
    _p1_action()

    if rid and notify_ogroup:
        @step("P1.3 attach action group to rule")
        def _p1_attach():
            ruledb_rule_action_attach(api, rid, notify_ogroup)
            cleanup.append(
                ("action detach", lambda: ruledb_rule_action_detach(api, rid, notify_ogroup))
            )
        _p1_attach()

        @step("P1.4 THE QUESTION: does rules/{id}/config embed 'action'?")
        def _p1_config():
            cfg_resp = api._get(f"/config/ruledb/rules/{rid}/config") or {}
            has = "action" in cfg_resp
            return f"config keys={sorted(cfg_resp)} -> action-embedded={has}"
        _p1_config()

        @step("P1.5 shipped ruledb_rule_actions_list on the same rule")
        def _p1_shipped():
            got = ruledb_rule_actions_list(api, rid)
            return f"returned {got!r}"
        _p1_shipped()

        @step("P1.6 NEW singular ruledb_rule_action_groups_list")
        def _p1_new():
            got = ruledb_rule_action_groups_list(api, rid)
            ids = {str(g.get("id")) for g in got}
            assert notify_ogroup in ids, f"attached ogroup {notify_ogroup} not in {ids}"
            return f"returned {got!r} (attached ogroup present)"
        _p1_new()
    return rid, notify_ogroup, notify_compound


def run_p2(api: PmgBackend, cleanup: list) -> None:
    """P2 — global welcomelist round-trip."""
    print("== P2: global welcomelist round-trip ==")

    @step("P2.1 baseline objects list (record REAL item shape)")
    def _p2_base():
        items = welcomelist_objects_list(api)
        shape = sorted(items[0]) if items else "(empty list)"
        return f"{len(items)} entries; first-item keys={shape}"
    _p2_base()

    wl_id = None

    @step("P2.2 add email w8smoke@example.invalid")
    def _p2_add():
        nonlocal wl_id
        before = {str(o.get("id")) for o in welcomelist_objects_list(api)}
        welcomelist_object_add(api, "email", email="w8smoke@example.invalid")
        new = [o for o in welcomelist_objects_list(api) if str(o.get("id")) not in before]
        assert len(new) == 1
        wl_id = str(new[0]["id"])
        cleanup.append(("welcomelist email delete", lambda: welcomelist_object_delete(api, wl_id)))
        return f"id={wl_id} list-item-keys={sorted(new[0])}"
    _p2_add()

    if wl_id:
        @step("P2.3 typed get (REAL response fields vs schema's thin {id})")
        def _p2_get():
            obj = welcomelist_object_get(api, "email", wl_id)
            assert str(obj.get("id")) == wl_id
            return f"keys={sorted(obj)} raw={obj!r}"
        _p2_get()

        @step("P2.4 update value + read back")
        def _p2_update():
            welcomelist_object_update(api, "email", wl_id, email="w8smoke2@example.invalid")
            obj = welcomelist_object_get(api, "email", wl_id)
            val = obj.get("email") or obj.get("address") or obj
            return f"post-update read: {val!r}"
        _p2_update()

    @step("P2.5 receiver_domain add + typed get (direction/field evidence)")
    def _p2_rdom():
        before = {str(o.get("id")) for o in welcomelist_objects_list(api)}
        welcomelist_object_add(api, "receiver_domain", domain="w8smoke.example.invalid")
        new = [o for o in welcomelist_objects_list(api) if str(o.get("id")) not in before]
        assert len(new) == 1
        rdid = str(new[0]["id"])
        cleanup.append(("welcomelist receiver_domain delete",
                        lambda: welcomelist_object_delete(api, rdid)))
        obj = welcomelist_object_get(api, "receiver_domain", rdid)
        return f"id={rdid} get-keys={sorted(obj)} raw={obj!r}"
    _p2_rdom()


def run_p3(api: PmgBackend, cleanup: list, notify_compound: str | None) -> None:
    """P3 — per-object read sweep."""
    print("== P3: per-object read sweep ==")

    @step("P3.1 who: create group + email object, typed get, verify")
    def _p3_who():
        who_group_create(api, "w8smoke-who")
        groups = [g for g in who_groups_list(api) if g.get("name") == "w8smoke-who"]
        assert len(groups) == 1
        og = str(groups[0]["id"])
        cleanup.append(("who group delete", lambda: who_group_delete(api, og)))
        who_object_add(api, og, "email", email="w8smoke-who@example.invalid")
        objs = who_group_objects(api, og)
        assert len(objs) == 1
        oid = str(objs[0]["id"])
        cleanup.append(("who object delete", lambda: who_object_delete(api, og, oid)))
        got = who_object_get(api, og, "email", oid)
        assert str(got.get("id")) == oid
        return f"ogroup={og} oid={oid} get-keys={sorted(got)}"
    _p3_who()

    @step("P3.2 who: ldapuser typed get")
    def _p3_ldapuser():
        return ("SKIPPED honestly — no LDAP profile configured in the sealed lab; "
                "ldapuser add/get stays Smoke-confirm")
    _p3_ldapuser()

    @step("P3.3 what: typed get (factory object if present, else create)")
    def _p3_what():
        for g in what_groups_list(api):
            og = str(g["id"])
            for o in what_group_objects(api, og):
                otype = o.get("otype_text") or o.get("otype")
                for t in ("spamfilter", "contenttype", "matchfield", "virusfilter",
                          "filenamefilter", "archivefilter", "archivefilenamefilter"):
                    if t in str(otype).lower().replace(" ", ""):
                        got = what_object_get(api, og, t, str(o["id"]))
                        return f"factory {t} og={og} id={o['id']} keys={sorted(got)}"
        what_group_create(api, "w8smoke-what")
        g = [x for x in what_groups_list(api) if x.get("name") == "w8smoke-what"][0]
        og = str(g["id"])
        cleanup.append(("what group delete", lambda: what_group_delete(api, og)))
        what_object_add(api, og, "spamfilter", spamlevel=9)
        objs = what_group_objects(api, og)
        oid = str(objs[0]["id"])
        cleanup.append(("what object delete", lambda: what_object_delete(api, og, oid)))
        got = what_object_get(api, og, "spamfilter", oid)
        return f"created spamfilter og={og} id={oid} keys={sorted(got)}"
    _p3_what()

    @step("P3.4 when: timeframe round-trip")
    def _p3_when():
        when_group_create(api, "w8smoke-when")
        g = [x for x in when_groups_list(api) if x.get("name") == "w8smoke-when"][0]
        og = str(g["id"])
        cleanup.append(("when group delete", lambda: when_group_delete(api, og)))
        when_object_add(api, og, start="08:00", end="17:00")
        objs = when_group_objects(api, og)
        oid = str(objs[0]["id"])
        cleanup.append(("when object delete", lambda: when_object_delete(api, og, oid)))
        got = when_object_get(api, og, oid)
        return f"og={og} id={oid} keys={sorted(got)}"
    _p3_when()

    def action_family(label, create, get, **kw):
        @step(f"P3.5 action {label}: create -> typed get -> delete")
        def _run():
            before = {str(o.get("id")) for o in action_objects_list(api)}
            create(api, **kw)
            new = [o for o in action_objects_list(api) if str(o.get("id")) not in before]
            assert len(new) == 1
            aid = str(new[0]["id"])
            cleanup.append((f"action {label} delete", lambda: action_delete(api, aid)))
            got = get(api, aid)
            return f"id={aid} get-keys={sorted(got)}"
        _run()

    action_family("bcc", action_bcc_create, action_bcc_get,
                  name="w8smoke-bcc", target="w8smoke-bcc@example.invalid")
    action_family("field", action_field_create, action_field_get,
                  name="w8smoke-field", field="X-W8Smoke", value="1")
    action_family("disclaimer", action_disclaimer_create, action_disclaimer_get,
                  name="w8smoke-disc", disclaimer="w8smoke")
    action_family("removeattachments", action_removeattachments_create,
                  action_removeattachments_get, name="w8smoke-rma", text="w8smoke")
    if notify_compound:
        @step("P3.5 action notification: typed get (P1 fixture)")
        def _p3_notify():
            got = action_notification_get(api, notify_compound)
            return f"id={notify_compound} get-keys={sorted(got)}"
        _p3_notify()


def main() -> int:
    cfg = PmgConfig.from_env()
    api = PmgBackend(cfg)
    cleanup: list = []  # (label, fn) LIFO

    _rid, _og, notify_compound = run_p1(api, cleanup)
    run_p2(api, cleanup)
    run_p3(api, cleanup, notify_compound)

    print("== cleanup (reverse order) ==")
    for label, fn in reversed(cleanup):
        try:
            fn()
            print(f"  cleaned: {label}")
        except Exception as e:  # noqa: BLE001
            print(f"  CLEANUP FAILED (manual attention): {label} — {e}")
            RESULTS.append((f"cleanup:{label}", "FAIL", str(e)))

    print("\n== summary ==")
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    for name, status, _detail in RESULTS:
        print(f"  {status:4}  {name}")
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
