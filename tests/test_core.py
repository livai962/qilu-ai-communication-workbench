"""核心模块离线自测：不依赖 Streamlit 与在线大模型。

运行：
    python -m pytest tests/test_core.py -v
或直接：
    python tests/test_core.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import audience, compliance, diff, exporter, generator, storage  # noqa: E402

SAMPLE_INPUTS = {
    "scenario": "县域文旅打卡",
    "project_name": "曲阜三孔景区",
    "selling_points": "孔庙古柏与大成殿；孔府大堂；孔林墓群；可穿汉服打卡",
    "target_audience": "年轻游客",
    "pain_points": "攻略千篇一律，怕踩雷，想找出片又有文化底蕴的路线",
    "platforms": ["小红书", "抖音"],
    "style": 0.75,
    "length": "中等",
    "constraints": "面向周末短途出行的大学生",
}


def test_validate_empty_inputs():
    errors = compliance.validate_inputs({})
    assert errors, "空白输入应返回校验提示"
    print("[ok] 空白输入容错校验")


def test_generate_local_contract():
    result = generator.generate(SAMPLE_INPUTS)
    content = result["content"]
    for key in ["headline", "body", "platform_copy", "tags", "selling_points", "storyboard", "image_prompts"]:
        assert key in content, f"缺少字段 {key}"
    assert set(content["platform_copy"].keys()) == {"小红书", "抖音"}
    assert len(content["storyboard"]) >= 3
    assert result["prompt_bundle"]["version"]
    print("[ok] 本地兜底生成契约完整")


def test_compliance_detects_risk():
    risky = {
        "headline": "全国第一最佳景区",
        "body": "包治百病的祖传秘方，加微信下单，百分百有效。",
        "platform_copy": {"抖音": "顶级体验，错过再等一年"},
        "tags": [],
        "storyboard": [],
    }
    report = compliance.scan_content(risky)
    assert report["high"] >= 1
    words = {f["word"] for f in report["findings"]}
    assert "最佳" in words or "全国第一" in words
    assert "包治百病" in words
    print("[ok] 合规风险分级与命中识别")


def test_polish_replaces_risky():
    text = "这是全国第一最佳的选择，包治百病。"
    polished, logs = compliance.polish_text(text)
    assert "最佳" not in polished
    assert logs
    print("[ok] 一键合规润色与替换记录")


def test_audience_analysis():
    result = generator.generate(SAMPLE_INPUTS)
    report = audience.analyze(result["content"], SAMPLE_INPUTS)
    assert 0 <= report["painpoint_hit_rate"] <= 100
    assert report["summary"]
    assert isinstance(report["suggestions"], list)
    print("[ok] 受众痛点与卖点覆盖分析")


def test_diff_and_revision():
    before = "欢迎来到曲阜三孔。"
    after = "欢迎来到曲阜三孔，建议穿汉服打卡。"
    summary = diff.diff_summary(before, after)
    assert summary["changed"] and summary["added_chars"] > 0
    rec = diff.make_revision_record("主推正文", before, after, "人工修订")
    assert rec["timestamp"] and rec["before"] and rec["after"]
    print("[ok] Diff 版本比对与留痕记录")


def test_exporter_and_storage():
    result = generator.generate(SAMPLE_INPUTS)
    trace_id = exporter.new_trace_id()
    meta = {
        "trace_id": trace_id,
        "created_at": diff.now_ts(),
        "engine": "local-fallback",
        "prompt_version": "v1.3.0",
        "engine_note": "离线测试",
    }
    comp = compliance.scan_content(result["content"])
    aud = audience.analyze(result["content"], SAMPLE_INPUTS)
    md = exporter.render_markdown(result["content"], meta, comp, aud)
    docx = exporter.render_docx(result["content"], meta, comp, aud)
    assert trace_id in md and "溯源" in md
    assert docx[:2] == b"PK"

    record = storage.build_record(SAMPLE_INPUTS, result["content"], meta)
    record["compliance"] = comp
    record["audience"] = aud
    storage.save_session(record)
    loaded = storage.load_session(trace_id)
    assert loaded and loaded["trace_id"] == trace_id
    assert loaded["ai_content"]["headline"]
    print("[ok] Markdown / Word 导出与会话持久化")


if __name__ == "__main__":
    test_validate_empty_inputs()
    test_generate_local_contract()
    test_compliance_detects_risk()
    test_polish_replaces_risky()
    test_audience_analysis()
    test_diff_and_revision()
    test_exporter_and_storage()
    print("\n全部核心自测通过 ✅")
