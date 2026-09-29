"""Run a local translator preview without storing personal text."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import MAX_CHARS, summarize, translate


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpha local rule-based translator preview")
    parser.add_argument("--kind", choices=("diary", "chat"), default="diary")
    parser.add_argument("--self-speaker", help="required for chat; exact speaker label")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="one text input")
    source.add_argument("--file", action="append", type=Path, help="UTF-8 .txt/.md; repeat for separate inputs")
    args = parser.parse_args()
    if args.kind == "chat" and not args.self_speaker:
        parser.error("--self-speaker is required for chat")
    try:
        if args.file:
            reports = []
            for path in args.file:
                if path.suffix.lower() not in {".txt", ".md"}:
                    raise ValueError("v1 supports only .txt and .md files")
                if path.stat().st_size > MAX_CHARS * 4:
                    raise ValueError(f"file exceeds v1 size limit: {path}")
                reports.append(translate(path.read_text(encoding="utf-8"), kind=args.kind,
                                         self_speaker=args.self_speaker))
            result = {"reports": reports, "summary": summarize(reports)}
        else:
            result = translate(args.text, kind=args.kind, self_speaker=args.self_speaker)
    except (OSError, UnicodeError, ValueError) as error:
        parser.error(str(error))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
