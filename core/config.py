"""全局配置与环境变量加载。

安全约定（对标工程化避坑指南）：
- API Key 只从环境变量 / 本地 .env 读取，绝不写入前端代码或公开仓库；
- 未配置在线模型时，自动降级为本地离线兜底引擎，保证评审现场可独立跑通。
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------- 路径常量 ----------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DOCS_DIR = ROOT_DIR / "docs"


def _resolve_session_dir() -> Path:
    """选择可写的会话目录。

    优先仓库内 ``data/sessions``；在只读文件系统的云托管环境下回退到
    ``/tmp`` 下的临时目录，避免启动期 ``mkdir`` / 写文件直接崩溃。
    """
    candidates = [DATA_DIR / "sessions", Path("/tmp") / "qilu_sessions"]
    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return directory
        except OSError:
            continue
    return candidates[-1]


SESSION_DIR = _resolve_session_dir()

# ---------- 应用元信息 ----------
APP_NAME = "齐鲁智传 · 山东本土文化 AI 传播智能工作台"
APP_SUBTITLE = "面向县域文旅 / 非遗老字号 / 助农农产品的多平台内容生产、合规校验与人机协作留痕工具"
ORG_NAME = "2026 山东省首届大学生 AI 大模型创新传播大赛 · 赛道三（AI 传播工具创新赛道）"

# 提示词版本号（与 prompts.PROMPT_VERSION 保持一致，便于技术文档佐证）
PROMPT_VERSION = "v1.3.0"


def _load_dotenv() -> None:
    """轻量 .env 解析（避免额外依赖 python-dotenv）。

    仅在环境变量尚未设置时写入 os.environ，不覆盖系统已注入的变量。
    """
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


# ---------- 大模型服务配置 ----------
LLM_ENABLED = _as_bool(os.environ.get("LLM_ENABLED")) and bool(os.environ.get("LLM_API_KEY"))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "20"))


def llm_config_summary() -> dict:
    """返回脱敏后的模型配置概览（不回显密钥），用于界面与技术文档展示。"""
    return {
        "enabled": LLM_ENABLED,
        "provider": "在线大模型（OpenAI 兼容接口）" if LLM_ENABLED else "本地离线兜底引擎",
        "model": LLM_MODEL if LLM_ENABLED else "rule-based local generator",
        "base_url": LLM_BASE_URL if LLM_ENABLED else "offline",
        "key_masked": "***" if LLM_API_KEY else "未配置",
    }
