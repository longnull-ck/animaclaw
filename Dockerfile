# ============================================================
# Anima — Multi-stage Docker Build
# Stage 1: 构建前端
# Stage 2: Python 运行时 + 前端静态产物
# ============================================================

# ── Stage 1: 前端构建 ─────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install

COPY web/ ./
RUN npm run build


# ── Stage 2: Python 运行时 ────────────────────────────────────
FROM python:3.12-slim AS runtime

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN useradd --create-home --shell /bin/bash anima
WORKDIR /app

# 安装 Python 依赖
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[all]"

# 复制应用代码
COPY anima/ ./anima/
COPY run.py ./

# 复制前端构建产物
COPY --from=frontend-builder /build/web/dist ./web/dist/

# 创建数据目录
RUN mkdir -p /app/data && chown -R anima:anima /app

# 切换到非 root 用户
USER anima

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ANIMA_DATA_DIR=/app/data

# 暴露端口
EXPOSE 3210

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:3210/api/status || exit 1

# 启动
CMD ["python", "run.py", "start"]
