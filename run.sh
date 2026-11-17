#!/usr/bin/env bash
# 本地一键启动脚本（Plan B：离线环境可直接运行本地兜底引擎）
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.headless true --server.port 8501
