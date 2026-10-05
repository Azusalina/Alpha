"""Bounded, eight-dimensional contrast geometry using only the standard library.

Rows are option differences in [-2, 2]. Each nonzero row is scaled by its
largest absolute coordinate, then normalized: magnitude does not
determine coverage. Rank and membership tolerances are engineering policies,
not statistical confidence, measurement precision, or magnitude coverage.
In particular, a direction dropped by rank policy can fail membership later,
including when querying the original training rows.

The construction uses deterministic pivoted, twice-reorthogonalized modified
Gram--Schmidt in an isolated 80-digit Decimal context. Original binary floats
are converted exactly before normalization; only the exported basis is rounded
to floats. This avoids amplifying binary normalization error in weak pivots.
Eighty digits provide guard precision for the bounded eight-pivot construction;
synthetic near-threshold, rotated and subnormal regressions exercise this choice,
not a formal numerical error bound or equivalence to SVD rank selection. Scalar
sums of squares compute norms; no squared Gram matrix is formed. Membership
still uses float reorthogonalization against the exported, validated basis.
"""

from decimal import (Context, Decimal, DivisionByZero, InvalidOperation,
                     Overflow, ROUND_HALF_EVEN, localcontext)
from math import fsum, hypot, isfinite


DIMENSION = 8
MAX_CONTRASTS = 7000
RANK_TOLERANCE = 1e-10
MEMBERSHIP_TOLERANCE = 1e-12
ORTHOGONALITY_TOLERANCE = 1e-12


def _iterator(values, label):
    # Unordered/mapping/string containers are not coordinate sequences.
    if isinstance(values, (str, bytes, bytearray, dict, set, frozenset)):
        raise ValueError(f"{label} must be an ordered iterable")
    try:
        return iter(values)
    except TypeError as exc:
        raise ValueError(f"{label} must be an ordered iterable") from exc


def _rows(values, limit, label):
    """Validate before conversion, consuming at most limit+1 rows, 9 scalars/row."""
    rows = []
    for row in _iterator(values, label):
        if len(rows) == limit:
            raise ValueError(f"{label} must contain at most {limit} rows")
        coordinates = []
        for value in _iterator(row, f"{label} row"):
            if len(coordinates) == DIMENSION:
                raise ValueError(f"{label} rows must have {DIMENSION} coordinates")
            # Exact builtin types exclude bool and user-defined coercion hooks.
            # Check bounds on integers BEFORE float conversion (even huge ints).
            if type(value) not in (int, float):
                raise ValueError(f"{label} coordinates must be real int/float values")
            if not -2 <= value <= 2 or not isfinite(value):
                raise ValueError(f"{label} coordinates must be finite and in [-2, 2]")
            coordinates.append(float(value))
        if len(coordinates) != DIMENSION:
            raise ValueError(f"{label} rows must have {DIMENSION} coordinates")
        rows.append(coordinates)
    return rows


def _canonical_sign(row):
    sign = next((1.0 if value > 0 else -1.0 for value in row if value), 1.0)
    return [sign * value if value else 0.0 for value in row]


def _unit_direction(row):
    scale = max(map(abs, row))
    if scale == 0.0:
        return None
    scaled = [value / scale for value in row]
    length = hypot(*scaled)
    return _canonical_sign([value / length for value in scaled])


def _dot(left, right):
    return fsum(a * b for a, b in zip(left, right))


def _residual(row, basis):
    residual = list(row)
    # Reorthogonalization is also used for membership. Always start from the
    # complete query direction; unsupported coordinates must remain in residual.
    for _ in range(2):
        for direction in basis:
            coefficient = _dot(residual, direction)
            residual = [fsum((value, -coefficient * component))
                        for value, component in zip(residual, direction)]
    return residual


def _precise_unit_direction(row):
    scale = max(value.copy_abs() for value in row)
    if not scale:
        return None
    scaled = [value / scale for value in row]
    length = sum(value * value for value in scaled).sqrt()
    sign = next(1 if value > 0 else -1 for value in scaled if value)
    return tuple(sign * value / length if value else Decimal(0) for value in scaled)


def _precise_residual(row, basis):
    residual = list(row)
    for _ in range(2):
        for direction in basis:
            coefficient = sum(a * b for a, b in zip(residual, direction))
            residual = [value - coefficient * component
                        for value, component in zip(residual, direction)]
    return residual


def _checked_basis(basis):
    rows = _rows(basis, DIMENSION, "basis")
    for index, row in enumerate(rows):
        if any(abs(value) > 1.0 for value in row):
            raise ValueError("basis coordinates must be in [-1, 1]")
        if abs(hypot(*row) - 1.0) > ORTHOGONALITY_TOLERANCE:
            raise ValueError("basis rows must be unit vectors")
        for previous in rows[:index]:
            if abs(_dot(row, previous)) > ORTHOGONALITY_TOLERANCE:
                raise ValueError("basis rows must be mutually orthogonal")
    return rows


def validate_basis(basis) -> None:
    """Raise ValueError unless basis has at most eight finite orthonormal rows.

    An empty basis is valid. Coordinates must be exactly within [-1, 1].
    Validation certifies unit length and pairwise orthogonality within
    ORTHOGONALITY_TOLERANCE; it never repairs input.
    """
    _checked_basis(basis)


def basis_from_contrasts(contrasts) -> list[list[float]]:
    """Return a deterministic numerical span of at most 7000 bounded rows.

    Exactly convert original floats, then normalize, canonicalize signs and
    deduplicate in Decimal arithmetic. Sort by float-rounded coordinate tuples,
    with precise tuples as a secondary tie breaker. Each pivot maximizes the
    binary64-rounded twice-orthogonalized residual norm; sorted order resolves
    rounded norm ties. This preserves the old binary ordering policy without
    using rounded coordinates in the span calculation.
    Precise residuals <= RANK_TOLERANCE are discarded. Recompute
    residuals from the precise normalized source rows on every iteration, keeping
    precise pivots until the complete basis is exported. A fresh full context
    isolates precision, rounding, exponent limits, flags and traps from callers.
    A failed certificate raises ValueError, never a full-rank fallback.
    """
    rows = _rows(contrasts, MAX_CONTRASTS, "contrasts")
    # Binary64 inputs span exponents down to -1074 (decimal order -324).
    # Scaling precedes norms; these exponent limits also accommodate their
    # squared coordinate ratios. Supply every context field, including traps,
    # rather than inheriting a caller's context or mutable DefaultContext.
    context = Context(prec=80, rounding=ROUND_HALF_EVEN, Emin=-999999,
                      Emax=999999, capitals=1, clamp=0, flags=[],
                      traps=[InvalidOperation, DivisionByZero, Overflow])
    with localcontext(context):
        directions = set()
        for row in rows:
            direction = _precise_unit_direction([Decimal.from_float(value) for value in row])
            if direction is not None:
                directions.add(direction)
        candidates = sorted(directions, key=lambda direction: (tuple(map(float, direction)),
                                                               direction))
        precise_basis = []
        while candidates and len(precise_basis) < DIMENSION:
            pivot_index = None
            pivot_residual = None
            rank_tolerance = Decimal.from_float(RANK_TOLERANCE)
            pivot_norm = -1.0
            for index, row in enumerate(candidates):
                residual = _precise_residual(row, precise_basis)
                length = sum(value * value for value in residual).sqrt()
                if length > rank_tolerance and float(length) > pivot_norm:
                    pivot_index, pivot_residual, pivot_norm = index, residual, float(length)
            if pivot_index is None:
                break
            direction = _precise_unit_direction(pivot_residual)
            if direction is None:
                raise ValueError("nonzero pivot could not be normalized")
            precise_basis.append(direction)
            candidates.pop(pivot_index)
        basis = [_canonical_sign([float(value) for value in direction])
                 for direction in precise_basis]
    validate_basis(basis)
    return basis


def contains_contrasts(contrasts, basis) -> bool:
    """Whether ALL nonzero query directions lie within membership tolerance.

    Validate all inputs even when an earlier query is outside. Zero rows impose
    no constraint. Coordinate/feature coverage alone is not span membership.
    Rows discarded during construction have no exemption from this check.
    """
    directions = _checked_basis(basis)
    rows = _rows(contrasts, MAX_CONTRASTS, "contrasts")
    for row in rows:
        direction = _unit_direction(row)
        if direction is not None:
            if hypot(*_residual(direction, directions)) > MEMBERSHIP_TOLERANCE:
                return False
    return True
