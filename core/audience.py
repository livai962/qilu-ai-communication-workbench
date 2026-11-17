"""受众语义与痛点击中率分析（本地可计算，无需在线模型）。

创新差异化能力（对标备赛方案 2.1）：
- 评估内容对目标受众痛点 / 兴趣点的命中程度；
- 评估卖点覆盖完整度；
- 给出情绪倾向与可执行的改进建议，辅助人工二次校准。
"""

from __future__ import annotations

import re

from . import knowledge

_POSITIVE = ["喜欢", "值得", "推荐", "舒服", "好看", "出片", "实惠", "贴心", "地道", "丰富", "省心", "惊喜", "温暖", "地道", "优质"]
_NEGATIVE = ["踩雷", "失望", "拥挤", "踩坑", "难吃", "偏远", "简陋", "昂贵", "排队久", "敷衍"]

_SPLIT_RE = re.compile(r"[，。；、,;/\s]+")


def _content_text(content: dict) -> str:
    parts = [content.get("headline", ""), content.get("body", "")]
    parts += list((content.get("platform_copy") or {}).values())
    for shot in content.get("storyboard", []) or []:
        parts += [shot.get("voiceover", ""), shot.get("subtitle", ""), shot.get("visual", "")]
    return "\n".join(p for p in parts if p)


def _keywords(text: str) -> list[str]:
    chunks = [c.strip() for c in _SPLIT_RE.split(text or "") if len(c.strip()) >= 2]
    # 去重保序
    seen, out = set(), []
    for c in chunks:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def analyze(content: dict, inputs: dict) -> dict:
    text = _content_text(content)
    if not text:
        return {
            "painpoint_hit_rate": 0,
            "selling_point_coverage": 0,
            "sentiment": "中性",
            "matched": [],
            "missing": [],
            "summary": "暂无内容可分析，请先生成初稿。",
            "suggestions": [],
        }

    profile = knowledge.audience_profile(inputs.get("target_audience", ""))
    interest_terms = profile.get("interests", [])
    pain_terms = _keywords(inputs.get("pain_points", ""))

    target_terms = interest_terms + pain_terms
    matched = [t for t in target_terms if t and t in text]
    missing = [t for t in target_terms if t and t not in text]
    hit_rate = round(100 * len(matched) / len(target_terms)) if target_terms else 0

    # 卖点覆盖：按分句检查是否在正文中有对应关键词
    sp_terms = _keywords(inputs.get("selling_points", ""))
    sp_matched = [t for t in sp_terms if t and t in text]
    sp_coverage = round(100 * len(sp_matched) / len(sp_terms)) if sp_terms else 0

    pos = sum(text.count(w) for w in _POSITIVE)
    neg = sum(text.count(w) for w in _NEGATIVE)
    if neg > pos:
        sentiment = "偏负"
    elif pos > neg:
        sentiment = "正向"
    else:
        sentiment = "中性"

    suggestions: list[str] = []
    if hit_rate < 60:
        suggestions.append(f"内容对受众痛点覆盖不足，建议补入：{('、'.join(missing[:4])) or '目标受众关心的场景'}。")
    if sp_coverage < 70:
        suggestions.append("部分卖点未在文案中体现，建议在正文或分镜中补充对应信息。")
    if sentiment == "偏负":
        suggestions.append("整体措辞偏负面，建议增加体验感与正向引导表述。")
    if not suggestions:
        suggestions.append("痛点与卖点覆盖较好，人工复核事实与合规后即可进入导出环节。")

    summary = (
        f"痛点击中率 {hit_rate}%，卖点覆盖 {sp_coverage}%，情绪倾向「{sentiment}」；"
        f"命中 {len(matched)} 个受众关注点，未覆盖 {len(missing)} 个。"
    )

    return {
        "painpoint_hit_rate": hit_rate,
        "selling_point_coverage": sp_coverage,
        "sentiment": sentiment,
        "matched": matched,
        "missing": missing,
        "summary": summary,
        "suggestions": suggestions,
    }
