FROM node:22-slim AS panel-builder
ARG SOUWEN_REPO=https://github.com/BlueSkyXN/SouWen.git
ARG SOUWEN_REF=main
ARG SKINS=all
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN git clone --depth 1 --branch "${SOUWEN_REF}" "${SOUWEN_REPO}" .
WORKDIR /build/panel
RUN npm ci --ignore-scripts && VITE_SKINS=${SKINS} npm run build

FROM modelscope-registry.cn-beijing.cr.aliyuncs.com/modelscope-repo/python:3.10

ARG SOUWEN_REPO=https://github.com/BlueSkyXN/SouWen.git
ARG SOUWEN_REF=main
ARG WGCF_VERSION=2.2.30
ARG WIREPROXY_VERSION=1.1.2
ARG USQUE_VERSION=3.0.0
ARG GH_PROXY=""
# 默认安装 web2pdf/SuperWeb2PDF 插件及其浏览器运行时
ARG WITH_WEB2PDF=0
# 可选：指定 Playwright 浏览器下载镜像（国内环境可用）
ARG PLAYWRIGHT_DOWNLOAD_HOST=""

ENV PORT=7860 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

# 安装基础工具和 Playwright Chromium 运行库（web2pdf/SuperWeb2PDF 插件需要）
# 以下为 Playwright Chromium 运行所需系统库（web2pdf/SuperWeb2PDF 插件需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl tzdata \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libwayland-client0 \
    && cp /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/user/app

# 预装 WARP 组件 (wireproxy + wgcf + usque)
RUN ARCH=$(dpkg --print-architecture 2>/dev/null || (uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')) && \
    WGCF_URL="https://github.com/ViRb3/wgcf/releases/download/v${WGCF_VERSION}/wgcf_${WGCF_VERSION}_linux_${ARCH}" && \
    WP_URL="https://github.com/pufferffish/wireproxy/releases/download/v${WIREPROXY_VERSION}/wireproxy_linux_${ARCH}.tar.gz" && \
    USQUE_URL="https://github.com/Diniboy1123/usque/releases/download/v${USQUE_VERSION}/usque_${USQUE_VERSION}_linux_${ARCH}.zip" && \
    if [ -n "${GH_PROXY}" ]; then WGCF_URL="${GH_PROXY}/${WGCF_URL}"; WP_URL="${GH_PROXY}/${WP_URL}"; USQUE_URL="${GH_PROXY}/${USQUE_URL}"; fi && \
    curl -fsSL -o /usr/local/bin/wgcf "${WGCF_URL}" && \
    chmod +x /usr/local/bin/wgcf && \
    curl -fsSL "${WP_URL}" | tar xz -C /usr/local/bin/ wireproxy && \
    chmod +x /usr/local/bin/wireproxy && \
    curl -fsSL "${USQUE_URL}" \
        | python -c "import io, sys, zipfile; zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())).extract('usque', '/usr/local/bin')" && \
    chmod +x /usr/local/bin/usque

RUN git clone --depth 1 --branch "${SOUWEN_REF}" "${SOUWEN_REPO}" .

# 前端面板：从 panel-builder 阶段复制构建产物（必须在 pip install 之前，
# 否则 panel.html 不会被打包进 site-packages）
COPY --from=panel-builder /build/panel/dist/index.html ./src/souwen/server/panel.html

RUN if [ "${WITH_WEB2PDF}" = "1" ]; then \
        pip install ".[server,tls,web2pdf]"; \
    else \
        pip install ".[server,tls]"; \
    fi \
    && python -c "import curl_cffi; print('curl_cffi OK')"

# 安装 Playwright Chromium（仅 web2pdf 插件需要，国内环境可配置下载镜像）
RUN if [ "${WITH_WEB2PDF}" = "1" ]; then \
        if [ -n "${PLAYWRIGHT_DOWNLOAD_HOST}" ]; then \
            PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST}" playwright install chromium; \
        else \
            playwright install chromium; \
        fi \
        && echo "✅ Playwright Chromium installed"; \
    fi

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN cp scripts/warp-init.sh /usr/local/bin/warp-init.sh 2>/dev/null || true
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    ([ -f /usr/local/bin/warp-init.sh ] && chmod +x /usr/local/bin/warp-init.sh || true)

RUN mkdir -p /home/user/app/data

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
