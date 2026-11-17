"""多格式导出与可追溯标识。

- 生成唯一溯源 ID，导出文件附带“AI 生成 + 人工校验”溯源标识；
- 支持 Markdown、Word(.docx)、纯文本（剪贴板）三种形式；
- 导出内容与界面当前人工修订版一致，保证“所见即所导”。
"""

from __future__ import annotations

import secrets
from datetime import datetime
from io import BytesIO

from docx import Document
from docx.shared import Pt

from . import config


def new_trace_id() -> str:
    date_part = datetime.now().strftime("%Y%m%d")
    return f"QL-{date_part}-{secrets.token_hex(3).upper()}"


def _meta_lines(meta: dict) -> list[str]:
    inputs = meta.get("inputs", {})
    return [
        f"- 传播场景：{inputs.get('scenario', '—')}",
        f"- 项目 / 产品：{inputs.get('project_name', '—')}",
        f"- 目标受众：{inputs.get('target_audience', '—')}",
        f"- 分发平台：{', '.join(inputs.get('platforms', []) or [])}",
        f"- 生成引擎：{meta.get('engine', '—')}",
        f"- 提示词版本：{meta.get('prompt_version', '—')}",
        f"- 溯源 ID：{meta.get('trace_id', '—')}",
        f"- 生成时间：{meta.get('created_at', '—')}",
    ]


def _compliance_lines(compliance: dict | None) -> list[str]:
    if not compliance:
        return []
    return [
        f"- 合规结论：{compliance.get('risk_level', '—')}"
        f"（高风险 {compliance.get('high', 0)} 项 / 中风险 {compliance.get('medium', 0)} 项）"
    ]


def render_markdown(content: dict, meta: dict, compliance: dict | None = None, audience: dict | None = None) -> str:
    c = content or {}
    lines: list[str] = []
    lines.append(f"# {c.get('headline', '传播内容')}")
    lines.append("")
    lines.append("## 项目信息")
    lines += _meta_lines(meta)
    lines += _compliance_lines(compliance)
    lines.append("")

    lines.append("## 主推文案")
    lines.append(c.get("body", ""))
    lines.append("")

    if c.get("platform_copy"):
        lines.append("## 分平台适配文案")
        for plat, copy in c["platform_copy"].items():
            lines.append(f"### {plat}")
            lines.append(copy)
            lines.append("")

    if c.get("tags"):
        lines.append("## 话题标签")
        lines.append(" ".join(c["tags"]))
        lines.append("")

    if c.get("selling_points"):
        lines.append("## 提炼卖点")
        for p in c["selling_points"]:
            lines.append(f"- {p}")
        lines.append("")

    if c.get("storyboard"):
        lines.append("## 短视频分镜脚本")
        lines.append("| 镜号 | 画面 | 口播 | 时长 | 字幕 | 配图提示词 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for s in c["storyboard"]:
            lines.append(
                f"| {s.get('shot', '')} | {s.get('visual', '')} | {s.get('voiceover', '')} | "
                f"{s.get('duration', '')} | {s.get('subtitle', '')} | {s.get('image_prompt', '')} |"
            )
        lines.append("")

    if c.get("image_prompts"):
        lines.append("## AI 配图提示词")
        for p in c["image_prompts"]:
            lines.append(f"- {p}")
        lines.append("")

    if audience:
        lines.append("## 受众分析")
        lines.append(audience.get("summary", ""))
        for sug in audience.get("suggestions", []):
            lines.append(f"- {sug}")
        lines.append("")

    lines.append("---")
    lines.append(
        f"溯源说明：本内容由「{config.APP_NAME}」辅助生成，AI 出初稿、人工二次校准后导出；"
        f"溯源 ID {meta.get('trace_id', '—')}，提示词版本 {meta.get('prompt_version', '—')}。"
        "对外发布前请人工复核事实、资质与合规表述。"
    )
    return "\n".join(lines)


def render_plain(content: dict) -> str:
    c = content or {}
    parts = [c.get("headline", ""), c.get("body", "")]
    for plat, copy in (c.get("platform_copy") or {}).items():
        parts.append(f"【{plat}】\n{copy}")
    if c.get("tags"):
        parts.append(" ".join(c["tags"]))
    return "\n\n".join(p for p in parts if p)


def render_docx(content: dict, meta: dict, compliance: dict | None = None, audience: dict | None = None) -> bytes:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(10.5)

    c = content or {}
    doc.add_heading(c.get("headline", "传播内容"), level=1)

    doc.add_heading("项目信息", level=2)
    for line in _meta_lines(meta):
        doc.add_paragraph(line)
    for line in _compliance_lines(compliance):
        doc.add_paragraph(line)

    doc.add_heading("主推文案", level=2)
    doc.add_paragraph(c.get("body", ""))

    if c.get("platform_copy"):
        doc.add_heading("分平台适配文案", level=2)
        for plat, copy in c["platform_copy"].items():
            doc.add_paragraph(plat, style="Heading 3")
            doc.add_paragraph(copy)

    if c.get("tags"):
        doc.add_heading("话题标签", level=2)
        doc.add_paragraph(" ".join(c["tags"]))

    if c.get("selling_points"):
        doc.add_heading("提炼卖点", level=2)
        for p in c["selling_points"]:
            doc.add_paragraph(p, style="List Bullet")

    if c.get("storyboard"):
        doc.add_heading("短视频分镜脚本", level=2)
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        for i, h in enumerate(["镜号", "画面", "口播", "时长", "字幕"]):
            hdr[i].text = h
        for s in c["storyboard"]:
            row = table.add_row().cells
            row[0].text = str(s.get("shot", ""))
            row[1].text = s.get("visual", "")
            row[2].text = s.get("voiceover", "")
            row[3].text = s.get("duration", "")
            row[4].text = s.get("subtitle", "")

    if c.get("image_prompts"):
        doc.add_heading("AI 配图提示词", level=2)
        for p in c["image_prompts"]:
            doc.add_paragraph(p, style="List Bullet")

    if audience:
        doc.add_heading("受众分析", level=2)
        doc.add_paragraph(audience.get("summary", ""))
        for sug in audience.get("suggestions", []):
            doc.add_paragraph(sug, style="List Bullet")

    doc.add_paragraph(
        f"溯源说明：本内容由「{config.APP_NAME}」辅助生成，AI 出初稿、人工二次校准后导出；"
        f"溯源 ID {meta.get('trace_id', '—')}，提示词版本 {meta.get('prompt_version', '—')}。"
        "对外发布前请人工复核事实、资质与合规表述。"
    )

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
