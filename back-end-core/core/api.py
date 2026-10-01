"""Versioned JSON-lines process boundary for a local desktop host."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import TextIO

from translator.pipeline import MAX_CHARS

from .brain import BrainCore
from .pagination import StaleCursor

SCHEMA_VERSION = 1
MAX_REQUEST_CHARS = MAX_CHARS * 6 + 4096
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "brain.sqlite3"

# Explicit allowlist: method -> required fields, optional fields.
METHODS = {
    "health": ((), ()), "baseline": ((), ()),
    "submit": (("text", "partition"), ("kind", "self_speaker", "source_ref", "immediate", "exclamation")),
    "input_get": (("source_id",), ()),
    "input_edit": (("source_id", "text", "immediate"), ("kind", "self_speaker")),
    "input_delete": (("source_id",), ()),
    "input_list": ((), ("partition", "status", "limit")),
    "input_page": ((), ("partition", "status", "limit", "cursor")),
    "preview": (("source_id",), ()),
    "review": (("source_id", "agree"), ()),
    "review_history": (("source_id",), ()),
    "correction_set": (("source_id", "corrections", "expected_revision"), ()),
    "correction_history": (("source_id",), ()),
    "revoke": (("source_id",), ()), "state": ((), ("partition",)),
    "effects": ((), ("source_id",)),
    "terms": (("partition",), ("min_documents",)), "rank": (("options",), ()),
    "candidate_propose": (("source_id", "claim", "evidence"), ()),
    "candidate_review": (("candidate_id", "accept"), ()),
    "candidate_list": ((), ("partition", "status", "limit")),
    "memory_list": ((), ("partition", "limit")),
    "memory_search": (("query",), ("partition", "limit")),
}
TEXT_FIELDS = {"text", "partition", "kind", "self_speaker", "source_ref", "source_id",
               "candidate_id", "claim", "evidence", "query", "status", "cursor"}


class RequestError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(value: str):
    raise ValueError("non-finite JSON numbers are not supported")


def error_response(request_id: str | None, code: str, message: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "id": request_id, "ok": False,
            "error": {"code": code, "message": message}}


class BrainAPI:
    def __init__(self, path: str | Path):
        self.brain = BrainCore(path)
        self.handlers = {method: getattr(self.brain, method)
                         for method in METHODS if method not in ("health", "baseline")}

    def handle(self, request: object) -> dict:
        request_id = None
        try:
            if not isinstance(request, dict):
                raise RequestError("INVALID_REQUEST", "request must be an object")
            if isinstance(request.get("id"), str) and 1 <= len(request["id"]) <= 128:
                request_id = request["id"]
            if set(request) != {"schema_version", "id", "method", "params"}:
                raise RequestError("INVALID_REQUEST", "request needs schema_version, id, method, params")
            if type(request["schema_version"]) is not int or request["schema_version"] != SCHEMA_VERSION:
                raise RequestError("UNSUPPORTED_VERSION", "schema_version must be 1")
            if request_id is None:
                raise RequestError("INVALID_REQUEST", "id must be a string of 1 to 128 characters")
            method, params = request["method"], request["params"]
            if not isinstance(method, str) or method not in METHODS:
                raise RequestError("METHOD_NOT_FOUND", "unknown method")
            if not isinstance(params, dict):
                raise RequestError("INVALID_ARGUMENT", "params must be an object")
            required, optional = METHODS[method]
            if not set(required) <= set(params) or set(params) - set(required) - set(optional):
                raise RequestError("INVALID_ARGUMENT", "missing or unknown parameter fields")
            for field, value in params.items():
                if value is None and field in optional and field in {"partition", "status",
                                                                    "self_speaker", "source_ref", "source_id", "cursor"}:
                    continue
                if field in TEXT_FIELDS and (not isinstance(value, str) or not value.strip()):
                    raise RequestError("INVALID_ARGUMENT", f"{field} must contain text")
                if field in TEXT_FIELDS:
                    try:
                        value.encode("utf-8")
                    except UnicodeEncodeError:
                        raise RequestError("INVALID_ARGUMENT", f"{field} must not contain surrogate code points") from None
                if field in {"agree", "accept", "immediate", "exclamation"} and type(value) is not bool:
                    raise RequestError("INVALID_ARGUMENT", f"{field} must be a boolean")
                if field in {"limit", "min_documents", "expected_revision"} and type(value) is not int:
                    raise RequestError("INVALID_ARGUMENT", f"{field} must be an integer")
                if field == "options" and not isinstance(value, list):
                    raise RequestError("INVALID_ARGUMENT", "options must be an array")
                if field == "corrections" and not isinstance(value, list):
                    raise RequestError("INVALID_ARGUMENT", "corrections must be an array")
            if method == "health":
                result = {"schema_version": SCHEMA_VERSION, "candidate_publication": "manual",
                          "model_epoch": self.brain.model.reset_info()["model_epoch"],
                          "llm_runtime_configured": False, "methods": sorted(METHODS),
                          "features": {"two_judgements": True, "exclamation_sets_both_true": True,
                                       "repeat_review": True, "preview_untrained": True,
                                       "input_summary": True, "input_pagination": True,
                                       "source_edit": True, "source_delete": True}}
            elif method == "baseline":
                result = self.brain.model.baseline()
            else:
                result = self.handlers[method](**params)
            return {"schema_version": SCHEMA_VERSION, "id": request_id, "ok": True,
                    "result": result}
        except RequestError as error:
            return error_response(request_id, error.code, str(error))
        except KeyError:
            return error_response(request_id, "NOT_FOUND", "input or candidate not found")
        except StaleCursor as error:
            return error_response(request_id, "STALE_CURSOR", str(error))
        except ValueError as error:
            return error_response(request_id, "INVALID_ARGUMENT", str(error))
        except RuntimeError as error:
            return error_response(request_id, "MODEL_UNAVAILABLE", str(error))
        except (OSError, sqlite3.Error):
            return error_response(request_id, "STORAGE_ERROR", "local storage operation failed")
        except Exception:
            return error_response(request_id, "INTERNAL_ERROR", "backend operation failed")


def serve(api: BrainAPI, input_stream: TextIO, output_stream: TextIO) -> None:
    """One response per input line. EOF ends the process; stdout is JSON only."""
    while True:
        line = input_stream.readline(MAX_REQUEST_CHARS + 1)
        if not line:
            return
        if len(line) > MAX_REQUEST_CHARS:
            while line and not line.endswith("\n"):
                line = input_stream.readline(MAX_REQUEST_CHARS + 1)
            response = error_response(None, "INVALID_REQUEST", "request exceeds size limit")
        else:
            try:
                request = json.loads(line, object_pairs_hook=_unique_object,
                                     parse_constant=_invalid_constant)
            except (ValueError, RecursionError):
                response = error_response(None, "INVALID_REQUEST", "invalid JSON request")
            else:
                response = api.handle(request)
        output_stream.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + "\n")
        output_stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpha local JSON-lines backend")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    try:
        api = BrainAPI(args.db)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        parser.exit(1, f"backend initialization failed: {type(error).__name__}\n")
    serve(api, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
