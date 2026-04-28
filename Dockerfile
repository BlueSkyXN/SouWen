# ===== 第一阶段：编译 microsocks SOCKS5 代理 =====
FROM alpine:latest AS microsocks-builder
# microsocks 是 C 语言编写的轻量级 SOCKS5 服务器，用于 WARP 内核模式
RUN apk add --no-cache build-base git && \
    git clone --depth 1 https://github.com/rofl0r/microsocks.git /src && \
    cd /src && make

# ===== 第二阶段：构建前端面板 =====
FROM node:22-slim AS panel-builder
# 使用 Vite 构建 SouWen 前端管理界面
ARG SKINS=all
WORKDIR /panel
COPY panel/package.json panel/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY panel/ ./
RUN VITE_SKINS=${SKINS} npm run build

# ===== 第三阶段：最终运行时镜像 =====
FROM python:3.11-slim

# 依赖版本配置
ARG WGCF_VERSION=2.2.30
ARG WIREPROXY_VERSION=1.1.2
# usque: MASQUE/QUIC 协议 WARP 客户端
ARG USQUE_VERSION=3.0.0
# 默认安装 web2pdf/SuperWeb2PDF 插件及其浏览器运行时
ARG WITH_WEB2PDF=1

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
    TZ=Asia/Shanghai

# ===== 系统依赖安装 =====
# 安装 WARP 相关工具：curl、wireguard-tools
# 安装时区数据、网络工具和 Playwright Chromium 运行库
# 以下为 Playwright Chromium 运行所需系统库（web2pdf/SuperWeb2PDF 插件需要）
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
RUN ARCH=$(dpkg --print-architecture) && \
    curl -fsSL -o /usr/local/bin/wgcf \
        "https://github.com/ViRb3/wgcf/releases/download/v${WGCF_VERSION}/wgcf_${WGCF_VERSION}_linux_${ARCH}" && \
    chmod +x /usr/local/bin/wgcf && \
    curl -fsSL "https://github.com/pufferffish/wireproxy/releases/download/v${WIREPROXY_VERSION}/wireproxy_linux_${ARCH}.tar.gz" \
        | tar xz -C /usr/local/bin/ wireproxy && \
    chmod +x /usr/local/bin/wireproxy && \
    curl -fsSL "https://github.com/Diniboy1123/usque/releases/download/v${USQUE_VERSION}/usque_${USQUE_VERSION}_linux_${ARCH}.zip" \
        | python -c "import io, sys, zipfile; zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())).extract('usque', '/usr/local/bin')" && \
    chmod +x /usr/local/bin/usque

# 复制预编译的 microsocks 可执行文件
COPY --from=microsocks-builder /src/microsocks /usr/local/bin/microsocks
RUN chmod +x /usr/local/bin/microsocks

WORKDIR /app

# ===== Python 依赖分层安装（优化 Docker 层缓存）=====
# 分两步安装以复用缓存：先装依赖（源码变更无需重新安装）
# 再装源码（仅源码变更时重新执行此层）

# 步骤 1：复制项目配置和版本信息，安装核心依赖
# 注：curl_cffi 位于 [tls] extras，用于专利爬虫/反爬指纹，必须同时安装
# 默认安装 web2pdf/SuperWeb2PDF 插件；可通过 --build-arg WITH_WEB2PDF=0 关闭
COPY pyproject.toml README.md LICENSE ./
COPY src/souwen/__init__.py ./src/souwen/__init__.py
RUN if [ "${WITH_WEB2PDF}" = "1" ]; then \
        pip install ".[server,tls,web2pdf]"; \
    else \
        pip install ".[server,tls]"; \
    fi

# 步骤 2：复制全部源码并重新安装（确保最新版本）
COPY src/ ./src/
# 复制前端面板的构建产物
COPY --from=panel-builder /panel/dist/index.html ./src/souwen/server/panel.html
RUN if [ "${WITH_WEB2PDF}" = "1" ]; then \
        pip install --no-deps ".[server,tls,web2pdf]"; \
    else \
        pip install --no-deps ".[server,tls]"; \
    fi \
    && python -c "import curl_cffi; print('curl_cffi OK')"

# 步骤 2.5：安装 Playwright Chromium（仅 web2pdf 插件需要）
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
