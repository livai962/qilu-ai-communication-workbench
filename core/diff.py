"""版本比对与人机协作留痕。

- 基于 diff-match-patch 对“AI 初稿”与“人工修订版”做字符级 Diff；
- 生成结构化操作序列（保留 / 新增 / 删除）与增删统计；
- 每一次人工修改都生成带时间戳、动作类型、修改前后内容的留痕记录，
  直接支撑“人机协作过程完整留痕”评分项。
"""

from __future__ import annotations

from datetime import datetime

from diff_match_patch import diff_match_patch

_dmp = diff_match_patch()

OP_LABEL = {0: "equal", 1: "insert", -1: "delete"}


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def diff_ops(original: str, revised: str) -> list[dict]:
    """返回字符级操作序列。"""
    original = original or ""
    revised = revised or ""
    ops = _dmp.diff_main(original, revised)
    _dmp.diff_cleanupSemantic(ops)
    return [{"op": OP_LABEL[op], "text": text} for op, text in ops if text]


def diff_summary(original: str, revised: str) -> dict:
    ops = diff_ops(original, revised)
    added = sum(len(o["text"]) for o in ops if o["op"] == "insert")
    removed = sum(len(o["text"]) for o in ops if o["op"] == "delete")
    changed = added > 0 or removed > 0
    return {
        "changed": changed,
        "added_chars": added,
        "removed_chars": removed,
        "ops": ops,
    }


def make_revision_record(field: str, before: str, after: str, action: str, author: str = "人工") -> dict:
    """生成一条人工修改留痕记录。"""
    summary = diff_summary(before, after)
    return {
        "timestamp": now_ts(),
        "author": author,
        "field": field,
        "action": action,
        "before": before,
        "after": after,
        "added_chars": summary["added_chars"],
        "removed_chars": summary["removed_chars"],
    }
