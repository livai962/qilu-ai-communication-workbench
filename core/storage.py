"""会话与协作轨迹持久化。

必须持久化的三类核心数据（对标开发指南存储层要求）：
1. 用户原始输入；
2. AI 生成全版本历史；
3. 人工修改全轨迹（时间戳 + 动作 + 修改前后内容）。

本地以 JSON 文件落盘，便于评审回溯与技术文档取证；目录已在 .gitignore 排除运行期数据。
"""

from __future__ import annotations

import json
from datetime import datetime

from . import config


def _path(trace_id: str):
    return config.SESSION_DIR / f"{trace_id}.json"


def save_session(record: dict) -> None:
    record["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _path(record["trace_id"]).open("w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def load_session(trace_id: str) -> dict | None:
    path = _path(trace_id)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def list_sessions() -> list[dict]:
    items: list[dict] = []
    for path in sorted(config.SESSION_DIR.glob("*.json"), reverse=True):
        if path.name.startswith("_"):
            continue
        try:
            with path.open(encoding="utf-8") as f:
                rec = json.load(f)
            if not isinstance(rec, dict):
                continue
            items.append(
                {
                    "trace_id": rec.get("trace_id"),
                    "project": (rec.get("inputs") or {}).get("project_name", "—"),
                    "created_at": rec.get("created_at"),
                    "updated_at": rec.get("updated_at"),
                    "risk": (rec.get("compliance") or {}).get("risk_level", "—"),
                    "revisions": len(rec.get("revisions", [])),
                }
            )
        except (json.JSONDecodeError, OSError, AttributeError):
            continue
    return items


def build_record(inputs: dict, ai_content: dict, meta: dict) -> dict:
    return {
        "trace_id": meta["trace_id"],
        "created_at": meta["created_at"],
        "inputs": inputs,
        "prompt_version": meta["prompt_version"],
        "engine": meta["engine"],
        "engine_note": meta.get("engine_note", ""),
        "ai_content": ai_content,
        "final_content": dict(ai_content),
        "revisions": [],
        "polish_logs": [],
        "compliance": None,
        "audience": None,
    }
