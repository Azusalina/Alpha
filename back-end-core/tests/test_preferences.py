"""Synthetic choice labels/impacts and temporary SQLite databases only."""

import copy
import hashlib
import json
import math
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from core.pagination import revision
from model import BrainModel, preferences, reset, sources
from model.catalog import BASELINE_PATH, PARAMETERS, PARTITIONS
from model.ranking import VALUE_PARAMETERS


def options():
    return [{"id": "a", "label": "Autonomy", "impacts": {"value.autonomy": 1}},
            {"id": "b", "label": "Connection", "impacts": {"value.autonomy": -1}}]


def record(source, *, actual="a", endorsed="b", partition="rational", domain="daily",
           endorsement_partition="rational", opts=None):
    return {"source_id": source, "partition": partition, "domain": domain,
            "options": options() if opts is None else opts, "actual_choice_id": actual,
            "endorsed_choice_id": endorsed,
            "endorsement_partition": endorsement_partition if endorsed is not None else None}


class PurePreferenceTests(unittest.TestCase):
    def fit(self, records, **kwargs):
        return preferences.fit_preferences(records, target=kwargs.pop("target", "actual"),
                                           partition=kwargs.pop("partition", "rational"),
                                           domain=kwargs.pop("domain", "daily"), **kwargs)

    def test_actual_vs_endorsed_reversal_and_pure_input_unchanged(self):
        records = [record(str(i)) for i in range(3)]
        before = copy.deepcopy(records)
        actual, endorsed = self.fit(records), self.fit(records, target="endorsed")
        self.assertEqual(records, before)
        self.assertEqual(actual["status"], "provisional")
        self.assertEqual(actual["training_sources"], 3)
        self.assertGreater(actual["weights"]["value.autonomy"], 0)
        self.assertLess(endorsed["weights"]["value.autonomy"], 0)
        self.assertEqual(preferences.rank_from_fit(options(), actual)[0]["id"], "a")
        self.assertEqual(preferences.rank_from_fit(options(), endorsed)[0]["id"], "b")
        self.assertEqual(set(actual["weights"]), set(VALUE_PARAMETERS))
        self.assertTrue(actual["not_calibrated"])
        self.assertTrue(all(value == 0 for key, value in actual["weights"].items()
                            if key != "value.autonomy"))

    def test_three_partitions_and_domains_are_isolated(self):
        records = [record(f"{p}-{d}-{i}", partition=p, domain=d,
                          actual="a" if p == "rational" else "b")
                   for p in PARTITIONS for d in preferences.DOMAINS for i in range(3)]
        for partition in PARTITIONS:
            for domain in preferences.DOMAINS:
                fit = self.fit(records, partition=partition, domain=domain)
                self.assertEqual(fit["training_sources"], 3)
                self.assertEqual(preferences.rank_from_fit(options(), fit)[0]["id"],
                                 "a" if partition == "rational" else "b")
        for partition in ("emotional", "crazy"):
            self.assertEqual(self.fit(records, target="endorsed", partition=partition)["reason"],
                             "endorsed_requires_rational_partition")

    def test_endorsements_use_endorsement_partition_not_source_partition(self):
        records = [record(str(i), partition="crazy") for i in range(3)]
        self.assertEqual(self.fit(records)["status"], "abstain")
        self.assertEqual(self.fit(records, target="endorsed")["status"], "provisional")
        for partition in ("emotional", "crazy"):
            nonrational = [record(str(i), endorsement_partition=partition) for i in range(3)]
            self.assertEqual(self.fit(nonrational, target="endorsed")["training_sources"], 0)

    def test_source_normalization_duplication_cannot_dominate(self):
        records = [record("one", actual="b"), record("two"), record("three")]
        fit = self.fit(records)
        duplicated = self.fit([records[0]] * 32 + records[1:])
        self.assertEqual(duplicated["training_sources"], 3)
        for key in VALUE_PARAMETERS:
            self.assertAlmostEqual(fit["weights"][key], duplicated["weights"][key], places=12)
        self.assertEqual(preferences.rank_from_fit(options(), duplicated)[0]["id"], "a")
        self.assertEqual(self.fit([records[0]] * 32)["status"], "abstain")

    def test_counterexamples_cancellation_constant_missing_and_tied_impacts(self):
        balanced = [record(str(i), actual="a" if i % 2 == 0 else "b") for i in range(4)]
        self.assertEqual(self.fit(balanced)["reason"], "no_identifiable_preference")
        for opts in ([{"id": "a", "impacts": {}}, {"id": "b", "impacts": {}}],
                     [{"id": "a", "impacts": {"value.autonomy": 1}},
                      {"id": "b", "impacts": {"value.autonomy": 1}}]):
            self.assertEqual(self.fit([record(str(i), opts=opts) for i in range(3)])["status"], "abstain")
        missing = [record(str(i), actual=None, endorsed=None) for i in range(3)]
        self.assertEqual(self.fit(missing)["training_sources"], 0)
        fit = self.fit([record(str(i)) for i in range(3)])
        opts = [{"id": "a", "impacts": {"value.connection": 1}},
                {"id": "b", "impacts": {"value.connection": -1}}]
        self.assertEqual(preferences.rank_from_fit(opts, fit), [])
        opts.append({"id": "c", "impacts": {"value.autonomy": -1}})
        self.assertEqual(preferences.rank_from_fit(opts, fit), [])  # top tie, not all scores equal

    def test_real_option_labels_nonfinite_and_explicit_flags(self):
        records = [record(str(i)) for i in range(3)]
        for label in (True, False, 0, "missing", "a\0", "\ud800"):
            invalid = copy.deepcopy(records)
            invalid[0]["actual_choice_id"] = label
            with self.subTest(label=repr(label)), self.assertRaises(ValueError):
                self.fit(invalid)
        for value in (float("nan"), float("inf"), -float("inf"), True, 1.1, 10 ** 1000):
            invalid = copy.deepcopy(records)
            invalid[0]["options"][0]["impacts"]["value.autonomy"] = value
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                self.fit(invalid)
        for field in ("training_consent", "model_active"):
            invalid = copy.deepcopy(records)
            invalid[0][field] = False
            self.assertEqual(self.fit(invalid)["status"], "abstain")
            invalid[0][field] = 1
            with self.assertRaises(ValueError):
                self.fit(invalid)

    def test_scoring_contributions_and_softmax_are_finite_and_sum(self):
        records = [record(str(i)) for i in range(3)]
        ranked = preferences.rank_from_fit(options(), self.fit(records))
        self.assertAlmostEqual(sum(item["model_probability"] for item in ranked), 1)
        for item in ranked:
            self.assertEqual(set(item["contributions"]), set(VALUE_PARAMETERS))
            self.assertAlmostEqual(item["score"], sum(item["contributions"].values()))
            self.assertTrue(math.isfinite(item["score"]))
        self.assertEqual(preferences.rank_from_fit(options(), self.fit([])), [])
        with self.assertRaises(ValueError):
            preferences.rank_from_fit(options(), {"status": "provisional", "weights": {}})
        for value in (True, float("nan"), float("inf"), 1e300):
            fit = self.fit(records)
            fit["weights"]["value.autonomy"] = value
            with self.assertRaises(ValueError):
                preferences.rank_from_fit(options(), fit)

    def test_fit_bounded_and_request_validation(self):
        self.assertEqual(self.fit([record("same")] * 1001)["reason"], "too_many_feedback_records")
        for kwargs in ({"target": "unknown"}, {"partition": None}, {"domain": "work"}):
            with self.assertRaises(ValueError):
                self.fit([], **kwargs)

    def test_unsupported_contrasts_are_not_neutral_and_constants_are_allowed(self):
        fit = self.fit([record(str(i)) for i in range(3)])
        self.assertEqual(fit["used_features"], ["value.autonomy"])
        opts = options()
        opts[0]["impacts"]["value.care"] = 1
        self.assertEqual(preferences.rank_from_fit(opts, fit), [])
        opts[1]["impacts"]["value.care"] = 1
        self.assertEqual(preferences.rank_from_fit(opts, fit)[0]["id"], "a")
        # Irrelevant domains cannot supply identifiability to this fit.
        records = [record(str(i)) for i in range(3)]
        records += [record("other", domain="study", opts=[
            {"id": "a", "impacts": {"value.care": 1}},
            {"id": "b", "impacts": {"value.care": -1}}])]
        self.assertEqual(self.fit(records)["used_features"], ["value.autonomy"])


class StoredPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.model = BrainModel(self.path)
        self.store = self.model.store
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            preferences.initialize(db)

    def submit(self, partition="rational", *, approved=True, immediate=True):
        return self.model.submit("Synthetic choice source.", partition=partition,
                                 immediate=immediate, exclamation=approved)

    def guards(self, source):
        with self.store._connect() as db:
            db.execute("BEGIN")
            return {"expected_source_version": db.execute(
                "SELECT source_version FROM brain_inputs WHERE source_id=?", (source,)).fetchone()[0],
                "expected_revision": revision(db), "expected_epoch": reset.epoch(db)}

    def save(self, source, **overrides):
        args = {"source_id": source, "event_id": "event", "domain": "daily", "options": options(),
                "actual_choice_id": "a", "endorsed_choice_id": "b", "endorsement_partition": "rational",
                "training_consent": True, **self.guards(source)}
        args.update(overrides)
        return preferences.set_feedback(self.store, **args)

    def rank(self, **overrides):
        args = {"options": options(), "target": "actual", "partition": "rational", "domain": "daily"}
        args.update(overrides)
        return preferences.rank_preferences(self.store, **args)

    def snapshot(self):
        with self.store._connect() as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {table: sorted([tuple(r) for r in db.execute(f'SELECT * FROM "{table}"')], key=repr)
                    for table in tables}

    def zero(self):
        info = self.model.reset_info()
        return self.model.reset_model(confirmation="RESET_MODEL", expected_epoch=info["model_epoch"],
                                      expected_revision=info["input_revision"])

    def test_initialize_is_additive_idempotent_and_fk_cascades(self):
        source = self.submit()
        self.save(source)
        before = self.snapshot()
        with self.store._connect() as db:
            preferences.initialize(db)
            fk = db.execute("PRAGMA foreign_key_list(brain_choice_feedback)").fetchone()
            self.assertEqual((fk["table"], fk["from"], fk["to"], fk["on_delete"]),
                             ("sources", "source_id", "id", "CASCADE"))
            columns = db.execute("PRAGMA table_info(brain_choice_feedback)").fetchall()
            self.assertEqual({r["name"]: r["pk"] for r in columns if r["pk"]},
                             {"source_id": 1, "event_id": 2})
        self.assertEqual(self.snapshot(), before)
        # Test actual FK cascade even if main's optional purge is integrated.
        with self.store._connect() as db:
            db.execute("DELETE FROM brain_effects WHERE source_id=?", (source,))
            for table in sources.DEPENDENT_TABLES:
                if table != "brain_choice_feedback":
                    db.execute(f"DELETE FROM {table} WHERE source_id=?", (source,))
            db.execute("DELETE FROM brain_inputs WHERE source_id=?", (source,))
            db.execute("DELETE FROM sources WHERE id=?", (source,))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM brain_choice_feedback").fetchone()[0], 0)

    def test_public_payload_shape_replacement_and_revision(self):
        source = self.submit()
        guards = self.guards(source)
        result = self.save(source, reason="Reviewed labels and impacts.")
        self.assertEqual(set(result), preferences.PAYLOAD_FIELDS | {"model_active", "input_revision"})
        self.assertTrue(result["model_active"])
        self.assertEqual(result["input_revision"], guards["expected_revision"] + 1)
        self.assertEqual(result["body_digest"], hashlib.sha256(b"Synthetic choice source.").hexdigest())
        with self.store._connect() as db:
            payload = json.loads(db.execute("SELECT payload FROM brain_choice_feedback").fetchone()[0])
        self.assertEqual(set(payload), preferences.PAYLOAD_FIELDS)
        replacement = self.save(source, actual_choice_id=None, endorsed_choice_id=None,
                                endorsement_partition=None, training_consent=False,
                                options=[{"id": "new-a", "impacts": {}}, {"id": "new-b", "impacts": {}}])
        self.assertFalse(replacement["model_active"])
        self.assertIsNone(replacement["reason"])
        self.assertIsNone(replacement["actual_choice_id"])
        fetched = preferences.get_feedback(self.store, source)
        self.assertEqual(set(fetched), {"source_id", "records", "input_revision", "model_epoch"})
        self.assertEqual(fetched["records"], [{k: v for k, v in replacement.items() if k != "input_revision"}])
        self.assertEqual(BrainModel(self.path).state(), self.model.state())

    def test_pending_double_approval_and_training_consent_are_independent(self):
        ids = [self.submit(approved=False) for _ in range(3)]
        for source in ids:
            self.assertFalse(self.save(source)["model_active"])
        self.assertEqual(self.rank()["training_sources"], 0)
        for source in ids:
            self.model.review(source, agree=True)
        self.assertEqual(self.rank()["status"], "provisional")
        self.assertTrue(preferences.get_feedback(self.store, ids[0])["records"][0]["model_active"])
        self.save(ids[0], training_consent=False)
        self.assertEqual(self.rank()["status"], "abstain")
        self.save(ids[0], training_consent=True)
        self.assertEqual(self.rank()["status"], "provisional")
        declined = self.submit(approved=False, immediate=False)
        self.assertFalse(self.save(declined)["model_active"])
        self.assertEqual(self.rank()["training_sources"], 3)

    def test_trained_live_rerank_and_no_rule_state_history_updates(self):
        ids = [self.submit() for _ in range(3)]
        before = self.snapshot()
        baseline_hash = hashlib.sha256(BASELINE_PATH.read_bytes()).digest()
        self.assertEqual(self.rank()["status"], "abstain")
        for source in ids:
            self.save(source)
        actual, endorsed = self.rank(), self.rank(target="endorsed")
        self.assertEqual(actual["ranked"][0]["id"], "a")
        self.assertEqual(endorsed["ranked"][0]["id"], "b")
        self.assertTrue(actual["not_calibrated"])
        self.assertEqual(len(PARAMETERS), 13)
        self.assertEqual(len(actual["weights"]), 8)
        after = self.snapshot()
        for table in before.keys() - {"brain_meta", "brain_choice_feedback"}:
            self.assertEqual(before[table], after[table], table)
        before_meta, after_meta = dict(before["brain_meta"]), dict(after["brain_meta"])
        before_meta.pop(sources.GENERATION_KEY)
        after_meta.pop(sources.GENERATION_KEY)
        self.assertEqual(before_meta, after_meta)
        self.assertEqual(hashlib.sha256(BASELINE_PATH.read_bytes()).digest(), baseline_hash)
        for source in ids:
            self.save(source, actual_choice_id="b")
        self.assertEqual(self.rank()["ranked"][0]["id"], "b")
        unchanged = self.snapshot()
        self.rank()
        preferences.get_feedback(self.store, ids[0])
        self.assertEqual(self.snapshot(), unchanged)

    def test_store_filters_three_partitions_domains_and_endorsement_scope(self):
        for partition in PARTITIONS:
            for domain in preferences.DOMAINS:
                for _ in range(3):
                    self.save(self.submit(partition), domain=domain,
                              endorsement_partition="emotional" if partition == "emotional" else "rational")
        for partition in PARTITIONS:
            for domain in preferences.DOMAINS:
                self.assertEqual(self.rank(partition=partition, domain=domain)["training_sources"], 3)
        self.assertEqual(self.rank(target="endorsed")["training_sources"], 6)
        self.assertEqual(self.rank(target="endorsed", partition="crazy")["status"], "abstain")

    def test_global_stale_source_guards_nonbool_integer_and_rollback(self):
        source, other = self.submit(), self.submit()
        stale = self.guards(source)
        self.save(other)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.save(source, **stale)
        for field in ("expected_source_version", "expected_revision", "expected_epoch"):
            for value in (True, False, -1, 0.0, "0", None):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.save(source, **{field: value})
            with self.assertRaises(ValueError):
                self.save(source, **{field: self.guards(source)[field] + 1})
        self.assertEqual(self.snapshot(), before)
        with patch("model.preferences.sources.bump_generation", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                self.save(source)
        self.assertEqual(self.snapshot(), before)

    def test_concurrent_guarded_replacements_only_one_commits(self):
        source = self.submit()
        guards = self.guards(source)
        def attempt(label):
            try:
                return self.save(source, actual_choice_id=label, **guards)
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ("a", "b")))
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(preferences.get_feedback(self.store, source)["input_revision"],
                         guards["expected_revision"] + 1)

    def test_reset_excludes_old_feedback_only_explicit_guarded_save_reenlists(self):
        ids = [self.submit() for _ in range(3)]
        for source in ids:
            self.save(source)
        stale = self.guards(ids[0])
        self.zero()
        self.assertEqual(self.rank()["training_sources"], 0)
        envelope = preferences.get_feedback(self.store, ids[0])
        self.assertEqual(envelope["model_epoch"], 1)
        self.assertEqual(envelope["records"][0]["model_epoch"], 0)
        self.assertFalse(envelope["records"][0]["model_active"])
        with self.assertRaises(ValueError):
            self.save(ids[0], **stale)
        # Restoring a rule fit does not reenlist feedback in the new epoch.
        self.model.review(ids[0], agree=True)
        self.assertEqual(self.rank()["training_sources"], 0)
        for source in ids:
            self.assertTrue(self.save(source)["model_active"])
        self.assertEqual(self.rank()["status"], "provisional")
        with self.store._connect() as db:
            self.assertEqual(db.execute("SELECT model_epoch FROM brain_inputs WHERE source_id=?",
                                        (ids[1],)).fetchone()[0], 0)
        # Active feedback does not pretend the old rule source was restored.
        self.assertEqual(preferences.get_feedback(self.store, ids[1])["records"][0]["model_epoch"], 1)

    def test_revoke_restore_and_hard_delete_eligibility(self):
        ids = [self.submit() for _ in range(3)]
        for source in ids:
            self.save(source)
        self.model.revoke(ids[0])
        self.assertEqual(self.rank()["status"], "abstain")
        self.assertFalse(preferences.get_feedback(self.store, ids[0])["records"][0]["model_active"])
        self.model.review(ids[0], agree=True)
        self.assertEqual(self.rank()["status"], "provisional")
        self.model.input_delete(ids[0])
        self.assertEqual(self.rank()["training_sources"], 2)
        with self.store._connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM brain_choice_feedback WHERE source_id=?",
                                         (ids[0],)).fetchone())
        with self.assertRaises(KeyError):
            preferences.get_feedback(self.store, ids[0])

    def test_source_version_change_excludes_until_explicit_replacement(self):
        source = self.submit()
        self.save(source)
        self.model.correction_reopen(source, corrections=[], immediate=True, **self.guards(source))
        self.model.review_version(source, agree=True, **self.guards(source))
        self.assertFalse(preferences.get_feedback(self.store, source)["records"][0]["model_active"])
        self.assertEqual(self.rank()["training_sources"], 0)
        result = self.save(source)
        self.assertEqual(result["source_version"], 1)
        self.assertTrue(result["model_active"])

    def test_f6_before_main_purge_hook_digest_blocks_same_version_old_feedback(self):
        source = self.submit()
        self.save(source, reason="Old event details.")
        self.model.revoke(source)
        # Deliberately emulate the pre-integration purge even when main adds its
        # optional table hook concurrently. This documents retention until hook.
        def legacy_purge(db, source_id):
            for table in sources.DEPENDENT_TABLES:
                if table != "brain_choice_feedback":
                    db.execute(f"DELETE FROM {table} WHERE source_id=?", (source_id,))
        with patch("model.sources.purge_dependents", side_effect=legacy_purge):
            self.model.input_edit(source, "Changed synthetic source.", immediate=True)
        self.model.review(source, agree=True)
        public = preferences.get_feedback(self.store, source)["records"][0]
        self.assertEqual(public["source_version"], self.guards(source)["expected_source_version"])
        self.assertFalse(public["model_active"])
        self.assertEqual(public["reason"], "Old event details.")
        self.assertEqual(self.rank()["training_sources"], 0)
        self.assertTrue(self.save(source)["model_active"])

    def test_event_and_payload_bounds_replacement_at_capacity(self):
        source = self.submit()
        for i in range(32):
            self.save(source, event_id=str(i))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.save(source, event_id="33")
        self.assertEqual(self.snapshot(), before)
        self.save(source, event_id="0", reason="replacement")
        self.assertEqual(len(preferences.get_feedback(self.store, source)["records"]), 32)
        # Persisted payloads have a DB byte bound as well as bounded API fields.
        with self.assertRaises(sqlite3.IntegrityError), self.store._connect() as db:
            db.execute("UPDATE brain_choice_feedback SET payload=?", ("x" * 65537,))

    def test_valid_unicode_boundary_text_and_reason_optional(self):
        source = self.submit()
        opts = [{"id": "😀" * 128, "label": "😀" * 512,
                 "impacts": {key: 1 for key in VALUE_PARAMETERS}},
                {"id": "β", "impacts": {key: -1 for key in VALUE_PARAMETERS}}]
        result = self.save(source, event_id="😀" * 128, options=opts,
                           actual_choice_id=opts[0]["id"], endorsed_choice_id="β", reason="😀" * 2048)
        self.assertEqual(result["event_id"], "😀" * 128)
        json.dumps(result, allow_nan=False).encode("utf-8")

    def test_strict_input_validation_no_partial_writes(self):
        source = self.submit()
        bad = [{"event_id": ""}, {"event_id": "x" * 129}, {"event_id": "a\0"},
               {"event_id": "\ud800"}, {"source_id": "\udfff"}, {"domain": "unknown"},
               {"domain": []}, {"training_consent": 1}, {"training_consent": None},
               {"actual_choice_id": True}, {"actual_choice_id": "unknown"},
               {"endorsed_choice_id": "b", "endorsement_partition": None},
               {"endorsed_choice_id": None}, {"endorsement_partition": "other"},
               {"reason": "x" * 2049}, {"reason": "a\0"}, {"reason": "\udfff"},
               {"options": options()[:1]}, {"options": options() * 5},
               {"options": [{**options()[0], "extra": 1}, options()[1]]},
               {"options": [{"id": "a", "impacts": {}, "label": None}, options()[1]]},
               {"options": [{"id": "a", "impacts": {}, "label": "x" * 513}, options()[1]]},
               {"options": [{"id": "a", "impacts": {}, "label": "\ud800"}, options()[1]]},
               {"options": [{"id": "a", "impacts": {}, "label": "x\0"}, options()[1]]},
               {"options": [options()[0], options()[0]]},
               {"options": [{"id": "a", "impacts": {"decision.outcome_utility": 1}}, options()[1]]}]
        for value in (True, float("nan"), float("inf"), -1.01, "1", 10 ** 1000):
            bad.append({"options": [{"id": "a", "impacts": {"value.autonomy": value}}, options()[1]]})
        before = self.snapshot()
        for args in bad:
            with self.subTest(args=repr(args)), self.assertRaises(ValueError):
                self.save(source, **args)
            self.assertEqual(self.snapshot(), before)

    def test_unknown_sources_not_legacy_and_no_provenance_free_store_fit(self):
        with self.assertRaises(KeyError):
            preferences.set_feedback(self.store, "missing", "event", "daily", options(),
                                     "a", "b", "rational", True, 0, 0, 0)
        legacy = self.store.add_source("Synthetic standalone source.")
        with self.assertRaises(KeyError):
            preferences.set_feedback(self.store, legacy, "event", "daily", options(),
                                     "a", "b", "rational", True, 0, 0, 0)
        # Live rank signature has no records argument: provided labels only enter
        # through guarded, source-bound set_feedback. Offline fit is explicit.
        with self.assertRaises(TypeError):
            preferences.rank_preferences(self.store, options(), "actual", "rational", "daily", records=[])

    def test_corrupt_provenance_fails_closed_and_read_does_not_repair(self):
        ids = [self.submit() for _ in range(3)]
        for source in ids:
            self.save(source)
        with self.store._connect() as db:
            row = db.execute("SELECT payload FROM brain_choice_feedback WHERE source_id=?", (ids[0],)).fetchone()
            payload = json.loads(row[0])
            payload["source_version"] = 99
            db.execute("UPDATE brain_choice_feedback SET payload=? WHERE source_id=?",
                       (json.dumps(payload), ids[0]))
        before = self.snapshot()
        self.assertEqual(self.rank()["reason"], "invalid_feedback_snapshot")
        with self.assertRaises(ValueError):
            preferences.get_feedback(self.store, ids[0])
        self.assertEqual(self.snapshot(), before)

    def test_oversized_snapshot_abstains_without_fitting_prefix(self):
        seed = self.submit()
        self.save(seed)
        with self.store._connect() as db:
            template = dict(db.execute("SELECT * FROM brain_choice_feedback").fetchone())
            payload = json.loads(template["payload"])
            # Synthetic SQL fixture exceeds the public bound to exercise the
            # bounded rank read without constructing/fitting 1001 real sources.
            for i in range(1000):
                item = {**payload, "event_id": f"fixture-{i}"}
                db.execute("INSERT INTO brain_choice_feedback VALUES (?,?,?,?,?,?,?)",
                           (seed, item["event_id"], item["source_version"], item["model_epoch"],
                            item["body_digest"], item["created_at"], json.dumps(item)))
        with patch("model.preferences.fit_preferences", side_effect=AssertionError("must not fit prefix")):
            self.assertEqual(self.rank()["reason"], "too_many_feedback_records")
        with self.assertRaises(ValueError):
            preferences.get_feedback(self.store, seed)

    def test_unsupported_features_live_abstention_and_top_ties(self):
        for _ in range(3):
            self.save(self.submit())
        opts = options()
        opts[0]["impacts"]["value.care"] = 0.2
        ranked = self.rank(options=opts)
        self.assertEqual(ranked["reason"], "unsupported_option_features")
        self.assertEqual(ranked["ranked"], [])
        self.assertEqual(ranked["used_features"], ["value.autonomy"])
        opts[1]["impacts"]["value.care"] = 0.2
        self.assertEqual(self.rank(options=opts)["status"], "provisional")
        self.assertEqual(self.rank(options=[{"id": "a", "impacts": {}},
                                            {"id": "b", "impacts": {}}])["reason"],
                         "options_tied_with_learned_weights")

    def test_fit_runs_after_read_transaction_and_reports_snapshot_tokens(self):
        source = self.submit()
        for _ in range(3):
            self.save(self.submit())
        expected = self.guards(source)
        original = preferences.fit_preferences
        def concurrent_mutation(records, **kwargs):
            # A separate writer's commit would block on a held read transaction.
            self.save(source)
            return original(records, **kwargs)
        with patch("model.preferences.fit_preferences", side_effect=concurrent_mutation):
            ranked = self.rank()
        self.assertEqual(ranked["input_revision"], expected["expected_revision"])
        self.assertEqual(ranked["model_epoch"], expected["expected_epoch"])
        self.assertEqual(ranked["training_sources"], 3)
        self.assertGreater(self.guards(source)["expected_revision"], ranked["input_revision"])


if __name__ == "__main__":
    unittest.main()
