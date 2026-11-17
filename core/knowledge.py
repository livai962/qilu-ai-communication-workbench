"""垂直领域知识库加载与检索。

内置：齐鲁文化元素库、主流平台爆款内容结构、受众画像、合规词库、标准案例。
知识库以 JSON 外置，便于后台扩充与迭代，不在代码中硬编码业务文案。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import config


def _load(name: str) -> dict:
    path = config.DATA_DIR / name
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def culture() -> dict:
    return _load("culture_elements.json")


@lru_cache(maxsize=1)
def sensitive() -> dict:
    return _load("sensitive_words.json")


@lru_cache(maxsize=1)
def examples() -> dict:
    return _load("examples.json")


# ---------- 场景与平台枚举（供表单与校验共用） ----------
SCENARIOS = ["齐鲁非遗 / 老字号焕新", "县域文旅打卡", "助农农产品"]
PLATFORMS = ["小红书", "抖音", "公众号"]
LENGTH_OPTIONS = ["简短", "中等", "较长"]


def platform_structure(platform: str) -> dict:
    return culture()["platform_structure"].get(
        platform, culture()["platform_structure"]["小红书"]
    )


def audience_profile(audience: str) -> dict:
    profiles = culture()["audience_profiles"]
    return profiles.get(audience, {"interests": [], "pain": ""})


def culture_hints(scenario: str) -> list[str]:
    """按场景返回可调用的本土文化元素提示，注入生成工作流。"""
    c = culture()
    if "非遗" in scenario:
        return c["intangible_heritage"] + c["old_brands"]
    if "文旅" in scenario:
        return c["culture_themes"] + c["landmarks"]
    if "农" in scenario:
        return c["culture_themes"] + c["local_cuisine"]
    return c["culture_themes"]


def example_list() -> list[dict]:
    return examples()["examples"]


def example_by_id(example_id: str) -> dict | None:
    for item in example_list():
        if item["id"] == example_id:
            return item
    return None
