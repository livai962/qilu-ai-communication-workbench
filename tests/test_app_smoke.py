"""Streamlit 脚本级冒烟测试（AppTest）：模拟加载案例 → 生成 → 校验 → 导出链路。"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"


def _click_button(at: AppTest, label: str):
    for btn in at.button:
        if label in btn.label:
            btn.click().run()
            return True
    raise AssertionError(f"未找到按钮：{label}")


def test_app_loads_and_generates():
    at = AppTest.from_file(str(APP), default_timeout=15)
    at.run()
    assert not at.exception, f"初始脚本异常：{at.exception}"

    # 加载“典型场景”案例
    _click_button(at, "典型场景")
    assert not at.exception

    # 一键生成
    _click_button(at, "一键生成内容矩阵")
    assert not at.exception, f"生成阶段异常：{at.exception}"

    # 生成后应出现结果 Tab 与指标
    assert len(at.tabs) == 3
    assert at.session_state["generated"] is True
    assert at.session_state.final_content is not None
    assert at.session_state.compliance is not None
    assert at.session_state.audience is not None

    # 保存人工修改并留痕
    _click_button(at, "保存人工修改并留痕")
    assert not at.exception

    # 导出按钮存在
    labels = [b.label for b in at.button] + [d.label for d in at.download_button]
    assert any("Markdown" in x for x in labels)
    assert any("Word" in x for x in labels)

    print("[ok] AppTest 冒烟：加载案例 → 生成 → 留痕 → 导出 链路正常")


def test_boundary_validation():
    at = AppTest.from_file(str(APP), default_timeout=15)
    at.run()
    _click_button(at, "测试空白输入容错")
    _click_button(at, "一键生成内容矩阵")
    assert not at.exception
    # 空白输入应出现 warning，而不是异常崩溃
    assert len(at.warning) >= 1
    print("[ok] 边界：空白输入触发友好容错提示")


if __name__ == "__main__":
    test_app_loads_and_generates()
    test_boundary_validation()
    print("\nAppTest 冒烟测试通过 ✅")
