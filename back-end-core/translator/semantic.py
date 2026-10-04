"""Standalone, local semantic retrieval; no persistence or approval decisions.

Only caller-approved, trusted local builtin exports should be supplied. Layout
validation is not an OS sandbox or a provenance/weight audit. Files must remain
unchanged during validation and loading. Offline flags remain process-wide once
loading starts. Callers own row eligibility and access control; similarity does
not endorse a claim or publish its evidence.
Importing this module requires only the standard library.
"""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import TextIOBase
import json
import logging
import math
from numbers import Real
import os
from pathlib import Path
import sys
from threading import RLock
from typing import Protocol
import warnings

__all__ = ["Encoder", "LocalSentenceEncoder", "rank_memories"]

_BATCH_SIZE = 32
_TEXT_LIMIT = 2048
_CLAIM_LIMIT = 512
_EVIDENCE_LIMIT = 1535
_UNAVAILABLE = "local semantic encoder unavailable"
_UNSAFE_SUFFIXES = {".bin", ".pt", ".pth", ".pkl", ".pickle"}
_MODULE_TYPES = {
    f"{prefix}.{name}": name
    for prefix in ("sentence_transformers.models", "sentence_transformers.sentence_transformer.modules")
    for name in ("Transformer", "Pooling", "Normalize")
}
_TRANSFORMER_CONFIGS = {
    f"sentence_{name}_config.json"
    for name in ("bert", "roberta", "distilbert", "camembert", "albert", "xlm-roberta", "xlnet")
}
_LOADER_KWARGS = {
    "model_args", "model_kwargs", "tokenizer_args", "processor_kwargs", "config_args", "config_kwargs",
}
_FORBIDDEN_CONFIG_KEYS = {
    "auto_map", "custom_pipelines", "base_model_name_or_path", "model_name_or_path",
    "tokenizer_name_or_path", "trust_remote_code", "local_files_only", "use_safetensors",
    "token", "use_auth_token", "code_revision", "cache_dir", "cache_folder", "subfolder",
    "pretrained_model_name_or_path", "hf_hub_id", "repo_id",
    "name_or_path", "processor_class", "feature_extractor_type", "image_processor_type",
    "device_map", "backend", "peft_type", "adapter_name", "load_in_4bit", "load_in_8bit",
    "quantization_config", "init_defaults", "module_classes", "config_filename",
}
_BACKBONE_TYPES = {"bert", "roberta", "distilbert", "albert", "camembert", "xlm-roberta", "mpnet", "electra"}
_TOKENIZER_CLASSES = {
    "bert": "Bert", "roberta": "Roberta", "distilbert": "DistilBert",
    "albert": "Albert", "camembert": "Camembert", "xlm-roberta": "XLMRoberta",
    "mpnet": "MPNet", "electra": "Electra",
}
_POOLING_MODES = {"cls", "max", "mean", "mean_sqrt_len_tokens", "weightedmean", "lasttoken"}
_LEGACY_POOLING_KEYS = {
    "pooling_mode_cls_token", "pooling_mode_max_tokens", "pooling_mode_mean_tokens",
    "pooling_mode_mean_sqrt_len_tokens", "pooling_mode_weightedmean_tokens", "pooling_mode_lasttoken",
}
_DEPENDENCY_LOCK = RLock()


class _Discard(TextIOBase):
    def write(self, text):
        return len(text)


@contextmanager
def _quiet_dependency():
    """Discard Python output, warnings, and logs without retaining any content.

    Calls through this module serialize global logging/warning/stream changes. This
    is not an OS sandbox: native fd writes or child processes are not intercepted.
    Unrelated application threads must not rely on these globals during a call.
    """
    with _DEPENDENCY_LOCK:
        previous_disable = logging.root.manager.disable
        with _Discard() as sink, redirect_stdout(sink), redirect_stderr(sink), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            logging.disable(sys.maxsize)
            try:
                yield
            finally:
                logging.disable(previous_disable)


def _set_offline():
    # Hub reads these at import time. Refuse an already-imported online Hub;
    # changing its cached constant or reloading it is not a supported contract.
    # https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    constants = sys.modules.get("huggingface_hub.constants")
    if constants is not None and getattr(constants, "HF_HUB_OFFLINE", None) is not True:
        raise ValueError("Hub was not imported offline")


def _check_config(value):
    if isinstance(value, dict):
        if _FORBIDDEN_CONFIG_KEYS.intersection(value):
            raise ValueError("unsupported model config")
        for key, child in value.items():
            # Saved overrides are outside the supported layout, even when they
            # appear in nested configs. Top-level local-only flags cannot prove
            # arbitrary alternate loader paths safe.
            if key in _LOADER_KWARGS and child != {}:
                raise ValueError("unsupported loader overrides")
            if key.endswith(("_file", "_path")) and key != "_name_or_path" and child is not None:
                raise ValueError("unsupported external file reference")
            _check_config(child)
    elif isinstance(value, list):
        for child in value:
            _check_config(child)


def _relative_path(value: object) -> Path:
    if (not isinstance(value, str) or "\x00" in value or "\\" in value or ":" in value
            or Path(value).is_absolute() or ".." in Path(value).parts):
        raise ValueError("nonlocal artifact path")
    return Path(value)


def _no_symlink_parents(path: Path):
    if any(entry.is_symlink() for entry in (path, *path.parents)):
        raise ValueError("symlink model path")


def _validate_vocabulary(vocab: object, *, unigram: bool = False):
    if unigram:
        if (not isinstance(vocab, list) or not vocab
                or any(not isinstance(item, list) or len(item) != 2
                       or not isinstance(item[0], str) or not item[0]
                       or isinstance(item[1], bool) or not isinstance(item[1], Real)
                       or not math.isfinite(float(item[1])) for item in vocab)):
            raise ValueError("invalid tokenizer vocabulary")
    elif (not isinstance(vocab, dict) or not vocab
          or any(not isinstance(token, str) or not token or type(index) is not int or index < 0
                 for token, index in vocab.items())
          or len(set(vocab.values())) != len(vocab)):
        raise ValueError("invalid tokenizer vocabulary")


def _validate_tokenizer(directory: Path, backbone: dict, configs: dict, files: set):
    tokenizer_config = configs.get(directory / "tokenizer_config.json")
    if directory / "tokenizer_config.json" in files and not isinstance(tokenizer_config, dict):
        raise ValueError("unsupported tokenizer config")
    prefix = _TOKENIZER_CLASSES[backbone["model_type"]]
    for config in (backbone, tokenizer_config or {}):
        if "tokenizer_class" in config and config["tokenizer_class"] not in {
                prefix + "Tokenizer", prefix + "TokenizerFast"}:
            raise ValueError("unsupported tokenizer class")
    if directory / "tokenizer.json" in files:
        tokenizer = configs[directory / "tokenizer.json"]
        model = tokenizer.get("model") if isinstance(tokenizer, dict) else None
        if (not isinstance(tokenizer, dict) or set(tokenizer) - {
                "version", "truncation", "padding", "added_tokens", "normalizer", "pre_tokenizer",
                "post_processor", "decoder", "model"}
                or not isinstance(model, dict) or model.get("type") not in {"WordPiece", "BPE", "Unigram"}):
            raise ValueError("unsupported tokenizer")
        _validate_vocabulary(model.get("vocab"), unigram=model["type"] == "Unigram")
        if model["type"] == "BPE" and not isinstance(model.get("merges"), list):
            raise ValueError("missing tokenizer merges")
        return
    # Legacy exports need both local vocabulary and an explicit builtin config.
    if not isinstance(tokenizer_config, dict) or not tokenizer_config:
        raise ValueError("missing local tokenizer config")
    model_type = backbone["model_type"]
    if model_type in {"bert", "distilbert", "electra", "mpnet"}:
        required = ("vocab.txt",)
    elif model_type == "roberta":
        required = ("vocab.json", "merges.txt")
        _validate_vocabulary(configs.get(directory / "vocab.json"))
    else:
        required = ("sentencepiece.bpe.model" if model_type in {"camembert", "xlm-roberta"}
                    else "spiece.model",)
    if any(directory / name not in files or (directory / name).stat().st_size == 0 for name in required):
        raise ValueError("missing local tokenizer vocabulary")
    if "vocab.txt" in required:
        vocab = (directory / "vocab.txt").read_text(encoding="utf-8").splitlines()
        if not vocab or not any(token.strip() for token in vocab) or len(set(vocab)) != len(vocab):
            raise ValueError("invalid tokenizer vocabulary")


def _validate_pooling(config: object, backbone: dict):
    if (not isinstance(config, dict) or set(config) - (
            {"embedding_dimension", "word_embedding_dimension", "pooling_mode", "include_prompt"}
            | _LEGACY_POOLING_KEYS)):
        raise ValueError("unsupported pooling config")
    dimension = config.get("embedding_dimension", config.get("word_embedding_dimension"))
    if type(dimension) is not int or dimension <= 0:
        raise ValueError("invalid pooling dimension")
    if "embedding_dimension" in config and "word_embedding_dimension" in config:
        if config["word_embedding_dimension"] != dimension:
            raise ValueError("conflicting pooling dimensions")
    if "hidden_size" in backbone and backbone["hidden_size"] != dimension:
        raise ValueError("inconsistent pooling dimension")
    for key in _LEGACY_POOLING_KEYS | {"include_prompt"}:
        if key in config and type(config[key]) is not bool:
            raise ValueError("invalid pooling flag")
    modes = config.get("pooling_mode", "mean")
    modes = [modes] if isinstance(modes, str) else modes
    if (not isinstance(modes, list) or not modes
            or any(not isinstance(mode, str) or mode not in _POOLING_MODES for mode in modes)):
        raise ValueError("invalid pooling mode")


def _validate_model_directory(path: Path):
    """Fail closed on unsupported layouts, without importing any model code.

    Supported: a self-contained Transformer -> Pooling -> optional Normalize
    export, using builtin public module types, JSON configs and safetensors.
    Backbone types are restricted to common builtin text encoders listed above.
    No symlinks, adapters, custom code, nested manifests or pickle artifacts.
    Trusted files must remain unchanged between this check and dependency load.
    Dependency/runtime acceptance is pending; this is not a provenance audit.
    """
    # Supported dependency: sentence-transformers==6.1.0 (pyproject.toml).
    # Official loader source, alongside the local ext-refs checkout:
    # https://github.com/huggingface/sentence-transformers/blob/v6.1.0/sentence_transformers/base/modules/transformer.py
    # https://github.com/huggingface/sentence-transformers/blob/v6.1.0/sentence_transformers/sentence_transformer/modules/pooling.py
    _no_symlink_parents(path)
    if not path.is_dir():
        raise ValueError("missing model directory")
    configs = {}
    files = set()
    for entry in path.rglob("*"):
        if entry.is_symlink() or entry.suffix.lower() in _UNSAFE_SUFFIXES:
            raise ValueError("unsafe model artifact")
        if entry.is_dir():
            continue
        if not entry.is_file() or not entry.resolve(strict=True).is_relative_to(path):
            raise ValueError("unsupported model artifact")
        files.add(entry)
        if (entry.suffix.lower() in {".py", ".pyc", ".pyo", ".pyw"}
                or entry.name.lower() in {"adapter_config.json", "peft_config.json"}
                or entry.name.lower().startswith("adapter_model.")):
            raise ValueError("unsupported model artifact")
        if entry.name == "modules.json" and entry.parent != path:
            raise ValueError("nested module manifest")
        if entry.suffix.lower() == ".json":
            config = json.loads(entry.read_text(encoding="utf-8"))
            # Tokenizer/vocabulary JSON contains vocabulary data, not loader
            # kwargs: ordinary tokens such as "token" must not be rejected.
            if entry.name not in {"tokenizer.json", "vocab.json"}:
                _check_config(config)
            configs[entry] = config
            if entry.name in _TRANSFORMER_CONFIGS:
                if (not isinstance(config, dict)
                        or set(config) - ({"max_seq_length", "do_lower_case", "transformer_task",
                                          "modality_config", "module_output_name", "processing_kwargs",
                                          "unpad_inputs", "query_length", "document_length", "query_expansion"}
                                         | _LOADER_KWARGS)
                        or config.get("transformer_task", "feature-extraction") != "feature-extraction"):
                    raise ValueError("unsupported transformer config")
                defaults = {"modality_config": {"text": {"method": "forward", "method_output_name": "last_hidden_state"}},
                            "module_output_name": "token_embeddings", "processing_kwargs": {},
                            "unpad_inputs": False, "query_length": None,
                            "document_length": None, "query_expansion": None}
                if any(key in config and config[key] != value for key, value in defaults.items()):
                    raise ValueError("unsupported transformer behavior")
                if ("max_seq_length" in config and (type(config["max_seq_length"]) is not int
                                                    or config["max_seq_length"] <= 0)
                        or "do_lower_case" in config and type(config["do_lower_case"]) is not bool):
                    raise ValueError("invalid transformer config")
    for config in configs.values():
        if isinstance(config, dict) and "weight_map" in config:
            weights = config["weight_map"]
            if not isinstance(weights, dict) or not weights:
                raise ValueError("unsupported weight index")
            for filename in weights.values():
                relative = _relative_path(filename)
                if len(relative.parts) != 1 or relative.suffix != ".safetensors":
                    raise ValueError("unsafe weight index")
    modules = configs.get(path / "modules.json")
    if not isinstance(modules, list) or len(modules) not in (2, 3):
        raise ValueError("unsupported module manifest")
    names = set()
    directories = set()
    backbone = None
    for index, (module, expected) in enumerate(zip(modules, ("Transformer", "Pooling", "Normalize"))):
        if (not isinstance(module, dict)
                or set(module) - {"idx", "name", "path", "type", "kwargs"}
                or type(module.get("idx")) is not int or module["idx"] != index
                or _MODULE_TYPES.get(module.get("type")) != expected
                or module.get("kwargs", []) != []):
            raise ValueError("unsupported module manifest")
        name = _text(module.get("name"))
        if name in names:
            raise ValueError("duplicate module name")
        names.add(name)
        relative = _relative_path(module.get("path"))
        directory = (path / relative).resolve(strict=True)
        if (not directory.is_relative_to(path) or not directory.is_dir()
                or directory in directories):
            raise ValueError("nonlocal module path")
        directories.add(directory)
        if index == 0:
            backbone = configs.get(directory / "config.json")
            if not isinstance(backbone, dict) or backbone.get("model_type") not in _BACKBONE_TYPES:
                raise ValueError("unsupported backbone")
            if (directory / "model.safetensors" not in files
                    and directory / "model.safetensors.index.json" not in files):
                raise ValueError("missing local safetensors")
            weight_index = configs.get(directory / "model.safetensors.index.json")
            if directory / "model.safetensors.index.json" in files:
                if not isinstance(weight_index, dict) or "weight_map" not in weight_index:
                    raise ValueError("unsupported weight index")
                for filename in weight_index["weight_map"].values():
                    if directory / filename not in files:
                        raise ValueError("missing local weight shard")
            _validate_tokenizer(directory, backbone, configs, files)
        elif index == 1:
            _validate_pooling(configs.get(directory / "config.json"), backbone)
        else:
            # Older Normalize exports have no config; newer ones may save the
            # builtin sentence-embedding defaults. No alternate feature keys.
            config = configs.get(directory / "config.json", {})
            if (not isinstance(config, dict)
                    or set(config) - {"module_input_name", "module_output_name"}
                    or config.get("module_input_name", "sentence_embedding") != "sentence_embedding"
                    or config.get("module_output_name") not in (None, "sentence_embedding")):
                raise ValueError("unsupported normalize config")


class Encoder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]:
        """Return one finite, nonzero vector per text, in input order."""
        ...


def _text(value: object, *, max_length: int | None = None) -> str:
    # Python lengths/slices count Unicode code points, including astral characters.
    if (not isinstance(value, str) or not value.strip()
            or (max_length is not None and len(value) > max_length)
            or "\x00" in value
            or any("\ud800" <= char <= "\udfff" for char in value)):
        raise ValueError("invalid semantic text")
    return value


def _normalized_vectors(vectors: object, count: int,
                        dimension: int | None = None) -> list[list[float]]:
    """Validate strict list output and normalize without squaring huge values.

    This internal function runs inside the sanitized encoder boundary. Scale
    first, so both near-max floats and subnormal nonzero vectors remain usable.
    """
    if not isinstance(vectors, list) or len(vectors) != count:
        raise ValueError("invalid vectors")
    result = []
    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise ValueError("invalid vector")
        if dimension is None:
            dimension = len(vector)
        if len(vector) != dimension:
            raise ValueError("inconsistent vector dimensions")
        if any(isinstance(value, bool) or not isinstance(value, Real) for value in vector):
            raise ValueError("invalid vector component")
        values = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("nonfinite vector")
        scale = max(abs(value) for value in values)
        if scale == 0:
            raise ValueError("zero vector")
        scaled = [value / scale for value in values]
        norm = math.sqrt(math.fsum(value * value for value in scaled))
        result.append([value / norm for value in scaled])
    return result


def _encode_batch(encoder: Encoder, texts: list[str],
                  dimension: int | None = None) -> list[list[float]]:
    try:
        with _quiet_dependency():
            return _normalized_vectors(encoder.encode(texts), len(texts), dimension)
    except Exception:
        pass
    # Raise after leaving the handler: no private exception context or cause.
    raise RuntimeError(_UNAVAILABLE)


class LocalSentenceEncoder:
    """Lazy CPU encoder for an explicit existing directory of approved files.

    No Hub identifiers or download fallback. Empty input does not import/load
    dependencies. Larger inputs are split into model calls of at most 32 texts.
    The loaded model is reused in memory; embeddings are never cached or saved.
    Dependency versions lacking the required safety options fail closed.
    Layout checks happen on first encode, before import/load, not in __init__.
    Only the restricted builtin layout described above is supported; Dense,
    Router, PEFT, custom modules and symlink-based Hub snapshots are excluded.
    A Hub already imported online is refused; use a fresh offline process.
    """

    def __init__(self, model_path: str | Path):
        path = None
        if isinstance(model_path, (str, Path)) and str(model_path):
            try:
                supplied = Path(model_path).absolute()
                _no_symlink_parents(supplied)
                candidate = supplied.resolve(strict=True)
                if candidate.is_dir():
                    path = candidate
            except (OSError, RuntimeError, ValueError):
                pass
        if path is None:
            raise ValueError("model_path must be an existing local directory")
        self._path = path
        self._model = None
        self._dimension: int | None = None

    def _load(self):
        with _DEPENDENCY_LOCK:
            return self._load_serialized()

    def _load_serialized(self):
        if self._model is not None:
            return self._model
        try:
            _validate_model_directory(self._path)
            with _quiet_dependency():
                _set_offline()
                from sentence_transformers import SentenceTransformer

                _set_offline()

                # Official constructor API (including token=False), verified at:
                # https://sbert.net/docs/package_reference/sentence_transformer/model.html
                # https://github.com/huggingface/sentence-transformers/blob/v6.1.0/sentence_transformers/sentence_transformer/model.py
                # use_safetensors applies to the backbone only; the preflight
                # restricts module types and rejects pickle files independently.
                model = SentenceTransformer(
                    str(self._path), device="cpu", local_files_only=True,
                    trust_remote_code=False, token=False,
                    model_kwargs={"use_safetensors": True},
                )
        except Exception:
            pass
        else:
            self._model = model
            return model
        raise RuntimeError(_UNAVAILABLE)

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not isinstance(texts, list):
            raise ValueError("texts must be a list")
        for text in texts:
            _text(text, max_length=_TEXT_LIMIT)
        if not texts:
            return []
        with _DEPENDENCY_LOCK:
            return self._encode_serialized(texts)

    def _encode_serialized(self, texts):
        model = self._load()
        vectors = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start:start + _BATCH_SIZE]
            try:
                # Same official API/source above, SentenceTransformer.encode:
                # convert_to_numpy and normalize_embeddings are documented.
                # An explicit empty prompt overrides saved/default prompts, so
                # only the bounded input text is embedded; progress is disabled.
                with _quiet_dependency():
                    _set_offline()
                    output = model.encode(
                        batch, batch_size=_BATCH_SIZE, device="cpu", prompt="",
                        normalize_embeddings=True, convert_to_numpy=True,
                        show_progress_bar=False,
                    )
                    normalized = _normalized_vectors(
                        output.tolist(), len(batch), self._dimension,
                    )
            except Exception:
                pass
            else:
                if self._dimension is None:
                    self._dimension = len(normalized[0])
                vectors.extend(normalized)
                continue
            raise RuntimeError(_UNAVAILABLE)
        return vectors


def rank_memories(query, rows: list[dict], encoder: Encoder, *,
                  limit: int = 20, min_score: float = 0.0) -> list[dict]:
    """Rank caller-eligible rows by cosine, then by ascending string ``id``.

    Rows require nonblank string ``id``, ``claim`` and ``evidence``. All text is
    validated before encoding, including clipped tails. The embedding text is
    claim[:512] + newline + evidence[:1535]; truncation is reported separately.
    Returned ``memory`` is the exact original row, with no modifications. Ties
    with identical IDs retain input order. Scores are similarity, not confidence.
    ``limit`` is a nonnegative integer; zero/empty rows perform no encoding.
    No row approval, ownership, or status filtering is performed here.
    """
    _text(query, max_length=_TEXT_LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    score_valid = False
    if not isinstance(min_score, bool) and isinstance(min_score, Real):
        try:
            threshold = float(min_score)
            score_valid = math.isfinite(threshold) and -1 <= threshold <= 1
        except (OverflowError, ValueError):
            pass
    if not score_valid:
        raise ValueError("min_score must be finite and between -1 and 1")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list of dictionaries")
    prepared = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("rows must be a list of dictionaries")
        _text(row.get("id"))
        claim = _text(row.get("claim"))
        evidence = _text(row.get("evidence"))
        prepared.append((row, claim[:_CLAIM_LIMIT] + "\n" + evidence[:_EVIDENCE_LIMIT],
                         len(claim) > _CLAIM_LIMIT or len(evidence) > _EVIDENCE_LIMIT))
    if not prepared or limit == 0:
        return []
    query_vector = _encode_batch(encoder, [query])[0]
    ranked = []
    for start in range(0, len(prepared), _BATCH_SIZE):
        batch = prepared[start:start + _BATCH_SIZE]
        vectors = _encode_batch(encoder, [text for _, text, _ in batch], len(query_vector))
        for (row, _, truncated), vector in zip(batch, vectors):
            cosine = math.fsum(left * right for left, right in zip(query_vector, vector))
            score = max(-1.0, min(1.0, cosine))
            if score >= threshold:
                ranked.append({"memory": row, "score": score,
                               "encoded_text_truncated": truncated})
    ranked.sort(key=lambda item: (-item["score"], item["memory"]["id"]))
    return ranked[:limit]
