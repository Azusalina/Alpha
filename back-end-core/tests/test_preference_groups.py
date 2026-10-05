"""Reviewed event groups: synthetic labels, temporary databases, no corpus."""

import copy
import json
import math
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from core.access import AccessSession, setup_access
from core.backup import create_backup, restore_backup, validate_database
from model import preferences
from model.ranking import VALUE_PARAMETERS
from tests.test_preferences import options, record


class PureGroupTests(unittest.TestCase):
    def fit(self, records, **changes):
        fields = dict(target="actual", partition="rational", domain="daily")
        fields.update(changes)
        return preferences.fit_preferences(records, **fields)

    def grouped(self, source, group, **changes):
        return {**record(source), "group_id": group, **changes}

    def test_many_source_ids_in_one_group_cannot_cross_gate(self):
        records = [self.grouped(f"source-{i}", "same-event") for i in range(32)]
        result = self.fit(records)
        self.assertEqual((result["training_sources"], result["training_groups"]), (32, 1))
        self.assertEqual(result["reason"], "insufficient_training_groups")
        self.assertEqual(result["ranked"], [])

    def test_three_reviewed_groups_in_one_source_pass_gate(self):
        records = [self.grouped("one-source", f"event-{i}") for i in range(3)]
        before = copy.deepcopy(records)
        result = self.fit(records)
        self.assertEqual((result["training_sources"], result["training_groups"]), (1, 3))
        self.assertEqual(result["status"], "provisional")
        self.assertEqual(records, before)

    def test_one_group_total_mass_across_sources_and_events(self):
        records = [self.grouped("counter", "group-counter", actual_choice_id="b"),
                   self.grouped("positive-1", "group-1"), self.grouped("positive-2", "group-2")]
        before = self.fit(records)
        repeated = [self.grouped(f"counter-{i}", "group-counter", actual_choice_id="b")
                    for i in range(96)] + records[1:]
        after = self.fit(repeated)
        self.assertEqual((after["training_sources"], after["training_groups"]), (98, 3))
        for key in VALUE_PARAMETERS:
            self.assertAlmostEqual(before["weights"][key], after["weights"][key], places=12)
        self.assertGreater(after["weights"]["value.autonomy"], 0)

    def test_contradictory_labels_within_group_keep_equal_group_mass(self):
        records = [self.grouped("same", "mixed", actual_choice_id="a"),
                   self.grouped("other", "mixed", actual_choice_id="b"),
                   self.grouped("same", "positive"),
                   self.grouped("same", "negative", actual_choice_id="b")]
        fit = self.fit(records)
        self.assertEqual((fit["training_sources"], fit["training_groups"]), (2, 3))
        self.assertEqual(fit["reason"], "no_identifiable_preference")
        # Doubling the mixed group's events must retain cancellation.
        self.assertEqual(self.fit(records[:2] * 20 + records[2:])["reason"],
                         "no_identifiable_preference")

    def test_group_average_matches_independent_scalar_optimum(self):
        records = [self.grouped(f"negative-{i}", "negative", actual_choice_id="b")
                   for i in range(30)]
        records += [self.grouped("one", "positive-1"), self.grouped("one", "positive-2")]
        # Each of the three group averages has the same mass: positive rate 2/3.
        lo, hi = -10.0, 10.0
        for _ in range(100):
            mid = (lo + hi) / 2
            derivative = 2 * (1 / (1 + math.exp(-2 * mid)) - 2 / 3) + .1 * mid
            if derivative > 0:
                hi = mid
            else:
                lo = mid
        self.assertAlmostEqual(self.fit(records)["weights"]["value.autonomy"], (lo + hi) / 2,
                               places=10)

    def test_explicit_group_fields_never_fall_back_and_strict_types(self):
        legacy = [record(str(i)) for i in range(3)]
        for item in legacy:
            item.pop("group_id")
            item.pop("group_reviewed")
        self.assertEqual(self.fit(legacy)["training_groups"], 3)
        for fields in ({"group_reviewed": False}, {"group_id": None},
                       {"group_id": "draft"}, {"group_id": None, "group_reviewed": False}):
            with self.subTest(fields=fields):
                self.assertEqual(self.fit([{**item, **fields} for item in legacy])["training_groups"], 0)
        for fields in ({"group_reviewed": True}, {"group_reviewed": None},
                       {"group_reviewed": 1}, {"group_reviewed": "true"},
                       {"group_id": True}, {"group_id": 0}, {"group_id": []},
                       {"group_id": ""}, {"group_id": " \t\n"}, {"group_id": "x" * 129},
                       {"group_id": "x\0"}, {"group_id": "\ud800"}):
            with self.subTest(fields=repr(fields)), self.assertRaises(ValueError):
                self.fit([{**item, **fields} for item in legacy])

    def test_group_counts_exclude_uninformative_unconsented_and_inactive(self):
        records = [self.grouped("one", "first"), self.grouped("one", "second"),
                   self.grouped("two", "no-label", actual_choice_id=None),
                   self.grouped("two", "no-consent", training_consent=False),
                   self.grouped("two", "inactive", model_active=False),
                   self.grouped("two", "draft", group_reviewed=False),
                   self.grouped("two", "no-contrast", options=[
                       {"id": "a", "impacts": {}}, {"id": "b", "impacts": {}}])]
        result = self.fit(records)
        self.assertEqual((result["training_sources"], result["training_groups"]), (1, 2))

    def test_groups_are_scoped_by_target_state_and_domain(self):
        records = [self.grouped("one", "shared"),
                   self.grouped("one", "emotional", partition="emotional",
                                endorsement_partition="emotional"),
                   self.grouped("one", "study", domain="study"),
                   self.grouped("one", "endorsed", actual_choice_id=None)]
        self.assertEqual(self.fit(records)["training_groups"], 1)
        self.assertEqual(self.fit(records, target="endorsed")["training_groups"], 2)
        self.assertEqual(self.fit(records, partition="emotional")["training_groups"], 1)
        self.assertEqual(self.fit(records, domain="study")["training_groups"], 1)

    def test_fallback_and_explicit_group_names_do_not_accidentally_merge(self):
        fallback = record("same-name")
        fallback.pop("group_id")
        fallback.pop("group_reviewed")
        records = [fallback, self.grouped("different-source", "same-name"),
                   self.grouped("different-source", "third")]
        self.assertEqual(self.fit(records)["training_groups"], 3)


class OnlineGroupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.api = BrainAPI(self.path)

    def call(self, method, **params):
        return self.api.handle(dict(schema_version=1, id="group-contract", method=method, params=params))

    def result(self, method, **params):
        response = self.call(method, **params)
        self.assertTrue(response["ok"], response)
        return response["result"]

    def submit(self, approved=True):
        return self.result("submit", text="Synthetic group source.", partition="rational",
                           exclamation=approved)["source_id"]

    def guards(self, source):
        info = self.api.brain.model.reset_info()
        return dict(expected_source_version=self.result("input_get", source_id=source)["source_version"],
                    expected_revision=info["input_revision"], expected_epoch=info["model_epoch"])

    def params(self, source, **changes):
        fields = dict(source_id=source, event_id="event", domain="daily", options=options(),
                      actual_choice_id="a", endorsed_choice_id="b", endorsement_partition="rational",
                      training_consent=True, **self.guards(source))
        fields.update(changes)
        return fields

    def save(self, source, **changes):
        return self.result("choice_feedback_set", **self.params(source, **changes))

    def rank(self):
        return self.result("preference_rank", options=options(), target="actual",
                           partition="rational", domain="daily")

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return tuple(db.iterdump())

    def raw(self, source):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT payload FROM brain_choice_feedback WHERE source_id=?",
                              (source,)).fetchone()[0]

    def make_legacy(self, source):
        payload = json.loads(self.raw(source))
        payload.pop("group_id")
        payload.pop("group_reviewed")
        self.assertEqual(set(payload), preferences.LEGACY_PAYLOAD_FIELDS)
        raw = json.dumps(payload, ensure_ascii=False, indent=2)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE brain_choice_feedback SET payload=? WHERE source_id=?", (raw, source))
        return raw

    def test_old_client_saves_drafts_and_three_group_events_in_one_source_train(self):
        source = self.submit()
        old = self.save(source)
        self.assertEqual((old["group_id"], old["group_reviewed"], old["model_active"]),
                         (None, False, False))
        self.assertEqual(self.rank()["training_groups"], 0)
        for i in range(3):
            self.save(source, event_id=f"event-{i}", group_id=f"group-{i}", group_reviewed=True)
        result = self.rank()
        self.assertEqual((result["status"], result["training_sources"], result["training_groups"]),
                         ("provisional", 1, 3))
        for i in range(3):
            self.save(source, event_id=f"event-{i}", group_id="same", group_reviewed=True)
        self.assertEqual(self.rank()["reason"], "insufficient_training_groups")
        self.assertEqual(self.rank()["training_groups"], 1)

    def test_group_false_nullable_and_ids_are_strict_at_api_and_store(self):
        source = self.submit()
        for fields in ({"group_id": None, "group_reviewed": True}, {"group_reviewed": True},
                       {"group_reviewed": None}, {"group_reviewed": 1}, {"group_reviewed": "false"},
                       {"group_id": False}, {"group_id": 1}, {"group_id": []},
                       {"group_id": ""}, {"group_id": " \t"}, {"group_id": "x" * 129},
                       {"group_id": "bad\0"}, {"group_id": "\udfff"}, {"unexpected": True}):
            with self.subTest(fields=repr(fields)):
                before = self.dump()
                params = self.params(source, **fields)
                response = self.call("choice_feedback_set", **params)
                self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
                if "unexpected" not in fields:
                    with self.assertRaises(ValueError):
                        preferences.set_feedback(self.api.brain.store, **params)
                self.assertEqual(self.dump(), before)
        for group_id in (None, "draft", "😀" * 128):
            saved = self.save(source, group_id=group_id, group_reviewed=False)
            self.assertFalse(saved["model_active"])
        self.assertTrue(self.save(source, group_id="😀" * 128, group_reviewed=True)["model_active"])

    def test_legacy_exact_raw_normalizes_without_writes_or_training_after_restart(self):
        sources = [self.submit() for _ in range(3)]
        raw = {}
        for source in sources:
            self.save(source, group_id=source, group_reviewed=True)
            raw[source] = self.make_legacy(source)
        before = self.dump()
        for restart in (False, True):
            if restart:
                self.api = BrainAPI(self.path)
            for source in sources:
                item = self.result("choice_feedback_get", source_id=source)["records"][0]
                self.assertEqual((item["group_id"], item["group_reviewed"], item["model_active"]),
                                 (None, False, False))
                self.assertEqual(self.raw(source), raw[source])
            self.assertEqual(self.rank()["training_groups"], 0)
            self.assertEqual(self.dump(), before)
        # A guarded old-client replacement is still a draft. Explicit reviewed
        # group saves are the only way to enlist this feedback.
        self.save(sources[0])
        self.assertEqual(self.rank()["training_groups"], 0)
        for source in sources:
            self.save(source, group_id=source, group_reviewed=True)
        self.assertEqual(self.rank()["status"], "provisional")

    def test_decoder_rejects_partial_new_and_unknown_payloads_without_repair(self):
        source = self.submit()
        self.save(source, group_id="reviewed", group_reviewed=True)
        original = json.loads(self.raw(source))
        for mutation in (lambda x: x.pop("group_id"), lambda x: x.pop("group_reviewed"),
                         lambda x: x.update(extra=True), lambda x: x.update(group_reviewed=1),
                         lambda x: x.update(group_id=None), lambda x: x.update(group_id=" ")):
            payload = copy.deepcopy(original)
            mutation(payload)
            raw = json.dumps(payload)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("UPDATE brain_choice_feedback SET payload=? WHERE source_id=?", (raw, source))
            before = self.dump()
            self.assertEqual(self.call("choice_feedback_get", source_id=source)["error"]["code"],
                             "INVALID_ARGUMENT")
            self.assertEqual(self.rank()["reason"], "invalid_feedback_snapshot")
            self.assertEqual(self.dump(), before)

    def test_group_reassignment_stale_revision_epoch_and_version_guards(self):
        source = self.submit()
        self.save(source, group_id="original", group_reviewed=True)
        stale = self.guards(source)
        self.save(source, group_id="new", group_reviewed=True)
        before = self.dump()
        response = self.call("choice_feedback_set", **self.params(
            source, group_id="stale", group_reviewed=True, **stale))
        self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.dump(), before)
        for guard in ("expected_source_version", "expected_revision", "expected_epoch"):
            params = self.params(source, group_id="bad", group_reviewed=True)
            params[guard] += 1
            self.assertEqual(self.call("choice_feedback_set", **params)["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(json.loads(self.raw(source))["group_id"], "new")

    def test_group_review_consent_and_source_double_approval_are_independent(self):
        source = self.submit(approved=False)
        self.assertFalse(self.save(source, group_id="group", group_reviewed=True)["model_active"])
        self.result("review", source_id=source, agree=True)
        self.assertTrue(self.result("choice_feedback_get", source_id=source)["records"][0]["model_active"])
        self.assertFalse(self.save(source, group_id="group", group_reviewed=False)["model_active"])
        self.assertFalse(self.save(source, group_id="group", group_reviewed=True,
                                   training_consent=False)["model_active"])

    def test_reset_restart_and_reopen_need_explicit_group_save_to_reenlist(self):
        source = self.submit()
        for i in range(3):
            self.save(source, event_id=f"event-{i}", group_id=f"group-{i}", group_reviewed=True)
        self.assertEqual(self.rank()["status"], "provisional")
        stale = self.guards(source)
        info = self.api.brain.model.reset_info()
        self.api.brain.model.reset_model(confirmation="RESET_MODEL", expected_epoch=info["model_epoch"],
                                        expected_revision=info["input_revision"])
        self.api = BrainAPI(self.path)
        self.result("review", source_id=source, agree=True)
        self.assertEqual(self.rank()["training_groups"], 0)
        self.assertEqual(self.call("choice_feedback_set", **self.params(
            source, group_id="stale", group_reviewed=True, **stale))["error"]["code"], "INVALID_ARGUMENT")
        self.save(source, event_id="event-0")
        self.assertEqual(self.rank()["training_groups"], 0)
        for i in range(3):
            self.save(source, event_id=f"event-{i}", group_id=f"group-{i}", group_reviewed=True)
        self.assertEqual(self.rank()["status"], "provisional")
        self.result("correction_reopen", source_id=source, corrections=[], immediate=True,
                    **self.guards(source))
        self.result("review_version", source_id=source, agree=True, **self.guards(source))
        self.assertEqual(self.rank()["training_groups"], 0)
        for i in range(3):
            self.save(source, event_id=f"event-{i}", group_id=f"group-{i}", group_reviewed=True)
        self.assertEqual(self.rank()["status"], "provisional")

    def test_revoke_f6_purge_and_delete_group_events(self):
        source = self.submit()
        self.save(source, group_id="group", group_reviewed=True)
        self.result("revoke", source_id=source)
        self.assertEqual(self.rank()["training_groups"], 0)
        self.result("input_edit", source_id=source, text="Edited synthetic group source.", immediate=True)
        self.assertEqual(self.result("choice_feedback_get", source_id=source)["records"], [])
        self.result("review", source_id=source, agree=True)
        self.assertEqual(self.rank()["training_groups"], 0)
        self.save(source, group_id="new", group_reviewed=True)
        self.result("input_delete", source_id=source)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM brain_choice_feedback").fetchone()[0], 0)

    def test_group_metadata_bounded_fit_snapshot_no_private_text_or_fit_writes(self):
        source = self.submit()
        for i in range(3):
            self.save(source, event_id=f"event-{i}", group_id=f"group-{i}", group_reviewed=True,
                      reason="Synthetic display-only text.")
        before = self.dump()
        fit = preferences.fit_preferences
        def inspect(records, **kwargs):
            self.assertEqual({item["group_id"] for item in records}, {"group-0", "group-1", "group-2"})
            self.assertTrue(all(item["group_reviewed"] is True for item in records))
            self.assertTrue(all("reason" not in item and "body" not in item for item in records))
            return fit(records, **kwargs)
        with patch("model.preferences.fit_preferences", side_effect=inspect):
            self.assertEqual(self.rank()["status"], "provisional")
        self.assertEqual(self.dump(), before)

    def test_many_online_source_ids_one_group_never_cross_gate(self):
        sources = [self.submit() for _ in range(3)]
        for source in sources:
            self.save(source, group_id="one-event", group_reviewed=True)
        fit = self.rank()
        self.assertEqual((fit["training_sources"], fit["training_groups"]), (3, 1))
        self.assertEqual(fit["reason"], "insufficient_training_groups")

    def test_backup_preserves_reviewed_and_exact_legacy_payload_without_backfill(self):
        source = self.submit()
        for i in range(3):
            self.save(source, event_id=f"event-{i}", group_id=f"group-{i}", group_reviewed=True)
        legacy_source = self.submit()
        self.save(legacy_source)
        legacy_raw = self.make_legacy(legacy_source)
        expected_feedback = self.result("choice_feedback_get", source_id=source)
        expected_rank = self.rank()
        self.assertEqual(expected_rank["status"], "provisional")
        with closing(sqlite3.connect(self.path)) as db:
            ddl_before = tuple(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name"))
        before = self.dump()
        validate_database(self.path)
        setup_access(self.path, "synthetic access password")
        session = AccessSession(self.path)
        session.unlock("synthetic access password")
        output = Path(self.temp.name) / "group-backup.alpha"
        target = Path(self.temp.name) / "group-restored.sqlite3"
        create_backup(self.path, output, "synthetic backup password", session=session)
        restore_backup(output, target, "synthetic backup password", "synthetic restored password")
        validate_database(target)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(tuple(db.iterdump()), before)
            self.assertEqual(tuple(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")),
                             ddl_before)
            self.assertEqual(db.execute("SELECT payload FROM brain_choice_feedback WHERE source_id=?",
                                        (legacy_source,)).fetchone()[0], legacy_raw)
        self.assertEqual(self.dump(), before)
        restored = BrainAPI(target)
        locked = restored.handle(dict(schema_version=1, id="backup", method="choice_feedback_get",
                                      params=dict(source_id=source)))
        self.assertEqual(locked["error"]["code"], "LOCKED")
        restored.handle(dict(schema_version=1, id="backup", method="unlock",
                             params=dict(password="synthetic restored password")))
        original_path, self.path = self.path, target
        self.api = restored
        self.assertEqual(self.result("choice_feedback_get", source_id=source), expected_feedback)
        legacy = self.result("choice_feedback_get", source_id=legacy_source)["records"][0]
        self.assertEqual((legacy["group_id"], legacy["group_reviewed"], legacy["model_active"]),
                         (None, False, False))
        self.assertEqual(self.rank(), expected_rank)
        self.assertEqual(self.raw(legacy_source), legacy_raw)
        self.assertEqual(self.dump(), before)
        self.path = original_path


if __name__ == "__main__":
    unittest.main()
