#!/bin/sh
# ============================================================
#  SouWen WARP 初始化脚本
#  用途：为容器环境自动配置和启动 Cloudflare WARP 代理
#
#  支持五种代理模式:
#    wireproxy — 用户态 WireGuard → SOCKS5 (默认, 全平台兼容)
#    usque     — MASQUE/QUIC 协议 (现代化方案, 支持 SOCKS5+HTTP)
#    external  — 外部代理容器 (零侵入, sidecar 架构)
#
#  环境变量:
#    WARP_ENABLED=1          启用 WARP (默认关闭)
#    WARP_MODE=auto          模式: auto (默认,自动检测) | wireproxy | usque | external
#    WARP_CONFIG_B64          Base64 编码的配置 (wireproxy格式 或 WireGuard格式)
#    WARP_ENDPOINT            自定义 WARP Endpoint (如 162.159.192.1:4500)
#    WARP_SOCKS_PORT          SOCKS5 监听端口 (默认 1080)
#    WARP_BIND_ADDRESS        代理绑定地址 (默认 127.0.0.1)
#    WARP_STARTUP_TIMEOUT     启动健康检查超时秒数 (默认 15)
#    WARP_DEVICE_NAME         usque 注册设备名
#    WARP_PROXY_USERNAME      代理认证用户名
#    WARP_PROXY_PASSWORD      代理认证密码
#    WARP_USQUE_CONFIG        usque 配置文件路径
#    WARP_USQUE_TRANSPORT     usque 传输: auto | quic | http2
#    WARP_HTTP_PORT           HTTP 代理端口 (usque, 默认不启用)
#    WARP_EXTERNAL_PROXY      外部代理地址 (external 模式)
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
    BIND_ADDRESS="${WARP_BIND_ADDRESS:-127.0.0.1}"

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
BindAddress = ${BIND_ADDRESS}:${SOCKS_PORT}
WIREPROXY_EOF
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
    WARP_BIND_ADDRESS="${WARP_BIND_ADDRESS:-127.0.0.1}"
    sed -i "s|^BindAddress.*|BindAddress = ${WARP_BIND_ADDRESS}:${WARP_SOCKS_PORT}|" "$WIREPROXY_CONF"

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

# usque 模式 ===== MASQUE/QUIC 协议代理 =====

_warp_start_usque() {
    # 启动 usque MASQUE/QUIC 代理
    # 特点：现代协议、跨平台、支持 SOCKS5+HTTP、无需内核权限
    USQUE_CONFIG="${WARP_USQUE_CONFIG:-/app/data/usque-config.json}"

    # 检查 usque 可执行文件
    if ! command -v usque >/dev/null 2>&1; then
        echo "==> [WARP] ❌ usque 未安装"
        return 1
    fi

    # 如果没有配置文件，尝试自动注册
    if [ ! -f "$USQUE_CONFIG" ]; then
        echo "==> [WARP] 正在注册 usque 账号..."
        USQUE_REGISTER_ARGS=""
        if [ -n "${WARP_DEVICE_NAME:-}" ]; then
            USQUE_REGISTER_ARGS="-n ${WARP_DEVICE_NAME}"
        fi
        if ! usque -c "$USQUE_CONFIG" register ${USQUE_REGISTER_ARGS} 2>/dev/null; then
            echo "==> [WARP] ❌ usque 注册失败（可能触发速率限制）"
            return 1
        fi
        echo "==> [WARP] ✅ usque 注册成功"
    fi

    # 启动 SOCKS5 代理
    WARP_BIND_ADDRESS="${WARP_BIND_ADDRESS:-127.0.0.1}"
    USQUE_GLOBAL_ARGS=""
    if [ "${WARP_USQUE_TRANSPORT:-auto}" = "http2" ]; then
        USQUE_GLOBAL_ARGS="--http2"
    fi
    USQUE_AUTH_ARGS=""
    if [ -n "${WARP_PROXY_USERNAME:-}" ] && [ -n "${WARP_PROXY_PASSWORD:-}" ]; then
        USQUE_AUTH_ARGS="-u ${WARP_PROXY_USERNAME} -w ${WARP_PROXY_PASSWORD}"
    fi
    usque -c "$USQUE_CONFIG" ${USQUE_GLOBAL_ARGS} socks --bind "${WARP_BIND_ADDRESS}" --port "${WARP_SOCKS_PORT}" ${USQUE_AUTH_ARGS} &
    USQUE_PID=$!
    echo "==> [WARP] usque SOCKS5 已启动 (PID: ${USQUE_PID})"

    # 如果配置了 HTTP 端口，额外启动 HTTP 代理
    WARP_HTTP_PORT="${WARP_HTTP_PORT:-0}"
    if [ "$WARP_HTTP_PORT" -gt 0 ] 2>/dev/null; then
        usque -c "$USQUE_CONFIG" ${USQUE_GLOBAL_ARGS} http-proxy --bind "${WARP_BIND_ADDRESS}" --port "${WARP_HTTP_PORT}" ${USQUE_AUTH_ARGS} &
        USQUE_HTTP_PID=$!
        echo "==> [WARP] usque HTTP 代理已启动 (PID: ${USQUE_HTTP_PID}, 端口: ${WARP_HTTP_PORT})"
    fi
}

# external 模式 ===== 外部代理容器 =====

_warp_start_external() {
    # 使用外部 WARP 代理容器
    # 特点：零侵入、独立容器、适合 sidecar 架构
    EXTERNAL_PROXY="${WARP_EXTERNAL_PROXY:-}"

    if [ -z "$EXTERNAL_PROXY" ]; then
        echo "==> [WARP] ❌ 未配置 WARP_EXTERNAL_PROXY"
        return 1
    fi

    echo "==> [WARP] 使用外部代理: ${EXTERNAL_PROXY}"
    # 外部模式不启动任何进程，仅设置代理地址
    export SOUWEN_PROXY="${EXTERNAL_PROXY}"
}

# 主入口 ===== 模式检测与初始化 =====

_warp_detect_mode() {
    # 自动检测最佳可用代理模式
    # 优先级：external(已配置) > usque > wireproxy > none
    local modes="external usque wireproxy"

    for mode in $modes; do
        case $mode in
            external)
                [ -n "${WARP_EXTERNAL_PROXY:-}" ] && echo "external" && return 0
                ;;
            usque)
                command -v usque >/dev/null 2>&1 && echo "usque" && return 0
                ;;
            wireproxy)
                command -v wireproxy >/dev/null 2>&1 && echo "wireproxy" && return 0
                ;;
        esac
    done
    echo "none"
}

_warp_mode_available() {
    case "$1" in
        external)
            [ -n "${WARP_EXTERNAL_PROXY:-}" ]
            ;;
        usque)
            command -v usque >/dev/null 2>&1
            ;;
        wireproxy)
            command -v wireproxy >/dev/null 2>&1
            ;;
        *)
            return 1
            ;;
    esac
}

_warp_start_mode() {
    case "$1" in
        wireproxy) _warp_start_wireproxy ;;
        usque) _warp_start_usque ;;
        external) _warp_start_external ;;
        *) return 1 ;;
    esac
}

_warp_stop_mode() {
    case "$1" in
        wireproxy)
            [ -n "${WIREPROXY_PID:-}" ] && kill "${WIREPROXY_PID}" 2>/dev/null || true
            ;;
        usque)
            [ -n "${USQUE_PID:-}" ] && kill "${USQUE_PID}" 2>/dev/null || true
            [ -n "${USQUE_HTTP_PID:-}" ] && kill "${USQUE_HTTP_PID}" 2>/dev/null || true
            ;;
    esac
}

_warp_verify_mode() {
    if [ "$1" = "external" ]; then
        WARP_READY=1
        WARP_STATUS="enabled"
        WARP_IP="ip=external"
        return 0
    fi

    WARP_READY=0
    _proxy_auth=""
    if [ -n "${WARP_PROXY_USERNAME:-}" ] && [ -n "${WARP_PROXY_PASSWORD:-}" ]; then
        _proxy_auth="${WARP_PROXY_USERNAME}:${WARP_PROXY_PASSWORD}@"
    fi
    for _i in $(seq 1 "${WARP_STARTUP_TIMEOUT:-15}"); do
        sleep 1
        if curl -s --socks5-hostname "${_proxy_auth}127.0.0.1:${WARP_SOCKS_PORT}" \
               --max-time 5 https://1.1.1.1/cdn-cgi/trace 2>/dev/null | grep -q "warp="; then
            WARP_READY=1
            break
        fi
    done

    if [ "$WARP_READY" = "1" ]; then
        WARP_IP=$(curl -s --socks5-hostname "${_proxy_auth}127.0.0.1:${WARP_SOCKS_PORT}" \
                      --max-time 5 https://1.1.1.1/cdn-cgi/trace 2>/dev/null | grep "ip=" || echo "ip=unknown")
        WARP_STATUS="enabled"
        return 0
    fi
    WARP_STATUS="enabled"
    WARP_IP="ip=pending"
    return 1
}

warp_init() {
    # 主初始化函数，负责启动 WARP 代理流程
    
    # 如果未启用 WARP，直接返回
    if [ "${WARP_ENABLED:-0}" != "1" ]; then
        return 0
    fi

    # 读取环境变量的默认值
    WARP_SOCKS_PORT="${WARP_SOCKS_PORT:-1080}"
    WARP_HTTP_PORT="${WARP_HTTP_PORT:-0}"
    WARP_BIND_ADDRESS="${WARP_BIND_ADDRESS:-127.0.0.1}"
    WARP_STARTUP_TIMEOUT="${WARP_STARTUP_TIMEOUT:-15}"
    WARP_MODE="${WARP_MODE:-auto}"

    WARP_AUTO_MODE=0
    if [ "$WARP_MODE" = "auto" ]; then
        WARP_AUTO_MODE=1
        if [ "$(_warp_detect_mode)" = "none" ]; then
            echo "==> [WARP] ⚠️ 未检测到可用的 WARP 组件 (wireproxy/wg-quick/usque)，跳过"
            return 0
        fi
    fi

    echo "==> [WARP] 初始化 Cloudflare WARP 代理 (模式: ${WARP_MODE})"

    if [ "$WARP_AUTO_MODE" = "1" ]; then
        WARP_STARTED=0
        for candidate in external usque wireproxy; do
            if ! _warp_mode_available "$candidate"; then
                continue
            fi
            echo "==> [WARP] auto 尝试模式: ${candidate}"
            if _warp_start_mode "$candidate"; then
                WARP_MODE="$candidate"
                if _warp_verify_mode "$candidate"; then
                    WARP_STARTED=1
                    break
                fi
                echo "==> [WARP] ⚠️ ${candidate} 验证失败，继续降级"
                _warp_stop_mode "$candidate"
            else
                echo "==> [WARP] ⚠️ ${candidate} 启动失败，继续降级"
            fi
        done
        if [ "$WARP_STARTED" != "1" ]; then
            echo "==> [WARP] ⚠️ auto 候选全部失败，继续无代理运行"
            return 0
        fi
        echo "==> [WARP] 自动选择模式: ${WARP_MODE}"
    else
        if ! _warp_mode_available "$WARP_MODE"; then
            echo "==> [WARP] ❌ 未知或不可用模式: ${WARP_MODE} (支持: auto, wireproxy, usque, external)"
            return 0
        fi
        _warp_start_mode "$WARP_MODE" || { echo "==> [WARP] ⚠️ ${WARP_MODE} 启动失败，继续无代理运行"; return 0; }
        if _warp_verify_mode "$WARP_MODE"; then
            :
        else
            echo "==> [WARP] ⚠️ 代理验证超时（可能仍在建立连接，继续启动应用）"
        fi
    fi

    if [ "${WARP_READY:-0}" = "1" ]; then
        echo "==> [WARP] ✅ 代理就绪 (${WARP_IP})"
    fi

    # 写入状态文件 ===== Python WARP 管理器读取 =====
    # 记录 WARP 代理的运行参数，供 Python 应用程序读取和管理
    WARP_STATE_FILE="/run/souwen-warp.json"
    _WARP_PID=""
    _WARP_PROTOCOL="wireguard"
    _WARP_PROXY_TYPE="socks5"
    if [ "$WARP_MODE" = "wireproxy" ]; then
        _WARP_PID="${WIREPROXY_PID:-}"
    elif [ "$WARP_MODE" = "usque" ]; then
        _WARP_PID="${USQUE_PID:-}"
        _WARP_PROTOCOL="masque"
        if [ "${WARP_HTTP_PORT:-0}" -gt 0 ] 2>/dev/null; then
            _WARP_PROXY_TYPE="both"
        fi
    elif [ "$WARP_MODE" = "external" ]; then
        _WARP_PID="0"
    fi
    cat > "$WARP_STATE_FILE" << STATE_EOF
{"owner":"shell","mode":"${WARP_MODE}","status":"${WARP_STATUS}","socks_port":${WARP_SOCKS_PORT},"http_port":${WARP_HTTP_PORT:-0},"pid":${_WARP_PID:-0},"interface":"wg0","ip":"${WARP_IP#ip=}","protocol":"${_WARP_PROTOCOL}","proxy_type":"${_WARP_PROXY_TYPE}"}
STATE_EOF
    echo "==> [WARP] 状态已写入 ${WARP_STATE_FILE}"

    # 导出代理地址 ===== 供应用程序使用 =====
    # 设置 SOUWEN_PROXY 环境变量，应用程序可直接使用此代理
    if [ "$WARP_MODE" != "external" ]; then
        if [ -n "${WARP_PROXY_USERNAME:-}" ] && [ -n "${WARP_PROXY_PASSWORD:-}" ]; then
            export SOUWEN_PROXY="socks5://${WARP_PROXY_USERNAME}:${WARP_PROXY_PASSWORD}@127.0.0.1:${WARP_SOCKS_PORT}"
        else
            export SOUWEN_PROXY="socks5://127.0.0.1:${WARP_SOCKS_PORT}"
        fi
    fi
    echo "==> [WARP] SOUWEN_PROXY=${SOUWEN_PROXY}"
}

# 执行初始化
warp_init
