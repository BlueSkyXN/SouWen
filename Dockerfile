# ===== 第一阶段：编译 microsocks SOCKS5 代理 =====
FROM alpine:latest@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b AS microsocks-builder
# microsocks 是 C 语言编写的轻量级 SOCKS5 服务器，用于 WARP 内核模式
ARG MICROSOCKS_REF=96bf8a87408c36951b73b7957687f42904e620f8
RUN apk add --no-cache build-base git && \
    git init /src && \
    git -C /src remote add origin https://github.com/rofl0r/microsocks.git && \
    git -C /src fetch --depth 1 origin "${MICROSOCKS_REF}" && \
    git -C /src checkout --detach FETCH_HEAD && \
    test "$(git -C /src rev-parse HEAD)" = "${MICROSOCKS_REF}" && \
    make -C /src

# ===== 第二阶段：构建前端面板 =====
FROM node:22-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS panel-builder
# 使用 Vite 构建 SouWen 前端管理界面
ARG SKINS=all
WORKDIR /panel
COPY panel/package.json panel/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY panel/ ./
RUN VITE_SKINS=${SKINS} npm run build

# ===== 第三阶段：最终运行时镜像 =====
FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

# 依赖版本配置
ARG WGCF_VERSION=2.2.30
ARG WIREPROXY_VERSION=1.1.2
# usque: MASQUE/QUIC 协议 WARP 客户端
ARG USQUE_VERSION=3.0.0
ARG SOUWEN_SOURCE_SHA=""
# 可选安装 web2pdf/SuperWeb2PDF 插件及其浏览器运行时
ARG WITH_WEB2PDF=0
# PyPI 暂无 superweb2pdf 发行，默认使用可解析的 GitHub archive；可用 build-arg 覆盖
ARG WEB2PDF_PACKAGE=https://github.com/BlueSkyXN/SuperWeb2PDF/archive/d1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip#sha256=f56a380aa3f06d169d3fcc723d5525779519afaff159b37e8a789e50b797c76b

# 环境变量配置
# WARP 代理环境变量
# WARP_ENABLED=1          启用 WARP
# WARP_MODE=auto          模式: auto|wireproxy|kernel|usque|warp-cli|external
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
# 安装 WARP 相关工具：curl、wireguard-tools
# 安装时区数据、网络工具和 Playwright Chromium 运行库
# 以下为 Playwright Chromium 运行所需系统库（SuperWeb2PDF 外部插件需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl tzdata wireguard-tools iptables iproute2 \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libwayland-client0 \
    && cp /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# ===== WARP 组件预装 =====
# 预装所有 WARP 相关工具以支持代理功能
# - wgcf: Cloudflare WARP 配置生成工具
# - wireproxy: 用户态 WireGuard SOCKS5 代理
# - usque: MASQUE/QUIC 协议 WARP 客户端
# - microsocks: 轻量级 SOCKS5 代理（内核模式）
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

# 复制预编译的 microsocks 可执行文件
COPY --from=microsocks-builder /src/microsocks /usr/local/bin/microsocks
RUN chmod +x /usr/local/bin/microsocks

WORKDIR /app
LABEL org.opencontainers.image.revision="${SOUWEN_SOURCE_SHA}"

RUN if [ -n "${SOUWEN_SOURCE_SHA}" ]; then \
        printf '%s' "${SOUWEN_SOURCE_SHA}" | grep -Eq '^[0-9a-fA-F]{40}$' \
        && printf '%s\n' "${SOUWEN_SOURCE_SHA}" > /app/runtime.source.sha; \
    fi

# ===== Python 依赖分层安装（优化 Docker 层缓存）=====
# 分两步安装以复用缓存：先装依赖（源码变更无需重新安装）
# 再装源码（仅源码变更时重新执行此层）

# 步骤 1：复制项目配置和版本信息，安装 pro/API 运行面依赖
# edition-pro 聚合 API server、MCP、TLS 指纹和 scraper 基础能力
# 可通过 --build-arg WITH_WEB2PDF=1 启用 web2pdf/SuperWeb2PDF 插件
COPY pyproject.toml README.md LICENSE ./
COPY src/souwen/__init__.py ./src/souwen/__init__.py
RUN if [ "${WITH_WEB2PDF}" = "1" ]; then \
        pip install ".[edition-pro]" "playwright>=1.40" "${WEB2PDF_PACKAGE}"; \
    else \
        pip install ".[edition-pro]"; \
    fi

# 步骤 2：复制全部源码并重新安装（确保最新版本）
COPY src/ ./src/
# 复制前端面板的构建产物
COPY --from=panel-builder /panel/dist/index.html ./src/souwen/server/panel.html
RUN pip install --no-deps ".[edition-pro]" \
    && python -c "import curl_cffi; print('curl_cffi OK')"

# 步骤 2.5：安装 Playwright Chromium（仅 SuperWeb2PDF 外部插件需要）
RUN if [ "${WITH_WEB2PDF}" = "1" ]; then \
        playwright install chromium \
        && echo "✅ Playwright Chromium installed"; \
    fi

# 步骤 3：复制运行时所需的脚本和配置文件
COPY cli.py souwen.example.yaml ./
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
    CMD curl -f http://localhost:49265/health || exit 1

# ===== 启动入口 =====
ENTRYPOINT ["entrypoint.sh"]
