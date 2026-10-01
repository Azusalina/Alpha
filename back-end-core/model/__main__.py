"""Local command-line contract for the active self-model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from translator.pipeline import MAX_CHARS

from .engine import BrainModel
from .reset import verify_existing

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "brain.sqlite3"


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpha local self-model v1")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("baseline")
    actions.add_parser("reset-info", help="inspect model epoch and input revision before reset")
    reset = actions.add_parser("reset", help="zero all model partitions, preserving translator and sources")
    reset.add_argument("--confirm", required=True, choices=("RESET_MODEL",))
    reset.add_argument("--expected-epoch", required=True, type=int)
    reset.add_argument("--expected-revision", required=True, type=int)
    submit = actions.add_parser("submit")
    submit.add_argument("--partition", required=True, choices=("rational", "emotional", "crazy"))
    submit.add_argument("--kind", choices=("diary", "chat", "philosophy"), default="diary")
    submit.add_argument("--self-speaker")
    submit.add_argument("--immediate", action=argparse.BooleanOptionalAction, default=True)
    submit.add_argument("--exclamation", action="store_true",
                        help="explicitly set both judgements true and fit during submit")
    source = submit.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--file", type=Path)
    preview = actions.add_parser("preview")
    preview.add_argument("source_id")
    review = actions.add_parser("review")
    review.add_argument("source_id")
    history = actions.add_parser("review-history")
    history.add_argument("source_id")
    choice = review.add_mutually_exclusive_group(required=True)
    choice.add_argument("--agree", action="store_true")
    choice.add_argument("--disagree", action="store_true")
    revoke = actions.add_parser("revoke")
    revoke.add_argument("source_id")
    state = actions.add_parser("state")
    state.add_argument("--partition", choices=("rational", "emotional", "crazy"))
    effects = actions.add_parser("effects")
    effects.add_argument("--source-id")
    terms = actions.add_parser("terms")
    terms.add_argument("--partition", required=True, choices=("rational", "emotional", "crazy"))
    terms.add_argument("--min-documents", type=int, default=2)
    rank = actions.add_parser("rank")
    rank.add_argument("--options-json", required=True,
                      help='JSON array: [{"id":"A","impacts":{"value.autonomy":0.5}}, ...]')
    args = parser.parse_args()

    try:
        if args.action == "baseline":
            result = BrainModel.baseline()
        else:
            if args.action in {"reset", "reset-info"}:
                verify_existing(args.db)
            model = BrainModel(args.db)
            if args.action == "reset-info":
                result = model.reset_info()
            elif args.action == "reset":
                result = model.reset_model(confirmation=args.confirm, expected_epoch=args.expected_epoch,
                                           expected_revision=args.expected_revision)
            elif args.action == "submit":
                if args.file:
                    if args.file.suffix.lower() not in {".txt", ".md"}:
                        raise ValueError("v1 supports only .txt and .md files")
                    if args.file.stat().st_size > MAX_CHARS * 4:
                        raise ValueError("file exceeds v1 size limit")
                    text = args.file.read_text(encoding="utf-8")
                    source_ref = str(args.file)
                else:
                    text, source_ref = args.text, None
                result = model.submit_result(text, partition=args.partition, kind=args.kind,
                                             self_speaker=args.self_speaker, source_ref=source_ref,
                                             immediate=args.immediate, exclamation=args.exclamation)
            elif args.action == "preview":
                result = model.preview(args.source_id)
            elif args.action == "review":
                result = model.review(args.source_id, agree=args.agree)
            elif args.action == "review-history":
                result = model.review_history(args.source_id)
            elif args.action == "revoke":
                result = model.revoke(args.source_id)
            elif args.action == "state":
                result = model.state(args.partition)
            elif args.action == "effects":
                result = model.effects(source_id=args.source_id)
            elif args.action == "terms":
                result = model.learned_terms(partition=args.partition,
                                             min_documents=args.min_documents)
            else:
                result = model.rank_options(json.loads(args.options_json))
    except (OSError, UnicodeError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as error:
        parser.error(str(error))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
