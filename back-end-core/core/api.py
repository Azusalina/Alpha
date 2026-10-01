"""Versioned JSON-lines process boundary for a local desktop host."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import sys
from pathlib import Path
from typing import TextIO

from translator.pipeline import MAX_CHARS
from model.engine import BrainModel
from model.reset import verify_existing

from .access import AccessError, AccessSession
from .brain import BrainCore
from .pagination import StaleCursor

SCHEMA_VERSION = 1
CONTRACT_REVISION = 2
MAX_REQUEST_CHARS = MAX_CHARS * 6 + 4096
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "brain.sqlite3"

# Explicit allowlist: method -> required fields, optional fields.
METHODS = {
    "health": ((), ()), "baseline": ((), ()),
    "access_status": ((), ()), "unlock": (("password",), ()), "lock": ((), ()),
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
    "correction_reopen": (("source_id", "corrections", "immediate", "expected_source_version", "expected_revision", "expected_epoch"), ()),
    "review_version": (("source_id", "agree", "expected_source_version", "expected_revision", "expected_epoch"), ()),
    "replay_preview": (("source_ids",), ()),
    "replay_reopen": (("source_ids", "immediate", "expected_source_versions", "expected_revision", "expected_epoch"), ()),
    "revoke": (("source_id",), ()), "state": ((), ("partition",)),
    "effects": ((), ("source_id",)),
    "terms": (("partition",), ("min_documents",)), "rank": (("options",), ()),
    "candidate_propose": (("source_id", "claim", "evidence"), ()),
    "candidate_review": (("candidate_id", "accept"), ()),
    "candidate_list": ((), ("partition", "status", "limit")),
    "memory_list": ((), ("partition", "limit")),
    "memory_search": (("query",), ("partition", "limit")),
}
PUBLIC_METHODS = frozenset({"health", "baseline", "access_status", "unlock", "lock"})
TEXT_FIELDS = {"text", "partition", "kind", "self_speaker", "source_ref", "source_id",
               "candidate_id", "claim", "evidence", "query", "status", "cursor"}


def _validate_revision(field: str, value: object) -> None:
    if type(value) is not int or value < 0:
        raise RequestError("INVALID_ARGUMENT", f"{field} must be a nonnegative integer")


def _validate_source_ids(value: object) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 16:
        raise RequestError("INVALID_ARGUMENT", "source_ids must contain 1 to 16 source IDs")
    for source_id in value:
        if not isinstance(source_id, str) or not source_id.strip() or "\0" in source_id:
            raise RequestError("INVALID_ARGUMENT", "source_ids must contain valid source IDs")
        try:
            source_id.encode("utf-8")
        except UnicodeEncodeError:
            raise RequestError("INVALID_ARGUMENT", "source_ids must not contain surrogate code points") from None
    if len(set(value)) != len(value):
        raise RequestError("INVALID_ARGUMENT", "source_ids must be unique")


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
    def __init__(self, path: str | Path, *, trace: bool = False):
        self.path = Path(path)
        self.trace = trace
        self.access = AccessSession(path)
        self._brain = None
        # A protected process must not construct/migrate/read the database.
        if not self._access_status()["locked"]:
            self.brain

    def _access_status(self) -> dict:
        try:
            status = self.access.status()
        except AccessError:
            status = {"configured": True, "locked": True}
        if status["locked"]:
            self._brain = None
        return status

    @property
    def brain(self) -> BrainCore:
        self.access.require()
        if self.access.status()["configured"]:
            try:
                info = self.path.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                    raise ValueError("invalid database")
                verify_existing(self.path.absolute())
            except (OSError, ValueError):
                self._brain = None
                raise RuntimeError("protected database unavailable") from None
        if self._brain is None:
            self._brain = BrainCore(self.path, trace=self.trace)
        return self._brain

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
            if not isinstance(method, str) or method not in PUBLIC_METHODS:
                self.access.require()
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
                if field in {"limit", "min_documents"} and type(value) is not int:
                    raise RequestError("INVALID_ARGUMENT", f"{field} must be an integer")
                if field in {"expected_revision", "expected_source_version", "expected_epoch"}:
                    _validate_revision(field, value)
                if field == "source_ids":
                    _validate_source_ids(value)
                if field == "expected_source_versions":
                    _validate_source_ids(params.get("source_ids"))
                    if not isinstance(value, dict) or set(value) != set(params["source_ids"]):
                        raise RequestError("INVALID_ARGUMENT", "expected_source_versions must match source_ids")
                    for version in value.values():
                        _validate_revision("expected_source_versions", version)
                if field == "options" and not isinstance(value, list):
                    raise RequestError("INVALID_ARGUMENT", "options must be an array")
                if field == "corrections" and not isinstance(value, list):
                    raise RequestError("INVALID_ARGUMENT", "corrections must be an array")
                if field == "corrections" and len(value) > 64:
                    raise RequestError("INVALID_ARGUMENT", "corrections must contain at most 64 items")
                if field == "password":
                    if not isinstance(value, str) or "\0" in value:
                        raise RequestError("INVALID_ARGUMENT", "invalid password")
                    try:
                        valid_password = 1 <= len(value.encode("utf-8")) <= 1024
                    except UnicodeEncodeError:
                        valid_password = False
                    if not valid_password:
                        raise RequestError("INVALID_ARGUMENT", "invalid password")
            if method == "health":
                access = self._access_status()
                result = {"schema_version": SCHEMA_VERSION, "contract_revision": CONTRACT_REVISION,
                          "candidate_publication": "automatic_double_approval", "access": access,
                          "llm_runtime_configured": False, "methods": sorted(METHODS),
                          "features": {"two_judgements": True, "exclamation_sets_both_true": True,
                                       "repeat_review": True, "preview_untrained": True,
                                       "input_summary": True, "input_pagination": True,
                                       "source_edit": True, "source_delete": True,
                                       "access_control": True, "source_versions": True,
                                       "correction_reopen": True, "explicit_replay": True,
                                       "typed_corrections": True}}
                if not access["configured"]:
                    result["model_epoch"] = self.brain.model.reset_info()["model_epoch"]
            elif method == "baseline":
                result = BrainModel.baseline()
            elif method == "access_status":
                result = self._access_status()
            elif method == "unlock":
                result = self.access.unlock(params["password"])
            elif method == "lock":
                result = self.access.lock()
                self._brain = None
            else:
                result = getattr(self.brain, method)(**params)
            return {"schema_version": SCHEMA_VERSION, "id": request_id, "ok": True,
                    "result": result}
        except RequestError as error:
            return error_response(request_id, error.code, str(error))
        except AccessError:
            self._brain = None
            return error_response(request_id, "LOCKED", "access is locked")
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
    parser.add_argument('--quiet', action='store_true', help='disable model terminal tracing')
    args = parser.parse_args()
    try:
        api = BrainAPI(args.db, trace=not args.quiet and os.environ.get('ALPHA_BRAIN_TRACE') != '0')
    except (AccessError, OSError, sqlite3.Error, RuntimeError) as error:
        parser.exit(1, f"backend initialization failed: {type(error).__name__}\n")
    serve(api, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
