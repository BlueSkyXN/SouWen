# ===== 第三阶段：最终运行时镜像 =====
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

# 依赖版本配置
ARG WGCF_VERSION=2.2.30
ARG WIREPROXY_VERSION=1.1.2
# usque: MASQUE/QUIC 协议 WARP 客户端
ARG USQUE_VERSION=3.0.0
ARG SOUWEN_SOURCE_SHA=""

# 环境变量配置
# WARP 代理环境变量
# WARP_ENABLED=1          启用 WARP
# WARP_MODE=auto          模式: auto|wireproxy|usque|external
# WARP_SOCKS_PORT=1080    SOCKS5 端口
# WARP_HTTP_PORT=0        HTTP 代理端口（0=不启用）
# WARP_ENDPOINT           自定义 Endpoint
# WARP_EXTERNAL_PROXY     外部代理地址（external 模式）
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SOUWEN_SOURCE_SHA_FILE=/app/runtime.source.sha \
    WARP_DATA_DIR=/app/data \
    WARP_RUNTIME_BIN_DIR=/app/data/bin \
    TZ=Asia/Shanghai

# ===== 系统依赖安装 =====
# 安装时区数据与基础工具（wireguard-tools/iptables 仅内核模式需要，已随模式裁剪删除）
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl tzdata \
    && cp /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# ===== WARP 组件预装 =====
# 预装所有 WARP 相关工具以支持代理功能
# - wgcf: Cloudflare WARP 配置生成工具
# - wireproxy: 用户态 WireGuard SOCKS5 代理
# - usque: MASQUE/QUIC 协议 WARP 客户端
COPY scripts/warp-checksums.txt /tmp/warp-checksums.txt
RUN set -eu; \
    ARCH="$(dpkg --print-architecture)"; \
    checksum() { awk -v tool="$1" -v version="$2" -v arch="${ARCH}" \
        '$1 == tool && $2 == version && $3 == "linux" && $4 == arch { print $5 }' \
        /tmp/warp-checksums.txt; }; \
    verify() { expected="$(checksum "$1" "$2")"; test -n "${expected}"; \
        printf '%s  %s\n' "${expected}" "$3" | sha256sum -c -; }; \
    curl -fsSL -o /tmp/wgcf \
        "https://github.com/ViRb3/wgcf/releases/download/v${WGCF_VERSION}/wgcf_${WGCF_VERSION}_linux_${ARCH}"; \
    verify wgcf "${WGCF_VERSION}" /tmp/wgcf; \
    install -m 0755 /tmp/wgcf /usr/local/bin/wgcf; \
    curl -fsSL -o /tmp/wireproxy.tar.gz \
        "https://github.com/pufferffish/wireproxy/releases/download/v${WIREPROXY_VERSION}/wireproxy_linux_${ARCH}.tar.gz"; \
    verify wireproxy "${WIREPROXY_VERSION}" /tmp/wireproxy.tar.gz; \
    tar xzf /tmp/wireproxy.tar.gz -C /usr/local/bin/ wireproxy; \
    chmod +x /usr/local/bin/wireproxy; \
    curl -fsSL -o /tmp/usque.zip \
        "https://github.com/Diniboy1123/usque/releases/download/v${USQUE_VERSION}/usque_${USQUE_VERSION}_linux_${ARCH}.zip"; \
    verify usque "${USQUE_VERSION}" /tmp/usque.zip; \
    python -c "import zipfile; zipfile.ZipFile('/tmp/usque.zip').extract('usque', '/usr/local/bin')"; \
    chmod +x /usr/local/bin/usque; \
    rm -f /tmp/wgcf /tmp/wireproxy.tar.gz /tmp/usque.zip /tmp/warp-checksums.txt

WORKDIR /app
LABEL org.opencontainers.image.revision="${SOUWEN_SOURCE_SHA}"

RUN if [ -n "${SOUWEN_SOURCE_SHA}" ]; then \
        printf '%s' "${SOUWEN_SOURCE_SHA}" | grep -Eq '^[0-9a-fA-F]{40}$' \
        && printf '%s\n' "${SOUWEN_SOURCE_SHA}" > /app/runtime.source.sha; \
    fi

# ===== Python 依赖分层安装（优化 Docker 层缓存）=====
# 分两步安装以复用缓存：先装依赖（源码变更无需重新安装）
# 再装源码（仅源码变更时重新执行此层）

# 步骤 1：复制项目配置和版本信息，安装 Server 运行面依赖
COPY pyproject.toml README.md LICENSE ./
COPY src/souwen/__init__.py ./src/souwen/__init__.py
RUN pip install ".[server,mcp,tls,web,robots,scraper,browser]"

# 步骤 2：复制全部源码并重新安装（确保最新版本）
COPY src/ ./src/
RUN pip install --no-deps ".[server,mcp,tls,web,robots,scraper,browser]" \
    && python -c "import curl_cffi; print('curl_cffi OK')"

# 步骤 2b：Playwright Chromium（browser 级出口；依赖系统库）
RUN playwright install --with-deps chromium \
    && python -c "import playwright; print('playwright OK')"

# 步骤 3：复制运行时所需的脚本和配置文件
COPY souwen.example.yaml ./
COPY scripts/census/queries.json /app/scripts/census/queries.json
COPY scripts/warp-init.sh /usr/local/bin/warp-init.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/warp-init.sh /usr/local/bin/entrypoint.sh

# ===== 数据卷和端口配置 =====
RUN mkdir -p /app/data

# 暴露默认 API 服务端口
EXPOSE 49265

# ===== 健康检查 =====
# 定期检测 API 服务是否正常运行
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:49265/healthz || exit 1

# ===== 启动入口 =====
ENTRYPOINT ["entrypoint.sh"]
