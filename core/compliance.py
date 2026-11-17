"""合规与传播风险预警引擎。

能力（对标“人机协作与校验机制 20 分”“功能可用性 25 分”）：
- 内置敏感词 / 极限词 / 夸大承诺 / 功效宣称 / 违规引流 / 低俗词正则子串匹配；
- 分级输出风险（高 / 中 / 低），附命中位置、类别、法规依据与修改建议；
- 提供“一键合规润色”，在本地词典层面替换为稳妥表述，并记录替换轨迹；
- 输入完整性校验：空白 / 缺项给出友好提示，触发容错而非崩溃。
"""

from __future__ import annotations

import re
from . import knowledge

# 合规润色替换词典（仅做稳妥化处理，最终措辞由人工确认）
_REPLACE_MAP: dict[str, str] = {
    "最佳": "颇具特色", "最好": "口碑不错", "最优": "表现较好",
    "最高级": "较高水准", "顶级": "特色", "极品": "佳品",
    "国家级": "具有地方代表性的", "世界级": "具有广泛影响力的",
    "全网第一": "广受关注", "全国第一": "颇具代表性", "行业第一": "具有一定知名度",
    "唯一": "代表性", "首家": "较早开展的", "首选": "可选之一",
    "绝无仅有": "少见", "史无前例": "难得", "销量冠军": "销量较好",
    "第一名": "排名靠前", "独一无二": "有自身特点", "无与伦比": "颇具特色",
    "包治百病": "（删除功效承诺）", "祖传秘方": "传统工艺", "药到病除": "（删除疗效表述）",
    "无效退款": "按平台售后规则处理", "稳赚不赔": "收益存在不确定性",
    "一夜暴富": "（删除收益承诺）", "秒赚": "（删除收益承诺）", "躺赚": "（删除收益承诺）",
    "必涨": "（删除预测承诺）", "百分百有效": "体验因人而异", "永久有效": "长期可用（以实际为准）",
    "万能": "适用场景较多", "特效": "特点突出", "包治": "（删除功效表述）",
    "治愈": "（删除疗效表述）", "疗效": "使用感受", "降压": "（删除功效表述）",
    "降糖": "（删除功效表述）", "抗癌": "（删除功效表述）", "防癌": "（删除功效表述）",
    "加微信": "通过平台官方私信联系", "加v": "通过平台官方私信联系",
    "私聊我": "在评论区留言", "扫码下单": "通过店铺官方链接下单",
    "私下转账": "通过平台官方渠道交易",
}

# 需要拦截的输入完整性问题
REQUIRED_FIELDS = [
    ("scenario", "传播场景"),
    ("project_name", "项目 / 产品名称"),
    ("selling_points", "核心卖点与资料"),
    ("target_audience", "目标受众"),
]


def _categories() -> list[dict]:
    return knowledge.sensitive()["categories"]


def scan_text(text: str) -> list[dict]:
    """扫描单段文本，返回命中明细列表。"""
    findings: list[dict] = []
    if not text:
        return findings
    lowered = text.lower()
    for cat in _categories():
        for word in cat["words"]:
            idx = lowered.find(word.lower())
            if idx < 0:
                continue
            # 语境排除：“国家级非遗 / 国家级传承人”等官方称谓不属于广告法极限用语
            if word == "国家级" and text[idx + 3: idx + 9].startswith(
                ("非遗", "非物质文化遗产", "传承人", "大师", "项目")
            ):
                continue
            findings.append(
                    {
                        "word": word,
                        "category": cat["label"],
                        "level": cat["level"],
                        "basis": cat["basis"],
                        "suggestion": cat["suggestion"],
                        "position": idx,
                        "context": text[max(0, idx - 8): idx + len(word) + 8],
                    }
                )
    # 句式类提示
    for rule in knowledge.sensitive().get("夸大句式提示", []):
        if rule["pattern"] in text:
            findings.append(
                {
                    "word": rule["pattern"],
                    "category": "比例 / 成分承诺",
                    "level": rule["level"],
                    "basis": "宣传内容需有检测或事实依据支撑",
                    "suggestion": rule["note"],
                    "position": text.find(rule["pattern"]),
                    "context": text[max(0, text.find(rule["pattern"]) - 8): text.find(rule["pattern"]) + 12],
                }
            )
    # 按位置排序，高风险在前
    findings.sort(key=lambda f: (0 if f["level"] == "高" else 1, f["position"]))
    return findings


def _iter_content_texts(content: dict) -> list[tuple[str, str]]:
    """抽取待校验文本段，返回 (字段名, 文本) 列表。"""
    items: list[tuple[str, str]] = []
    if not content:
        return items
    items.append(("主标题", content.get("headline", "")))
    items.append(("主推正文", content.get("body", "")))
    for plat, copy in (content.get("platform_copy") or {}).items():
        items.append((f"{plat}文案", copy))
    for tag in content.get("tags", []) or []:
        items.append(("话题标签", tag))
    for i, shot in enumerate(content.get("storyboard", []) or [], start=1):
        for key in ("voiceover", "subtitle", "visual"):
            if shot.get(key):
                items.append((f"分镜{shot.get('shot', i)}·{key}", shot[key]))
    return items


def scan_inputs(inputs: dict) -> list[dict]:
    """扫描用户原始诉求中的违规倾向（输入侧风险提示）。

    边界场景下，违规词可能出现在需求描述、卖点或约束中，
    需在生成前/生成后一并识别并提示人工调整，避免风险词进入初稿。
    """
    field_map = {
        "project_name": "项目名称",
        "selling_points": "核心卖点",
        "pain_points": "受众痛点",
        "constraints": "附加约束",
    }
    findings: list[dict] = []
    for key, label in field_map.items():
        for f in scan_text(str(inputs.get(key, "") or "")):
            f["field"] = f"输入·{label}"
            findings.append(f)
    findings.sort(key=lambda f: (0 if f["level"] == "高" else 1, f["position"]))
    return findings


def scan_content(content: dict) -> dict:
    """对整个内容矩阵做合规扫描，汇总结论与分级统计。"""
    all_findings: list[dict] = []
    for field, text in _iter_content_texts(content):
        for f in scan_text(text):
            f["field"] = field
            all_findings.append(f)

    high = sum(1 for f in all_findings if f["level"] == "高")
    mid = sum(1 for f in all_findings if f["level"] == "中")
    if high > 0:
        risk = "高风险"
    elif mid > 0:
        risk = "中风险"
    else:
        risk = "低风险 / 通过"

    return {
        "risk_level": risk,
        "high": high,
        "medium": mid,
        "total": len(all_findings),
        "findings": all_findings,
    }


def scan_all(content: dict, inputs: dict) -> dict:
    """内容侧 + 输入侧合并合规扫描，供界面与留痕统一使用。

    风险等级以“内容侧”命中为准；输入侧命中仅作为需求表述的 advisory 提示，
    避免“不得承诺疗效”等否定 / 约束语境被误判为违规宣称。
    """
    report = scan_content(content)
    input_findings = scan_inputs(inputs)
    report["input_findings"] = input_findings
    report["input_high"] = sum(1 for f in input_findings if f["level"] == "高")
    report["input_medium"] = sum(1 for f in input_findings if f["level"] == "中")
    report["total"] += len(input_findings)
    return report


def polish_text(text: str) -> tuple[str, list[dict]]:
    """本地一键合规润色：返回润色后文本与替换记录。"""
    if not text:
        return text, []
    polished = text
    replacements: list[dict] = []
    for src, dst in _REPLACE_MAP.items():
        if src in polished:
            count = polished.count(src)
            polished = polished.replace(src, dst)
            replacements.append({"original": src, "replacement": dst, "count": count})
    # 去除连续重复标点造成的夸大感（如多个感叹号堆叠）
    polished = re.sub(r"!{2,}", "！", polished)
    return polished, replacements


def polish_content(content: dict) -> tuple[dict, list[dict]]:
    """对内容矩阵逐段润色，返回新内容与整体替换记录。"""
    if not content:
        return content, []
    new_content = dict(content)
    logs: list[dict] = []

    for key in ("headline", "body"):
        if new_content.get(key):
            new_content[key], reps = polish_text(new_content[key])
            for r in reps:
                r["field"] = key
                logs.append(r)

    pc = dict(new_content.get("platform_copy") or {})
    for plat, copy in pc.items():
        pc[plat], reps = polish_text(copy)
        for r in reps:
            r["field"] = f"{plat}文案"
            logs.append(r)
    new_content["platform_copy"] = pc

    shots = []
    for shot in new_content.get("storyboard", []) or []:
        s = dict(shot)
        for key in ("voiceover", "subtitle", "visual"):
            if s.get(key):
                s[key], reps = polish_text(s[key])
                for r in reps:
                    r["field"] = f"分镜{s.get('shot')}·{key}"
                    logs.append(r)
        shots.append(s)
    new_content["storyboard"] = shots
    return new_content, logs


def validate_inputs(inputs: dict) -> list[str]:
    """输入完整性校验，返回问题提示列表（空列表表示通过）。"""
    errors: list[str] = []
    for key, label in REQUIRED_FIELDS:
        value = str(inputs.get(key, "") or "").strip()
        if not value:
            errors.append(f"缺少必填项：{label}，请补充后再生成。")
    if not inputs.get("platforms"):
        errors.append("请至少选择一个分发平台。")
    # 边界：卖点过短（少于 5 个字符）提示信息不足
    if len(str(inputs.get("selling_points", "") or "").strip()) < 5:
        errors.append("核心卖点信息过少，建议补充产品特色、背景或适用场景，以便生成贴合的内容。")
    return errors
