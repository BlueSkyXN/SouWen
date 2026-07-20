ARG SOUWEN_REF=0000000000000000000000000000000000000000

FROM node:22-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS panel-builder
ARG SOUWEN_REPO=https://github.com/BlueSkyXN/SouWen.git
ARG SOUWEN_REF
ARG SKINS=all
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN git init . \
    && git remote add origin "${SOUWEN_REPO}" \
    && printf '%s' "${SOUWEN_REF}" | grep -Eq '^[0-9a-fA-F]{40}$' \
    && test "${SOUWEN_REF}" != "0000000000000000000000000000000000000000" \
    && git fetch --depth 1 origin "${SOUWEN_REF}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${SOUWEN_REF}"
WORKDIR /build/panel
RUN npm ci --ignore-scripts && VITE_SKINS=${SKINS} npm run build

FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

ARG SOUWEN_REPO=https://github.com/BlueSkyXN/SouWen.git
ARG SOUWEN_REF
ARG WGCF_VERSION=2.2.30
ARG WIREPROXY_VERSION=1.1.2
# 可选安装 web2pdf/SuperWeb2PDF 插件及其浏览器运行时
ARG WITH_WEB2PDF=0
# PyPI 暂无 superweb2pdf 发行，默认使用可解析的 GitHub archive；可用 build-arg 覆盖
ARG WEB2PDF_PACKAGE=https://github.com/BlueSkyXN/SuperWeb2PDF/archive/d1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip#sha256=f56a380aa3f06d169d3fcc723d5525779519afaff159b37e8a789e50b797c76b

ENV PORT=49265 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SOUWEN_SOURCE_SHA_FILE=/app/runtime.source.sha \
    WARP_DATA_DIR=/app/data \
    WARP_RUNTIME_BIN_DIR=/app/data/bin \
    TZ=Asia/Shanghai

# 安装基础工具和 Playwright Chromium 运行库（SuperWeb2PDF 外部插件需要）
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
COPY --from=panel-builder /build/scripts/warp-checksums.txt /tmp/warp-checksums.txt
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
    rm -f /tmp/wgcf /tmp/wireproxy.tar.gz /tmp/warp-checksums.txt

WORKDIR /app
LABEL org.opencontainers.image.revision="${SOUWEN_REF}"

RUN git init . \
    && git remote add origin "${SOUWEN_REPO}" \
    && printf '%s' "${SOUWEN_REF}" | grep -Eq '^[0-9a-fA-F]{40}$' \
    && test "${SOUWEN_REF}" != "0000000000000000000000000000000000000000" \
    && git fetch --depth 1 origin "${SOUWEN_REF}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${SOUWEN_REF}" \
    && git rev-parse HEAD > /app/runtime.source.sha

# 前端面板：从 panel-builder 阶段复制构建产物（必须在 pip install 之前，
# 否则 panel.html 不会被打包进 site-packages）
COPY --from=panel-builder /build/panel/dist/index.html ./src/souwen/server/panel.html

RUN if [ "${WITH_WEB2PDF}" = "1" ]; then \
        pip install ".[edition-pro]" "playwright>=1.40" "${WEB2PDF_PACKAGE}"; \
    else \
        pip install ".[edition-pro]"; \
    fi \
    && python -c "import curl_cffi; print('curl_cffi OK')"

# 安装 Playwright Chromium（仅 SuperWeb2PDF 外部插件需要）
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
