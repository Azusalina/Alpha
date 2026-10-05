"""Contrast-span integration using synthetic records and temporary databases only."""

import copy
import json
import math
import sqlite3
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from model import preferences
from model.ranking import VALUE_PARAMETERS
from tests.test_preferences import record


GROWTH, SECURITY = "value.growth", "value.security"


def pair(x=.5, y=.5):
    return [{"id": "a", "impacts": {GROWTH: x, SECURITY: y}},
            {"id": "b", "impacts": {GROWTH: -x, SECURITY: -y}}]


def fit(records, **changes):
    fields = dict(target="actual", partition="rational", domain="daily")
    fields.update(changes)
    return preferences.fit_preferences(records, **fields)


def cohort(opts=None, count=3):
    return [record(f"synthetic-{i}", opts=pair() if opts is None else copy.deepcopy(opts))
            for i in range(count)]


class PureSpanTests(unittest.TestCase):
    def assertGeometry(self, result, rank):
        self.assertEqual(result["contrast_rank"], rank)
        basis = result["contrast_basis"]
        self.assertEqual(len(basis), rank)
        for i, row in enumerate(basis):
            self.assertIsInstance(row, list)
            self.assertEqual(len(row), 8)
            self.assertTrue(all(type(x) is float and math.isfinite(x) and -1 <= x <= 1 for x in row))
            for j, other in enumerate(basis):
                self.assertAlmostEqual(math.fsum(x * y for x, y in zip(row, other)),
                                       float(i == j), delta=1e-12)

    def test_same_columns_unseen_growth_security_direction_rejected(self):
        result = fit(cohort())
        self.assertGeometry(result, 1)
        self.assertEqual(result["status"], "provisional")
        self.assertEqual(set(result["used_features"]), {GROWTH, SECURITY})
        unseen = pair(1, -.5)
        # The old column-only check admitted this with a nonzero score gap.
        gap = 2 * (result["weights"][GROWTH] - .5 * result["weights"][SECURITY])
        self.assertGreater(abs(gap), preferences.TIE_TOLERANCE)
        self.assertEqual(preferences.rank_from_fit(unseen, result), [])

    def test_span_allowed_query_has_nontrivial_scores_without_projection(self):
        result = fit(cohort())
        query = pair(.25, .25)
        before = copy.deepcopy((query, result))
        ranked = preferences.rank_from_fit(query, result)
        self.assertEqual([item["id"] for item in ranked], ["a", "b"])
        self.assertGreater(ranked[0]["score"] - ranked[1]["score"], preferences.TIE_TOLERANCE)
        self.assertAlmostEqual(ranked[0]["score"],
                               .25 * (result["weights"][GROWTH] + result["weights"][SECURITY]))
        self.assertEqual((query, result), before)

    def test_every_query_contrast_must_be_in_span(self):
        result = fit(cohort())
        query = pair()
        query.append({"id": "c", "impacts": {GROWTH: .25, SECURITY: -.25}})
        self.assertEqual(preferences.rank_from_fit(query, result), [])
        query[-1]["impacts"] = {GROWTH: -.25, SECURITY: -.25}
        self.assertEqual(len(preferences.rank_from_fit(query, result)), 3)

    def test_rank_two_allows_previously_unseen_direction(self):
        records = cohort()
        records[1]["options"] = pair(.5, -.5)
        result = fit(records)
        self.assertGeometry(result, 2)
        ranked = preferences.rank_from_fit(pair(1, -.5), result)
        self.assertEqual(ranked[0]["id"], "a")
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])

    def test_full_eight_dimensional_span_allows_new_query(self):
        records = [record(f"axis-{i}", opts=[
            {"id": "a", "impacts": {feature: .5}},
            {"id": "b", "impacts": {feature: -.5}}])
            for i, feature in enumerate(VALUE_PARAMETERS)]
        result = fit(records)
        self.assertGeometry(result, 8)
        query = [{"id": "a", "impacts": dict.fromkeys(VALUE_PARAMETERS, .25)},
                 {"id": "b", "impacts": dict.fromkeys(VALUE_PARAMETERS, -.25)}]
        self.assertEqual(preferences.rank_from_fit(query, result)[0]["id"], "a")

    def test_near_collinear_events_do_not_supply_an_independent_axis(self):
        records = cohort()
        records[1]["options"] = pair(.5, .5 + 1e-13)
        result = fit(records)
        self.assertGeometry(result, 1)
        self.assertEqual(preferences.rank_from_fit(pair(1, -.5), result), [])

    def test_common_offsets_zero_rows_and_order_preserve_geometry(self):
        original = fit(cohort())
        records = cohort()
        for item in records:
            for option in item["options"]:
                option["impacts"][GROWTH] += .25
                option["impacts"][SECURITY] -= .25
                option["impacts"][VALUE_PARAMETERS[0]] = .5
            item["options"].reverse()
        records.reverse()
        records.append(record("constant", opts=[
            {"id": "a", "impacts": {VALUE_PARAMETERS[1]: .5}},
            {"id": "b", "impacts": {VALUE_PARAMETERS[1]: .5}}]))
        shifted = fit(records)
        self.assertEqual(shifted["contrast_basis"], original["contrast_basis"])
        self.assertEqual((shifted["training_sources"], shifted["training_groups"]), (3, 3))
        for feature in VALUE_PARAMETERS:
            self.assertAlmostEqual(shifted["weights"][feature], original["weights"][feature], delta=1e-12)
        query = pair(.25, .25)
        for option in query:
            option["impacts"][VALUE_PARAMETERS[0]] = .5
        self.assertEqual(preferences.rank_from_fit(query, original)[0]["id"], "a")
        constants = [{"id": "a", "impacts": {}}, {"id": "b", "impacts": {}}]
        self.assertEqual(preferences.rank_from_fit(constants, original), [])
        self.assertGeometry(fit(cohort(constants)), 0)

    def test_canonical_record_and_option_order_preserves_exact_public_fit(self):
        records = cohort()
        records[1]["options"] = pair(.5, -.5)
        expected = fit(records)
        for item in records:
            item["options"].reverse()
        records.reverse()
        self.assertEqual(fit(records), expected)

    def test_option_id_and_label_renaming_preserves_semantic_geometry(self):
        # Near-dependent rows make a unit-normalized numerical rank policy
        # sensitive to a changed anchor. IDs must not choose that anchor.
        opts = [{"id": "a", "impacts": {GROWTH: 0, SECURITY: 0}},
                {"id": "b", "impacts": {GROWTH: .5, SECURITY: .5}},
                {"id": "c", "impacts": {GROWTH: 1, SECURITY: 1 - 5e-11}}]
        records = cohort(opts)
        original = fit(records)
        renamed = copy.deepcopy(records)
        mapping = {"a": "z", "b": "y", "c": "x"}
        for item in renamed:
            item["actual_choice_id"] = mapping[item["actual_choice_id"]]
            item["endorsed_choice_id"] = mapping[item["endorsed_choice_id"]]
            for option in item["options"]:
                option["id"] = mapping[option["id"]]
                option["label"] = "Renamed synthetic option " + option["id"]
        actual = fit(renamed)
        for field in ("contrast_rank", "contrast_basis", "used_features", "training_groups", "training_sources", "status"):
            self.assertEqual(actual[field], original[field], field)
        for feature in VALUE_PARAMETERS:
            self.assertAlmostEqual(actual["weights"][feature], original["weights"][feature], delta=1e-12)

    def test_pair_cancellation_checks_tiny_unsupported_direction(self):
        result = fit(cohort())
        # Strict metadata permits a varied column whose tiny direction was
        # discarded by the engineering rank policy.
        result["contrast_basis"] = [[float(feature == GROWTH) for feature in VALUE_PARAMETERS]]
        query = [{"id": "a", "impacts": {}},
                 {"id": "b", "impacts": {GROWTH: 1, SECURITY: .5e-12}},
                 {"id": "c", "impacts": {GROWTH: 1, SECURITY: -.5e-12}}]
        vectors = preferences._vectors(query)
        anchor_rows = [[x - y for x, y in zip(row, vectors[0])] for row in vectors[1:]]
        self.assertTrue(preferences.contains_contrasts(anchor_rows, result["contrast_basis"]))
        self.assertEqual(len(preferences._query_contrast_rows(vectors)), 3)
        self.assertEqual(preferences.rank_from_fit(query, result), [])

    def test_informative_events_only_and_axes_do_not_expand_geometry(self):
        other = pair(.5, -.5)
        exclusions = [
            dict(training_consent=False), dict(model_active=False),
            dict(group_reviewed=False), dict(actual_choice_id=None),
            dict(partition="emotional"), dict(domain="study"),
            dict(domain="relationships"),
        ]
        expected = fit(cohort())
        records = cohort() + [{**record(f"excluded-{i}", opts=other), **fields}
                              for i, fields in enumerate(exclusions)]
        # A labelled option duplicated in feature space is also uninformative.
        duplicate = pair(.5, -.5)
        duplicate.append({"id": "c", "impacts": dict(duplicate[0]["impacts"])})
        records.append(record("duplicate-label", opts=duplicate))
        self.assertEqual(fit(records), expected)
        endorsed_records = [{**item, "endorsed_choice_id": None,
                             "endorsement_partition": None} for item in cohort()]
        endorsed_records += [{**record("endorsed-only", opts=other), "actual_choice_id": None}]
        self.assertGeometry(fit(endorsed_records), 1)
        endorsed = fit(endorsed_records, target="endorsed")
        self.assertGeometry(endorsed, 1)
        self.assertEqual((endorsed["training_sources"], endorsed["training_groups"]), (1, 1))
        self.assertNotEqual(endorsed["contrast_basis"], expected["contrast_basis"])
        wrong_state = [{**record("wrong-state", opts=other), "endorsement_partition": "crazy"}]
        self.assertGeometry(fit(wrong_state, target="endorsed"), 0)

    def test_group_gate_and_source_counts_unchanged_geometry_exists_before_gate(self):
        records = [{**record(f"source-{i}", opts=pair()), "group_id": "one-group"}
                   for i in range(16)]
        result = fit(records)
        self.assertGeometry(result, 1)
        self.assertEqual((result["training_sources"], result["training_groups"]), (16, 1))
        self.assertEqual(result["reason"], "insufficient_training_groups")
        records = [{**record("one-source", opts=pair()), "group_id": f"group-{i}"}
                   for i in range(3)]
        result = fit(records)
        self.assertEqual((result["training_sources"], result["training_groups"]), (1, 3))
        self.assertEqual(result["status"], "provisional")
        self.assertGeometry(result, 1)

    def test_solver_failure_and_cancellation_retain_geometry_early_failure_defaults(self):
        for failure in ("fit_not_converged", "nonfinite_fit"):
            with patch.object(preferences, "_minimize", return_value=(None, failure)):
                result = fit(cohort())
            self.assertGeometry(result, 1)
            self.assertEqual(result["reason"], failure)
            self.assertEqual(result["ranked"], [])
        cancelled = cohort(count=4)
        for item in cancelled[2:]:
            item["actual_choice_id"] = "b"
        result = fit(cancelled)
        self.assertGeometry(result, 1)
        self.assertEqual(result["reason"], "no_identifiable_preference")
        for result in (fit([]), fit(cohort(count=1001)),
                       fit([], target="endorsed", partition="emotional")):
            self.assertGeometry(result, 0)

    def test_basis_built_from_at_most_seven_rows_per_event_without_solver_change(self):
        opts = [{"id": chr(97 + i), "impacts": {GROWTH: i / 8, SECURITY: i / 8}}
                for i in range(8)]
        records = cohort(opts, count=1000)
        with patch.object(preferences, "basis_from_contrasts", wraps=preferences.basis_from_contrasts) as build, \
                patch.object(preferences, "_minimize", return_value=(None, "fit_not_converged")) as solve:
            result = fit(records)
        rows = build.call_args.args[0]
        self.assertEqual(len(rows), 7000)
        self.assertTrue(all(len(row) == 8 for row in rows))
        normalized = solve.call_args.args[0]
        self.assertEqual(len(normalized), 1000)
        self.assertTrue(all(chosen == 0 and scale == .001 for _, chosen, scale in normalized))
        self.assertGeometry(result, 1)

    def test_provisional_metadata_strict_before_even_tied_or_unsupported_queries(self):
        valid = fit(cohort())
        mutations = [
            lambda x: x.pop("contrast_rank"), lambda x: x.pop("contrast_basis"),
            lambda x: x.update(contrast_rank=True), lambda x: x.update(contrast_rank=1.0),
            lambda x: x.update(contrast_rank=-1), lambda x: x.update(contrast_rank=9),
            lambda x: x.update(contrast_rank=0, contrast_basis=[]),
            lambda x: x.update(contrast_rank=2), lambda x: x.update(contrast_basis=()),
            lambda x: x.update(contrast_basis={}),
            lambda x: x["contrast_basis"][0].pop(),
            lambda x: x["contrast_basis"][0].append(0.0),
            lambda x: x["contrast_basis"][0].__setitem__(0, True),
            lambda x: x["contrast_basis"][0].__setitem__(0, math.nan),
            lambda x: x["contrast_basis"][0].__setitem__(0, math.inf),
            lambda x: x["contrast_basis"][0].__setitem__(0, -math.inf),
            lambda x: x["contrast_basis"][0].__setitem__(0, 1.1),
            lambda x: x.update(contrast_basis=[[0.0] * 5 + [1.0 + 5e-13, 0.0, 0.0]]),
            lambda x: x["contrast_basis"][0].__setitem__(0, 10 ** 1000),
            lambda x: x.update(contrast_basis=[tuple(x["contrast_basis"][0])]),
            lambda x: x.update(contrast_basis=[[0.0] * 8]),
            lambda x: x.update(contrast_rank=2, contrast_basis=x["contrast_basis"] * 2),
            lambda x: x.update(used_features=[GROWTH]),
            lambda x: x.update(contrast_basis=[[1.0] + [0.0] * 7]),
        ]
        tied = [{"id": "a", "impacts": {}}, {"id": "b", "impacts": {}}]
        for index, mutate in enumerate(mutations):
            for query in (pair(), tied, [{"id": "a", "impacts": {VALUE_PARAMETERS[0]: 1}},
                                         {"id": "b", "impacts": {}}]):
                with self.subTest(mutation=index, query=query):
                    invalid = copy.deepcopy(valid)
                    mutate(invalid)
                    with self.assertRaises(ValueError), \
                            patch.object(preferences, "_minimize", side_effect=AssertionError("pure scoring must not fit")):
                        preferences.rank_from_fit(query, invalid)


class LiveSpanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.api = BrainAPI(self.path)

    def call(self, method, **params):
        response = self.api.handle({"schema_version": 1, "id": "span-test", "method": method, "params": params})
        self.assertTrue(response["ok"], response.get("error"))
        return response["result"]

    def submit(self, **changes):
        fields = dict(text="Synthetic contrast source.", partition="rational", exclamation=True)
        fields.update(changes)
        return self.call("submit", **fields)["source_id"]

    def save(self, source, **changes):
        info = self.api.brain.model.reset_info()
        fields = dict(source_id=source, event_id="synthetic-event", options=pair(), domain="daily",
                      actual_choice_id="a", endorsed_choice_id="b", endorsement_partition="rational",
                      training_consent=True, group_id=source, group_reviewed=True,
                      expected_source_version=self.call("input_get", source_id=source)["source_version"],
                      expected_revision=info["input_revision"], expected_epoch=info["model_epoch"])
        fields.update(changes)
        return self.call("choice_feedback_set", **fields)

    def rank(self, **changes):
        fields = dict(options=pair(), target="actual", partition="rational", domain="daily")
        fields.update(changes)
        return self.call("preference_rank", **fields)

    def seed(self):
        sources = [self.submit() for _ in range(3)]
        for source in sources:
            self.save(source)
        return sources

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def test_live_counterexample_reason_and_feature_precedence(self):
        self.seed()
        allowed = self.rank(options=pair(.25, .25))
        rejected = self.rank(options=pair(1, -.5))
        self.assertEqual(allowed["ranked"][0]["id"], "a")
        self.assertEqual((rejected["status"], rejected["reason"], rejected["ranked"]),
                         ("abstain", "unidentified_option_contrasts", []))
        self.assertEqual((rejected["contrast_rank"], rejected["contrast_basis"]),
                         (1, allowed["contrast_basis"]))
        self.assertEqual(rejected["weights"], allowed["weights"])
        self.assertEqual(preferences.rank_from_fit(pair(1, -.5), allowed), [])
        query = pair(1, -.5)
        query[0]["impacts"][VALUE_PARAMETERS[0]] = 1
        self.assertEqual(self.rank(options=query)["reason"], "unsupported_option_features")
        self.assertEqual(self.rank(options=[{"id": "a", "impacts": {}},
                                            {"id": "b", "impacts": {}}])["reason"],
                         "options_tied_with_learned_weights")

    def test_live_rank_two_expands_span_after_explicit_reviewed_save(self):
        sources = self.seed()
        self.assertEqual(self.rank(options=pair(1, -.5))["reason"], "unidentified_option_contrasts")
        self.save(sources[0], event_id="independent-direction", options=pair(.5, -.5))
        result = self.rank(options=pair(1, -.5))
        self.assertEqual((result["contrast_rank"], result["training_sources"], result["training_groups"]), (2, 3, 3))
        self.assertEqual(result["status"], "provisional")
        self.assertEqual(result["ranked"][0]["id"], "a")

    def test_live_pair_cancellation_returns_unidentified_reason(self):
        sources = self.seed()
        for source in sources:
            self.save(source, options=pair(.5, 0))
        self.save(sources[0], event_id="tiny-varied-column", options=pair(.5, 1e-14))
        query = [{"id": "a", "impacts": {}},
                 {"id": "b", "impacts": {GROWTH: 1, SECURITY: .5e-12}},
                 {"id": "c", "impacts": {GROWTH: 1, SECURITY: -.5e-12}}]
        trained = self.rank(options=pair(.25, 0))
        self.assertEqual(trained["contrast_rank"], 1)
        self.assertEqual(set(trained["used_features"]), {GROWTH, SECURITY})
        self.assertTrue(preferences.contains_contrasts(
            [[option["impacts"].get(feature, 0) for feature in VALUE_PARAMETERS] for option in query[1:]],
            trained["contrast_basis"]))
        rejected = self.rank(options=query)
        self.assertEqual((rejected["reason"], rejected["ranked"]), ("unidentified_option_contrasts", []))
        self.assertEqual(preferences.rank_from_fit(query, trained), [])

    def test_excluded_persisted_events_cannot_expand_span_or_counts(self):
        self.seed()
        expected = self.rank()
        for fields in (dict(training_consent=False), dict(group_reviewed=False),
                       dict(actual_choice_id=None, endorsed_choice_id=None, endorsement_partition=None),
                       dict(domain="study"), dict(domain="relationships")):
            self.save(self.submit(), options=pair(.5, -.5), **fields)
        self.save(self.submit(exclamation=False), options=pair(.5, -.5))
        self.save(self.submit(partition="emotional"), options=pair(.5, -.5),
                  endorsement_partition="emotional")
        legacy_source = self.submit()
        self.save(legacy_source, options=pair(.5, -.5))
        # Synthetic historical payload only: runtime must normalize without backfill.
        with closing(sqlite3.connect(self.path)) as db, db:
            payload = json.loads(db.execute("SELECT payload FROM brain_choice_feedback WHERE source_id=?",
                                            (legacy_source,)).fetchone()[0])
            payload.pop("group_id")
            payload.pop("group_reviewed")
            db.execute("UPDATE brain_choice_feedback SET payload=? WHERE source_id=?",
                       (json.dumps(payload), legacy_source))
        before = self.snapshot()
        actual = self.rank()
        for field in ("weights", "used_features", "contrast_rank", "contrast_basis",
                      "training_sources", "training_groups", "ranked"):
            self.assertEqual(actual[field], expected[field], field)
        self.assertEqual(self.rank(options=pair(1, -.5))["reason"], "unidentified_option_contrasts")
        self.assertEqual(self.snapshot(), before)

    def test_target_partition_domain_span_isolation(self):
        sources = self.seed()
        for source in sources:
            self.save(source, endorsed_choice_id=None, endorsement_partition=None)
        for i in range(3):
            self.save(self.submit(), options=pair(.5, -.5), actual_choice_id=None)
            self.save(self.submit(partition="emotional"), options=pair(.5, -.5),
                      endorsed_choice_id=None, endorsement_partition=None)
            self.save(self.submit(), options=pair(.5, -.5), domain="study",
                      endorsed_choice_id=None, endorsement_partition=None)
        actual = self.rank(options=pair(1, -.5))
        self.assertEqual(actual["reason"], "unidentified_option_contrasts")
        endorsed = self.rank(target="endorsed", options=pair(.25, -.25))
        self.assertEqual(endorsed["ranked"][0]["id"], "b")
        self.assertEqual(self.rank(partition="emotional", options=pair(.25, -.25))["ranked"][0]["id"], "a")
        self.assertEqual(self.rank(domain="study", options=pair(.25, -.25))["ranked"][0]["id"], "a")
        for result in (actual, endorsed, self.rank(partition="emotional"), self.rank(domain="study")):
            self.assertEqual((result["contrast_rank"], result["training_sources"], result["training_groups"]), (1, 3, 3))

    def test_no_sql_writes_encoder_rule_reset_or_lifecycle_changes(self):
        self.seed()
        state, effects = self.call("state"), self.call("effects")
        reset_info = self.api.brain.model.reset_info()
        before = self.snapshot()
        statements = []
        store = self.api.brain.store
        connect = store._connect

        @contextmanager
        def traced():
            with connect() as db:
                db.set_trace_callback(statements.append)
                yield db

        with patch.object(store, "_connect", side_effect=traced), \
                patch("translator.semantic.LocalSentenceEncoder", side_effect=AssertionError("no encoder")):
            for query in (pair(), pair(1, -.5)):
                self.rank(options=query)
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().split()[0].upper() in {"SELECT", "BEGIN", "COMMIT", "PRAGMA"}
                            for sql in statements), statements)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.call("state"), state)
        self.assertEqual(self.call("effects"), effects)
        self.assertEqual(self.api.brain.model.reset_info(), reset_info)

    def test_public_geometry_survives_restart_then_reset_excludes_old_epoch(self):
        sources = self.seed()
        expected = self.rank()
        self.api = BrainAPI(self.path)
        self.assertEqual(self.rank(), expected)
        info = self.api.brain.model.reset_info()
        self.api.brain.model.reset_model(confirmation="RESET_MODEL", expected_epoch=info["model_epoch"],
                                        expected_revision=info["input_revision"])
        result = self.rank()
        self.assertEqual((result["contrast_rank"], result["contrast_basis"], result["training_groups"]), (0, [], 0))
        for source in sources:
            self.save(source)
        result = self.rank()
        self.assertEqual((result["contrast_rank"], result["training_groups"]), (1, 3))
        self.assertEqual(result["status"], "provisional")


if __name__ == "__main__":
    unittest.main()
