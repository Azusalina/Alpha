"""Small local CLI to exercise the store before Tauri integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .store import MemoryStore
from .access import AccessError, authorize_database


DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "brain.sqlite3"


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpha local brain prototype")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("init")
    add = actions.add_parser("add-source")
    add.add_argument("text")
    add.add_argument("--origin", default="input")
    actions.add_parser("list-sources")
    propose = actions.add_parser("propose")
    propose.add_argument("source_id")
    propose.add_argument("claim")
    propose.add_argument("evidence")
    actions.add_parser("list-candidates")
    accept = actions.add_parser("accept")
    accept.add_argument("candidate_id")
    reject = actions.add_parser("reject")
    reject.add_argument("candidate_id")
    actions.add_parser("list-memories")
    search = actions.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    try:
        session = authorize_database(args.db)
        session.require()
        store = MemoryStore(args.db)
        session.require()
        store.initialize()
        session.require()
        if args.action == "init":
            result = {"database": str(args.db)}
        elif args.action == "add-source":
            result = {"id": store.add_source(args.text, origin=args.origin)}
        elif args.action == "list-sources":
            result = store.list_sources()
        elif args.action == "propose":
            result = {"id": store.propose(args.source_id, args.claim, args.evidence)}
        elif args.action == "list-candidates":
            result = store.list_candidates()
        elif args.action == "accept":
            result = store.resolve(args.candidate_id, accept=True)
        elif args.action == "reject":
            result = store.resolve(args.candidate_id, accept=False)
        elif args.action == "search":
            result = store.search_memories(args.query, limit=args.limit)
        else:
            result = store.list_memories()
    except AccessError:
        parser.exit(1, "access is locked\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
