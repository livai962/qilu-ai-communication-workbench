"""内容生成工作流：在线大模型引擎 + 本地离线兜底引擎。

双引擎策略（对标“运行可靠、容错运行”与本地 Plan B）：
- 配置了 LLM_API_KEY 且 LLM_ENABLED=true 时，走 OpenAI 兼容接口；
- 未配置 / 调用超时 / 返回解析失败时，自动降级为本地规则模板引擎，
  保证评审在无网络、无密钥条件下仍可完整跑通全流程；
- 两种引擎输出同一 JSON 契约，下游校验、编辑、留痕、导出逻辑完全一致。
"""

from __future__ import annotations

import json
import re

import requests

from . import config, knowledge, prompts

# 输出契约必填字段，用于校验模型返回
_REQUIRED_KEYS = ["headline", "body", "platform_copy", "tags", "selling_points", "storyboard", "image_prompts"]


# --------------------------------------------------------------------------
# 在线大模型引擎
# --------------------------------------------------------------------------
def _call_llm(inputs: dict, platforms: list[str]) -> dict:
    bundle = prompts.prompt_bundle(inputs, platforms)
    url = f"{config.LLM_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": bundle["system"]},
            {"role": "user", "content": bundle["user"]},
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(url, headers=headers, json=body, timeout=config.LLM_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return _normalize(parsed, platforms)


# --------------------------------------------------------------------------
# 本地离线兜底引擎
# --------------------------------------------------------------------------
def _split_points(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[，。；、;\n]+", text or "") if p.strip()]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _style_words(style: float) -> dict:
    if style >= 0.6:
        return {
            "hook": "谁懂啊",
            "tone": "轻松口语、像朋友安利",
            "cta": "快收藏，周末就出发～",
            "adj": "出片、好逛、有料",
        }
    return {
        "hook": "值得关注",
        "tone": "条理清晰、表述稳妥",
        "cta": "欢迎通过官方渠道了解咨询。",
        "adj": "特色鲜明、内容扎实",
    }


def _local_generate(inputs: dict, platforms: list[str]) -> dict:
    name = inputs.get("project_name", "").strip()
    points = _split_points(inputs.get("selling_points", ""))
    audience = inputs.get("target_audience", "").strip()
    pain = inputs.get("pain_points", "").strip()
    length = inputs.get("length", "中等")
    sw = _style_words(float(inputs.get("style", 0.5)))
    hints = knowledge.culture_hints(inputs.get("scenario", ""))

    def _pick_hint() -> str:
        for h in hints:
            tokens = [t for t in h.replace("（", " ").replace("）", " ").split() if t]
            if any(t and t in name for t in tokens):
                return h
        return hints[0] if hints else "齐鲁大地"

    hint = _pick_hint()

    point_line = "；".join(points[:5]) if points else "特色鲜明，值得体验"

    # 主标题与主推正文
    headline = f"{name}｜{sw['adj']}，{audience}值得一看的齐鲁选择"
    body = (
        f"【场景引入】{sw['hook']}，如果你是{audience}，正在为“{pain or '不知道怎么选'}”发愁，"
        f"不妨了解一下{name}。\n\n"
        f"【核心看点】{point_line}。\n\n"
        f"【文化联结】这里融合了{hint}的地域气质，体验过程既能感受到本土特色，也便于安排行程与分享。\n\n"
        f"【适合人群】{audience}，尤其看重真实体验与性价比的朋友。\n\n"
        f"【行动建议】{sw['cta']}（具体开放时间、价格与预约方式以官方发布为准。）"
    )

    # 分平台适配
    platform_copy: dict[str, str] = {}
    for plat in platforms:
        ps = knowledge.platform_structure(plat)
        if plat == "小红书":
            platform_copy[plat] = (
                f"标题：{headline}\n\n"
                f"姐妹们，{name}真的值得安排！{point_line}。\n"
                f"适合{audience}，{pain}的朋友可以参考这条路线。\n"
                f"小贴士：出行前记得核对官方开放信息，错峰体验更舒服。\n"
                f"#{' #'.join(_tags(name, hints, audience))}"
            )
        elif plat == "抖音":
            platform_copy[plat] = (
                f"（3 秒钩子）{sw['hook']}，{name}到底值不值得去？\n"
                f"（痛点）{pain}？这条视频一次说清。\n"
                f"（卖点）{point_line}。\n"
                f"（引导）点赞收藏，评论区聊聊你最想体验哪一项。"
            )
        else:
            platform_copy[plat] = (
                f"一、项目概览：{name}面向{audience}，围绕本土特色提供相关体验与服务。\n"
                f"二、特色亮点：{point_line}。\n"
                f"三、适配场景：{pain}的需求可在此获得对应参考。\n"
                f"四、温馨提示：相关信息以官方发布为准，欢迎通过正规渠道咨询了解。"
            )

    tags = _tags(name, hints, audience)

    storyboard = [
        {"shot": 1, "visual": f"{name}主体外观 / 标志性场景全景亮相", "voiceover": f"今天带大家走进{name}。", "duration": "0-3s", "subtitle": name, "image_prompt": f"写实风光镜头，{name}主体，{hint}背景，青蓝与暖金色调，自然光，干净构图"},
        {"shot": 2, "visual": f"目标受众视角的体验画面，呼应痛点：{pain}", "voiceover": f"如果你也在意：{pain}", "duration": "3-8s", "subtitle": "你是不是也有这些顾虑？", "image_prompt": f"人物体验中景，自然神态，本土场景，柔和色调"},
        {"shot": 3, "visual": "卖点细节特写（工艺 / 食材 / 建筑 / 展品）", "voiceover": f"这里的亮点包括：{point_line}", "duration": "8-18s", "subtitle": "核心亮点逐一呈现", "image_prompt": "细节特写镜头，材质与纹理清晰，浅景深，自然光线"},
        {"shot": 4, "visual": "互动 / 体验 / 品尝环节画面", "voiceover": "沉浸式感受本土特色与氛围。", "duration": "18-28s", "subtitle": "沉浸式体验", "image_prompt": "互动体验场景，温暖氛围，记录真实瞬间"},
        {"shot": 5, "visual": "收尾空镜 + 官方信息提示卡", "voiceover": sw["cta"], "duration": "28-35s", "subtitle": "信息以官方发布为准", "image_prompt": "收尾空镜，地域元素点缀，留白构图，简洁标题位"},
    ]

    image_prompts = [
        f"{name}主视觉海报，{hint}元素，青蓝白简约配色，写实风格，竖版构图，留白充足",
        f"体验场景插画，{audience}视角，本土文化符号点缀，线条简洁，低饱和配色",
        f"卖点细节图，突出材质 / 工艺 / 口感，自然光，干净背景，适合社交平台配图",
    ]

    return {
        "headline": headline,
        "body": body,
        "platform_copy": platform_copy,
        "tags": tags,
        "selling_points": points,
        "storyboard": storyboard,
        "image_prompts": image_prompts,
        "audience_notes": f"面向{audience}，重点回应“{pain}”，语气{sw['tone']}。",
    }


def _tags(name: str, hints: list[str], audience: str) -> list[str]:
    base = [f"#{name}", "#好客山东"]
    if hints:
        base.append(f"#{hints[0]}")
    if audience:
        base.append(f"#{audience}")
    base += ["#本地宝藏", "#周末去哪儿"]
    # 去重保序
    seen, out = set(), []
    for t in base:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:8]


def _normalize(parsed: dict, platforms: list[str]) -> dict:
    """补齐模型返回中缺失的字段，保证下游契约一致。"""
    local = _local_generate({"project_name": parsed.get("headline", ""), "selling_points": "", "target_audience": "", "pain_points": "", "style": 0.5, "length": "中等", "scenario": ""}, platforms)
    merged = dict(local)
    for key in _REQUIRED_KEYS:
        if parsed.get(key) not in (None, "", []):
            merged[key] = parsed[key]
    # 平台文案补齐缺失平台
    pc = dict(merged.get("platform_copy") or {})
    for plat in platforms:
        pc.setdefault(plat, local["platform_copy"].get(plat, ""))
    merged["platform_copy"] = pc
    return merged


# --------------------------------------------------------------------------
# 对外主入口
# --------------------------------------------------------------------------
def generate(inputs: dict) -> dict:
    platforms = inputs.get("platforms") or knowledge.PLATFORMS
    bundle = prompts.prompt_bundle(inputs, platforms)

    if config.LLM_ENABLED:
        try:
            content = _call_llm(inputs, platforms)
            return {
                "content": content,
                "engine": "online-llm",
                "engine_note": "已通过在线大模型生成；下方内容仍为待人工校准的初稿。",
                "prompt_bundle": bundle,
            }
        except Exception as exc:  # 容错：任何异常都降级本地引擎
            return {
                "content": _local_generate(inputs, platforms),
                "engine": "local-fallback",
                "engine_note": f"在线模型暂不可用（{type(exc).__name__}），已自动切换本地离线兜底引擎，内容可完整演示。",
                "prompt_bundle": bundle,
            }

    return {
        "content": _local_generate(inputs, platforms),
        "engine": "local-fallback",
        "engine_note": "当前为本地离线兜底引擎（未配置在线模型）；生成结构与在线引擎一致，可完整演示全流程。",
        "prompt_bundle": bundle,
    }
