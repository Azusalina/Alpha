# Model v1 parameter register

These are **local modeling hypotheses**, not standardized psychological scores.
All numeric personal values start at 0 in `model/baseline.json`; `support=0`
means unobserved. Each of the three partitions has its own copy. A source can
contribute at most once to any one parameter. Only sources with whole-input
`immediate=true` and `confirm=true` contribute in the current model epoch;
`revoke` removes them from the active fit. Approval history alone is not current
model participation (`model_active`/`model_epoch`).

Confirmed decisions (2026-10-01), pending implementation/verification: extracted
candidate memories will publish automatically on current-source double approval,
without silently publishing legacy pending/rejected candidates. This does not
activate the deferred parameter hypotheses below. Reviewed semantic revisions
must withdraw current contributions and obtain renewed double consent before
fitting; explicit replay must preserve historical effects and reset exclusions.

## Active in v1

| Parameter IDs | Domain | Evidence accepted now | Not inferred from |
| --- | --- | --- | --- |
| `value.autonomy`, `value.fairness`, `value.care`, `value.truth` | Value priorities | Explicit first-person importance statements, or agreed `philosophy` statements | Topic mentions or another speaker's views |
| `value.security`, `value.growth`, `value.achievement`, `value.connection` | Value priorities | Same narrow rule | Single events without an expressed value |
| `affect.disappointment`, `affect.sadness`, `affect.happiness`, `affect.anger` | Textual affect | Non-negated self-expression candidates from translator | A clinical diagnosis, voice prosody, or durable personality |
| `expression.less_initiative` | Stated intention | Explicit first-person reduced-contact wording | Actual future behavior or general attachment style |

Value labels are inspired by work on value priorities, but **this project's
scores are not Schwartz questionnaire scores**. The subset and Chinese word
patterns are engineering choices pending user validation. See the original
[Schwartz et al. paper](https://pubmed.ncbi.nlm.nih.gov/22823292/).

The active score is `net evidence / (support + 4)`. The fixed `4` shrinks small
samples toward zero; it is an algorithm constant, not a personal parameter.
`support`, source references, exact evidence spans, update rule IDs, and the
revision history must be inspected alongside every value. A value at zero can
mean either no evidence or balanced positive/negative evidence; `observed`
disambiguates them. The three partitions are never averaged into one trait.

## Deferred until there is relevant feedback

| Candidate | Why it is deferred | Minimum evidence needed |
| --- | --- | --- |
| `decision.risk_sensitivity` | Narrative mentions do not identify risk preference | Comparable choices with known uncertainty and retrospective endorsement |
| `decision.time_horizon` | Short/long-term behavior may reflect circumstance | Repeated trade-offs across time and context |
| `decision.evidence_threshold` | Need to observe information-seeking before decisions | Choices made with different levels of uncertainty |
| `decision.outcome_utility` | Cannot assume one universal definition of “benefit” | User-defined outcomes and pairwise preference feedback |
| `relationship.boundary_rule` | Person-specific events should not become a global trait | Repeated relationship-specific decisions and correction |
| `identity.long_term_goal` | One aspiration is not a fitted parameter | Explicit goals plus dated revisions and user confirmation |
| `choice_endorsement_gap` | A choice can be real but not endorsed in hindsight | Separate factual-choice and retrospective-endorsement labels |

The first personal-fit evaluation should use held-out, retrospectively
endorsed choices in the targeted daily/study/interpersonal domains. Compare
the model with and without each candidate parameter (ablation), measure
coverage/abstention and ranking quality, and keep a parameter only when the
data support its benefit. Until such labels exist, `rank_options` is a
provisional *value-alignment* utility, not “the user's most likely choice.”

No real private held-out material is available this round; deliver local collection
templates/readiness tools only, pending worker verification. Independent real
labels and coverage/predictive validation remain external prerequisites; synthetic
fixtures do not justify activating or pruning parameters. F14 frontend choice
feedback remains deferred. See `TODO.md` for current scope exclusions and the
confirmed, still-pending F13 access-gate/encrypted-backup work; the current SQLite
database remains plaintext and whole-database encryption is outside this round.
