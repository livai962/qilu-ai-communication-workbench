"""提示词工程层：可配置模板、版本号与迭代记录。

设计要点（对标“AI 技术应用与提示词工程 15 分”）：
- System Prompt 注入营销专业逻辑、山东本土文化属性与合规红线；
- 模板与业务知识外置，不在代码中堆砌一次性指令；
- 每个生成结果附带当前提示词版本号，便于技术文档佐证与版本回溯；
- PROMPT_CHANGELOG 记录提示词版本迭代轨迹，对应“关键提示词版本迭代记录”交付要求。
"""

from __future__ import annotations

from . import config
from .knowledge import platform_structure

PROMPT_VERSION = config.PROMPT_VERSION

# 提示词版本迭代记录（决赛技术说明文档直接引用）
PROMPT_CHANGELOG = [
    {
        "version": "v1.0.0",
        "date": "2026-10-20",
        "change": "初版：通用营销文案生成指令，仅输出单平台文案。",
    },
    {
        "version": "v1.1.0",
        "date": "2026-10-28",
        "change": "注入齐鲁文化元素库与三类场景定位，输出从单文案扩展为“文案+标签+分镜+配图提示词”矩阵。",
    },
    {
        "version": "v1.2.0",
        "date": "2026-11-06",
        "change": "加入合规红线与广告法约束，要求模型规避绝对化用语、功效承诺与站外导流；补充受众痛点匹配要求。",
    },
    {
        "version": "v1.3.0",
        "date": "2026-11-15",
        "change": "结构化输出 JSON 契约，分平台适配各自内容结构与语气；明确人机协作边界：AI 出初稿，人工负责最终校准与发布决策。",
    },
]


def system_prompt() -> str:
    """系统提示词：角色 + 领域知识 + 合规约束 + 输出契约。"""
    return f"""你是“齐鲁智传”传播内容策划助手，服务于山东县域文旅、非遗老字号与助农农产品三类本土场景。

【角色与分工边界】
- 你负责：提炼卖点、按平台结构生成初稿、给出话题标签、分镜脚本与配图提示词、提示合规风险。
- 你不负责：替代人工做最终发布决策；所有输出均为“待人工校准的初稿”，不得宣称可直接定稿发布。

【本土文化要求】
- 优先调用齐鲁文化元素（好客山东、儒家文化、齐风鲁韵、地标、非遗、鲁菜等），避免与本地无关的泛泛套话。
- 尊重地域文化与产品事实，不编造历史典故、产地、工艺与资质。

【合规红线（必须遵守）】
- 不使用广告法绝对化用语（最佳、第一、顶级、唯一、国家级等）；
- 不做虚假夸大、收益承诺与疾病治疗/保健功效宣称；
- 不留站外联系方式、不引导私下交易；
- 涉及数据、比例、资质时，若无依据不得写死，用“以实际为准”等稳妥表述。

【输出契约】
严格输出如下 JSON（不要输出 JSON 以外的解释文字）：
{{
  "headline": "主标题",
  "body": "主推正文（主平台）",
  "platform_copy": {{"平台名": "该平台适配文案"}},
  "tags": ["话题标签"],
  "selling_points": ["提炼后的卖点"],
  "storyboard": [{{"shot": 1, "visual": "画面", "voiceover": "口播", "duration": "时长", "subtitle": "字幕", "image_prompt": "配图/画面提示词"}}],
  "image_prompts": ["AI 配图提示词"],
  "audience_notes": "面向目标受众的沟通要点说明"
}}
"""


def build_user_prompt(inputs: dict, platforms: list[str]) -> str:
    """根据结构化输入组装用户提示词，并内嵌各平台内容结构要求。"""
    platform_blocks = []
    for p in platforms:
        ps = platform_structure(p)
        platform_blocks.append(
            f"- {p}：结构要求「{ps['structure']}」；语气「{ps['tone']}」；篇幅「{ps['length']}」；标签「{ps['tag_style']}」。"
        )

    style_desc = (
        "偏年轻网感、活泼口语化"
        if inputs.get("style", 0.5) >= 0.6
        else "偏稳重专业、信息严谨"
    )

    return f"""【传播场景】{inputs.get('scenario', '')}
【项目 / 产品名称】{inputs.get('project_name', '')}
【核心卖点与资料】{inputs.get('selling_points', '')}
【目标受众】{inputs.get('target_audience', '')}
【受众痛点】{inputs.get('pain_points', '')}
【分发平台】{', '.join(platforms)}
【内容风格】{style_desc}（风格系数 {inputs.get('style', 0.5)}）
【篇幅】{inputs.get('length', '中等')}
【附加约束】{inputs.get('constraints', '无')}

【各平台结构要求】
{chr(10).join(platform_blocks)}

请按系统提示词的 JSON 契约输出完整内容矩阵。"""


def prompt_bundle(inputs: dict, platforms: list[str]) -> dict:
    """返回一次生成所用的完整提示词包（供留痕与界面展示）。"""
    return {
        "version": PROMPT_VERSION,
        "system": system_prompt(),
        "user": build_user_prompt(inputs, platforms),
        "changelog": PROMPT_CHANGELOG,
    }
