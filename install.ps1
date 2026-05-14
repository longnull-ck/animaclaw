# ============================================================
# Anima — Windows 一键安装脚本 (PowerShell)
# 用法：irm https://raw.githubusercontent.com/longnull-ck/animaclaw/main/install.ps1 | iex
# 或者：.\install.ps1
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  Anima — 全能型 AI 员工 安装中..." -ForegroundColor Cyan
Write-Host ""

# ── 检测 Python ──────────────────────────────────────────────
$Python = $null

if (Get-Command python3 -ErrorAction SilentlyContinue) {
    $Python = "python3"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
}

if (-not $Python) {
    Write-Host "  [X] 未找到 Python！" -ForegroundColor Red
    Write-Host ""
    Write-Host "  请先安装 Python 3.11+："
    Write-Host "    下载地址: https://www.python.org/downloads/"
    Write-Host "    安装时请勾选 'Add Python to PATH'"
    Write-Host ""
    exit 1
}

# 检查版本
$PyVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$PyMajor = & $Python -c "import sys; print(sys.version_info.major)"
$PyMinor = & $Python -c "import sys; print(sys.version_info.minor)"

if ([int]$PyMajor -lt 3 -or ([int]$PyMajor -eq 3 -and [int]$PyMinor -lt 11)) {
    Write-Host "  [X] Python 版本太低：$PyVersion（需要 3.11+）" -ForegroundColor Red
    Write-Host "  请升级 Python 后重试。"
    exit 1
}

Write-Host "  [OK] Python $PyVersion 已就绪" -ForegroundColor Green

# ── 克隆仓库（如果不在仓库目录内） ────────────────────────────
if (-not (Test-Path "pyproject.toml")) {
    Write-Host "  下载 Anima..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        git clone https://github.com/longnull-ck/animaclaw.git anima-workspace
        Set-Location anima-workspace
    } else {
        Write-Host "  [X] 未找到 git，请先安装 git 或手动下载仓库" -ForegroundColor Red
        Write-Host "    下载地址: https://git-scm.com/download/win"
        exit 1
    }
}

# ── 安装依赖 ─────────────────────────────────────────────────
Write-Host "  安装依赖..."
& $Python -m pip install -e ".[all]" --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install -e ".[all]"
}

Write-Host "  [OK] 依赖安装完成" -ForegroundColor Green

# ── 创建 .env 文件 ───────────────────────────────────────────
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "  [OK] 已创建 .env 文件（请编辑填入 API Key）" -ForegroundColor Green
    }
}

# ── 运行初始化引导 ───────────────────────────────────────────
Write-Host ""
Write-Host "  --- 开始配置 ---"
Write-Host ""
& $Python -m anima.cli init

Write-Host ""
Write-Host "  [OK] 配置完成，正在启动 Anima..." -ForegroundColor Green
Write-Host ""

# ── 自动启动 ─────────────────────────────────────────────────
& $Python run.py start
