# Mixed diary/chat materials: static review (2026-10-03)

This change does not import, preview, fit or evaluate personal material. The
offline formatter uses only standard-library file operations, creates a new
0600 Markdown reading copy, and never overwrites the source or output.

## What v1 can read

- UTF-8 txt/md within the existing size limits, without NUL/surrogates.
- Diary/philosophy prose: bounded lexical rules, not comprehensive understanding.
- Chat: one `speaker: content` per line, exact `self_speaker` match. A standalone
  nickname, timestamp or continuation line is not automatically a chat message.
- Markdown is text, not an import schema. Headings/YAML/chapters do not create
  sources, assign consent or reliably exclude metadata from vocabulary learning.

## Gaps and handling

- Mixed periods/states must become separately reviewed inputs, not one whole-file
  approval. v1 has no per-event timeline/decay or automatic state partitioning.
- Third-person autobiographical narration is not a supported self-identity
  annotation. Existing ownership guards may withhold it as another person's
  viewpoint. Never globally replace pronouns: actual other people appear too.
- Multi-line chat exports, aliases and reply quotations need explicit provenance;
  do not guess speakers or flatten someone else's quoted reply into self speech.
- Self descriptions, others' traits, aspirations, hypotheses and analysis are
  different kinds of evidence. A self-authored report does not automatically
  endorse every cited statement. Human confirmation and exact corrections remain.
- Lexical coverage is narrow (13 numeric parameters); rich event interpretation,
  irony, complex negation and philosophical beliefs may be missed. No clinical
  diagnosis or comprehensive personality/choice validity is established.
- Words repeated across an entire compilation do not supply independent-source
  support. Splitting purely to inflate support is not valid.
- An unmatched quote can conservatively withhold later text. A narrow fix now
  treats a separator-delimited numeric day/month/year followed by `'` as date
  decoration only when no quote is already open. Genuine closing quotes and
  uncertain unmatched quotes retain their protection. Frozen fits are untouched.

## Reading copy

`scripts/materials/reformat.py` keeps source order and every non-whitespace
character in the source body. Explicit line boundaries create readable sections;
blank runs and tab indentation are normalized. Added titles are navigation, not
extracted facts. Original date spellings, quoted opinions and uncertain aliases
are unchanged. Evidence offsets must be regenerated from the exact text later
submitted; source line ranges and SHA-256 refer to the untouched original.

Do not submit the entire reading copy as one approved diary or assume the
formatter makes it training-ready. A canonical chat subset requires deliberate
speaker/reply verification first. No model, translator, database or actual tests
were run as part of this material review; the quote fix requires future synthetic
regression verification before being treated as validated.

Private originals and reading copies should stay local and out of Git history.

## Current material outcome (static only)

- The inspected original is valid UTF-8: 82,100 bytes, 31,302 Unicode characters,
  no BOM or NUL, and below the current text/file bounds. This establishes file
  readability, not extraction accuracy or predictive value.
- User confirmed self-statement/diary material and the self label `Azusaring`.
  Other aliases remain unknown. No state or consent was inferred.
- A seven-section Markdown reading copy was saved beside the original with mode
  0600; the original checksum remained unchanged. It is not a training package.
- Numeric-date apostrophe handling was changed by source inspection only. No
  runtime extraction/regression test was performed; validate with synthetic cases
  separately before claiming improved extraction or using the fix operationally.
