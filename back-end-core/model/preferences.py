"""Local choice feedback and an exploratory, uncalibrated preference baseline.

Integration: after BrainModel initialization, call initialize(db) in its own
transaction. Public store hooks own their transactions; the API caller must
enforce its existing unlock boundary. F6 editing purges optional feedback through
sources.purge_dependents; digest/version checks also exclude obsolete feedback.
Hard source deletion cascades.

These eight learned feature weights are separate from the thirteen rule state
parameters. Nothing here writes rule state, fits, effects, or review history.
No clinical, accuracy, calibrated probability, or maximum outcome utility claim.
Pure fit callers supply provenance-screened records; store ranking does that
screening in one snapshot. Three user-reviewed groups are only an exploratory
gate; neither group identities nor source counts prove event independence.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone

from core.pagination import revision
from . import reset, sources
from .catalog import PARTITIONS
from .contrast import basis_from_contrasts, contains_contrasts, validate_basis
from .ranking import VALUE_PARAMETERS, validate_options

DOMAINS = ("daily", "study", "relationships")
TARGETS = ("actual", "endorsed")
MAX_EVENTS = 32
MAX_RECORDS = 1000
MAX_PAYLOAD_BYTES = 65536
MAX_ITERATIONS = 64
MAX_BACKTRACKS = 32
GRADIENT_TOLERANCE = 1e-11
L2 = 0.1
MIN_GROUPS = 3
# Strong convexity gives ||w-w*||2 <= ||g||2/L2. In eight dimensions,
# ||option contrast||2 <= 2*sqrt(8), so gap error <= 160*||g||inf.
# This exceeds 160*GRADIENT_TOLERANCE (1.6e-9), with roundoff slack.
TIE_TOLERANCE = 1e-8
LEGACY_PAYLOAD_FIELDS = frozenset((
    "source_id", "event_id", "domain", "options", "actual_choice_id",
    "endorsed_choice_id", "endorsement_partition", "training_consent", "reason",
    "partition", "source_version", "model_epoch", "body_digest", "created_at",
))
PAYLOAD_FIELDS = LEGACY_PAYLOAD_FIELDS | {"group_id", "group_reviewed"}


def initialize(db: sqlite3.Connection) -> None:
    """Add only this table, idempotently; caller owns migration transaction."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS brain_choice_feedback (
            source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            event_id TEXT NOT NULL CHECK (length(event_id) BETWEEN 1 AND 128),
            source_version INTEGER NOT NULL CHECK (source_version >= 0),
            model_epoch INTEGER NOT NULL CHECK (model_epoch >= 0),
            body_digest TEXT NOT NULL CHECK (length(body_digest) = 64),
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
                CHECK (length(CAST(payload AS BLOB)) <= 65536),
            PRIMARY KEY (source_id, event_id)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS brain_choice_feedback_epoch "
               "ON brain_choice_feedback(model_epoch,source_id,event_id)")


def _text(value, name: str, maximum: int, *, minimum: int = 0) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{name} must be text with {minimum} to {maximum} characters")
    if "\0" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError(f"{name} must not contain NUL or surrogate code points")
    return value


def _enum(value, choices: tuple, name: str) -> str:
    _text(value, name, 128, minimum=1)
    if value not in choices:
        raise ValueError(f"invalid {name}")
    return value


def _group(group_id, group_reviewed) -> None:
    if type(group_reviewed) is not bool:
        raise ValueError("group_reviewed must be an explicit boolean")
    if group_id is not None:
        _text(group_id, "group_id", 128, minimum=1)
        if not group_id.strip():
            raise ValueError("group_id must contain text")
    if group_reviewed and group_id is None:
        raise ValueError("reviewed feedback requires a nonempty group_id")


def _integer(value, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative nonbool integer")
    return value


def _options(options: list[dict]) -> list[dict]:
    if not isinstance(options, list) or not 2 <= len(options) <= 8:
        raise ValueError("options must contain 2 to 8 items")
    checked = []
    for option in options:
        if (not isinstance(option, dict) or not {"id", "impacts"} <= option.keys()
                or option.keys() - {"id", "label", "impacts"}):
            raise ValueError("option fields must be id, impacts and optional label")
        item = {"id": _text(option["id"], "option id", 128, minimum=1)}
        if "label" in option:
            item["label"] = _text(option["label"], "option label", 512)
        impacts = option["impacts"]
        if not isinstance(impacts, dict) or len(impacts) > len(VALUE_PARAMETERS):
            raise ValueError("impacts must contain only the eight value features")
        for key, value in impacts.items():
            _enum(key, VALUE_PARAMETERS, "impact feature")
            if type(value) not in (int, float) or not -1 <= value <= 1 or not math.isfinite(value):
                raise ValueError("impacts must be finite nonbool numbers in [-1, 1]")
        item["impacts"] = dict(impacts)
        checked.append(item)
    validate_options(checked)
    return checked


def _labels(options, actual, endorsed, endorsement_partition) -> None:
    ids = {option["id"] for option in options}
    for label in (actual, endorsed):
        if label is not None:
            _text(label, "choice id", 128, minimum=1)
            if label not in ids:
                raise ValueError("choice ids must identify an option or be null")
    if endorsed is None:
        if endorsement_partition is not None:
            raise ValueError("null endorsement requires null endorsement_partition")
    else:
        _enum(endorsement_partition, PARTITIONS, "endorsement_partition")


def _request(target, partition, domain) -> None:
    _enum(target, TARGETS, "target")
    _enum(partition, PARTITIONS, "partition")
    _enum(domain, DOMAINS, "domain")


def _source(db, source_id):
    row = db.execute("SELECT i.*, s.body FROM brain_inputs i JOIN sources s "
                     "ON s.id=i.source_id WHERE i.source_id=?", (source_id,)).fetchone()
    if row is None:
        raise KeyError("brain input not found")
    return row


def _digest(body: str) -> str:
    if not isinstance(body, str) or len(body) > sources.MAX_CHARS:
        raise ValueError("source body exceeds text bound")
    digest = hashlib.sha256()
    for start in range(0, len(body), 65536):
        digest.update(body[start:start + 65536].encode("utf-8"))
    return digest.hexdigest()


def _source_metadata(db, source_id) -> dict:
    # Never cache i.*: interpretation/source references can also contain text.
    row = db.execute("SELECT i.status,i.immediate,i.confirm,i.source_version,i.partition "
                     "FROM brain_inputs i JOIN sources s ON s.id=i.source_id "
                     "WHERE i.source_id=?", (source_id,)).fetchone()
    if row is None:
        raise KeyError("brain input not found")
    return {**dict(row), "body_digest": None}


def _source_digest(db, source_id) -> str:
    # Bound validated, NUL-free source text before materializing it. SQLite's
    # length stops at NUL; _digest rechecks Python length after fetching legacy
    # text. This is not an allocation guarantee against malicious DB rewrites.
    # This helper's single body dies on return; the cache receives only a digest.
    row = db.execute("SELECT body FROM sources WHERE id=? AND length(body)<=?",
                     (source_id, sources.MAX_CHARS)).fetchone()
    if row is None:
        raise ValueError("source body missing or exceeds text bound")
    return _digest(row["body"])


def _public(payload: dict, row, epoch: int) -> dict:
    approved = row["status"] == "agreed" and row["immediate"] == 1 and row["confirm"] == 1
    eligible = (approved and payload["training_consent"] is True
                and payload["group_reviewed"] is True
                and payload["source_version"] == row["source_version"]
                and payload["partition"] == row["partition"]
                and payload["body_digest"] == _digest(row["body"])
                and payload["model_epoch"] == epoch)
    # This is feedback activity, not the rule model's per-source activity.
    return {**payload, "model_active": bool(eligible)}


def _decode(row) -> dict:
    raw = row["payload"]
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("invalid feedback payload")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or set(payload) not in (LEGACY_PAYLOAD_FIELDS, PAYLOAD_FIELDS):
        raise ValueError("invalid feedback schema")
    if set(payload) == LEGACY_PAYLOAD_FIELDS:
        # Normalize only the decoded view; never backfill persisted history.
        payload = {**payload, "group_id": None, "group_reviewed": False}
    for key in ("source_id", "event_id", "source_version", "model_epoch", "body_digest", "created_at"):
        if type(payload[key]) is not type(row[key]) or payload[key] != row[key]:
            raise ValueError("feedback provenance differs from row")
    _text(payload["source_id"], "source_id", 128, minimum=1)
    _text(payload["event_id"], "event_id", 128, minimum=1)
    _integer(payload["source_version"], "source_version")
    _integer(payload["model_epoch"], "model_epoch")
    digest = _text(payload["body_digest"], "body_digest", 64, minimum=64)
    if any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid body digest")
    _text(payload["created_at"], "created_at", 128, minimum=1)
    _training_record(payload)
    return payload


def set_feedback(store, source_id, event_id, domain, options, actual_choice_id,
                 endorsed_choice_id, endorsement_partition, training_consent,
                 expected_source_version, expected_revision, expected_epoch,
                 reason=None, group_id: str | None = None, group_reviewed: bool = False) -> dict:
    """Fully replace one event under exact version/revision/epoch guards.

    Pending feedback is saved, but consent never substitutes for source double
    approval. This explicit guarded save binds feedback to the current epoch;
    it cannot re-enlist the old rule model's fits. No automatic retry.
    """
    _text(source_id, "source_id", 128, minimum=1)
    _text(event_id, "event_id", 128, minimum=1)
    _enum(domain, DOMAINS, "domain")
    options = _options(options)
    _labels(options, actual_choice_id, endorsed_choice_id, endorsement_partition)
    if type(training_consent) is not bool:
        raise ValueError("training_consent must be an explicit boolean")
    _group(group_id, group_reviewed)
    if reason is not None:
        _text(reason, "reason", 2048)
    for name, value in (("expected_source_version", expected_source_version),
                        ("expected_revision", expected_revision), ("expected_epoch", expected_epoch)):
        _integer(value, name)
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = _source(db, source_id)
        epoch = reset.epoch(db)
        if (row["source_version"] != expected_source_version
                or revision(db) != expected_revision or epoch != expected_epoch):
            raise ValueError("feedback source/version/revision/epoch changed; refresh before saving")
        exists = db.execute("SELECT 1 FROM brain_choice_feedback WHERE source_id=? AND event_id=?",
                            (source_id, event_id)).fetchone()
        if not exists and db.execute("SELECT COUNT(*) FROM brain_choice_feedback WHERE source_id=?",
                                    (source_id,)).fetchone()[0] >= MAX_EVENTS:
            raise ValueError("at most 32 feedback events per input")
        payload = {"source_id": source_id, "event_id": event_id, "domain": domain,
                   "options": options, "actual_choice_id": actual_choice_id,
                   "endorsed_choice_id": endorsed_choice_id,
                   "endorsement_partition": endorsement_partition,
                   "training_consent": training_consent, "reason": reason,
                   "group_id": group_id, "group_reviewed": group_reviewed,
                   "partition": row["partition"], "source_version": row["source_version"],
                   "model_epoch": epoch, "body_digest": _digest(row["body"]),
                   "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError("feedback payload exceeds byte limit")
        db.execute("INSERT INTO brain_choice_feedback "
                   "(source_id,event_id,source_version,model_epoch,body_digest,created_at,payload) "
                   "VALUES (?,?,?,?,?,?,?) ON CONFLICT(source_id,event_id) DO UPDATE SET "
                   "source_version=excluded.source_version, model_epoch=excluded.model_epoch, "
                   "body_digest=excluded.body_digest, created_at=excluded.created_at, payload=excluded.payload",
                   (source_id, event_id, payload["source_version"], epoch, payload["body_digest"],
                    payload["created_at"], serialized))
        sources.bump_generation(db)
        return {**_public(payload, row, epoch), "input_revision": revision(db)}


def get_feedback(store, source_id) -> dict:
    """Current snapshot envelope; records retain their saved version/epoch."""
    _text(source_id, "source_id", 128, minimum=1)
    with store._connect() as db:
        db.execute("BEGIN")
        source = _source(db, source_id)
        epoch = reset.epoch(db)
        rows = db.execute("SELECT * FROM brain_choice_feedback WHERE source_id=? "
                          "ORDER BY event_id LIMIT 33", (source_id,)).fetchall()
        if len(rows) > MAX_EVENTS:
            raise ValueError("feedback event limit exceeded")
        return {"source_id": source_id, "records": [_public(_decode(r), source, epoch) for r in rows],
                "input_revision": revision(db), "model_epoch": epoch}


def _training_record(record: dict) -> tuple[list[dict], str | None, str | None]:
    if not isinstance(record, dict):
        raise ValueError("feedback record must be an object")
    _text(record.get("source_id"), "source_id", 128, minimum=1)
    _enum(record.get("partition"), PARTITIONS, "partition")
    _enum(record.get("domain"), DOMAINS, "domain")
    options = _options(record.get("options"))
    actual, endorsed = record.get("actual_choice_id"), record.get("endorsed_choice_id")
    _labels(options, actual, endorsed, record.get("endorsement_partition"))
    if "training_consent" in record and type(record["training_consent"]) is not bool:
        raise ValueError("training_consent must be an explicit boolean")
    if "model_active" in record and type(record["model_active"]) is not bool:
        raise ValueError("model_active must be boolean")
    if "group_id" in record or "group_reviewed" in record:
        _group(record.get("group_id"), record.get("group_reviewed", False))
    if record.get("reason") is not None:
        _text(record["reason"], "reason", 2048)
    return options, actual, endorsed


def _result(target, partition, domain, *, reason, training_sources=0, training_groups=0, weights=None,
            used_features=(), contrast_basis=None) -> dict:
    contrast_basis = [] if contrast_basis is None else contrast_basis
    return {"status": "abstain" if reason else "provisional", "reason": reason,
            "basis": "personal_choice_feedback_multinomial_logistic",
            "not_calibrated": True, "target": target, "partition": partition, "domain": domain,
            "training_sources": training_sources, "training_groups": training_groups,
            "used_features": list(used_features),
            "contrast_rank": len(contrast_basis), "contrast_basis": contrast_basis,
            "weights": weights if weights is not None else dict.fromkeys(VALUE_PARAMETERS, 0.0),
            "ranked": []}


def _vectors(options):
    # Sparse/missing features explicitly mean zero user-supplied impact.
    return [[float(option["impacts"].get(feature, 0)) for feature in VALUE_PARAMETERS]
            for option in options]


def _contrasts(vectors) -> set[str]:
    return {feature for index, feature in enumerate(VALUE_PARAMETERS)
            if any(vector[index] != vectors[0][index] for vector in vectors[1:])}


def _training_contrast_rows(vectors):
    # Vector content, rather than option IDs or labels, defines the anchor and
    # row order. At most seven rows describe an event's training geometry.
    ordered = sorted(vectors)
    return [[x - anchor for x, anchor in zip(vector, ordered[0])]
            for vector in ordered[1:]]


def _query_contrast_rows(vectors):
    # Approximate, normalized membership of anchor rows does not imply
    # membership of their difference: cancellation can expose a new direction.
    # Check all <=28 pairs; never project a query back into the training span.
    return [[x - y for x, y in zip(vector, other)]
            for i, vector in enumerate(vectors) for other in vectors[i + 1:]]


def _query_contrast_reason(vectors, used_features, contrast_basis):
    # Column support retains precedence; spanning those columns is a separate
    # engineering condition, not a claim of statistical validity or confidence.
    if _contrasts(vectors) - set(used_features):
        return "unsupported_option_features"
    if not contains_contrasts(_query_contrast_rows(vectors), contrast_basis):
        return "unidentified_option_contrasts"
    return None


def _softmax(scores):
    maximum = max(scores)
    exp = [math.exp(score - maximum) for score in scores]
    total = math.fsum(exp)
    return [value / total for value in exp]


def _objective(weights, events, *, derivatives=True):
    """Group-normalized NLL + L2/2 * ||w||2, gradient and SPD Hessian."""
    dimension = len(VALUE_PARAMETERS)
    loss = L2 / 2 * math.fsum(w * w for w in weights)
    gradient = [L2 * w for w in weights] if derivatives else []
    hessian = [[L2 if i == j else 0.0 for j in range(dimension)]
               for i in range(dimension)] if derivatives else []
    for vectors, chosen, scale in events:
        scores = [math.fsum(w * x for w, x in zip(weights, vector)) for vector in vectors]
        if not all(math.isfinite(score) for score in scores):
            raise ArithmeticError("nonfinite objective scores")
        maximum = max(scores)
        exp = [math.exp(score - maximum) for score in scores]
        total = math.fsum(exp)
        loss += scale * (maximum - scores[chosen] + math.log(total))
        if not derivatives:
            continue
        probabilities = [value / total for value in exp]
        mean = [math.fsum(p * vector[i] for p, vector in zip(probabilities, vectors))
                for i in range(dimension)]
        for i in range(dimension):
            gradient[i] += scale * (mean[i] - vectors[chosen][i])
        # Centered covariance avoids subtracting nearly equal second moments.
        for probability, vector in zip(probabilities, vectors):
            centered = [x - m for x, m in zip(vector, mean)]
            mass = scale * probability
            for i in range(dimension):
                for j in range(i + 1):
                    hessian[i][j] += mass * centered[i] * centered[j]
    for i in range(len(hessian)):
        for j in range(i):
            hessian[j][i] = hessian[i][j]
    if (not math.isfinite(loss) or not all(math.isfinite(g) for g in gradient)
            or not all(math.isfinite(x) for row in hessian for x in row)):
        raise ArithmeticError("nonfinite objective derivatives")
    return loss, gradient, hessian


def _solve_spd(hessian, gradient):
    """Cholesky solve H*d = -g; L2 makes every exact Hessian positive definite."""
    dimension = len(gradient)
    lower = [[0.0] * dimension for _ in gradient]
    for i in range(dimension):
        for j in range(i + 1):
            value = hessian[i][j] - math.fsum(lower[i][k] * lower[j][k] for k in range(j))
            if not math.isfinite(value) or (i == j and value <= 0):
                raise ArithmeticError("Hessian is not finite SPD")
            lower[i][j] = math.sqrt(value) if i == j else value / lower[j][j]
    forward = []
    for i in range(dimension):
        forward.append((-gradient[i] - math.fsum(lower[i][j] * forward[j] for j in range(i)))
                       / lower[i][i])
    direction = [0.0] * dimension
    for i in reversed(range(dimension)):
        direction[i] = (forward[i] - math.fsum(lower[j][i] * direction[j]
                                              for j in range(i + 1, dimension))) / lower[i][i]
    if not all(math.isfinite(value) for value in direction):
        raise ArithmeticError("nonfinite Newton direction")
    return direction


def _minimize(events):
    # Damped Newton/backtracking: Boyd & Vandenberghe, Convex Optimization, ch. 9
    # https://web.stanford.edu/~boyd/cvxbook/bv_cvxslides.pdf
    # A decrement or a small step alone never certifies a publishable fit.
    weights = [0.0] * len(VALUE_PARAMETERS)
    for iteration in range(MAX_ITERATIONS + 1):
        try:
            loss, gradient, hessian = _objective(weights, events)
        except (ArithmeticError, ValueError):
            return None, "nonfinite_fit"
        if max(abs(g) for g in gradient) <= GRADIENT_TOLERANCE:
            return weights, None  # actual gradient at the returned weights
        if iteration == MAX_ITERATIONS:
            break
        try:
            direction = _solve_spd(hessian, gradient)
        except (ArithmeticError, ValueError):
            break
        slope = math.fsum(g * d for g, d in zip(gradient, direction))
        if not math.isfinite(slope) or slope >= 0:
            break
        step = 1.0
        for _ in range(MAX_BACKTRACKS):
            candidate = [w + step * d for w, d in zip(weights, direction)]
            try:
                candidate_loss, _, _ = _objective(candidate, events, derivatives=False)
            except (ArithmeticError, ValueError):
                return None, "nonfinite_fit"
            # Close to the minimum, an Armijo decrease may be below loss
            # roundoff. That bounded exception also requires residual reduction.
            slack = 8 * math.ulp(max(1.0, abs(loss)))
            armijo = loss + 0.01 * step * slope
            accept = candidate_loss <= armijo
            if (not accept and abs(0.01 * step * slope) <= slack
                    and candidate_loss <= armijo + slack):
                try:
                    _, candidate_gradient, _ = _objective(candidate, events)
                except (ArithmeticError, ValueError):
                    return None, "nonfinite_fit"
                accept = max(abs(g) for g in candidate_gradient) < max(abs(g) for g in gradient)
            if accept:
                weights = candidate
                break
            step *= 0.5
        else:
            break
    return None, "fit_not_converged"


def fit_preferences(records: list[dict], *, target: str, partition: str, domain: str) -> dict:
    """Pure converged L2 multinomial fit, initialized at eight zero weights.

    Records require source_id, partition, domain, options; choice ids default to
    null. An endorsed id requires endorsement_partition. Pure callers screen
    provenance first; optional consent/eligibility flags are honored if present.
    Explicit group fields require user review; each informative group receives
    equal total loss mass across its sources and events, for this target/state/
    domain. Absent group fields retain caller-screened source_id fallback for
    offline callers. Three groups do not prove independence. Contradictory
    events remain counterexamples.
    """
    _request(target, partition, domain)
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if len(records) > MAX_RECORDS:
        return _result(target, partition, domain, reason="too_many_feedback_records")
    if target == "endorsed" and partition != "rational":
        return _result(target, partition, domain, reason="endorsed_requires_rational_partition")
    events = []
    informative_sources = set()
    for record in records:
        options, actual, endorsed = _training_record(record)
        if (record["domain"] != domain or record.get("training_consent") is False
                or record.get("model_active") is False):
            continue
        if "group_id" in record or "group_reviewed" in record:
            if record.get("group_reviewed", False) is not True:
                continue
            group = ("reviewed", record["group_id"])
        else:
            group = ("source", record["source_id"])
        if target == "actual":
            if record["partition"] != partition:
                continue
            label = actual
        else:
            if record.get("endorsement_partition") != "rational":
                continue
            label = endorsed
        if label is None:
            continue
        options = sorted(options, key=lambda option: option["id"])
        vectors = _vectors(options)
        if all(vector == vectors[0] for vector in vectors[1:]):
            continue
        chosen = next(i for i, option in enumerate(options) if option["id"] == label)
        # A labelled option sharing its entire feature vector supplies an
        # unidentifiable label; do not count it toward informative support.
        if any(vector == vectors[chosen] for i, vector in enumerate(vectors) if i != chosen):
            continue
        events.append((group, vectors, chosen))
        informative_sources.add(record["source_id"])
    counts = Counter(group for group, _, _ in events)
    training_sources, training_groups = len(informative_sources), len(counts)
    varied = set().union(*(_contrasts(vectors) for _, vectors, _ in events))
    used_features = [feature for feature in VALUE_PARAMETERS if feature in varied]
    # Geometry uses exactly the informative events admitted above. Canonical
    # accumulation and <=1000 events bound this to <=7000 eight-dimensional rows.
    events.sort(key=lambda event: (event[0], event[1], event[2]))
    contrast_basis = basis_from_contrasts([
        row for _, vectors, _ in events for row in _training_contrast_rows(vectors)])
    if training_groups < MIN_GROUPS:
        return _result(target, partition, domain, reason="insufficient_training_groups",
                       training_sources=training_sources, training_groups=training_groups,
                       used_features=used_features, contrast_basis=contrast_basis)
    normalized = [(vectors, chosen, 1.0 / (training_groups * counts[group]))
                  for group, vectors, chosen in events]
    weights, failure = _minimize(normalized)
    if failure:
        return _result(target, partition, domain, reason=failure,
                       training_sources=training_sources, training_groups=training_groups,
                       used_features=used_features, contrast_basis=contrast_basis)
    learned = dict(zip(VALUE_PARAMETERS, weights))
    if not contrast_basis or max(abs(weight) for weight in weights) <= TIE_TOLERANCE:
        return _result(target, partition, domain, reason="no_identifiable_preference",
                       training_sources=training_sources, training_groups=training_groups,
                       weights=learned, used_features=used_features, contrast_basis=contrast_basis)
    return _result(target, partition, domain, reason=None,
                   training_sources=training_sources, training_groups=training_groups,
                   weights=learned, used_features=used_features, contrast_basis=contrast_basis)


def rank_preferences(store, options, target, partition, domain) -> dict:
    """Fit on each bounded snapshot; never persist learned weights.

    Scan at most 1001 rows in the current epoch. Oversized or
    malformed snapshots abstain instead of fitting a biased partial sample.
    Snapshot revision/epoch describe the fit even if a later writer changes DB.
    """
    _request(target, partition, domain)
    options = _options(options)
    with store._connect() as db:
        db.execute("BEGIN")
        epoch, input_revision = reset.epoch(db), revision(db)
        # domain is in JSON so no unbounded JSON predicate scan; cap the whole
        # current-epoch cohort before parsing/filtering its domains.
        cohort_size = db.execute("SELECT COUNT(*) FROM (SELECT 1 FROM brain_choice_feedback "
                                 "WHERE model_epoch=? LIMIT 1001)", (epoch,)).fetchone()[0]
        if cohort_size > MAX_RECORDS:
            result = _result(target, partition, domain, reason="too_many_feedback_records")
        else:
            records, source_rows = [], {}
            try:
                rows = db.execute("SELECT * FROM brain_choice_feedback WHERE model_epoch=? "
                                  "ORDER BY source_id,event_id LIMIT 1001", (epoch,))
                for row in rows:
                    payload = _decode(row)
                    # Decode even excluded events: malformed provenance must
                    # still fail the snapshot closed. Skip text access afterward.
                    if (not payload["training_consent"] or not payload["group_reviewed"]
                            or payload["domain"] != domain
                            or (target == "actual" and (payload["partition"] != partition
                                                        or payload["actual_choice_id"] is None))
                            or (target == "endorsed" and (partition != "rational"
                                or payload["endorsement_partition"] != "rational"
                                or payload["endorsed_choice_id"] is None))):
                        continue
                    source_id = payload["source_id"]
                    if source_id not in source_rows:
                        source_rows[source_id] = _source_metadata(db, source_id)
                    source = source_rows[source_id]
                    if (source["status"] != "agreed" or source["immediate"] != 1
                            or source["confirm"] != 1
                            or payload["source_version"] != source["source_version"]
                            or payload["partition"] != source["partition"]
                            or payload["model_epoch"] != epoch):
                        continue
                    if source["body_digest"] is None:
                        source["body_digest"] = _source_digest(db, source_id)
                    if payload["body_digest"] == source["body_digest"]:
                        records.append({
                            "source_id": source_id, "partition": payload["partition"],
                            "domain": payload["domain"],
                            "options": [{"id": option["id"], "impacts": option["impacts"]}
                                        for option in payload["options"]],
                            "actual_choice_id": payload["actual_choice_id"],
                            "endorsed_choice_id": payload["endorsed_choice_id"],
                            "endorsement_partition": payload["endorsement_partition"],
                            "training_consent": True, "model_active": True,
                            "group_id": payload["group_id"], "group_reviewed": True,
                        })
                result = None
            except (ValueError, KeyError, UnicodeError, RecursionError, OverflowError):
                result = _result(target, partition, domain, reason="invalid_feedback_snapshot")
    # Release the read snapshot before numerical fitting. Return its
    # revision/epoch so consumers can detect a concurrently superseded result.
    if result is None:
        result = fit_preferences(records, target=target, partition=partition, domain=domain)
    result.update(model_epoch=epoch, input_revision=input_revision)
    if result["status"] == "abstain":
        return result
    contrast_reason = _query_contrast_reason(
        _vectors(options), result["used_features"], result["contrast_basis"])
    if contrast_reason:
        result.update(status="abstain", reason=contrast_reason)
        return result
    ranked = rank_from_fit(options, result)
    if not ranked:
        result.update(status="abstain", reason="options_tied_with_learned_weights")
    else:
        result["ranked"] = ranked
    return result


def rank_from_fit(options, fit: dict) -> list[dict]:
    """Pure scoring: abstention, unsupported/unidentified contrasts or top ties give [].

    model_probability is only a softmax model output, never calibrated personal
    likelihood. No source access, database writes, or rule-state interaction.
    """
    options = _options(options)
    if not isinstance(fit, dict) or fit.get("status") not in ("abstain", "provisional"):
        raise ValueError("fit must be a preference fit result")
    if fit["status"] == "abstain":
        return []
    used_features = fit.get("used_features")
    if (not isinstance(used_features, list)
            or any(not isinstance(key, str) or key not in VALUE_PARAMETERS for key in used_features)
            or len(set(used_features)) != len(used_features)):
        raise ValueError("fit must list distinct varied training features")
    contrast_rank, contrast_basis = fit.get("contrast_rank"), fit.get("contrast_basis")
    if (type(contrast_rank) is not int or not 1 <= contrast_rank <= 8
            or not isinstance(contrast_basis, list) or len(contrast_basis) != contrast_rank):
        raise ValueError("provisional fit requires an exact nonbool contrast rank and basis")
    if any(not isinstance(row, list) or len(row) != 8
           or any(type(value) not in (int, float) or not -1 <= value <= 1
                  or not math.isfinite(value) for value in row)
           for row in contrast_basis):
        raise ValueError("fit contrast basis requires eight finite nonbool coordinates in [-1, 1]")
    validate_basis(contrast_basis)
    if any(row[i] != 0 for row in contrast_basis
           for i, feature in enumerate(VALUE_PARAMETERS) if feature not in used_features):
        raise ValueError("fit contrast basis must be zero in unused feature columns")
    learned = fit.get("weights")
    if not isinstance(learned, dict) or set(learned) != set(VALUE_PARAMETERS):
        raise ValueError("fit must have exactly eight learned weights")
    weights = []
    for feature in VALUE_PARAMETERS:
        value = learned[feature]
        if type(value) not in (int, float) or abs(value) > 10 or not math.isfinite(value):
            raise ValueError("fit weights must be finite numbers bounded by 10")
        weights.append(float(value))
    vectors = _vectors(options)
    if _query_contrast_reason(vectors, used_features, contrast_basis):
        return []
    scores = [math.fsum(w * x for w, x in zip(weights, vector)) for vector in vectors]
    probabilities = _softmax(scores)
    ranked = sorted((
        {"id": option["id"], "score": score, "model_probability": probability,
         "contributions": {feature: weight * value
                           for feature, weight, value in zip(VALUE_PARAMETERS, weights, vector)}}
        for option, vector, score, probability in zip(options, vectors, scores, probabilities)
    ), key=lambda item: (-item["score"], item["id"]))
    if abs(ranked[0]["score"] - ranked[1]["score"]) <= TIE_TOLERANCE:
        return []
    return ranked
