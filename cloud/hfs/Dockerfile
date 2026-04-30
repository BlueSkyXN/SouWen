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

FROM python:3.11-slim

ARG SOUWEN_REPO=https://github.com/BlueSkyXN/SouWen.git
ARG SOUWEN_REF=main
ARG WGCF_VERSION=2.2.30
ARG WIREPROXY_VERSION=1.1.2
# 默认安装 web2pdf/SuperWeb2PDF 插件及其浏览器运行时
ARG WITH_WEB2PDF=0

ENV PORT=49265 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

# 安装基础工具和 Playwright Chromium 运行库（web2pdf/SuperWeb2PDF 插件需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl tzdata \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libwayland-client0 \
    && cp /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 预装 WARP 组件 (wireproxy 用户态 WireGuard + wgcf 注册工具)
RUN ARCH=$(dpkg --print-architecture) && \
    curl -fsSL -o /usr/local/bin/wgcf \
        "https://github.com/ViRb3/wgcf/releases/download/v${WGCF_VERSION}/wgcf_${WGCF_VERSION}_linux_${ARCH}" && \
    chmod +x /usr/local/bin/wgcf && \
    curl -fsSL "https://github.com/pufferffish/wireproxy/releases/download/v${WIREPROXY_VERSION}/wireproxy_linux_${ARCH}.tar.gz" \
        | tar xz -C /usr/local/bin/ wireproxy && \
    chmod +x /usr/local/bin/wireproxy

WORKDIR /app

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

# 安装 Playwright Chromium（仅 web2pdf 插件需要）
RUN if [ "${WITH_WEB2PDF}" = "1" ]; then \
        playwright install chromium \
        && echo "✅ Playwright Chromium installed"; \
    fi

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN cp scripts/warp-init.sh /usr/local/bin/warp-init.sh 2>/dev/null || true
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    ([ -f /usr/local/bin/warp-init.sh ] && chmod +x /usr/local/bin/warp-init.sh || true)

RUN mkdir -p /app/data

EXPOSE 49265

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
