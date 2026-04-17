#!/bin/sh
# 用途：Docker 容器启动入口脚本
# 负责初始化环境、检查依赖、启动 SouWen API 服务
set -e

PORT="${PORT:-49265}"

# ===== 启动日志与环境信息 =====
echo "===== Application Startup at $(date '+%Y-%m-%d %H:%M:%S') ====="
echo ""
echo "=========================================="
echo "  SouWen 搜文 — Docker"
echo "=========================================="
echo "  PORT:     ${PORT}"
echo "  PYTHON:   $(python --version 2>&1)"
echo "  SOUWEN:   $(python -c 'import souwen; print(souwen.__version__)' 2>/dev/null || echo 'unknown')"
echo "=========================================="

# ===== WARP 代理初始化 =====
# 在所有 Python 代码之前执行，建立网络代理（如启用）
if [ "${WARP_ENABLED:-0}" = "1" ] && [ -f /usr/local/bin/warp-init.sh ]; then
    . /usr/local/bin/warp-init.sh
fi

# ===== 配置注入 =====
# 支持通过 SOUWEN_CONFIG_B64 环境变量注入 Base64 编码的配置文件
if [ -n "${SOUWEN_CONFIG_B64}" ]; then
    printf '%s' "${SOUWEN_CONFIG_B64}" | base64 -d > /app/souwen.yaml
    chmod 600 /app/souwen.yaml
    echo "✅ 已从 SOUWEN_CONFIG_B64 写入 souwen.yaml"
fi

# ===== 依赖检查 =====
# 验证 FastAPI、Uvicorn、SouWen 等核心依赖是否正确安装
python -c "
import fastapi, uvicorn, souwen
from souwen.server.app import app
print('✅ 依赖检查通过')
"

# ===== 启动 Web 服务 =====
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
