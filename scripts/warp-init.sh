#!/bin/sh
# ============================================================
#  SouWen WARP 初始化脚本
#  用途：为容器环境自动配置和启动 Cloudflare WARP 代理
#
#  支持两种代理模式:
#    wireproxy — 用户态 WireGuard → SOCKS5 (默认, 全平台兼容)
#    kernel    — 内核 WireGuard + microsocks (需 NET_ADMIN, 高性能)
#
#  环境变量:
#    WARP_ENABLED=1          启用 WARP (默认关闭)
#    WARP_MODE=auto          模式: auto (默认,自动检测) | wireproxy | kernel
#    WARP_CONFIG_B64          Base64 编码的配置 (wireproxy格式 或 WireGuard格式)
#    WARP_ENDPOINT            自定义 WARP Endpoint (如 162.159.192.1:4500)
#    WARP_SOCKS_PORT          SOCKS5 监听端口 (默认 1080)
#    GH_PROXY                 GitHub 下载代理前缀
#
#  用法: 在 entrypoint.sh 中 source 本脚本:
#    . /usr/local/bin/warp-init.sh
# ============================================================

# 工具函数 ===== 配置格式转换 =====

_warp_convert_to_wireproxy() {
    # 将 wgcf 生成的 WireGuard 配置转换为 wireproxy 格式
    # wireproxy 是用户态 SOCKS5 代理，无需内核权限
    SRC="$1"
    DST="$2"
    SOCKS_PORT="${WARP_SOCKS_PORT:-1080}"

    # 从 WireGuard 配置中提取关键参数
    PRIVATE_KEY=$(grep '^PrivateKey' "$SRC" | sed 's/^PrivateKey[[:space:]]*=[[:space:]]*//')
    IPV4_ADDR=$(grep '^Address' "$SRC" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]+' | head -1)
    PUBLIC_KEY=$(grep '^PublicKey' "$SRC" | sed 's/^PublicKey[[:space:]]*=[[:space:]]*//')
    ENDPOINT=$(grep '^Endpoint' "$SRC" | sed 's/^Endpoint[[:space:]]*=[[:space:]]*//')

    # 生成 wireproxy 格式配置文件
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

_warp_patch_kernel_conf() {
    # 为内核 WireGuard 模式洗白/优化配置
    # 主要调整：纯 IPv4、去 DNS 防崩溃、心跳保活、删除兼容性问题
    WG_CONF="$1"

    # 提取纯 IPv4 地址（支持内核 WireGuard）
    IPV4_ADDR=$(grep '^Address' "$WG_CONF" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]+' | head -1)

    # 删除所有 Address / AllowedIPs / DNS (防止双栈崩溃)
    sed -i '/^Address/d' "$WG_CONF"
    sed -i '/^AllowedIPs/d' "$WG_CONF"
    sed -i '/^DNS.*/d' "$WG_CONF"

    # 重建纯 IPv4 规则（内核 WireGuard 兼容格式）
    if [ -n "$IPV4_ADDR" ]; then
        sed -i "/\[Interface\]/a Address = $IPV4_ADDR" "$WG_CONF"
    fi
    sed -i "/\[Peer\]/a AllowedIPs = 0.0.0.0\/0" "$WG_CONF"

    # 注入心跳保活（防连接断开）
    if ! grep -q "PersistentKeepalive" "$WG_CONF"; then
        sed -i '/\[Peer\]/a PersistentKeepalive = 15' "$WG_CONF"
    else
        sed -i 's/PersistentKeepalive.*/PersistentKeepalive = 15/g' "$WG_CONF"
    fi

    # 删除 Alpine wg-quick 不兼容的路由标记
    if [ -f /usr/bin/wg-quick ]; then
        sed -i '/src_valid_mark/d' /usr/bin/wg-quick 2>/dev/null || true
    fi
}

_warp_register() {
    # 使用 wgcf 工具自动注册 WARP 并生成 WireGuard 配置文件
    # 此操作与 Cloudflare 服务通信，申请免费 WARP 账户和配置
    OUTPUT_CONF="$1"

    if ! command -v wgcf >/dev/null 2>&1; then
        echo "==> [WARP] ❌ wgcf 未安装，无法自动注册"
        return 1
    fi

    # 创建临时目录运行 wgcf（避免污染容器根目录）
    WGCF_DIR=$(mktemp -d)
    cd "$WGCF_DIR"

    # 执行 wgcf 注册（同意 ToS）
    if ! wgcf register --accept-tos 2>/dev/null; then
        echo "==> [WARP] ❌ WARP 注册失败（可能触发速率限制）"
        cd /app 2>/dev/null || cd /
        rm -rf "$WGCF_DIR"
        return 1
    fi

    # 生成配置文件
    if ! wgcf generate 2>/dev/null || [ ! -f wgcf-profile.conf ]; then
        echo "==> [WARP] ❌ 配置生成失败"
        cd /app 2>/dev/null || cd /
        rm -rf "$WGCF_DIR"
        return 1
    fi

    # 复制配置到目标位置
    cp wgcf-profile.conf "$OUTPUT_CONF"

    # 清理临时文件
    cd /app 2>/dev/null || cd /
    rm -rf "$WGCF_DIR"
    echo "==> [WARP] ✅ WARP 注册成功"
}

# wireproxy 模式 ===== 用户态 SOCKS5 代理 =====

_warp_start_wireproxy() {
    # 启动 wireproxy 用户态 SOCKS5 代理
    # 特点：跨平台、无需内核权限、性能一般
    WIREPROXY_CONF="/tmp/wireproxy.conf"

    # 获取配置：环境变量 > 持久化文件 > 自动注册
    if [ -n "${WARP_CONFIG_B64:-}" ]; then
        printf '%s' "${WARP_CONFIG_B64}" | base64 -d > "$WIREPROXY_CONF"
        echo "==> [WARP] ✅ 从 WARP_CONFIG_B64 加载配置"
    elif [ -f "/app/data/wireproxy.conf" ]; then
        cp /app/data/wireproxy.conf "$WIREPROXY_CONF"
        echo "==> [WARP] ✅ 从持久化文件加载配置"
    else
        # 自动注册新配置
        RAW_CONF=$(mktemp)
        if ! _warp_register "$RAW_CONF"; then return 1; fi
        _warp_convert_to_wireproxy "$RAW_CONF" "$WIREPROXY_CONF"
        rm -f "$RAW_CONF"
        # 持久化配置到数据卷（下次容器启动时复用）
        if [ -d /app/data ]; then
            cp "$WIREPROXY_CONF" /app/data/wireproxy.conf 2>/dev/null || true
            echo "==> [WARP] 配置已持久化到 /app/data/wireproxy.conf"
        fi
    fi

    # 应用自定义 Endpoint（规避 ISP/QoS 限制）
    if [ -n "${WARP_ENDPOINT:-}" ]; then
        _escaped_ep=$(printf '%s\n' "${WARP_ENDPOINT}" | sed 's/\\/\\\\/g; s/[|&/]/\\&/g')
        sed -i "s|^Endpoint.*|Endpoint = ${_escaped_ep}|" "$WIREPROXY_CONF"
        echo "==> [WARP] 🔀 自定义 Endpoint: ${WARP_ENDPOINT}"
    fi
    sed -i "s|^BindAddress.*|BindAddress = 127.0.0.1:${WARP_SOCKS_PORT}|" "$WIREPROXY_CONF"

    # 检查 wireproxy 可执行文件
    if ! command -v wireproxy >/dev/null 2>&1; then
        echo "==> [WARP] ❌ wireproxy 未安装"
        return 1
    fi

    # 后台启动 wireproxy
    wireproxy -c "$WIREPROXY_CONF" &
    WIREPROXY_PID=$!
    echo "==> [WARP] wireproxy 已启动 (PID: ${WIREPROXY_PID})"
}

# kernel 模式 ===== 内核级 WireGuard 高性能代理 =====

_warp_start_kernel() {
    # 启动内核级 WireGuard + microsocks SOCKS5 组合
    # 特点：高性能、低延迟、需要 NET_ADMIN 权限和 /dev/net/tun 支持
    WG_CONF="/etc/wireguard/wg0.conf"
    mkdir -p /etc/wireguard

    # 获取配置：环境变量 > 持久化文件 > 自动注册
    if [ -n "${WARP_CONFIG_B64:-}" ]; then
        printf '%s' "${WARP_CONFIG_B64}" | base64 -d > "$WG_CONF"
        echo "==> [WARP] ✅ 从 WARP_CONFIG_B64 加载配置"
    elif [ -f "/app/data/wg0.conf" ]; then
        cp /app/data/wg0.conf "$WG_CONF"
        echo "==> [WARP] ✅ 从持久化文件加载配置"
    else
        # 自动注册新配置
        if ! _warp_register "$WG_CONF"; then return 1; fi
        # 持久化配置到数据卷
        if [ -d /app/data ]; then
            cp "$WG_CONF" /app/data/wg0.conf 2>/dev/null || true
        fi
    fi

    # 洗白配置为内核 WireGuard 兼容格式
    _warp_patch_kernel_conf "$WG_CONF"

    # 应用自定义 Endpoint
    if [ -n "${WARP_ENDPOINT:-}" ]; then
        _escaped_ep=$(printf '%s\n' "${WARP_ENDPOINT}" | sed 's/\\/\\\\/g; s/[|&/]/\\&/g')
        sed -i "s|^Endpoint.*|Endpoint = ${_escaped_ep}|" "$WG_CONF"
        echo "==> [WARP] 🔀 自定义 Endpoint: ${WARP_ENDPOINT}"
    fi

    # 检查依赖：wg-quick（内核 WireGuard 管理）和 microsocks（SOCKS5 代理）
    if ! command -v wg-quick >/dev/null 2>&1; then
        echo "==> [WARP] ❌ wireguard-tools 未安装 (需要 --build-arg WARP_KERNEL=1 构建)"
        return 1
    fi
    if ! command -v microsocks >/dev/null 2>&1; then
        echo "==> [WARP] ❌ microsocks 未安装"
        return 1
    fi

    # 启动内核网卡
    echo "==> [WARP] 正在启动 Linux 内核级 wg0 网卡..."
    wg-quick up wg0 2>/dev/null

    # 启动 microsocks SOCKS5 代理（监听本地端口）
    microsocks -i 127.0.0.1 -p "${WARP_SOCKS_PORT}" &
    MICROSOCKS_PID=$!
    echo "==> [WARP] microsocks 已启动 (PID: ${MICROSOCKS_PID})"
}

# 主入口 ===== 模式检测与初始化 =====

_warp_detect_mode() {
    # 自动检测最佳可用代理模式
    # 优先级：kernel（性能最优）> wireproxy（兼容性好）> none（不可用）
    if command -v wg-quick >/dev/null 2>&1 && \
       [ -e /dev/net/tun ] && \
       command -v microsocks >/dev/null 2>&1; then
        echo "kernel"
    elif command -v wireproxy >/dev/null 2>&1; then
        echo "wireproxy"
    else
        echo "none"
    fi
}

warp_init() {
    # 主初始化函数，负责启动 WARP 代理流程
    
    # 如果未启用 WARP，直接返回
    if [ "${WARP_ENABLED:-0}" != "1" ]; then
        return 0
    fi

    # 读取环境变量的默认值
    WARP_SOCKS_PORT="${WARP_SOCKS_PORT:-1080}"
    WARP_MODE="${WARP_MODE:-auto}"

    # 自动检测模式
    if [ "$WARP_MODE" = "auto" ]; then
        WARP_MODE=$(_warp_detect_mode)
        if [ "$WARP_MODE" = "none" ]; then
            echo "==> [WARP] ⚠️ 未检测到可用的 WARP 组件 (wireproxy/wg-quick)，跳过"
            return 0
        fi
        echo "==> [WARP] 自动检测模式: ${WARP_MODE}"
    fi

    echo "==> [WARP] 初始化 Cloudflare WARP 代理 (模式: ${WARP_MODE})"

    # 启动对应模式的代理
    case "$WARP_MODE" in
        wireproxy)
            _warp_start_wireproxy || { echo "==> [WARP] ⚠️ wireproxy 启动失败，继续无代理运行"; return 0; }
            ;;
        kernel)
            _warp_start_kernel || { echo "==> [WARP] ⚠️ 内核模式启动失败，继续无代理运行"; return 0; }
            ;;
        *)
            echo "==> [WARP] ❌ 未知模式: ${WARP_MODE} (支持: auto, wireproxy, kernel)"
            return 0
            ;;
    esac

    # 验证代理连接 ===== 可用性检测 =====
    WARP_READY=0
    for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        # 通过 curl 测试 SOCKS5 代理是否就绪（检测 WARP 标记）
        if curl -s --socks5-hostname "127.0.0.1:${WARP_SOCKS_PORT}" \
               --max-time 5 https://1.1.1.1/cdn-cgi/trace 2>/dev/null | grep -q "warp="; then
            WARP_READY=1
            break
        fi
    done

    # 输出代理状态
    if [ "$WARP_READY" = "1" ]; then
        WARP_IP=$(curl -s --socks5-hostname "127.0.0.1:${WARP_SOCKS_PORT}" \
                      --max-time 5 https://1.1.1.1/cdn-cgi/trace 2>/dev/null | grep "ip=" || echo "ip=unknown")
        echo "==> [WARP] ✅ 代理就绪 (${WARP_IP})"
        WARP_STATUS="enabled"
    else
        echo "==> [WARP] ⚠️ 代理验证超时（可能仍在建立连接，继续启动应用）"
        WARP_STATUS="enabled"
        WARP_IP="ip=pending"
    fi

    # 写入状态文件 ===== Python WARP 管理器读取 =====
    # 记录 WARP 代理的运行参数，供 Python 应用程序读取和管理
    WARP_STATE_FILE="/run/souwen-warp.json"
    _WARP_PID=""
    if [ "$WARP_MODE" = "wireproxy" ]; then
        _WARP_PID="${WIREPROXY_PID:-}"
    elif [ "$WARP_MODE" = "kernel" ]; then
        _WARP_PID="${MICROSOCKS_PID:-}"
    fi
    cat > "$WARP_STATE_FILE" << STATE_EOF
{"owner":"shell","mode":"${WARP_MODE}","status":"${WARP_STATUS}","socks_port":${WARP_SOCKS_PORT},"pid":${_WARP_PID:-0},"interface":"wg0","ip":"${WARP_IP#ip=}"}
STATE_EOF
    echo "==> [WARP] 状态已写入 ${WARP_STATE_FILE}"

    # 导出代理地址 ===== 供应用程序使用 =====
    # 设置 SOUWEN_PROXY 环境变量，应用程序可直接使用此代理
    export SOUWEN_PROXY="socks5://127.0.0.1:${WARP_SOCKS_PORT}"
    echo "==> [WARP] SOUWEN_PROXY=${SOUWEN_PROXY}"
}

# 执行初始化
warp_init
