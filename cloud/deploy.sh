#!/bin/bash
# SouWen 云平台部署脚本
# 将源码同步到 cloud/<target>/ 目录，使其包含构建所需的全部文件
#
# 用法：
#   ./cloud/deploy.sh hfs       # 同步到 cloud/hfs/
#   ./cloud/deploy.sh modelscope # 同步到 cloud/modelscope/
#   ./cloud/deploy.sh all        # 同步到所有平台

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

sync_target() {
    local target="$1"
    local target_dir="${SCRIPT_DIR}/${target}"

    if [ ! -d "$target_dir" ]; then
        echo "❌ 目标不存在: ${target_dir}"
        exit 1
    fi

    echo "📦 同步源码到 cloud/${target}/ ..."

    # 同步 src/
    rm -rf "${target_dir}/src"
    cp -r "${PROJECT_ROOT}/src" "${target_dir}/src"

    # 同步项目元文件
    cp "${PROJECT_ROOT}/pyproject.toml" "${target_dir}/pyproject.toml"
    cp "${PROJECT_ROOT}/LICENSE" "${target_dir}/LICENSE"

    # 清理 Python 缓存
    find "${target_dir}/src" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "${target_dir}/src" -name "*.pyc" -delete 2>/dev/null || true

    echo "✅ cloud/${target}/ 同步完成"
    echo "   文件列表："
    ls -la "${target_dir}/"
    echo ""
}

case "${1:-}" in
    hfs)
        sync_target "hfs"
        ;;
    modelscope)
        sync_target "modelscope"
        ;;
    all)
        sync_target "hfs"
        sync_target "modelscope"
        ;;
    *)
        echo "用法: $0 {hfs|modelscope|all}"
        echo ""
        echo "示例:"
        echo "  $0 hfs           # 同步到 HuggingFace Spaces"
        echo "  $0 modelscope    # 同步到 ModelScope 创空间"
        echo "  $0 all           # 同步全部"
        exit 1
        ;;
esac

echo "🎉 部署文件就绪，可推送到对应平台仓库"
