"""Local choice feedback and an exploratory, uncalibrated preference baseline.

Integration: after BrainModel initialization, call initialize(db) in its own
transaction. Public store hooks own their transactions; the API caller must
enforce its existing unlock boundary. F6 editing must later add an optional
DELETE FROM brain_choice_feedback WHERE source_id=? to sources.purge_dependents.
Until then, digest/version checks exclude retained obsolete feedback, but do
not erase its labels/reason. Hard source deletion already cascades.

These eight learned feature weights are separate from the thirteen rule state
parameters. Nothing here writes rule state, fits, effects, or review history.
No clinical, accuracy, calibrated probability, or maximum outcome utility claim.
Pure fit callers supply provenance-screened records; store ranking does that
screening in one snapshot. Three source identities are only an exploratory gate.
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
from .ranking import VALUE_PARAMETERS, validate_options

DOMAINS = ("daily", "study", "relationships")
TARGETS = ("actual", "endorsed")
MAX_EVENTS = 32
MAX_RECORDS = 1000
MAX_PAYLOAD_BYTES = 65536
ITERATIONS = 400
L2 = 0.1
STEP = 0.2
MIN_SOURCES = 3
TIE_TOLERANCE = 1e-10
PAYLOAD_FIELDS = frozenset((
    "source_id", "event_id", "domain", "options", "actual_choice_id",
    "endorsed_choice_id", "endorsement_partition", "training_consent", "reason",
    "partition", "source_version", "model_epoch", "body_digest", "created_at",
))


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
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _public(payload: dict, row, epoch: int) -> dict:
    approved = row["status"] == "agreed" and row["immediate"] == 1 and row["confirm"] == 1
    eligible = (approved and payload["training_consent"] is True
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
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_FIELDS:
        raise ValueError("invalid feedback schema")
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
                 reason=None) -> dict:
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
    if record.get("reason") is not None:
        _text(record["reason"], "reason", 2048)
    return options, actual, endorsed


def _result(target, partition, domain, *, reason, training_sources=0, weights=None,
            used_features=()) -> dict:
    return {"status": "abstain" if reason else "provisional", "reason": reason,
            "basis": "personal_choice_feedback_multinomial_logistic",
            "not_calibrated": True, "target": target, "partition": partition, "domain": domain,
            "training_sources": training_sources,
            "used_features": list(used_features),
            "weights": weights if weights is not None else dict.fromkeys(VALUE_PARAMETERS, 0.0),
            "ranked": []}


def _vectors(options):
    # Sparse/missing features explicitly mean zero user-supplied impact.
    return [[float(option["impacts"].get(feature, 0)) for feature in VALUE_PARAMETERS]
            for option in options]


def _contrasts(vectors) -> set[str]:
    return {feature for index, feature in enumerate(VALUE_PARAMETERS)
            if any(vector[index] != vectors[0][index] for vector in vectors[1:])}


def _softmax(scores):
    maximum = max(scores)
    exp = [math.exp(score - maximum) for score in scores]
    total = sum(exp)
    return [value / total for value in exp]


def fit_preferences(records: list[dict], *, target: str, partition: str, domain: str) -> dict:
    """Pure fixed-step L2 multinomial fit, initialized at eight zero weights.

    Records require source_id, partition, domain, options; choice ids default to
    null. An endorsed id requires endorsement_partition. Pure callers screen
    provenance first; optional consent/eligibility flags are honored if present.
    Every independent source receives equal total loss mass, divided over its
    informative labelled events. Contradictory events remain counterexamples.
    """
    _request(target, partition, domain)
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if len(records) > MAX_RECORDS:
        return _result(target, partition, domain, reason="too_many_feedback_records")
    if target == "endorsed" and partition != "rational":
        return _result(target, partition, domain, reason="endorsed_requires_rational_partition")
    events = []
    for record in records:
        options, actual, endorsed = _training_record(record)
        if (record["domain"] != domain or record.get("training_consent") is False
                or record.get("model_active") is False):
            continue
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
        vectors = _vectors(options)
        if all(vector == vectors[0] for vector in vectors[1:]):
            continue
        chosen = next(i for i, option in enumerate(options) if option["id"] == label)
        # A labelled option sharing its entire feature vector supplies an
        # unidentifiable label; do not count it toward independent support.
        if any(vector == vectors[chosen] for i, vector in enumerate(vectors) if i != chosen):
            continue
        events.append((record["source_id"], vectors, chosen))
    counts = Counter(source for source, _, _ in events)
    varied = set().union(*(_contrasts(vectors) for _, vectors, _ in events))
    used_features = [feature for feature in VALUE_PARAMETERS if feature in varied]
    if len(counts) < MIN_SOURCES:
        return _result(target, partition, domain, reason="insufficient_independent_sources",
                       training_sources=len(counts), used_features=used_features)
    weights = [0.0] * len(VALUE_PARAMETERS)
    for _ in range(ITERATIONS):
        gradient = [L2 * weight for weight in weights]
        for source, vectors, chosen in events:
            scores = [sum(w * x for w, x in zip(weights, vector)) for vector in vectors]
            probabilities = _softmax(scores)
            scale = 1.0 / (len(counts) * counts[source])
            for index, vector in enumerate(vectors):
                error = (probabilities[index] - int(index == chosen)) * scale
                for feature, value in enumerate(vector):
                    gradient[feature] += error * value
        weights = [w - STEP * g for w, g in zip(weights, gradient)]
    learned = dict(zip(VALUE_PARAMETERS, weights))
    if not all(math.isfinite(weight) for weight in weights):
        return _result(target, partition, domain, reason="nonfinite_fit", training_sources=len(counts))
    if max(abs(weight) for weight in weights) <= TIE_TOLERANCE:
        return _result(target, partition, domain, reason="no_identifiable_preference",
                       training_sources=len(counts), weights=learned, used_features=used_features)
    return _result(target, partition, domain, reason=None, training_sources=len(counts),
                   weights=learned, used_features=used_features)


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
        rows = db.execute("SELECT * FROM brain_choice_feedback WHERE model_epoch=? "
                          "ORDER BY source_id,event_id LIMIT 1001", (epoch,)).fetchall()
        if len(rows) > MAX_RECORDS:
            result = _result(target, partition, domain, reason="too_many_feedback_records")
        else:
            records, source_rows = [], {}
            try:
                for row in rows:
                    payload = _decode(row)
                    source_id = payload["source_id"]
                    if source_id not in source_rows:
                        source_rows[source_id] = _source(db, source_id)
                    public = _public(payload, source_rows[source_id], epoch)
                    if public["model_active"]:
                        records.append(public)
                result = None
            except (ValueError, KeyError, UnicodeError, RecursionError, OverflowError):
                result = _result(target, partition, domain, reason="invalid_feedback_snapshot")
    # Release the read snapshot before all 400 gradient iterations. Return its
    # revision/epoch so consumers can detect a concurrently superseded result.
    if result is None:
        result = fit_preferences(records, target=target, partition=partition, domain=domain)
    result.update(model_epoch=epoch, input_revision=input_revision)
    if result["status"] == "abstain":
        return result
    if _contrasts(_vectors(options)) - set(result["used_features"]):
        result.update(status="abstain", reason="unsupported_option_features")
        return result
    ranked = rank_from_fit(options, result)
    if not ranked:
        result.update(status="abstain", reason="options_tied_with_learned_weights")
    else:
        result["ranked"] = ranked
    return result


def rank_from_fit(options, fit: dict) -> list[dict]:
    """Pure scoring: abstention, unsupported option contrasts or top ties give [].

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
    learned = fit.get("weights")
    if not isinstance(learned, dict) or set(learned) != set(VALUE_PARAMETERS):
        raise ValueError("fit must have exactly eight learned weights")
    weights = []
    for feature in VALUE_PARAMETERS:
        value = learned[feature]
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 10:
            raise ValueError("fit weights must be finite numbers bounded by 10")
        weights.append(float(value))
    vectors = _vectors(options)
    if _contrasts(vectors) - set(used_features):
        return []
    scores = [sum(w * x for w, x in zip(weights, vector)) for vector in vectors]
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
