#!/bin/bash
# ============================================================
# Anima — 一键安装脚本
# 用法：curl -fsSL https://raw.githubusercontent.com/longnull-ck/animaclaw/main/install.sh | bash
# 或者：bash install.sh
# ============================================================

set -e

echo ""
echo "  🦾 Anima — 全能型 AI 员工 安装中..."
echo ""

# ── 检测 Python ──────────────────────────────────────────────
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
fi

if [ -z "$PYTHON" ]; then
    echo "  ❌ 未找到 Python！"
    echo ""
    echo "  请先安装 Python 3.11+："
    echo "    macOS:   brew install python"
    echo "    Ubuntu:  sudo apt install python3 python3-pip"
    echo "    Windows: https://www.python.org/downloads/"
    echo ""
    exit 1
fi

# 检查版本
PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]); then
    echo "  ❌ Python 版本太低：$PY_VERSION（需要 3.11+）"
    echo "  请升级 Python 后重试。"
    exit 1
fi

echo "  ✅ Python $PY_VERSION 已就绪"

# ── 克隆仓库（如果不在仓库目录内） ────────────────────────────
if [ ! -f "pyproject.toml" ]; then
    echo "  📥 下载 Anima..."
    if command -v git &>/dev/null; then
        git clone https://github.com/longnull-ck/animaclaw.git anima-workspace
        cd anima-workspace
    else
        echo "  ❌ 未找到 git，请先安装 git 或手动下载仓库"
        exit 1
    fi
fi

# ── 安装依赖 ─────────────────────────────────────────────────
echo "  📦 安装依赖..."
$PYTHON -m pip install -e ".[all]" --quiet 2>/dev/null || $PYTHON -m pip install -e ".[all]"

echo "  ✅ 依赖安装完成"

# ── 运行初始化引导 ───────────────────────────────────────────
echo ""
echo "  ─── 开始配置 ───"
echo ""
$PYTHON -m anima.cli init

echo ""
echo "  ✅ 配置完成，正在启动 Anima..."
echo ""

# ── 自动启动 ─────────────────────────────────────────────────
$PYTHON run.py start
