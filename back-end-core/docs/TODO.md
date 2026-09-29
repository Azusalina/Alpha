# Backend TODO

## Deferred: MMPI report import

- Not part of brain/model v1. The user will decide the version and input format later.
- If implemented, parse a user-provided official report as a separate source type,
  preserving test version, report date, scale names, supplied scores, validity
  notices, original interpretation, and source references.
- Do not reconstruct proprietary test scoring from items, generate a diagnosis,
  or automatically overwrite the user's value/decision model with clinical
  report fields. Interpretation and weighting require a separate decision.

## Model v1 decisions recorded

- Scope: local backend model for daily life, study, interpersonal events, and
  user-supplied philosophical statements/ideas. No frontend or sphere work.
- The frontend will have three separate input pages: rational, emotional, and
  user-named "crazy". A source belongs to one page/state. This last name is a
  user-facing state label, not a clinical diagnosis.
- One frontend boolean applies to one whole input and means agree/disagree.
  Agreement on rational material updates the rational partition; agreement on
  emotional or "crazy" material updates only its corresponding partition,
  without endorsing the recorded decision as a rational ideal.
- Preserve raw input even when the boolean is false, but do not use a rejected
  interpretation to fit the endorsed-self model. A correction path is needed.
- Keep an untouched original model snapshot with all numeric parameters at 0.
  Zero must also carry a separate "unobserved" marker so absence of evidence
  is not mistaken for a measured neutral preference. Only an active copy may
  learn from approved material; all updates stay local.
- The translator itself learns personal vocabulary from agreed material.
  Semantic-rule correction still requires more targeted feedback.
- Every parameter change needs an exact evidence reference and a reversible
  change record. The frontend can later consume these effects.

## Frontend feedback contract to implement later

- Provide three source-entry pages (rational, emotional, "crazy"). Return a
  stable `source_id`, page/state, and one agree/disagree boolean per whole input.
- Provide separate feedback for whether a past *choice* is still endorsed in
  hindsight. This is distinct from confirming that the source is authentic;
  its exact payload and timing are still to be agreed.
- Show the source, any inferred parameter changes, and the evidence behind
  them; permit correction without silently rewriting history.

## Pending decisions for model v1

- Add targeted semantic correction feedback so the translator can learn meaning,
  not only user vocabulary. One source-level boolean cannot identify a wrong
  extracted phrase, value, or event.
- Evaluate whether candidate parameters improve predictions using future
  retrospectively endorsed choice labels; remove ineffective parameters.
- Define the user's retrospectively endorsed choice labels and the model's
  abstention rule when too few examples exist.
