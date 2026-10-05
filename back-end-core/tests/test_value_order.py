"""Fixed public value columns, using synthetic records and pure fits only."""

import copy
import importlib
import json
import math
import random
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from model import catalog, preferences, ranking


PUBLIC_ORDER = (
    "value.autonomy", "value.fairness", "value.care", "value.truth",
    "value.security", "value.growth", "value.achievement", "value.connection",
)

INVALID_IMPACTS = (
    ("huge_positive", 10**1000), ("huge_negative", -(10**1000)),
    ("max_finite", sys.float_info.max), ("min_finite", -sys.float_info.max),
    ("above_endpoint", math.nextafter(1.0, math.inf)),
    ("below_endpoint", math.nextafter(-1.0, -math.inf)),
    ("nan", math.nan), ("positive_inf", math.inf), ("negative_inf", -math.inf),
    ("true", True), ("false", False),
)
VALID_IMPACTS = (-1, 0, 1, -1.0, -0.5, -0.0, 0.0, 0.5, 1.0,
                 math.nextafter(-1.0, 0.0), math.nextafter(1.0, 0.0))


def impact_options(value):
    return [{"id": "impact", "impacts": {"value.fairness": value}},
            {"id": "zero", "impacts": {}}]


@contextmanager
def reloaded_with_catalog(order):
    # Restore the exact dictionaries, including function/tuple identities, even
    # after assertion failures. Existing from-import references stay valid.
    saved = [(module, module.__dict__.copy()) for module in (ranking, preferences)]
    with patch.object(catalog, "PARAMETERS", order):
        try:
            importlib.reload(ranking)
            importlib.reload(preferences)
            yield
        finally:
            for module, namespace in saved:
                module.__dict__.clear()
                module.__dict__.update(namespace)


def axis_options(feature):
    return [{"id": "positive", "impacts": {feature: 1}},
            {"id": "negative", "impacts": {feature: -1}}]


def axis_fit(feature, sign):
    records = [{"source_id": f"synthetic-{i}", "partition": "rational",
                "domain": "daily", "group_id": f"group-{i}", "group_reviewed": True,
                "options": axis_options(feature),
                "actual_choice_id": "positive" if sign > 0 else "negative"}
               for i in range(3)]
    return preferences.fit_preferences(records, target="actual", partition="rational", domain="daily")


class ImpactValidationTests(unittest.TestCase):
    def test_impact_boundaries_preserve_inputs_state_and_weights(self):
        state = {"value.fairness": {"value": 0.5, "support": 2}}
        fit = axis_fit("value.fairness", 1)
        original_state, original_fit = copy.deepcopy(state), copy.deepcopy(fit)
        for label, value in INVALID_IMPACTS:
            options = impact_options(value)
            original_options = copy.deepcopy(options)
            for name, call in (
                ("validate", lambda: ranking.validate_options(options)),
                ("state_rank", lambda: ranking.rank_from_state(options, state)),
                ("fit_rank", lambda: preferences.rank_from_fit(options, fit)),
            ):
                with self.subTest(value=label, call=name):
                    with self.assertRaises(ValueError):
                        call()
                    self.assertEqual(options, original_options)
                    self.assertIs(options[0]["impacts"]["value.fairness"], value)
                    self.assertEqual(state, original_state)
                    self.assertEqual(fit, original_fit)

        for value in VALID_IMPACTS:
            with self.subTest(value=value, kind=type(value).__name__):
                options = impact_options(value)
                original_options = copy.deepcopy(options)
                self.assertIsNone(ranking.validate_options(options))
                result = ranking.rank_from_state(options, state)
                ranked = preferences.rank_from_fit(options, fit)
                if value == 0:
                    self.assertEqual(result["status"], "abstain")
                    self.assertEqual(ranked, [])
                else:
                    self.assertEqual(result["status"], "provisional")
                    scores = {item["id"]: item["alignment_score"] for item in result["ranked"]}
                    self.assertEqual(scores, {"impact": 0.5 * value, "zero": 0})
                    scores = {item["id"]: item["score"] for item in ranked}
                    self.assertEqual(scores, {"impact": fit["weights"]["value.fairness"] * value,
                                              "zero": 0})
                self.assertEqual(options, original_options)
                self.assertIs(options[0]["impacts"]["value.fairness"], value)
                self.assertEqual(state, original_state)
                self.assertEqual(fit, original_fit)


class ImpactAPIValidationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="alpha-impact-")
        self.addCleanup(temp.cleanup)
        self.api = BrainAPI(Path(temp.name) / "synthetic.sqlite3")
        self.model = self.api.brain.model
        for _ in range(2):
            source = self.model.submit("我重视公平。", partition="rational")
            self.model.review(source, agree=True)
        self.baseline_bytes = catalog.BASELINE_PATH.read_bytes()
        self.state = self.model.state()
        self.database = self.database_dump()

    def database_dump(self):
        with self.model.store._connect() as db:
            return tuple(db.iterdump())

    def call(self, method, options):
        params = {"options": options}
        if method == "preference_rank":
            params.update(target="actual", partition="rational", domain="daily")
        return self.api.handle({"schema_version": 1, "id": "impact-validation",
                                "method": method, "params": params})

    def assert_unchanged(self, options, original_options):
        self.assertEqual(options, original_options)
        self.assertEqual(self.model.state(), self.state)
        self.assertEqual(self.database_dump(), self.database)
        self.assertEqual(catalog.BASELINE_PATH.read_bytes(), self.baseline_bytes)

    def test_impact_boundaries_return_expected_api_results_without_writes(self):
        for label, value in INVALID_IMPACTS:
            options = impact_options(value)
            original_options = copy.deepcopy(options)
            with self.subTest(value=label, method="model_rank"):
                with self.assertRaises(ValueError):
                    self.model.rank_options(options)
                self.assert_unchanged(options, original_options)
            for method in ("rank", "preference_rank"):
                with self.subTest(value=label, method=method):
                    response = self.call(method, options)
                    self.assertEqual(set(response), {"schema_version", "id", "ok", "error"})
                    self.assertEqual(response["schema_version"], 1)
                    self.assertEqual(response["id"], "impact-validation")
                    self.assertIs(response["ok"], False)
                    self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
                    self.assert_unchanged(options, original_options)

        for value in VALID_IMPACTS:
            options = impact_options(value)
            original_options = copy.deepcopy(options)
            for method in ("rank", "preference_rank"):
                with self.subTest(value=value, kind=type(value).__name__, method=method):
                    response = self.call(method, options)
                    self.assertIs(response["ok"], True, response)
                    if method == "rank":
                        self.assertEqual(response["result"],
                                         ranking.rank_from_state(options, self.state["rational"]))
                    else:
                        self.assertEqual(response["result"]["status"], "abstain")
                    self.assertIs(options[0]["impacts"]["value.fairness"], value)
                    self.assert_unchanged(options, original_options)


class ValueOrderTests(unittest.TestCase):
    def test_public_tuple_schema_and_original_rule_catalog_align(self):
        schema_path = Path(__file__).resolve().parents[1] / "docs/api.schema.json"
        definitions = json.loads(schema_path.read_text(encoding="utf-8"))["$defs"]
        baseline = json.loads(catalog.BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertIsInstance(ranking.VALUE_PARAMETERS, tuple)
        self.assertEqual(ranking.VALUE_PARAMETERS, PUBLIC_ORDER)
        self.assertEqual(tuple(definitions["valueFeature"]["enum"]), ranking.VALUE_PARAMETERS)
        self.assertEqual(tuple(definitions["valueWeights"]["required"]), ranking.VALUE_PARAMETERS)
        self.assertEqual(tuple(baseline["parameters"]), catalog.PARAMETERS)
        self.assertEqual(len(catalog.PARAMETERS), 13)
        self.assertEqual({key for key in catalog.PARAMETERS if key.startswith("value.")},
                         set(ranking.VALUE_PARAMETERS))
        self.assertEqual(set(catalog.VALUE_WORDS), set(ranking.VALUE_PARAMETERS))
        self.assertTrue(all(value == 0 for value in baseline["parameters"].values()))
        row = definitions["contrastBasis"]["items"]
        self.assertEqual((row["minItems"], row["maxItems"]), (8, 8))

    def test_dense_and_sparse_vectors_use_named_columns(self):
        impacts = {feature: (i + 1) / 8 for i, feature in reversed(list(enumerate(PUBLIC_ORDER)))}
        options = [{"id": "dense", "impacts": impacts},
                   {"id": "sparse", "impacts": {"value.truth": -0.5, "value.connection": 0.25}}]
        self.assertEqual(preferences._vectors(options),
                         [[0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0],
                          [0.0, 0.0, 0.0, -0.5, 0.0, 0.0, 0.0, 0.25]])

    def test_each_learned_weight_and_exported_basis_has_its_named_column(self):
        # Independent scalar optimum for three identical, equally weighted
        # binary events: L2*w = 2/(1+exp(2*w)). No production vector/solver oracle.
        low, high = 0.0, 10.0
        for _ in range(80):
            middle = (low + high) / 2
            if preferences.L2 * middle < 2 / (1 + math.exp(2 * middle)):
                low = middle
            else:
                high = middle
        magnitude = (low + high) / 2
        for column, feature in enumerate(PUBLIC_ORDER):
            for sign in (-1, 1):
                with self.subTest(feature=feature, sign=sign):
                    fit = axis_fit(feature, sign)
                    self.assertEqual(fit["status"], "provisional")
                    self.assertEqual(fit["used_features"], [feature])
                    self.assertEqual(fit["contrast_rank"], 1)
                    self.assertEqual(fit["contrast_basis"],
                                     [[float(i == column) for i in range(8)]])
                    self.assertEqual(tuple(fit["weights"]), PUBLIC_ORDER)
                    for name, weight in fit["weights"].items():
                        self.assertAlmostEqual(weight, sign * magnitude if name == feature else 0,
                                               places=9)
                    ranked = preferences.rank_from_fit(axis_options(feature), fit)
                    self.assertEqual(ranked[0]["id"], "positive" if sign > 0 else "negative")
                    self.assertAlmostEqual(ranked[0]["score"], magnitude, places=9)
                    self.assertAlmostEqual(ranked[0]["contributions"][feature], magnitude, places=9)

    def test_named_weights_score_independently_of_dictionary_iteration(self):
        weights = {feature: (i + 1) * (-1 if i % 2 else 1)
                   for i, feature in reversed(list(enumerate(PUBLIC_ORDER)))}
        impacts = {feature: (i + 1) / 8 for i, feature in enumerate(PUBLIC_ORDER)}
        options = [{"id": "dense", "impacts": impacts}, {"id": "zero", "impacts": {}}]
        fit = {"status": "provisional", "used_features": list(PUBLIC_ORDER), "weights": weights,
               "contrast_rank": 8,
               "contrast_basis": [[float(i == j) for j in range(8)] for i in range(8)]}
        ranked = preferences.rank_from_fit(options, fit)
        dense = next(item for item in ranked if item["id"] == "dense")
        expected = {feature: weights[feature] * impact for feature, impact in impacts.items()}
        self.assertEqual(dense["contributions"], expected)
        self.assertEqual(dense["score"], math.fsum(expected.values()))
        self.assertEqual(ranked[0]["id"], "zero")

    def test_shuffled_catalog_reload_cannot_move_exported_basis_columns(self):
        original = catalog.PARAMETERS
        baseline_bytes = catalog.BASELINE_PATH.read_bytes()
        # Serialize before changing catalog order: a consumer must interpret
        # already exported geometry the same way after a fresh import.
        fits = [json.loads(json.dumps(axis_fit(feature, 1))) for feature in PUBLIC_ORDER]
        shuffled = list(original)
        random.Random(20261005).shuffle(shuffled)
        for order in (tuple(reversed(original)), tuple(sorted(original)), tuple(shuffled)):
            with self.subTest(order=order), reloaded_with_catalog(order):
                self.assertNotEqual(tuple(key for key in order if key.startswith("value.")), PUBLIC_ORDER)
                for column, (feature, exported) in enumerate(zip(PUBLIC_ORDER, fits)):
                    with self.subTest(feature=feature):
                        fresh = axis_fit(feature, 1)
                        self.assertEqual(fresh["contrast_basis"],
                                         [[float(i == column) for i in range(8)]])
                        self.assertEqual(fresh, exported)
                        self.assertEqual(preferences._vectors(axis_options(feature))[0],
                                         [float(i == column) for i in range(8)])
                        self.assertEqual(preferences.rank_from_fit(axis_options(feature), exported)[0]["id"],
                                         "positive")
                self.assertEqual(ranking.VALUE_PARAMETERS, PUBLIC_ORDER)
                self.assertIs(preferences.VALUE_PARAMETERS, ranking.VALUE_PARAMETERS)
        self.assertIs(catalog.PARAMETERS, original)
        self.assertEqual(catalog.BASELINE_PATH.read_bytes(), baseline_bytes)

    def test_adversarial_reload_restores_exact_module_state_on_failure(self):
        original_catalog = catalog.PARAMETERS
        saved = [(module, module.__dict__.copy()) for module in (ranking, preferences)]
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            with reloaded_with_catalog(tuple(reversed(original_catalog))):
                raise RuntimeError("synthetic failure")
        self.assertIs(catalog.PARAMETERS, original_catalog)
        for module, namespace in saved:
            self.assertEqual(module.__dict__.keys(), namespace.keys())
            for name, value in namespace.items():
                self.assertIs(module.__dict__[name], value, name)


if __name__ == "__main__":
    unittest.main()
