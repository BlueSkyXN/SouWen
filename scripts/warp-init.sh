#!/bin/sh
# ============================================================
#  SouWen WARP 初始化脚本
#  使用 wireproxy (用户态 WireGuard → SOCKS5) 实现 Cloudflare WARP
#  无需 NET_ADMIN / TUN 设备，兼容所有平台 (HFS/ModelScope/自建)
#
#  环境变量:
#    WARP_ENABLED=1          启用 WARP (默认关闭)
#    WARP_CONFIG_B64          Base64 编码的 wireproxy 配置 (推荐)
#    WARP_ENDPOINT            自定义 WARP Endpoint (如 162.159.192.1:4500)
#    WARP_SOCKS_PORT          SOCKS5 监听端口 (默认 1080)
#    GH_PROXY                 GitHub 下载代理前缀
#
#  用法: 在 entrypoint.sh 中 source 本脚本:
#    . /usr/local/bin/warp-init.sh
# ============================================================

_warp_convert_config() {
    # 将 wgcf 生成的 WireGuard 配置转换为 wireproxy 格式
    SRC="$1"
    DST="$2"
    SOCKS_PORT="${WARP_SOCKS_PORT:-1080}"

    PRIVATE_KEY=$(grep '^PrivateKey' "$SRC" | sed 's/^PrivateKey[[:space:]]*=[[:space:]]*//')
    IPV4_ADDR=$(grep '^Address' "$SRC" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]+' | head -1)
    PUBLIC_KEY=$(grep '^PublicKey' "$SRC" | sed 's/^PublicKey[[:space:]]*=[[:space:]]*//')
    ENDPOINT=$(grep '^Endpoint' "$SRC" | sed 's/^Endpoint[[:space:]]*=[[:space:]]*//')

    cat > "$DST" << WIREPROXY_EOF
[Interface]
PrivateKey = ${PRIVATE_KEY}
Address = ${IPV4_ADDR}

[Peer]
PublicKey = ${PUBLIC_KEY}
AllowedIPs = 0.0.0.0/0
Endpoint = ${ENDPOINT}
PersistentKeepalive = 15

[Socks5]
BindAddress = 127.0.0.1:${SOCKS_PORT}
WIREPROXY_EOF
}

warp_init() {
    if [ "${WARP_ENABLED:-0}" != "1" ]; then
        return 0
    fi

    WARP_SOCKS_PORT="${WARP_SOCKS_PORT:-1080}"
    WIREPROXY_CONF="/tmp/wireproxy.conf"

    echo "==> [WARP] 初始化 Cloudflare WARP 代理..."

    # ---- 第一步: 获取 wireproxy 配置 ----
    if [ -n "${WARP_CONFIG_B64:-}" ]; then
        # 优先使用用户提供的预生成配置
        printf '%s' "${WARP_CONFIG_B64}" | base64 -d > "$WIREPROXY_CONF"
        echo "==> [WARP] ✅ 从 WARP_CONFIG_B64 加载配置"

    elif [ -f "/app/data/wireproxy.conf" ]; then
        # 从持久化存储加载
        cp /app/data/wireproxy.conf "$WIREPROXY_CONF"
        echo "==> [WARP] ✅ 从持久化文件加载配置"

    else
        # 自动注册 WARP 账号
        echo "==> [WARP] 未检测到配置，正在自动注册 Cloudflare WARP..."

        if ! command -v wgcf >/dev/null 2>&1; then
            echo "==> [WARP] ❌ wgcf 未安装，跳过 WARP 初始化"
            return 1
        fi

        WGCF_DIR=$(mktemp -d)
        cd "$WGCF_DIR"

        if ! wgcf register --accept-tos 2>/dev/null; then
            echo "==> [WARP] ❌ WARP 注册失败（可能触发速率限制）"
            cd /app
            rm -rf "$WGCF_DIR"
            return 1
        fi

        if ! wgcf generate 2>/dev/null || [ ! -f wgcf-profile.conf ]; then
            echo "==> [WARP] ❌ 配置生成失败"
            cd /app
            rm -rf "$WGCF_DIR"
            return 1
        fi

        _warp_convert_config wgcf-profile.conf "$WIREPROXY_CONF"

        # 持久化配置 (如果 /app/data 可写)
        if [ -d /app/data ]; then
            cp "$WIREPROXY_CONF" /app/data/wireproxy.conf 2>/dev/null || true
            echo "==> [WARP] 配置已持久化到 /app/data/wireproxy.conf"
        fi

        # 阅后即焚: 清理注册凭据
        cd /app
        rm -rf "$WGCF_DIR"
        echo "==> [WARP] ✅ WARP 注册成功"
    fi

    # ---- 应用自定义 Endpoint ----
    if [ -n "${WARP_ENDPOINT:-}" ]; then
        sed -i "s|^Endpoint.*|Endpoint = ${WARP_ENDPOINT}|" "$WIREPROXY_CONF"
        echo "==> [WARP] 🔀 自定义 Endpoint: ${WARP_ENDPOINT}"
    fi

    # 确保 SOCKS5 端口正确
    sed -i "s|^BindAddress.*|BindAddress = 127.0.0.1:${WARP_SOCKS_PORT}|" "$WIREPROXY_CONF"

    # ---- 第二步: 启动 wireproxy ----
    if ! command -v wireproxy >/dev/null 2>&1; then
        echo "==> [WARP] ❌ wireproxy 未安装，跳过 WARP 初始化"
        return 1
    fi

    wireproxy -c "$WIREPROXY_CONF" &
    WIREPROXY_PID=$!
    echo "==> [WARP] wireproxy 已启动 (PID: ${WIREPROXY_PID})"

    # ---- 第三步: 验证代理 ----
    WARP_READY=0
    for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        if curl -s --socks5-hostname "127.0.0.1:${WARP_SOCKS_PORT}" \
               --max-time 5 https://1.1.1.1/cdn-cgi/trace 2>/dev/null | grep -q "warp="; then
            WARP_READY=1
            break
        fi
    done

    if [ "$WARP_READY" = "1" ]; then
        WARP_IP=$(curl -s --socks5-hostname "127.0.0.1:${WARP_SOCKS_PORT}" \
                      --max-time 5 https://1.1.1.1/cdn-cgi/trace 2>/dev/null | grep "ip=" || echo "ip=unknown")
        echo "==> [WARP] ✅ 代理就绪 (${WARP_IP})"
    else
        echo "==> [WARP] ⚠️ 代理验证超时（可能仍在建立连接，继续启动应用）"
    fi

    # ---- 第四步: 导出代理到 SouWen ----
    export SOUWEN_PROXY="socks5://127.0.0.1:${WARP_SOCKS_PORT}"
    echo "==> [WARP] SOUWEN_PROXY=${SOUWEN_PROXY}"
}

# 执行初始化
warp_init
