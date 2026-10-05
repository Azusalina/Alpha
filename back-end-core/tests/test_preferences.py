"""Synthetic choice labels/impacts and temporary SQLite databases only."""

import copy
import hashlib
import json
import math
import random
import sqlite3
import tempfile
import time
import tracemalloc
import unittest
from collections import Counter
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
            "group_id": source, "group_reviewed": True,
            "options": options() if opts is None else opts, "actual_choice_id": actual,
            "endorsed_choice_id": endorsed,
            "endorsement_partition": endorsement_partition if endorsed is not None else None}


def random_records(seed, count=12, option_count=2):
    rng = random.Random(seed)
    records = []
    for i in range(count):
        opts = [{"id": chr(97 + j), "impacts": dict(zip(
            VALUE_PARAMETERS, [rng.uniform(-1, 1) for _ in VALUE_PARAMETERS]))}
                for j in range(option_count)]
        choice = rng.choice(list(range(option_count)))
        records.append(record(str(i), opts=opts, actual=opts[choice]["id"]))
    return records


def reference_loss_gradient(records, weights):
    """Independent full-batch equations, not production objective/softmax helpers."""
    counts = Counter(item["source_id"] for item in records)
    losses = [0.05 * math.fsum(w * w for w in weights)]
    terms = [[0.1 * w] for w in weights]
    for item in records:
        vectors = [[option["impacts"].get(key, 0) for key in VALUE_PARAMETERS]
                   for option in item["options"]]
        chosen = next(i for i, option in enumerate(item["options"])
                      if option["id"] == item["actual_choice_id"])
        logits = [math.fsum(w * x for w, x in zip(weights, vector)) for vector in vectors]
        offset = max(logits)
        exp = [math.exp(logit - offset) for logit in logits]
        denominator = math.fsum(exp)
        mass = 1 / (len(counts) * counts[item["source_id"]])
        losses.append(mass * (offset + math.log(denominator) - logits[chosen]))
        for k in range(len(weights)):
            terms[k].append(mass * (math.fsum(e * vector[k] for e, vector in zip(exp, vectors))
                                    / denominator - vectors[chosen][k]))
    return math.fsum(losses), [math.fsum(values) for values in terms]


def reference_fit(records):
    # Independent gradient descent: original ||x||2^2 <= 8 bounds the
    # covariance's spectral norm by 8, so 1/(8+.1) is a safe global step.
    weights = [0.0] * 8
    for _ in range(10000):
        _, gradient = reference_loss_gradient(records, weights)
        if max(abs(g) for g in gradient) <= 2e-13:
            return weights
        weights = [w - g / 8.1 for w, g in zip(weights, gradient)]
    raise AssertionError("independent reference did not converge")


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
        self.assertEqual(actual["contrast_rank"], 1)
        self.assertEqual(actual["contrast_basis"], endorsed["contrast_basis"])
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
        for value in (True, float("nan"), float("inf"), 1e300, 10 ** 1000, -(10 ** 1000)):
            fit = self.fit(records)
            fit["weights"]["value.autonomy"] = value
            with self.assertRaises(ValueError):
                preferences.rank_from_fit(options(), fit)

    def test_fit_bounded_and_request_validation(self):
        self.assertEqual(self.fit([record("same")] * 1001)["reason"], "too_many_feedback_records")
        for kwargs in ({"target": "unknown"}, {"partition": None}, {"domain": "work"}):
            with self.assertRaises(ValueError):
                self.fit([], **kwargs)

    def test_scalar_fit_matches_independent_bisection(self):
        for impact in (0.02, 0.5, 1.0):
            for labels in (("a", "a", "a"), ("a", "a", "b"), ("b", "b", "b")):
                with self.subTest(impact=impact, labels=labels):
                    opts = [{"id": "a", "impacts": {VALUE_PARAMETERS[0]: impact}},
                            {"id": "b", "impacts": {VALUE_PARAMETERS[0]: -impact}}]
                    records = [record(str(i), actual=label, opts=opts) for i, label in enumerate(labels)]
                    fit = self.fit(records)
                    self.assertEqual(fit["status"], "provisional")
                    fraction = labels.count("a") / len(labels)
                    low, high = -10.0, 10.0
                    for _ in range(100):
                        middle = (low + high) / 2
                        gradient = 0.1 * middle + 2 * impact * (
                            1 / (1 + math.exp(-2 * impact * middle)) - fraction)
                        if gradient > 0:
                            high = middle
                        else:
                            low = middle
                    self.assertAlmostEqual(fit["weights"][VALUE_PARAMETERS[0]], (low + high) / 2,
                                           delta=1e-10)

    def test_seed_reference_comparison_and_804_near_tie(self):
        for seed, option_count in ((804, 2), (0, 8), (21, 3), (97, 2)):
            with self.subTest(seed=seed, option_count=option_count):
                records = random_records(seed, option_count=option_count)
                reference = reference_fit(records)
                fit = self.fit(records)
                self.assertEqual(fit["status"], "provisional")
                weights = [fit["weights"][key] for key in VALUE_PARAMETERS]
                for actual, expected in zip(weights, reference):
                    self.assertAlmostEqual(actual, expected, delta=2e-10)
                _, gradient = reference_loss_gradient(records, weights)
                self.assertLessEqual(max(abs(g) for g in gradient), 1.01e-11)
                if seed == 804:
                    query = [0.08703643075086724, 0.5, 0.14972186216520075,
                             -0.07513219054725351, 0.10724907134065176, 0.249086959555357,
                             0.3958451180536002, -0.1527763092777365]
                    reference_gap = 2 * math.fsum(w * x for w, x in zip(reference, query))
                    self.assertLess(reference_gap, 0)
                    opts = [{"id": "a", "impacts": dict(zip(VALUE_PARAMETERS, query))},
                            {"id": "b", "impacts": dict(zip(VALUE_PARAMETERS, [-x for x in query]))}]
                    ranked = preferences.rank_from_fit(opts, fit)
                    self.assertTrue(not ranked or ranked[0]["id"] == "b")

    def test_record_and_option_permutations_preserve_fit_and_ranking(self):
        records = random_records(42, option_count=8)
        records += [copy.deepcopy(records[0]), copy.deepcopy(records[1])]
        expected = self.fit(records)
        expected_rank = preferences.rank_from_fit(records[2]["options"], expected)
        self.assertTrue(expected_rank)
        rng = random.Random(113)
        permuted = copy.deepcopy(records)
        for _ in range(4):
            rng.shuffle(permuted)
            for item in permuted:
                rng.shuffle(item["options"])
            actual = self.fit(permuted)
            self.assertEqual(actual, expected)
            self.assertEqual(preferences.rank_from_fit(list(reversed(records[2]["options"])), actual),
                             expected_rank)

    def test_objective_gradient_hessian_finite_and_finite_difference_sanity(self):
        records = random_records(13, option_count=8)
        events = [(preferences._vectors(item["options"]),
                   next(i for i, option in enumerate(item["options"])
                        if option["id"] == item["actual_choice_id"]), 1 / len(records))
                  for item in records]
        weights = [0.1 * (i - 3) for i in range(8)]
        loss, gradient, hessian = preferences._objective(weights, events)
        ref_loss, ref_gradient = reference_loss_gradient(records, weights)
        self.assertAlmostEqual(loss, ref_loss, places=14)
        for i in range(8):
            self.assertAlmostEqual(gradient[i], ref_gradient[i], places=14)
            plus, minus = list(weights), list(weights)
            plus[i] += 1e-5
            minus[i] -= 1e-5
            fp, gp, _ = preferences._objective(plus, events)
            fm, gm, _ = preferences._objective(minus, events)
            self.assertAlmostEqual(gradient[i], (fp - fm) / 2e-5, delta=1e-9)
            for j in range(8):
                self.assertAlmostEqual(hessian[j][i], (gp[j] - gm[j]) / 2e-5, delta=1e-9)
                self.assertEqual(hessian[i][j], hessian[j][i])
        for direction in ([1.0] * 8, [(-1.0) ** i for i in range(8)]):
            curvature = math.fsum(direction[i] * hessian[i][j] * direction[j]
                                   for i in range(8) for j in range(8))
            self.assertGreaterEqual(curvature, 0.1 * math.fsum(x * x for x in direction))
        for invalid in ([math.inf] * 8, [math.nan] * 8, [1e308] * 8):
            with self.assertRaises((ArithmeticError, ValueError)):
                preferences._objective(invalid, events)

    def test_nonconvergence_and_nonfinite_solver_fail_closed_with_schema_reason(self):
        records = [record(str(i)) for i in range(3)]
        for budget in (0, 1):
            with patch.object(preferences, "MAX_ITERATIONS", budget):
                fit = self.fit(records)
            self.assertEqual(fit["reason"], "fit_not_converged")
            self.assertEqual(fit["status"], "abstain")
            self.assertEqual(fit["ranked"], [])
            self.assertTrue(all(w == 0 for w in fit["weights"].values()))
            self.assertEqual((fit["contrast_rank"], len(fit["contrast_basis"])), (1, 1))
        with patch.object(preferences, "MAX_BACKTRACKS", 0):
            self.assertEqual(self.fit(records)["reason"], "fit_not_converged")
        with patch.object(preferences, "_objective", side_effect=ArithmeticError("nonfinite Hessian")):
            self.assertEqual(self.fit(records)["reason"], "nonfinite_fit")
        schema = json.loads((Path(__file__).resolve().parents[1] / "docs/api.schema.json").read_text())
        self.assertIn("fit_not_converged", schema["$defs"]["preferenceResult"]["properties"]["reason"]["enum"])

    def test_roundoff_slack_requires_residual_reduction_and_final_gradient(self):
        hessian = [[float(i == j) for j in range(8)] for i in range(8)]
        def stalled(weights, events, *, derivatives=True):
            loss = 1.0 if not any(weights) else math.nextafter(1.0, math.inf)
            return loss, [2e-11] * 8 if derivatives else [], hessian if derivatives else []
        with patch.object(preferences, "_objective", side_effect=stalled):
            self.assertEqual(preferences._minimize([]), (None, "fit_not_converged"))

    def test_tie_margin_covers_gradient_error_bound(self):
        self.assertGreater(preferences.TIE_TOLERANCE,
                           2 * len(VALUE_PARAMETERS) * preferences.GRADIENT_TOLERANCE / preferences.L2)
        fit = self.fit([record(str(i)) for i in range(3)])
        # A contrast smaller than the conservative gap threshold abstains.
        impact = preferences.TIE_TOLERANCE / (4 * abs(fit["weights"][VALUE_PARAMETERS[0]]))
        opts = [{"id": "a", "impacts": {VALUE_PARAMETERS[0]: impact}},
                {"id": "b", "impacts": {VALUE_PARAMETERS[0]: -impact}}]
        self.assertEqual(preferences.rank_from_fit(opts, fit), [])

    def test_cpu_maximum_records_eight_options_acceptance(self):
        records = random_records(211, count=preferences.MAX_RECORDS, option_count=8)
        start = time.process_time()
        fit = self.fit(records)
        elapsed = time.process_time() - start
        self.assertEqual(fit["status"], "provisional")
        self.assertEqual(fit["training_sources"], preferences.MAX_RECORDS)
        self.assertEqual((fit["contrast_rank"], len(fit["contrast_basis"])), (8, 8))
        weights = [fit["weights"][key] for key in VALUE_PARAMETERS]
        loss, gradient = reference_loss_gradient(records, weights)
        self.assertTrue(math.isfinite(loss))
        self.assertLessEqual(max(abs(g) for g in gradient), 1.01e-11)
        self.assertLess(elapsed, 10.0, f"bounded CPU fit took {elapsed:.3f}s")

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
                "training_consent": True, "group_id": source, "group_reviewed": True,
                **self.guards(source)}
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

    def large_source_fixture(self, character, consent):
        """40 distinct bounded bodies, 25 labelled events each; all synthetic."""
        ids = [self.submit() for _ in range(40)]
        self.save(ids[0])
        with self.store._connect() as db:
            template = dict(db.execute("SELECT * FROM brain_choice_feedback").fetchone())
            original = json.loads(template["payload"])
            for i, source_id in enumerate(ids):
                body = f"{i:08d}" + character * (sources.MAX_CHARS - 8)
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                db.execute("UPDATE sources SET body=? WHERE id=?", (body, source_id))
                opts = options()
                for option in opts:
                    option["label"] = "😀" * 512
                for j in range(25):
                    payload = {**original, "source_id": source_id,
                               "group_id": source_id,
                               "event_id": "event" if j == 0 else f"event-{j}",
                               "body_digest": digest, "training_consent": consent,
                               "options": opts, "reason": "😀" * 2048}
                    values = tuple(payload[key] for key in (
                        "source_id", "event_id", "source_version", "model_epoch", "body_digest", "created_at"))
                    db.execute("INSERT OR REPLACE INTO brain_choice_feedback VALUES (?,?,?,?,?,?,?)",
                               values + (json.dumps(payload, ensure_ascii=False),))
        return ids

    def test_many_distinct_large_sources_bounded_peak_with_and_without_consent(self):
        ids = self.large_source_fixture("x", True)
        for character in ("x", "😀"):
            if character != "x":
                with self.store._connect() as db:
                    for i, source_id in enumerate(ids):
                        body = f"{i:08d}" + character * (sources.MAX_CHARS - 8)
                        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                        db.execute("UPDATE sources SET body=? WHERE id=?", (body, source_id))
                        for row in db.execute("SELECT * FROM brain_choice_feedback WHERE source_id=?",
                                              (source_id,)).fetchall():
                            payload = json.loads(row["payload"])
                            payload["body_digest"] = digest
                            db.execute("UPDATE brain_choice_feedback SET body_digest=?,payload=? "
                                       "WHERE source_id=? AND event_id=?",
                                       (digest, json.dumps(payload, ensure_ascii=False), source_id, row["event_id"]))
                del body, payload, row
            for consent in (False, True):
                with self.store._connect() as db:
                    for row in db.execute("SELECT * FROM brain_choice_feedback").fetchall():
                        payload = json.loads(row["payload"])
                        payload["training_consent"] = consent
                        db.execute("UPDATE brain_choice_feedback SET payload=? WHERE source_id=? AND event_id=?",
                                   (json.dumps(payload, ensure_ascii=False), row["source_id"], row["event_id"]))
                del payload, row
                with self.subTest(character=character, consent=consent):
                    tracemalloc.start()
                    try:
                        result = self.rank()
                        _, peak = tracemalloc.get_traced_memory()
                    finally:
                        tracemalloc.stop()
                    self.assertLess(peak, 12_000_000 if character == "😀" else 8_000_000,
                                    f"rank retained {peak} bytes for distinct large sources")
                    self.assertEqual(result["training_sources"], 40 if consent else 0)
                    self.assertEqual(result["training_groups"], 40 if consent else 0)
                    self.assertEqual(result["status"], "provisional" if consent else "abstain")
                    if consent:
                        self.assertEqual(result["ranked"][0]["id"], "a")

    def test_rank_caches_only_metadata_digest_and_strips_nontraining_fields(self):
        ids = [self.submit() for _ in range(3)]
        for source in ids:
            self.save(source, reason="Synthetic nontraining reason.")
            self.save(source, event_id="second")
        original_fit = preferences.fit_preferences
        original_digest = preferences._source_digest
        digests = []
        def checked_digest(db, source_id):
            digests.append(source_id)
            return original_digest(db, source_id)
        def checked_fit(records, **kwargs):
            expected = {"source_id", "partition", "domain", "options", "actual_choice_id",
                        "endorsed_choice_id", "endorsement_partition", "training_consent", "model_active",
                        "group_id", "group_reviewed"}
            for item in records:
                self.assertEqual(set(item), expected)
                for option in item["options"]:
                    self.assertEqual(set(option), {"id", "impacts"})
            return original_fit(records, **kwargs)
        with patch.object(preferences, "_source", side_effect=AssertionError("full source cache")), \
                patch.object(preferences, "_source_digest", side_effect=checked_digest), \
                patch.object(preferences, "fit_preferences", side_effect=checked_fit):
            self.assertEqual(self.rank()["training_sources"], 3)
        self.assertCountEqual(digests, ids)
        with self.store._connect() as db:
            metadata = preferences._source_metadata(db, ids[0])
        self.assertEqual(set(metadata), {"status", "immediate", "confirm", "source_version",
                                         "partition", "body_digest"})

    def test_rank_avoids_body_load_for_ineligible_records_but_decodes_provenance(self):
        ids = [self.submit() for _ in range(3)]
        for source in ids:
            self.save(source)
        with patch.object(preferences, "_source_digest", side_effect=AssertionError("excluded body")):
            self.assertEqual(self.rank(domain="study")["training_sources"], 0)
            self.assertEqual(self.rank(partition="emotional")["training_sources"], 0)
            self.assertEqual(self.rank(target="endorsed", partition="crazy")["reason"],
                             "endorsed_requires_rational_partition")
            for source in ids:
                self.model.revoke(source)
            self.assertEqual(self.rank()["training_sources"], 0)
        for source in ids:
            self.save(source, training_consent=False)
        with patch.object(preferences, "_source_metadata", side_effect=AssertionError("no consent source")):
            self.assertEqual(self.rank()["training_sources"], 0)
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM brain_choice_feedback WHERE source_id=?", (ids[0],)).fetchone()
            payload = json.loads(row["payload"])
            payload["source_version"] += 1
            db.execute("UPDATE brain_choice_feedback SET payload=? WHERE source_id=?",
                       (json.dumps(payload), ids[0]))
        self.assertEqual(self.rank()["reason"], "invalid_feedback_snapshot")

    def test_rank_digest_tampering_and_oversized_body_fail_closed(self):
        ids = [self.submit() for _ in range(4)]
        for source in ids:
            self.save(source)
        with self.store._connect() as db:
            db.execute("UPDATE sources SET body=? WHERE id=?", ("Tampered synthetic body.", ids[0]))
        ranked = self.rank()
        self.assertEqual(ranked["training_sources"], 3)
        self.assertEqual(ranked["ranked"][0]["id"], "a")
        with self.store._connect() as db:
            db.execute("UPDATE sources SET body=? WHERE id=?", ("x" * (sources.MAX_CHARS + 1), ids[1]))
        self.assertEqual(self.rank()["reason"], "invalid_feedback_snapshot")

    def test_live_forced_nonconvergence_validates_full_schema(self):
        for _ in range(3):
            self.save(self.submit())
        with patch.object(preferences, "MAX_ITERATIONS", 0):
            result = self.rank()
        self.assertEqual(result["reason"], "fit_not_converged")
        self.assertEqual(result["ranked"], [])
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("install alpha-brain[test-schema] for full contract validation")
        schema = json.loads((Path(__file__).resolve().parents[1] / "docs/api.schema.json").read_text())
        Draft202012Validator({**schema, "$ref": "#/$defs/preferenceResult"}).validate(result)

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
