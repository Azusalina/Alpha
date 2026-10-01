"""Pure value-alignment ranking shared by live model and offline evaluation."""

from __future__ import annotations

import math

from .catalog import PARAMETERS

VALUE_PARAMETERS = tuple(key for key in PARAMETERS if key.startswith("value."))


def validate_options(options: list[dict]) -> None:
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError("provide at least two options")
    ids = []
    for option in options:
        if not isinstance(option, dict) or not isinstance(option.get("id"), str) or not option["id"]:
            raise ValueError("each option needs a nonempty id")
        impacts = option.get("impacts")
        if not isinstance(impacts, dict):
            raise ValueError("each option needs impacts")
        for parameter, value in impacts.items():
            if parameter not in VALUE_PARAMETERS:
                raise ValueError(f"unknown or non-value parameter: {parameter}")
            if type(value) not in (int, float) or not math.isfinite(value) or not -1 <= value <= 1:
                raise ValueError("impacts must be finite numbers from -1 to 1")
        ids.append(option["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("option ids must be distinct")


def rank_from_state(options: list[dict], rational: dict, *, excluded: tuple[str, ...] = ()) -> dict:
    validate_options(options)
    if any(key not in VALUE_PARAMETERS for key in excluded):
        raise ValueError("only value parameters can be excluded")
    usable = {key: item["value"] for key, item in rational.items()
              if key in VALUE_PARAMETERS and key not in excluded and item["support"] >= 2}
    if not usable or not any(any(key in usable and impact != 0
                                 for key, impact in option["impacts"].items())
                             for option in options):
        return {"status": "abstain", "reason": "insufficient_confirmed_value_evidence", "ranked": []}
    ranked = sorted(
        ({"id": option["id"], "alignment_score": sum(usable.get(key, 0) * value
                                                     for key, value in option["impacts"].items())}
         for option in options),
        key=lambda item: (-item["alignment_score"], item["id"]),
    )
    if all(item["alignment_score"] == ranked[0]["alignment_score"] for item in ranked):
        return {"status": "abstain", "reason": "options_indistinguishable_with_current_evidence", "ranked": []}
    return {"status": "provisional", "basis": "confirmed_value_alignment_only",
            "not_a_probability": True, "used_parameters": sorted(usable), "ranked": ranked}
