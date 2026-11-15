#!/usr/bin/env bash
# 在容器里跑一个 hfs_image_check 模式，并保证失败也不丢报告。
#
# 顺序固定：先运行探针并保留其退出码 → 再把 JSON 报告 docker cp 出来 →
# 最后按 --keep-going 与否决定本步退出码。此前探针一失败，set -e 直接退出，
# docker cp 被跳过，随后 cleanup 又删掉容器——失败现场就没了。
#
# 用法: hfs_probe_step.sh <container> <report-name> [探针参数...]
#
# 环境变量:
#   REPORTS             报告输出目录（默认 hfs-image-reports）
#   GITHUB_STEP_SUMMARY 追加 Markdown 摘要（本地缺省写 /dev/null）
#   HFS_KEEP_GOING=1    不传播探针退出码（WARP 腿：先收报告，由分类器判定）

set -uo pipefail

container="${1:?container required}"
report_name="${2:?report name required}"
shift 2

summary="${GITHUB_STEP_SUMMARY:-/dev/null}"
report_dir="${REPORTS:-hfs-image-reports}"
status=0

if docker exec "$container" python -m scripts.hfs_image_check "$@" | tee -a "$summary"; then
    :
else
    status=$?
    echo "probe exited with status ${status}" | tee -a "$summary"
fi

mkdir -p "$report_dir"
if docker cp "$container:/tmp/report-${report_name}.json" "${report_dir}/${report_name}.json"; then
    :
else
    echo "::warning::could not copy /tmp/report-${report_name}.json from ${container}; the failure scene is only in the log" | tee -a "$summary" >&2
fi

if [ "${HFS_KEEP_GOING:-0}" = "1" ]; then
    echo "kept probe status ${status} for classification (HFS_KEEP_GOING=1)" | tee -a "$summary"
    exit 0
fi
exit "$status"
