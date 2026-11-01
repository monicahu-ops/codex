#!/bin/zsh
# 双击此文件即可启动工作记录本地服务。
set -e

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3。请先安装 Command Line Tools for Xcode。"
  read "?按回车键退出..."
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "正在创建本地运行环境..."
  python3 -m venv .venv
fi

if ! .venv/bin/python -c "import flask" >/dev/null 2>&1; then
  echo "正在安装应用依赖（首次启动需要联网）..."
  .venv/bin/pip install -r requirements.txt
fi

echo ""
echo "工作记录已启动，请在浏览器打开："
echo "http://127.0.0.1:5000"
echo ""
echo "保持此窗口打开即可运行；按 Control + C 可停止服务。"
open "http://127.0.0.1:5000"
exec .venv/bin/python app.py
