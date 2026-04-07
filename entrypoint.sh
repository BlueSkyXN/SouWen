#!/bin/sh
set -e

PORT="${PORT:-49265}"

echo "===== Application Startup at $(date '+%Y-%m-%d %H:%M:%S') ====="
echo ""
echo "=========================================="
echo "  SouWen 搜文 — Docker"
echo "=========================================="
echo "  PORT:     ${PORT}"
echo "  PYTHON:   $(python --version 2>&1)"
echo "  SOUWEN:   $(python -c 'import souwen; print(souwen.__version__)' 2>/dev/null || echo 'unknown')"
echo "=========================================="

# ----- WARP 代理初始化 (在所有 Python 代码之前) -----
if [ "${WARP_ENABLED:-0}" = "1" ] && [ -f /usr/local/bin/warp-init.sh ]; then
    . /usr/local/bin/warp-init.sh
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

exec uvicorn souwen.server.app:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers 1 \
    --log-level info \
    --access-log \
    --timeout-keep-alive 120
