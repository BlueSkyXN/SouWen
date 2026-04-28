#!/bin/sh
set -e

PORT="${PORT:-49265}"

echo "===== Application Startup at $(date '+%Y-%m-%d %H:%M:%S') ====="
echo ""
echo "=========================================="
echo "  SouWen 搜文 — HuggingFace Spaces"
echo "=========================================="
echo "  PORT:     ${PORT}"
echo "  PYTHON:   $(python --version 2>&1)"
echo "  SOUWEN:   $(python -c 'import souwen; print(souwen.__version__)' 2>/dev/null || echo 'unknown')"
echo "=========================================="

# ----- Runtime bin 目录 (WARP 组件动态安装目录) -----
RUNTIME_BIN="${WARP_RUNTIME_BIN_DIR:-/app/data/bin}"
if [ -d "$RUNTIME_BIN" ]; then
    export PATH="${RUNTIME_BIN}:${PATH}"
fi

# ----- WARP 代理初始化 -----
# WARP_ENTRYPOINT_INIT=1 时在 entrypoint 同步初始化 (旧行为, 阻塞启动)
# WARP_ENTRYPOINT_INIT=0 (默认) 跳过, 由 Python WarpManager 后台异步启动
if [ "${WARP_ENABLED:-0}" = "1" ]; then
    if [ "${WARP_ENTRYPOINT_INIT:-0}" = "1" ] && [ -f /usr/local/bin/warp-init.sh ]; then
        echo "==> [WARP] entrypoint 同步初始化 (WARP_ENTRYPOINT_INIT=1)"
        . /usr/local/bin/warp-init.sh
    else
        echo "==> [WARP] 已启用, 将由 Python WarpManager 后台启动"
    fi
fi

# ----- 配置注入 -----
if [ -n "${SOUWEN_CONFIG_B64}" ]; then
    printf '%s' "${SOUWEN_CONFIG_B64}" | base64 -d > /app/souwen.yaml
    chmod 600 /app/souwen.yaml
    echo "✅ 已从 SOUWEN_CONFIG_B64 写入 souwen.yaml"
fi

# ----- 依赖检查 -----
python -c "
import fastapi, uvicorn, souwen
from souwen.server.app import app
print('✅ 依赖检查通过')
"

echo "=========================================="
echo "🚀 启动服务 → 0.0.0.0:${PORT}"
echo "=========================================="

# Ignore HUP so HFS load-balancer reconnects don't kill the server
trap '' HUP

exec uvicorn souwen.server.app:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers 1 \
    --log-level info \
    --access-log \
    --timeout-keep-alive 120
