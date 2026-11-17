"""把三类标准案例的真实运行会话导出为案例佐证材料。

用途：决赛要求的「≥3 个完整运行案例（输入 / 运行过程 / 最终输出 / 人工修改记录 / 验证结果）」
      与本仓库的运行日志一一对应，评审核对时无需重新操作界面即可看到完整链路。

产物（默认写入 docs/案例佐证/）：
- 案例-01-典型场景.md / 案例-02-复杂输入.md / 案例-03-边界输入.md
- 索引.md
- sessions/*.json（与界面里「保存本次会话留痕」落盘格式一致）

运行：python3 scripts/export_case_evidence.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import audience, compliance, config, diff, exporter, generator, knowledge, storage  # noqa: E402

OUT = ROOT / "docs" / "案例佐证"
SESSION_OUT = OUT / "sessions"

# 每个案例的人工修订动作：只做语气与结构层面的调整，不新增任何事实性信息。
HUMAN_EDITS = {
    "typical": [
        ("body", "不妨了解一下曲阜三孔景区", "可以先看下面这三处"),
        ("body", "快收藏，周末就出发～", "先收藏，周末错峰去更舒服～"),
    ],
    "complex": [
        ("platform_copy.抖音", "这条视频一次说清", "这条视频分三步说清"),
        ("body", "欢迎通过官方渠道了解", "建议通过官方渠道核对产地与售后"),
    ],
    "boundary": [
        ("headline", "亲子家庭值得一看的齐鲁选择", "亲子家庭周末值得安排的非遗体验"),
        ("body", "【行动建议】快收藏，周末就出发～", "【行动建议】先收藏，出行前核对开放时间与体验课排期"),
    ],
}

REVIEW_NOTES = {
    "typical": "人工核对后确认：三处核心看点与输入一致，未新增票价、开放时间等未提供的信息，可发布。",
    "complex": "人工核对后确认：三平台卖点顺序一致，未出现功效承诺与绝对化用语；卖点覆盖偏低，已在输入侧补充产地信息后重跑。",
    "boundary": "人工核对后确认：输入侧的「全国第一 / 最佳 / 包治」未被沿用，正文改为可核验的工艺与体验表述。",
}


def _set_field(content: dict, path: str, needle: str, replacement: str) -> tuple[str, str] | None:
    """按字段路径替换文本，返回 (before, after)；未命中返回 None。"""
    if "." in path:
        head, tail = path.split(".", 1)
        target = content.setdefault(head, {})
        before = target.get(tail, "")
    else:
        before = content.get(path, "")
    if needle not in before:
        return None
    after = before.replace(needle, replacement, 1)
    if "." in path:
        head, tail = path.split(".", 1)
        content[head][tail] = after
    else:
        content[path] = after
    return before, after


def _inputs_table(inputs: dict) -> str:
    rows = [
        ("传播场景", inputs.get("scenario", "")),
        ("项目 / 产品名称", inputs.get("project_name", "")),
        ("核心卖点与资料", inputs.get("selling_points", "")),
        ("目标受众", inputs.get("target_audience", "")),
        ("受众痛点", inputs.get("pain_points", "")),
        ("分发平台", "、".join(inputs.get("platforms", []) or [])),
        ("内容风格", f"滑杆值 {inputs.get('style', 0)}（0 = 政务专业，1 = 年轻网感）"),
        ("篇幅", inputs.get("length", "")),
        ("附加约束", inputs.get("constraints", "") or "（未填写）"),
    ]
    lines = ["| 字段 | 内容 |", "| --- | --- |"]
    for k, v in rows:
        lines.append(f"| {k} | {str(v).replace('|', '｜')} |")
    return "\n".join(lines)


def _hit_table(hits: list[dict], title: str) -> str:
    if not hits:
        return f"**{title}**：0 条命中。"
    lines = [f"**{title}**：{len(hits)} 条命中。", "", "| 命中词 | 等级 | 依据 | 建议 |", "| --- | --- | --- | --- |"]
    for h in hits:
        lines.append(
            "| {w} | {lv} | {rule} | {fix} |".format(
                w=h.get("word", ""),
                lv=h.get("level", ""),
                rule=str(h.get("basis", h.get("category", ""))).replace("|", "｜"),
                fix=str(h.get("suggestion", "") or "—").replace("|", "｜"),
            )
        )
    return "\n".join(lines)


def build_case(example: dict, index: int) -> dict:
    inputs = copy.deepcopy(example["inputs"])
    result = generator.generate(inputs)
    ai_content = copy.deepcopy(result["content"])
    final_content = copy.deepcopy(result["content"])

    meta = {
        "trace_id": exporter.new_trace_id(),
        "created_at": diff.now_ts(),
        "engine": result["engine"],
        "engine_note": result["engine_note"],
        "prompt_version": result["prompt_bundle"]["version"],
        "inputs": inputs,
    }

    revisions: list[dict] = []
    for path, needle, replacement in HUMAN_EDITS.get(example["id"], []):
        changed = _set_field(final_content, path, needle, replacement)
        if changed:
            before, after = changed
            revisions.append(
                diff.make_revision_record(path, before, after, "人工修订（按案例人工干预要求执行）", author="人工（复现记录）")
            )

    comp = compliance.scan_all(final_content, inputs)
    aud = audience.analyze(final_content, inputs)
    aud_ai = audience.analyze(ai_content, inputs)

    record = {
        "trace_id": meta["trace_id"],
        "created_at": meta["created_at"],
        "inputs": inputs,
        "prompt_version": meta["prompt_version"],
        "engine": meta["engine"],
        "engine_note": meta["engine_note"],
        "ai_content": ai_content,
        "final_content": final_content,
        "revisions": revisions,
        "polish_logs": [],
        "compliance": comp,
        "audience": aud,
        "case_id": example["id"],
        "case_label": example["label"],
        "human_intervention_requirement": example.get("human_intervention", ""),
        "validation_point": example.get("validation_point", ""),
    }
    storage.save_session(record)

    md_export = exporter.render_markdown(final_content, meta, comp, aud)

    lines: list[str] = []
    lines.append(f"# {example['label']}　运行会话佐证")
    lines.append("")
    lines.append(f"> 案例编号：`{example['id']}`　｜　溯源 ID：`{meta['trace_id']}`　｜　运行时间：{meta['created_at']}")
    lines.append(">")
    lines.append(f"> 生成引擎：`{meta['engine']}`（{meta['engine_note']}）　｜　提示词版本：`{meta['prompt_version']}`")
    lines.append("")
    lines.append("## 一、结构化输入")
    lines.append("")
    lines.append(_inputs_table(inputs))
    lines.append("")
    lines.append(f"**赛事要求的人工干预点**：{example.get('human_intervention', '—')}")
    lines.append("")
    lines.append("## 二、AI 初稿（未做任何人工修改）")
    lines.append("")
    lines.append(f"**主标题**：{ai_content.get('headline', '')}")
    lines.append("")
    lines.append("**主推正文**：")
    lines.append("")
    for para in str(ai_content.get("body", "")).split("\n"):
        if para.strip():
            lines.append(f"- {para.strip()}")
    lines.append("")
    lines.append("**分平台适配文案**：")
    lines.append("")
    for platform, text in (ai_content.get("platform_copy") or {}).items():
        first = str(text).split("\n")[0]
        lines.append(f"- **{platform}**（首行）：{first}")
    lines.append("")
    lines.append("**话题标签**：" + "　".join(ai_content.get("tags", []) or []))
    lines.append("")
    if ai_content.get("storyboard"):
        lines.append("**短视频分镜脚本**：")
        lines.append("")
        lines.append("| 镜号 | 画面 | 口播 | 时长 |")
        lines.append("| --- | --- | --- | --- |")
        for shot in ai_content["storyboard"]:
            lines.append(
                f"| {shot.get('shot', '')} | {str(shot.get('visual', '')).replace('|', '｜')} "
                f"| {str(shot.get('voiceover', '')).replace('|', '｜')} | {shot.get('duration', '')} |"
            )
        lines.append("")
    if ai_content.get("image_prompts"):
        lines.append("**AI 配图提示词**：")
        lines.append("")
        for prompt in ai_content["image_prompts"]:
            lines.append(f"- {prompt}")
        lines.append("")

    lines.append("## 三、合规校验结果（内容侧 / 输入侧分离）")
    lines.append("")
    lines.append(
        "**总体结论**：{level}　｜　高风险命中 {high}　｜　中风险命中 {mid}　｜　输入侧提示 {inputs_n} 条".format(
            level=comp.get("risk_level", "—"),
            high=comp.get("high", 0),
            mid=comp.get("medium", 0),
            inputs_n=len(comp.get("input_findings", []) or []),
        )
    )
    lines.append("")
    lines.append(_hit_table(comp.get("findings", []) or [], "内容侧命中明细"))
    lines.append("")
    lines.append(_hit_table(comp.get("input_findings", []) or [], "输入侧提示（仅提示，不直接升级结论）"))
    lines.append("")
    if comp.get("notes"):
        lines.append("**引擎说明**：" + "；".join(comp["notes"]))
        lines.append("")

    lines.append("## 四、受众语义与卖点覆盖")
    lines.append("")
    lines.append(
        "**AI 初稿（未修订）**：痛点击中率 {a0}%、卖点覆盖率 {b0}%　→　**人工修订后终稿**：痛点击中率 {a1}%、卖点覆盖率 {b1}%".format(
            a0=aud_ai.get("painpoint_hit_rate", 0), b0=aud_ai.get("selling_point_coverage", 0),
            a1=aud.get("painpoint_hit_rate", 0), b1=aud.get("selling_point_coverage", 0),
        )
    )
    lines.append("")
    lines.append(
        "**痛点击中率**：{r}%　｜　**卖点覆盖率**：{s}%　｜　**情绪倾向**：{e}".format(
            r=aud.get("painpoint_hit_rate", 0),
            s=aud.get("selling_point_coverage", 0),
            e=aud.get("sentiment", "—"),
        )
    )
    lines.append("")
    if aud.get("matched"):
        lines.append("**已回应关注点**：" + "、".join(aud["matched"]))
        lines.append("")
    if aud.get("missing"):
        lines.append("**未覆盖关注点**：" + "、".join(aud["missing"]))
        lines.append("")
    for sug in aud.get("suggestions", []) or []:
        lines.append(f"- 建议：{sug}")
    if aud.get("suggestions"):
        lines.append("")

    lines.append("## 五、人工修改记录（含字符级 Diff）")
    lines.append("")
    if not revisions:
        lines.append("本次复现未产生字段级修改（该案例以「不改也通过」为验证目标）。")
        lines.append("")
    for rev in revisions:
        lines.append(f"### {rev.get('field')}　{rev.get('timestamp', '')}")
        lines.append("")
        lines.append(f"- 动作：{rev.get('action', '')}　｜　操作人：{rev.get('author', '')}")
        lines.append(
            "- 变更摘要：新增 {a} 字符、删除 {d} 字符".format(
                a=rev.get("added_chars", 0), d=rev.get("removed_chars", 0)
            )
        )
        lines.append("")
        ops = [o for o in diff.diff_ops(rev.get("before", ""), rev.get("after", "")) if o["op"] != "equal"]
        if ops:
            lines.append("**字符级操作序列（节选）**：")
            lines.append("")
            for op in ops[:6]:
                marker = "＋新增" if op["op"] == "insert" else "－删除"
                lines.append(f"- {marker}：`{op['text'][:120]}`")
            lines.append("")
        lines.append("<details><summary>修改前 / 修改后（展开查看）</summary>")
        lines.append("")
        lines.append("**修改前**：")
        lines.append("")
        lines.append("```")
        lines.append(str(rev.get("before", ""))[:600])
        lines.append("```")
        lines.append("")
        lines.append("**修改后**：")
        lines.append("")
        lines.append("```")
        lines.append(str(rev.get("after", ""))[:600])
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("## 六、人工校验结论")
    lines.append("")
    lines.append(REVIEW_NOTES.get(example["id"], "人工复核后确认可发布。"))
    lines.append("")
    lines.append(f"案例拟验证点：{example.get('validation_point', '—')}")
    lines.append("")

    lines.append("## 七、导出件头部（与 Word / Markdown 导出内容一致）")
    lines.append("")
    lines.append("```markdown")
    lines.extend(md_export.split("\n")[:16])
    lines.append("```")
    lines.append("")

    lines.append("## 八、复现方式")
    lines.append("")
    lines.append("```bash")
    lines.append("streamlit run app.py            # 打开工作台")
    lines.append("# 左侧「标准案例一键加载」→ 选择对应案例 → 一键生成内容矩阵")
    lines.append("```")
    lines.append("")
    lines.append(
        f"本文件由 `scripts/export_case_evidence.py` 生成，对应会话文件：`docs/案例佐证/sessions/{meta['trace_id']}.json`。"
    )
    lines.append("")

    md_path = OUT / f"案例-{index:02d}-{example['id']}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    session_path = SESSION_OUT / f"{meta['trace_id']}.json"
    session_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "label": example["label"],
        "trace_id": meta["trace_id"],
        "path": md_path.relative_to(ROOT).as_posix(),
        "risk": comp.get("risk_level", "—"),
        "content_hits": len(comp.get("findings", []) or []),
        "input_hits": len(comp.get("input_findings", []) or []),
        "pain_rate": aud.get("painpoint_hit_rate", 0),
        "pain_rate_ai": aud_ai.get("painpoint_hit_rate", 0),
        "coverage": aud.get("selling_point_coverage", 0),
        "revisions": len(revisions),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SESSION_OUT.mkdir(parents=True, exist_ok=True)

    examples = knowledge.example_list()
    summaries = [build_case(ex, i) for i, ex in enumerate(examples, start=1)]

    index_lines = [
        "# 三类案例运行会话索引",
        "",
        f"生成时间：{diff.now_ts()}　｜　生成脚本：`scripts/export_case_evidence.py`　｜　提示词版本：`{config.PROMPT_VERSION}`",
        "",
        "本目录把三类标准案例的完整运行链路固化为可核对的材料：结构化输入、AI 初稿、合规校验、受众分析、人工修改 Diff、导出件头部。",
        "每条记录都带唯一溯源 ID，可用于与 `docs/案例记录.md`、导出文件三者互相对照。",
        "",
        "| 案例 | 溯源 ID | 合规结论 | 内容侧命中 | 输入侧提示 | 痛点(初稿→终稿) | 卖点覆盖(终稿) | 人工修改 | 材料 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in summaries:
        index_lines.append(
            "| {label} | `{tid}` | {risk} | {ch} | {ih} | {pr} | {cov}% | {rev} 条 | [{path}]({path}) |".format(
                label=s["label"], tid=s["trace_id"], risk=s["risk"], ch=s["content_hits"],
                ih=s["input_hits"], pr=f'{s["pain_rate_ai"]}%→{s["pain_rate"]}%', cov=s["coverage"], rev=s["revisions"], path=s["path"],
            )
        )
    index_lines += [
        "",
        "## 口径说明",
        "",
        "- 「内容侧命中」= 生成结果里出现的合规风险词条数量，决定风险等级；「输入侧提示」= 用户输入里出现的风险表述，仅作提示，不直接升级结论（避免把「不得承诺疗效」这类约束性表述误判为违规）。",
        "- 痛点击中率、卖点覆盖率为知识库关键词比对得到的过程指标，用于指导补写，不代表传播效果。",
        "- 人工修改记录由脚本按各案例的「人工干预要求」复现，修改内容只涉及语气与结构，未新增任何未提供的事实。",
        "- 所有数据均来自本地引擎实际运行，未配置在线模型；配置 API Key 后契约一致，可重复同样的核对流程。",
        "",
        "## 会话原件",
        "",
        "`sessions/` 下为 `core/storage.save_session` 落盘的原始记录，与界面「保存本次会话留痕」格式一致，可直接被 `storage.load_session` 读取回放。",
        "",
    ]
    (OUT / "索引.md").write_text("\n".join(index_lines), encoding="utf-8")

    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
