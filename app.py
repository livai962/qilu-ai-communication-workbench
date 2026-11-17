"""齐鲁智传 · 山东本土文化 AI 传播智能工作台 —— Streamlit 主入口。

运行方式：
    streamlit run app.py

界面分区（对标备赛方案 4.1 左右分栏）：
- 左侧 30%：结构化输入面板（场景 / 要素 / 平台 / 风格 / 约束）；
- 右侧 70%：Tab 工作台（文案编辑 / 分镜配图 / 合规校验与协作留痕）；
- 底部固定操作栏：生成、合规校验、合规润色、多格式导出。
"""

from __future__ import annotations

import copy
import json

import pandas as pd
import streamlit as st

from core import (
    audience,
    compliance,
    config,
    diff,
    exporter,
    generator,
    knowledge,
    prompts,
    storage,
)

# ---------------------------------------------------------------------------
# 页面基础配置
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=config.APP_NAME,
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _default_inputs() -> dict:
    return {
        "scenario": knowledge.SCENARIOS[0],
        "project_name": "",
        "selling_points": "",
        "target_audience": "",
        "pain_points": "",
        "platforms": ["小红书"],
        "style": 0.5,
        "length": "中等",
        "constraints": "",
    }


def _init_state() -> None:
    if "inputs" not in st.session_state:
        st.session_state.inputs = _default_inputs()
    for key, default in [
        ("ai_content", None),
        ("final_content", None),
        ("baseline", None),
        ("revisions", []),
        ("polish_logs", []),
        ("compliance", None),
        ("audience", None),
        ("meta", None),
        ("generated", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


_init_state()


# ---------------------------------------------------------------------------
# 内容快照与留痕辅助
# ---------------------------------------------------------------------------
def _flat(content: dict) -> dict:
    """把可编辑内容压成 {字段名: 文本}，用于版本比对。"""
    if not content:
        return {}
    flat = {
        "标题": content.get("headline", ""),
        "主推正文": content.get("body", ""),
    }
    for plat, copy_text in (content.get("platform_copy") or {}).items():
        flat[f"{plat}文案"] = copy_text
    flat["分镜脚本"] = json.dumps(content.get("storyboard", []), ensure_ascii=False)
    flat["配图提示词"] = "\n".join(content.get("image_prompts", []) or [])
    return flat


def _persist() -> None:
    """把当前会话状态落盘为留痕记录。"""
    if not st.session_state.meta:
        return
    record = {
        "trace_id": st.session_state.meta["trace_id"],
        "created_at": st.session_state.meta["created_at"],
        "inputs": st.session_state.inputs,
        "prompt_version": st.session_state.meta["prompt_version"],
        "engine": st.session_state.meta["engine"],
        "engine_note": st.session_state.meta.get("engine_note", ""),
        "ai_content": st.session_state.ai_content,
        "final_content": st.session_state.final_content,
        "revisions": st.session_state.revisions,
        "polish_logs": st.session_state.polish_logs,
        "compliance": st.session_state.compliance,
        "audience": st.session_state.audience,
    }
    storage.save_session(record)


def _refresh_analysis() -> None:
    st.session_state.compliance = compliance.scan_all(
        st.session_state.final_content, st.session_state.inputs
    )
    st.session_state.audience = audience.analyze(st.session_state.final_content, st.session_state.inputs)


def _commit_edits(action: str = "人工修订") -> int:
    """比对当前工作稿与已提交基线，记录发生变化的字段，返回修改条数。"""
    current = _flat(st.session_state.final_content)
    before = _flat(st.session_state.baseline)
    count = 0
    for field, after in current.items():
        old = before.get(field, "")
        if after != old:
            st.session_state.revisions.append(
                diff.make_revision_record(field, old, after, action)
            )
            count += 1
    st.session_state.baseline = copy.deepcopy(st.session_state.final_content)
    _refresh_analysis()
    _persist()
    return count


# ---------------------------------------------------------------------------
# 顶部 Banner
# ---------------------------------------------------------------------------
st.title("🧭 " + config.APP_NAME)
st.caption(config.APP_SUBTITLE)
st.caption(config.ORG_NAME)

cfg = config.llm_config_summary()
meta_cols = st.columns(4)
meta_cols[0].markdown(f"**生成引擎**：{cfg['provider']}")
meta_cols[1].markdown(f"**模型**：{cfg['model']}")
meta_cols[2].markdown(f"**提示词版本**：{prompts.PROMPT_VERSION}")
meta_cols[3].markdown(f"**密钥状态**：{cfg['key_masked']}")

st.divider()

# ---------------------------------------------------------------------------
# 左侧：结构化输入面板
# ---------------------------------------------------------------------------
left, right = st.columns([0.3, 0.7], gap="large")

with left:
    st.subheader("① 场景与要素定义")
    inputs = st.session_state.inputs

    scenario_index = (
        knowledge.SCENARIOS.index(inputs["scenario"])
        if inputs["scenario"] in knowledge.SCENARIOS else 0
    )
    inputs["scenario"] = st.selectbox("传播场景", knowledge.SCENARIOS, index=scenario_index)

    inputs["project_name"] = st.text_input(
        "项目 / 产品名称 *", value=inputs["project_name"]
    )

    inputs["selling_points"] = st.text_area(
        "核心卖点与资料 *",
        height=120,
        value=inputs["selling_points"],
        placeholder="如：产地、工艺、特色、体验项目、规格、政策等，逐条描述",
    )

    inputs["target_audience"] = st.text_input(
        "目标受众 *", value=inputs["target_audience"],
        placeholder="如：年轻游客 / 亲子家庭 / 采购消费者",
    )

    inputs["pain_points"] = st.text_area("受众痛点", height=80, value=inputs["pain_points"])

    inputs["platforms"] = st.multiselect(
        "分发平台 *", knowledge.PLATFORMS, default=inputs["platforms"]
    )

    inputs["style"] = st.slider(
        "内容风格（政务专业 ↔ 年轻网感）", 0.0, 1.0, float(inputs["style"]), 0.05
    )

    length_index = knowledge.LENGTH_OPTIONS.index(inputs["length"]) if inputs["length"] in knowledge.LENGTH_OPTIONS else 1
    inputs["length"] = st.radio("篇幅", knowledge.LENGTH_OPTIONS, index=length_index, horizontal=True)

    inputs["constraints"] = st.text_area("附加约束 / 备注", height=70, value=inputs["constraints"])

    st.markdown("**标准案例一键加载**")
    ex_cols = st.columns(3)
    for i, ex in enumerate(knowledge.example_list()):
        if ex_cols[i].button(ex["label"].split(" · ")[-1], key=f"ex_{ex['id']}", use_container_width=True):
            st.session_state.inputs = copy.deepcopy(ex["inputs"])
            st.rerun()

    if st.button("🧪 测试空白输入容错", use_container_width=True):
        st.session_state.inputs = _default_inputs()
        st.rerun()

# ---------------------------------------------------------------------------
# 生成动作
# ---------------------------------------------------------------------------
generate_clicked = left.button("🚀 一键生成内容矩阵", type="primary", use_container_width=True)

if generate_clicked:
    errors = compliance.validate_inputs(st.session_state.inputs)
    if errors:
        for e in errors:
            st.warning(e)
    else:
        result = generator.generate(st.session_state.inputs)
        content = result["content"]
        meta = {
            "trace_id": exporter.new_trace_id(),
            "created_at": diff.now_ts(),
            "engine": result["engine"],
            "engine_note": result["engine_note"],
            "prompt_version": result["prompt_bundle"]["version"],
        }
        st.session_state.ai_content = content
        st.session_state.final_content = copy.deepcopy(content)
        st.session_state.baseline = copy.deepcopy(content)
        st.session_state.revisions = []
        st.session_state.polish_logs = []
        st.session_state.meta = meta
        st.session_state.generated = True
        _refresh_analysis()
        _persist()
        st.success(f"内容矩阵已生成。{meta['trace_id']}｜{result['engine_note']}")

# ---------------------------------------------------------------------------
# 右侧：结果工作台
# ---------------------------------------------------------------------------
with right:
    if not st.session_state.generated or not st.session_state.final_content:
        st.info("请在左侧填写结构化要素并点击「一键生成内容矩阵」；也可先加载标准案例体验完整流程。")
        with st.expander("💡 工具能做什么"):
            st.markdown(
                "- **结构化输入**：锁定文旅 / 非遗老字号 / 助农三类本土场景，而非通用聊天框；\n"
                "- **矩阵输出**：主推文案 + 分平台适配 + 话题标签 + 短视频分镜 + AI 配图提示词；\n"
                "- **合规预警**：分级识别极限词、夸大承诺、功效宣称、违规引流并给出依据；\n"
                "- **受众分析**：痛点击中率、卖点覆盖与情绪倾向评估；\n"
                "- **人机协作留痕**：在线编辑、Diff 版本比对、修改轨迹持久化、溯源 ID；\n"
                "- **多格式导出**：Markdown / Word / 纯文本，所见即所导。"
            )
        st.stop()

    content = st.session_state.final_content
    tab_edit, tab_story, tab_review = st.tabs(["📝 文案预览与编辑", "🎬 分镜脚本与配图", "🛡️ 合规校验与协作留痕"])

    # ---- Tab 1：文案编辑 ----
    with tab_edit:
        content["headline"] = st.text_input("主标题", value=content.get("headline", ""))
        content["body"] = st.text_area("主推正文", value=content.get("body", ""), height=260)

        st.markdown("**分平台适配文案**")
        for plat in knowledge.PLATFORMS:
            if plat in (content.get("platform_copy") or {}):
                content["platform_copy"][plat] = st.text_area(
                    f"{plat}",
                    value=content["platform_copy"].get(plat, ""),
                    height=160,
                    key=f"pc_{plat}",
                )

        col_a, col_b = st.columns(2)
        if col_a.button("💾 保存人工修改并留痕", use_container_width=True):
            n = _commit_edits("人工修订")
            st.success(f"已保存 {n} 处修改并写入协作日志。")
        if col_b.button("↩️ 还原为 AI 初稿", use_container_width=True):
            st.session_state.final_content = copy.deepcopy(st.session_state.ai_content)
            st.session_state.baseline = copy.deepcopy(st.session_state.ai_content)
            _refresh_analysis()
            _persist()
            st.info("已还原为 AI 原始初稿。")

    # ---- Tab 2：分镜与配图 ----
    with tab_story:
        st.markdown("**短视频分镜脚本**（可直接编辑单元格）")
        shots = content.get("storyboard", [])
        df_shots = pd.DataFrame(shots)
        edited_shots = st.data_editor(
            df_shots,
            column_config={
                "shot": "镜号",
                "visual": "画面",
                "voiceover": "口播",
                "duration": "时长",
                "subtitle": "字幕",
                "image_prompt": "配图提示词",
            },
            use_container_width=True,
            num_rows="dynamic",
            key="editor_shots",
        )
        content["storyboard"] = edited_shots.to_dict("records")

        st.markdown("**AI 配图提示词**（每行一条）")
        img_text = "\n".join(content.get("image_prompts", []) or [])
        img_edited = st.text_area("配图提示词", value=img_text, height=140, key="editor_img")
        content["image_prompts"] = [line.strip() for line in img_edited.splitlines() if line.strip()]

        if st.button("💾 保存分镜与配图修改", use_container_width=True):
            n = _commit_edits("人工修订（分镜/配图）")
            st.success(f"已保存 {n} 处修改并写入协作日志。")

    # ---- Tab 3：合规与留痕 ----
    with tab_review:
        comp = st.session_state.compliance
        aud = st.session_state.audience

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("合规结论", comp["risk_level"])
        c2.metric("高风险", comp["high"])
        c3.metric("中风险", comp["medium"])
        c4.metric("痛点击中率", f"{aud['painpoint_hit_rate']}%")

        st.markdown("**合规命中明细（内容侧）**")
        if not comp["findings"]:
            st.success("内容侧未命中合规风险词，仍建议人工复核事实与资质表述。")
        else:
            for f in comp["findings"]:
                level_color = {"高": "🔴", "中": "🟠", "低": "🟡"}.get(f["level"], "⚪")
                with st.expander(f"{level_color} [{f['level']}] {f['field']}：命中「{f['word']}」"):
                    st.write(f"**类别**：{f['category']}")
                    st.write(f"**依据**：{f['basis']}")
                    st.write(f"**上下文**：…{f['context']}…")
                    st.write(f"**修改建议**：{f['suggestion']}")

        input_findings = comp.get("input_findings", [])
        if input_findings:
            st.markdown("**输入侧风险提示（需求描述中需规避的表述）**")
            for f in input_findings:
                level_color = {"高": "🔴", "中": "🟠", "低": "🟡"}.get(f["level"], "⚪")
                with st.expander(f"{level_color} [{f['level']}] {f['field']}：命中「{f['word']}」"):
                    st.write(f"**类别**：{f['category']}")
                    st.write(f"**依据**：{f['basis']}")
                    st.write(f"**修改建议**：{f['suggestion']}")

        st.markdown("**受众分析**")
        st.write(aud["summary"])
        a1, a2 = st.columns(2)
        a1.write(f"卖点覆盖：{aud['selling_point_coverage']}%｜情绪倾向：{aud['sentiment']}")
        a2.write(f"已命中：{('、'.join(aud['matched']) or '—')}")
        if aud["missing"]:
            st.write(f"未覆盖：{('、'.join(aud['missing']))}")
        for sug in aud["suggestions"]:
            st.markdown(f"- {sug}")

        st.markdown("**合规润色**")
        if st.button("✨ 一键合规润色（人工确认后生效）", use_container_width=True):
            new_content, logs = compliance.polish_content(st.session_state.final_content)
            before_flat = _flat(st.session_state.final_content)
            st.session_state.final_content = new_content
            after_flat = _flat(new_content)
            for field, after in after_flat.items():
                old = before_flat.get(field, "")
                if after != old:
                    st.session_state.revisions.append(
                        diff.make_revision_record(field, old, after, "AI 合规润色（待人工确认）")
                    )
            st.session_state.polish_logs.extend(logs)
            st.session_state.baseline = copy.deepcopy(new_content)
            _refresh_analysis()
            _persist()
            st.success(f"合规润色完成，共替换 {sum(l['count'] for l in logs)} 处表述，请人工复核后定稿。")

        st.markdown("**版本比对（AI 初稿 ↔ 当前工作稿）**")
        if st.session_state.baseline:
            diff_fields = list(_flat(st.session_state.final_content).keys())
            field_sel = st.selectbox("选择比对字段", diff_fields)
            ops = diff.diff_ops(
                _flat(st.session_state.ai_content).get(field_sel, ""),
                _flat(st.session_state.final_content).get(field_sel, ""),
            )
            for op in ops:
                if op["op"] == "equal":
                    st.text(op["text"])
                elif op["op"] == "insert":
                    st.markdown(f":green[+ {op['text']}]")
                else:
                    st.markdown(f":red[- {op['text']}]")

        st.markdown("**协作修改日志（Diff Log）**")
        if not st.session_state.revisions:
            st.caption("暂无人工修改记录。在文案或分镜中修改并点击「保存留痕」后，将在此展示时间戳、字段与前后对比。")
        else:
            log_df = pd.DataFrame([
                {
                    "时间": r["timestamp"],
                    "操作人": r["author"],
                    "字段": r["field"],
                    "动作": r["action"],
                    "新增字数": r["added_chars"],
                    "删除字数": r["removed_chars"],
                }
                for r in st.session_state.revisions
            ])
            st.dataframe(log_df, use_container_width=True, hide_index=True)
            for r in reversed(st.session_state.revisions):
                with st.expander(f"{r['timestamp']}｜{r['field']}｜{r['action']}"):
                    st.write("**修改前**：")
                    st.text(r["before"] or "（空）")
                    st.write("**修改后**：")
                    st.text(r["after"] or "（空）")

        with st.expander("📌 提示词版本与迭代记录"):
            st.write(f"当前版本：{prompts.PROMPT_VERSION}")
            for ch in prompts.PROMPT_CHANGELOG:
                st.markdown(f"- **{ch['version']}**（{ch['date']}）：{ch['change']}")

# ---------------------------------------------------------------------------
# 底部：导出操作栏
# ---------------------------------------------------------------------------
if st.session_state.generated and st.session_state.final_content:
    st.divider()
    st.subheader("④ 多维导出与协作留痕")
    meta = st.session_state.meta
    md = exporter.render_markdown(
        st.session_state.final_content, meta, st.session_state.compliance, st.session_state.audience
    )
    docx_bytes = exporter.render_docx(
        st.session_state.final_content, meta, st.session_state.compliance, st.session_state.audience
    )
    plain = exporter.render_plain(st.session_state.final_content)

    d1, d2, d3, d4 = st.columns(4)
    d1.download_button("⬇️ 导出 Markdown", data=md, file_name=f"{meta['trace_id']}.md", mime="text/markdown", use_container_width=True)
    d2.download_button("⬇️ 导出 Word(.docx)", data=docx_bytes, file_name=f"{meta['trace_id']}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
    if d3.button("🧾 重新合规校验", use_container_width=True):
        _refresh_analysis()
        _persist()
        st.toast("合规与受众分析已刷新")
    if d4.button("💾 保存本次会话留痕", use_container_width=True):
        _persist()
        st.success(f"会话 {meta['trace_id']} 已保存至本地留痕记录。")

    with st.expander("📋 纯文本预览（可直接复制）"):
        st.code(plain, language="text")

    with st.expander("🗂️ 历史会话留痕记录"):
        sessions = storage.list_sessions()
        if not sessions:
            st.caption("暂无历史会话。")
        else:
            st.dataframe(pd.DataFrame(sessions), use_container_width=True, hide_index=True)
