FROM node:22-slim AS panel-builder
ARG SOUWEN_REPO=https://github.com/BlueSkyXN/SouWen.git
ARG SOUWEN_REF=main
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN git clone --depth 1 --branch "${SOUWEN_REF}" "${SOUWEN_REPO}" .
WORKDIR /build/panel
RUN npm ci --ignore-scripts && VITE_SKINS=all npm run build

FROM python:3.11-slim

ARG SOUWEN_REPO=https://github.com/BlueSkyXN/SouWen.git
ARG SOUWEN_REF=main
ARG WGCF_VERSION=2.2.30
ARG WIREPROXY_VERSION=1.1.2

ENV PORT=49265 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl tzdata \
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

RUN git clone --depth 1 --branch "${SOUWEN_REF}" "${SOUWEN_REPO}" . \
    && pip install ".[server]" \
    && python -c "import curl_cffi; print('curl_cffi OK')"

COPY --from=panel-builder /build/panel/dist/index.html ./src/souwen/server/panel.html

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN cp scripts/warp-init.sh /usr/local/bin/warp-init.sh 2>/dev/null || true
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    ([ -f /usr/local/bin/warp-init.sh ] && chmod +x /usr/local/bin/warp-init.sh || true)

RUN mkdir -p /app/data

EXPOSE 49265

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
