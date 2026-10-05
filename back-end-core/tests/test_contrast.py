"""Offline synthetic numerical tests; import the file without model side effects."""

import ast
import decimal
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
import sys
import time
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "model/contrast.py"
SPEC = importlib.util.spec_from_file_location("alpha_contrast_numerical", MODULE_PATH)
contrast = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contrast)


def row(*values):
    return list(values) + [0.0] * (8 - len(values))


def axis(index):
    return [float(index == coordinate) for coordinate in range(8)]


def walsh(index):
    # Dyadic orthogonal directions: rotation introduces no arithmetic rounding.
    return [(-0.25 if bin(index & coordinate).count("1") % 2 else 0.25)
            for coordinate in range(8)]


def rotate(vector):
    # Dense orthogonal Householder reflection I - (1/4)11': exactly dyadic.
    offset = sum(vector) / 4
    return [value - offset for value in vector]


class ContrastTests(unittest.TestCase):
    def assertCertificate(self, basis):
        self.assertLessEqual(len(basis), 8)
        self.assertIsNone(contrast.validate_basis(basis))
        for index, vector in enumerate(basis):
            self.assertTrue(all(type(value) is float and math.isfinite(value)
                                for value in vector))
            self.assertTrue(all(abs(value) <= 1 for value in vector))
            self.assertLessEqual(abs(math.hypot(*vector) - 1), 1e-12)
            for previous in basis[:index]:
                self.assertLessEqual(abs(math.fsum(a * b for a, b in
                                                  zip(vector, previous))), 1e-12)

    def test_public_policy_constants(self):
        self.assertEqual(contrast.DIMENSION, 8)
        self.assertEqual(contrast.MAX_CONTRASTS, 7000)
        self.assertEqual(contrast.RANK_TOLERANCE, 1e-10)
        self.assertEqual(contrast.MEMBERSHIP_TOLERANCE, 1e-12)
        self.assertEqual(contrast.ORTHOGONALITY_TOLERANCE, 1e-12)

    def test_empty_and_zero_span(self):
        self.assertEqual(contrast.basis_from_contrasts([]), [])
        self.assertEqual(contrast.basis_from_contrasts([row(), row(-0.0)]), [])
        self.assertTrue(contrast.contains_contrasts([], []))
        self.assertTrue(contrast.contains_contrasts([row(), row(-0.0)], []))
        self.assertFalse(contrast.contains_contrasts([axis(0)], []))

    def test_exact_collinear_rows(self):
        rows = [row(1, 2, -1), row(-0.5, -1, 0.5), row(0.25, 0.5, -0.25)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 1)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows, basis))

    def test_orthogonal_rows(self):
        rows = [axis(1), axis(4), axis(7)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 3)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows, basis))
        self.assertFalse(contrast.contains_contrasts([axis(0)], basis))

    def test_mixed_dependent_rows(self):
        rows = [row(1, 1), row(1, -1), row(2, 0), row(0, 2), row()]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 2)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts([row(-1.25, 0.75)], basis))

    def test_full_rank_axes(self):
        basis = contrast.basis_from_contrasts([axis(i) for i in range(8)])
        self.assertEqual(len(basis), 8)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts([[2, -2, 1, -1, 0, 0.5, -0.5, 2]], basis))

    def test_dense_full_rank(self):
        rows = [[1.0 if i == j else 0.25 for j in range(8)] for i in range(8)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 8)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows, basis))

    def test_permutations_and_duplicates_are_exactly_deterministic(self):
        rows = [row(1, 0.2, 0.3), row(0.4, 1, 0.6), row(0.7, 0.8, 1)]
        expected = contrast.basis_from_contrasts(rows)
        for permutation in itertools.permutations(rows):
            self.assertEqual(contrast.basis_from_contrasts(list(permutation) * 3), expected)

    def test_sign_changes_and_signed_zero_are_exactly_deterministic(self):
        rows = [row(1, 0, -0.5), row(0, 1, 0.25)]
        expected = contrast.basis_from_contrasts(rows)
        for signs in itertools.product((-1, 1), repeat=2):
            changed = [[sign * value for value in vector] for sign, vector in zip(signs, rows)]
            self.assertEqual(contrast.basis_from_contrasts(changed), expected)
        for vector in expected:
            for value in vector:
                if value == 0:
                    self.assertEqual(math.copysign(1, value), 1)

    def test_common_power_of_two_rescaling_is_exactly_deterministic(self):
        rows = [row(1, 0.5, 0.25), row(0.125, 1, -0.5)]
        expected = contrast.basis_from_contrasts(rows)
        for scale in (2.0, 0.5, 2.0 ** -1000, -(2.0 ** -1000)):
            changed = [[scale * value for value in vector] for vector in rows]
            self.assertEqual(contrast.basis_from_contrasts(changed), expected)
            self.assertTrue(contrast.contains_contrasts(changed, expected))

    def test_arbitrary_rescaling_preserves_span_with_roundoff(self):
        rows = [row(0.3, 0.7, 0.1), row(0.8, -0.2, 0.6)]
        basis = contrast.basis_from_contrasts(rows)
        for scale in (1.3, 1e-300, -0.7):
            changed = [[scale * value for value in vector] for vector in rows]
            actual = contrast.basis_from_contrasts(changed)
            self.assertEqual(len(actual), 2)
            self.assertCertificate(actual)
            self.assertTrue(contrast.contains_contrasts(rows, actual))
            self.assertTrue(contrast.contains_contrasts(changed, basis))

    def test_pivot_selects_largest_residual_after_first_direction(self):
        rows = [axis(0), row(1, 2e-10), axis(2)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 3)
        # Lexicographic normalized order picks e2 first; e0 then has norm 1.
        self.assertEqual(basis[:2], [axis(2), axis(0)])
        self.assertTrue(contrast.contains_contrasts(rows, basis))

    def test_nearly_dependent_above_rank_tolerance(self):
        rows = [axis(0), row(1, 2e-10)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 2)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows, basis))

    def test_weak_rotated_pivot_preserves_original_dyadic_plane(self):
        v, w, normal = row(0.5, 0.75, -0.25), row(-0.25, 0.5, 0.75), row(11/8, -5/8, 7/8)
        rows = [v, [x + 2**-30 * y for x, y in zip(v, w)]]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 2)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows + [v, w, row(0.25, 1.25, 0.5)], basis))
        self.assertFalse(contrast.contains_contrasts([normal], basis))
        unit_normal = [x / math.hypot(*normal) for x in normal]
        for direction in basis:
            self.assertLessEqual(abs(math.fsum(a*b for a, b in zip(direction, unit_normal))),
                                 1e-15)

    def test_dense_dyadic_planes_under_rotation_scaling_and_permutation(self):
        v, w, normal = map(rotate, (row(0.5, 0.75, -0.25), row(-0.25, 0.5, 0.75),
                                   row(11/8, -5/8, 7/8)))
        # All eight coordinates participate; an independent exact normal checks
        # source-plane accuracy, beyond orthogonality of the exported basis.
        self.assertTrue(all(v) and all(w) and all(normal))
        for exponent in (-30, -32, -33):
            weak = [x + 2**exponent * y for x, y in zip(v, w)]
            for permutation in (tuple(range(8)), (7, 2, 5, 0, 6, 1, 4, 3)):
                permute = lambda vector: [vector[i] for i in permutation]
                queries = [permute(v), permute(w), permute([a+b for a, b in zip(v, w)])]
                reference = contrast.basis_from_contrasts([permute(v), permute(weak)])
                for scale in (1.0, -2.0, 2**-1000):
                    with self.subTest(exponent=exponent, permutation=permutation, scale=scale):
                        rows = [[scale*x for x in permute(vector)] for vector in (v, weak)]
                        basis = contrast.basis_from_contrasts(rows)
                        self.assertEqual(len(basis), 2)
                        self.assertEqual(basis, reference)
                        self.assertEqual(contrast.basis_from_contrasts(rows[::-1] * 2), basis)
                        self.assertCertificate(basis)
                        self.assertTrue(contrast.contains_contrasts(rows + queries, basis))
                        self.assertFalse(contrast.contains_contrasts([permute(normal)], basis))
                        n = permute(normal)
                        for direction in basis:
                            self.assertLessEqual(abs(math.fsum(a*b for a, b in zip(direction, n)))
                                                 / math.hypot(*n), 1e-15)

    def test_dense_ill_conditioned_partial_and_full_rank_source_spans(self):
        directions = [walsh(i) for i in range(8)]
        for rank in range(2, 9):
            for exponent in (-28, -30):
                with self.subTest(rank=rank, exponent=exponent):
                    rows = [directions[0]] + [[a + 2**exponent*b for a, b in
                                              zip(directions[0], direction)]
                                             for direction in directions[1:rank]]
                    basis = contrast.basis_from_contrasts(rows)
                    self.assertEqual(len(basis), rank)
                    self.assertCertificate(basis)
                    self.assertTrue(contrast.contains_contrasts(rows + directions[:rank], basis))
                    self.assertEqual(contrast.basis_from_contrasts(rows[::-1]), basis)
                    for normal in directions[rank:]:
                        self.assertFalse(contrast.contains_contrasts([normal], basis))
                        for direction in basis:
                            self.assertLessEqual(abs(math.fsum(a*b for a, b in
                                                              zip(direction, normal))), 1e-15)

    def test_dense_subnormal_plane_preserves_exact_source_span(self):
        tiny = math.ulp(0.0)
        v, w = rotate(row(0.5, 0.75, -0.25)), rotate(row(-0.25, 0.5, 0.75))
        normal = rotate(row(11/8, -5/8, 7/8))
        # Integer multiples of the smallest subnormal preserve the dyadic plane.
        rows = [[int(16*x)*tiny for x in v],
                [int(16*a + 16*b)*tiny for a, b in zip(v, w)]]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 2)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows + [v, w], basis))
        self.assertFalse(contrast.contains_contrasts([normal], basis))

    def test_dense_hierarchical_near_threshold_source_spans(self):
        directions = [walsh(i) for i in range(8)]
        permutation = (6, 0, 4, 2, 7, 1, 5, 3)
        directions = [[v[i] for i in permutation] for v in directions]
        for rank in range(2, 8):
            # Successive weak directions differ by factors of eight. The last
            # direction is only 2**-32, just above the unchanged rank policy.
            exponents = range(-32 + 3*(rank-2), -33, -3)
            rows = [directions[0]] + [[a + 2**e*b for a, b in zip(directions[0], v)]
                                     for e, v in zip(exponents, directions[1:rank])]
            reference = contrast.basis_from_contrasts(rows)
            for scale in (1.0, -2**-900):
                with self.subTest(rank=rank, scale=scale):
                    scaled = [[scale*x for x in vector] for vector in rows]
                    basis = contrast.basis_from_contrasts(scaled[::-1])
                    self.assertEqual(len(basis), rank)
                    self.assertEqual(basis, reference)
                    self.assertCertificate(basis)
                    self.assertTrue(contrast.contains_contrasts(scaled + directions[:rank], basis))
                    for normal in directions[rank:]:
                        self.assertFalse(contrast.contains_contrasts([normal], basis))
                        for direction in basis:
                            self.assertLessEqual(abs(math.fsum(a*b for a, b in
                                                              zip(direction, normal))), 1e-15)

    def test_builder_isolates_and_restores_complete_decimal_context(self):
        rows = [rotate(row(0.5, 0.75, -0.25)), rotate(row(-0.25, 0.5, 0.75))]
        rows[1] = [a + 2**-33*b for a, b in zip(rows[0], rows[1])]
        expected = contrast.basis_from_contrasts(rows)
        outer = decimal.getcontext()
        with decimal.localcontext() as hostile:
            hostile.prec = 2
            hostile.rounding = decimal.ROUND_UP
            hostile.Emin, hostile.Emax = -2, 2
            hostile.capitals, hostile.clamp = 0, 1
            for signal in hostile.traps:
                hostile.traps[signal] = True
                hostile.flags[signal] = True
            saved = (hostile.prec, hostile.rounding, hostile.Emin, hostile.Emax,
                     hostile.capitals, hostile.clamp, dict(hostile.flags), dict(hostile.traps))
            self.assertEqual(contrast.basis_from_contrasts(rows), expected)
            with self.assertRaises(ValueError):
                contrast.basis_from_contrasts([row(True)])
            self.assertIs(decimal.getcontext(), hostile)
            self.assertEqual((hostile.prec, hostile.rounding, hostile.Emin, hostile.Emax,
                              hostile.capitals, hostile.clamp, dict(hostile.flags),
                              dict(hostile.traps)), saved)
        self.assertIs(decimal.getcontext(), outer)

    def test_builder_does_not_inherit_mutable_default_decimal_context(self):
        rows = [rotate(row(0.5, 0.75, -0.25)), rotate(row(-0.25, 0.5, 0.75))]
        rows[1] = [a + 2**-33*b for a, b in zip(rows[0], rows[1])]
        expected = contrast.basis_from_contrasts(rows)
        default = decimal.DefaultContext
        saved = default.copy()
        try:
            default.prec, default.rounding = 2, decimal.ROUND_FLOOR
            default.Emin, default.Emax = -2, 2
            default.capitals, default.clamp = 0, 1
            for signal in default.traps:
                default.traps[signal] = True
                default.flags[signal] = True
            self.assertEqual(contrast.basis_from_contrasts(rows), expected)
            self.assertEqual(default.prec, 2)
            self.assertTrue(all(default.flags.values()) and all(default.traps.values()))
        finally:
            for field in ("prec", "rounding", "Emin", "Emax", "capitals", "clamp", "flags", "traps"):
                setattr(default, field, getattr(saved, field))

    def test_nearly_dependent_below_rank_tolerance_refuses_own_weak_contrast(self):
        rows = [axis(0), row(1, 5e-11)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 1)
        # Both unit norms round to 1.0. Binary coordinate ordering retains e0,
        # rather than letting Decimal norm rounding select the unsupported tilt.
        self.assertEqual(basis, [axis(0)])
        self.assertTrue(contrast.contains_contrasts([axis(0)], basis))
        self.assertFalse(contrast.contains_contrasts(rows, basis))
        self.assertFalse(contrast.contains_contrasts([rows[1]], basis))

    def test_rank_tolerance_boundary_is_inclusive(self):
        for epsilon, expected_rank in ((1e-10, 1), (math.nextafter(1e-10, math.inf), 2)):
            with self.subTest(epsilon=epsilon):
                self.assertEqual(len(contrast.basis_from_contrasts([axis(0), row(1, epsilon)])),
                                 expected_rank)

    def test_membership_tolerance_is_stricter_than_rank(self):
        basis = [axis(0)]
        for epsilon, expected in ((5e-13, True), (1e-12, True), (2e-12, False)):
            with self.subTest(epsilon=epsilon):
                self.assertEqual(contrast.contains_contrasts([row(1, epsilon)], basis), expected)

    def test_dropped_direction_below_membership_tolerance_is_covered(self):
        rows = [axis(0), row(1, 5e-13)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 1)
        self.assertTrue(contrast.contains_contrasts(rows, basis))

    def test_smallest_subnormal_direction_does_not_disappear(self):
        tiny = math.ulp(0.0)
        rows = [row(tiny, tiny), row(tiny, -tiny)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 2)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows, basis))
        self.assertFalse(contrast.contains_contrasts([row(tiny, tiny)], []))

    def test_subnormal_anisotropy_normalizes_before_norm(self):
        tiny = math.ulp(0.0)
        vector = row(tiny, tiny * 1024)
        basis = contrast.basis_from_contrasts([vector])
        self.assertEqual(len(basis), 1)
        self.assertCertificate(basis)
        self.assertGreater(basis[0][0], 0)
        self.assertAlmostEqual(basis[0][1] / basis[0][0], 1024)
        self.assertTrue(contrast.contains_contrasts([row(1 / 1024, 1)], basis))

    def test_extreme_anisotropy_still_certifies(self):
        tiny = math.ulp(0.0)
        rows = [row(2, tiny), row(1e-300, 2e-300), axis(7)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 3)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows, basis))

    def test_tiny_absolute_but_independent_direction_retained(self):
        basis = contrast.basis_from_contrasts([axis(0), row(0, 1e-300)])
        self.assertEqual(len(basis), 2)
        self.assertTrue(contrast.contains_contrasts([axis(1)], basis))

    def test_all_features_covered_can_still_be_outside_span(self):
        basis = contrast.basis_from_contrasts([[1.0] * 8])
        self.assertTrue(all(value != 0 for value in basis[0]))
        self.assertTrue(contrast.contains_contrasts([[-2.0] * 8], basis))
        self.assertFalse(contrast.contains_contrasts([axis(0)], basis))

    def test_all_queries_required_even_if_most_are_supported(self):
        basis = [axis(0)]
        self.assertFalse(contrast.contains_contrasts([axis(0)] * 20 + [axis(1)], basis))
        self.assertFalse(contrast.contains_contrasts([axis(1)] + [axis(0)] * 20, basis))

    def test_membership_normalizes_query_magnitude(self):
        basis = [axis(0)]
        for scale in (1, 1e-300, math.ulp(0.0)):
            self.assertFalse(contrast.contains_contrasts([row(0, scale)], basis))
            self.assertTrue(contrast.contains_contrasts([row(scale)], basis))

    def test_unsupported_part_of_query_is_never_projected_away(self):
        basis = contrast.basis_from_contrasts([row(1, 1)])
        self.assertTrue(contrast.contains_contrasts([row(0.5, 0.5)], basis))
        self.assertFalse(contrast.contains_contrasts([row(0.5, 0.5, 1e-8)], basis))

    def test_accepted_anchors_do_not_imply_pairwise_cancellation_coverage(self):
        epsilon = contrast.MEMBERSHIP_TOLERANCE / 4
        anchors = [row(1, epsilon), row(1, -epsilon)]
        options = [row(), *anchors]
        all_pairs = [[a - b for a, b in zip(left, right)]
                     for left, right in itertools.combinations(options, 2)]
        cancellation = all_pairs[-1]
        self.assertEqual(cancellation, row(0, 2 * epsilon))
        trained_basis = contrast.basis_from_contrasts(anchors)
        self.assertEqual(len(trained_basis), 1)
        for basis in ([axis(0)], trained_basis):
            with self.subTest(basis=basis):
                self.assertCertificate(basis)
                for anchor in anchors:
                    self.assertTrue(contrast.contains_contrasts([anchor], basis))
                self.assertTrue(contrast.contains_contrasts(anchors, basis))
                # Cancellation leaves a tiny pure e2; normalization makes its
                # unsupported direction visible, regardless of absolute size.
                self.assertFalse(contrast.contains_contrasts([cancellation], basis))
                self.assertFalse(contrast.contains_contrasts(all_pairs, basis))

    def test_builtin_integer_coordinates_and_closed_bounds(self):
        rows = [row(2, -2), row(0, 2)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 2)
        self.assertTrue(contrast.contains_contrasts(rows, basis))

    def test_invalid_contrast_scalars_rejected_by_build_and_query(self):
        for value in (True, False, None, "1", 1j, math.nan, math.inf, -math.inf,
                      2.0000000000000004, -2.0000000000000004, 10 ** 10000, -(10 ** 10000)):
            with self.subTest(value_type=type(value).__name__):
                bad = row(value)
                with self.assertRaises(ValueError):
                    contrast.basis_from_contrasts([bad])
                with self.assertRaises(ValueError):
                    contrast.contains_contrasts([bad], [])

    def test_no_user_defined_numeric_coercion(self):
        class Coercible:
            def __float__(self):
                raise AssertionError("must not convert")

        class FloatSubclass(float):
            def __float__(self):
                raise AssertionError("must not convert")

        for value in (Coercible(), FloatSubclass(1)):
            with self.assertRaises(ValueError):
                contrast.basis_from_contrasts([row(value)])

    def test_invalid_contrast_dimensions_and_containers(self):
        for values in (None, 1, "12345678", {}, set(), [None], [1], [[0] * 7], [[0] * 9],
                       ["12345678"], [{i: 0 for i in range(8)}], [{0, 1}]):
            with self.subTest(value_type=type(values).__name__):
                with self.assertRaises(ValueError):
                    contrast.basis_from_contrasts(values)
                with self.assertRaises(ValueError):
                    contrast.contains_contrasts(values, [])

    def test_invalid_query_after_outside_row_still_rejected(self):
        with self.assertRaises(ValueError):
            contrast.contains_contrasts([axis(1), row(True)], [axis(0)])

    def test_basis_rejects_dimensions_count_and_nonunit_rows(self):
        for basis in ([[0] * 8], [[0] * 7], [[0] * 9], [row(2)], [row(0.5)],
                      [axis(i % 8) for i in range(9)]):
            with self.subTest(basis=basis):
                with self.assertRaises(ValueError):
                    contrast.validate_basis(basis)
                with self.assertRaises(ValueError):
                    contrast.contains_contrasts([], basis)

    def test_basis_rejects_nonorthogonal_and_duplicate_rows(self):
        diagonal = row(math.sqrt(0.5), math.sqrt(0.5))
        for basis in ([axis(0), axis(0)], [axis(0), diagonal], [axis(0), row(-1)]):
            with self.assertRaises(ValueError):
                contrast.validate_basis(basis)

    def test_basis_rejects_invalid_scalars_and_containers(self):
        for value in (math.nan, math.inf, -math.inf, True, False, None, "1", 1j,
                      10 ** 10000, -(10 ** 10000)):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    contrast.validate_basis([row(value)])
                with self.assertRaises(ValueError):
                    contrast.contains_contrasts([], [row(value)])
        for basis in (None, 1, "12345678", {}, set(), [None]):
            with self.assertRaises(ValueError):
                contrast.validate_basis(basis)

    def test_basis_validation_does_not_normalize_or_repair(self):
        with self.assertRaises(ValueError):
            contrast.validate_basis([row(1e-300)])
        with self.assertRaises(ValueError):
            contrast.contains_contrasts([axis(0)], [row(1e-300)])

    def test_basis_certificate_tolerance(self):
        self.assertIsNone(contrast.validate_basis([row(1 - 0.25e-12)]))
        with self.assertRaises(ValueError):
            contrast.validate_basis([row(1 - 2e-12)])
        self.assertIsNone(contrast.validate_basis([axis(0), row(0.5e-12, 1)]))
        with self.assertRaises(ValueError):
            contrast.validate_basis([axis(0), row(2e-12, 1)])

    def test_basis_coordinates_enforce_exact_schema_bounds_without_clamping(self):
        for magnitude in (math.nextafter(1.0, 2.0), 1.0 + 5e-13):
            for sign in (-1, 1):
                for index in range(8):
                    with self.subTest(magnitude=magnitude, sign=sign, index=index):
                        vector = axis(index)
                        vector[index] = sign * magnitude
                        saved = vector[:]
                        with self.assertRaises(ValueError):
                            contrast.validate_basis([vector])
                        with self.assertRaises(ValueError):
                            contrast.contains_contrasts([], [vector])
                        self.assertEqual(vector, saved)
                        # These same values remain valid bounded contrast inputs.
                        built = contrast.basis_from_contrasts([vector])
                        self.assertEqual(built, [axis(index)])
                        self.assertCertificate(built)
                        self.assertTrue(contrast.contains_contrasts([vector], built))

    def test_basis_accepts_exact_signed_coordinate_endpoints(self):
        for sign in (-1, 1):
            basis = [[sign * value for value in axis(index)] for index in range(8)]
            self.assertIsNone(contrast.validate_basis(basis))
            self.assertTrue(contrast.contains_contrasts([[2.0, -2.0] * 4], basis))

    def test_certificate_failure_raises_without_full_rank_fallback(self):
        # Fault-inject omitted orthogonalization; the public certificate must fail.
        with patch.object(contrast, "_precise_residual", side_effect=lambda vector, basis: list(vector)):
            with self.assertRaises(ValueError):
                contrast.basis_from_contrasts([axis(0), row(1, 1)])

    def test_generator_inputs_and_basis_are_consumed_once(self):
        basis = contrast.basis_from_contrasts((iter(axis(i)) for i in (0, 1)))
        self.assertTrue(contrast.contains_contrasts((iter(row(1, -1)) for _ in range(2)),
                                                  (iter(vector) for vector in basis)))
        self.assertIsNone(contrast.validate_basis(iter(basis)))

    def test_inputs_and_basis_are_not_mutated(self):
        rows = [row(-1, -0.5), axis(2)]
        saved = [vector[:] for vector in rows]
        basis = contrast.basis_from_contrasts(rows)
        saved_basis = [vector[:] for vector in basis]
        contrast.validate_basis(basis)
        self.assertTrue(contrast.contains_contrasts(rows, basis))
        self.assertEqual(rows, saved)
        self.assertEqual(basis, saved_basis)

    def test_budget_accepts_7000_rows_before_deduplication(self):
        rows = [axis(i % 8) for i in range(7000)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 8)
        self.assertTrue(contrast.contains_contrasts(rows, basis))

    def test_budget_rejects_7001_including_duplicates_and_zeros(self):
        for vector in (row(), axis(0)):
            with self.assertRaises(ValueError):
                contrast.basis_from_contrasts([vector] * 7001)
            with self.assertRaises(ValueError):
                contrast.contains_contrasts([vector] * 7001, [])

    def test_bounded_consumption_of_infinite_iterables(self):
        for operation in (contrast.basis_from_contrasts,
                          lambda values: contrast.contains_contrasts(values, [])):
            consumed = []

            def endless():
                while True:
                    consumed.append(1)
                    yield row()

            with self.assertRaises(ValueError):
                operation(endless())
            self.assertEqual(len(consumed), 7001)
            with self.assertRaises(ValueError):
                operation([itertools.repeat(0)])
        with self.assertRaises(ValueError):
            contrast.validate_basis(itertools.repeat(axis(0)))

    def test_budget_with_7000_unique_dense_rows(self):
        rng = random.Random(20261005)
        rows = [[rng.uniform(-2, 2) for _ in range(8)] for _ in range(7000)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 8)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows, basis))
        self.assertEqual(contrast.basis_from_contrasts(reversed(rows)), basis)

    def test_random_known_subspace_and_independent_query(self):
        rng = random.Random(83)
        # Disjoint blocks make an independently known 3D subspace of R8.
        rows = []
        for _ in range(100):
            a, b, c = (rng.uniform(-1, 1) for _ in range(3))
            rows.append([a, a, b, -b, c, c, c, c])
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 3)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows + [[1, 1, 2, -2, -1, -1, -1, -1]], basis))
        self.assertFalse(contrast.contains_contrasts([axis(0)], basis))

    def test_dense_ill_conditioned_rows_above_rank_policy_certify(self):
        rows = [[1.0 + (2e-9 if i == j else 0.0) for j in range(8)] for i in range(8)]
        basis = contrast.basis_from_contrasts(rows)
        self.assertEqual(len(basis), 8)
        self.assertCertificate(basis)
        self.assertTrue(contrast.contains_contrasts(rows, basis))

    def test_pure_stdlib_module_imports(self):
        # Inspect this file's imports without depending on other tests' imports.
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                imports.append(node.module)
        self.assertEqual(imports, ["decimal", "math"])


def benchmark():
    """Repeatable synthetic CPU/wall measurements; not API latency or a proof."""
    rng = random.Random(20261005)
    rows = [[rng.uniform(-2, 2) for _ in range(8)] for _ in range(7000)]
    assert len(set(map(tuple, rows))) == 7000
    wall, cpu = time.perf_counter(), time.process_time()
    basis = contrast.basis_from_contrasts(rows)
    construction = {"wall_seconds": time.perf_counter() - wall,
                    "cpu_seconds": time.process_time() - cpu}
    assert len(basis) == 8
    wall, cpu = time.perf_counter(), time.process_time()
    assert contrast.contains_contrasts(rows, basis)
    membership = {"wall_seconds": time.perf_counter() - wall,
                  "cpu_seconds": time.process_time() - cpu}

    cases = []
    v, w, n = map(rotate, (row(0.5, 0.75, -0.25), row(-0.25, 0.5, 0.75),
                            row(11/8, -5/8, 7/8)))
    for exponent in (-30, -32, -33):
        for _ in range(12):
            permutation = rng.sample(range(8), 8)
            signs = [rng.choice((-1, 1)) for _ in range(8)]
            transform = lambda vector: [sign*vector[i] for sign, i in zip(signs, permutation)]
            scale = rng.choice((1.0, -2.0, 2**-1000))
            training = [[scale*x for x in transform(vector)] for vector in
                        (v, [a + 2**exponent*b for a, b in zip(v, w)])]
            cases.append((2, training, [transform(v), transform(w)], [transform(n)]))
    for rank in range(2, 9):
        for trial in range(12):
            permutation = rng.sample(range(8), 8)
            signs = [rng.choice((-1, 1)) for _ in range(8)]
            directions = [[sign*rotate(walsh(j))[i] for sign, i in zip(signs, permutation)]
                          for j in range(8)]
            exponents = ([-30]*(rank-1) if trial % 2 else
                         range(-32 + 3*(rank-2), -33, -3))
            training = [directions[0]] + [[a + 2**e*b for a, b in zip(directions[0], d)]
                                         for e, d in zip(exponents, directions[1:rank])]
            scale = rng.choice((1.0, -2.0, 2**-1000))
            training = [[scale*x for x in vector] for vector in training]
            cases.append((rank, training, directions[:rank], directions[rank:]))
    wall, cpu = time.perf_counter(), time.process_time()
    leakage = 0.0
    query_error = 0.0
    for rank, training, queries, normals in cases:
        basis = contrast.basis_from_contrasts(training)
        assert len(basis) == rank
        assert contrast.contains_contrasts(training + queries, basis)
        assert contrast.basis_from_contrasts(reversed(training)) == basis
        for query in queries:
            query_error = max(query_error, math.hypot(*contrast._residual(
                contrast._unit_direction(query), basis)))
        for normal in normals:
            assert not contrast.contains_contrasts([normal], basis)
            for direction in basis:
                leakage = max(leakage, abs(math.fsum(a*b for a, b in zip(direction, normal)))
                              / math.hypot(*normal))
    diverse = {"cases": len(cases), "wall_seconds": time.perf_counter() - wall,
               "cpu_seconds": time.process_time() - cpu,
               "max_normalized_normal_leakage": leakage,
               "max_independent_query_residual": query_error}
    assert leakage <= 1e-15 and query_error <= contrast.MEMBERSHIP_TOLERANCE
    print(json.dumps({"python": sys.version.split()[0], "unique_dense_rows": len(rows),
                      "dense_rank": 8, "dense_construction": construction,
                      "dense_membership": membership, "diverse_ill_conditioned": diverse},
                     sort_keys=True))


if __name__ == "__main__":
    if sys.argv[1:] == ["--benchmark"]:
        benchmark()
    else:
        unittest.main()
