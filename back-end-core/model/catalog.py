"""Small, explicit v1 parameter vocabulary. Not a clinical scale."""

from __future__ import annotations

import json
from pathlib import Path

BASELINE_PATH = Path(__file__).with_name("baseline.json")
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
PARTITIONS = tuple(BASELINE["partitions"])
PARAMETERS = tuple(BASELINE["parameters"])
PRIOR_STRENGTH = 4  # shrink one mention; not a learned personal parameter

# Values are only updated by an explicit, endorsed statement of importance.
VALUE_WORDS = {
    "value.autonomy": ("自由", "自主", "自我决定", "自我決定"),
    "value.fairness": ("公平", "公正"),
    "value.care": ("关怀", "關懷", "照顾", "照顧", "善待"),
    "value.truth": ("真实", "真實", "诚实", "誠實", "真相"),
    "value.security": ("安全", "稳定", "穩定"),
    "value.growth": ("成长", "成長", "学习", "學習", "进步", "進步"),
    "value.achievement": ("成就", "成果", "成功"),
    "value.connection": ("陪伴", "归属", "歸屬", "联结", "連結"),
}


def zero_state() -> dict[str, dict[str, dict]]:
    return {
        partition: {
            parameter: {"value": 0.0, "support": 0, "observed": False}
            for parameter in PARAMETERS
        }
        for partition in PARTITIONS
    }
