FROM alpine:latest AS microsocks-builder
RUN apk add --no-cache build-base git && \
    git clone --depth 1 https://github.com/rofl0r/microsocks.git /src && \
    cd /src && make

FROM node:22-slim AS panel-builder
ARG SKINS=all
WORKDIR /panel
COPY panel/package.json panel/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY panel/ ./
RUN VITE_SKINS=${SKINS} npm run build

FROM python:3.11-slim

ARG WGCF_VERSION=2.2.30
ARG WIREPROXY_VERSION=1.1.2

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl tzdata wireguard-tools iptables iproute2 \
    && cp /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 预装全部 WARP 组件: wgcf(注册) + wireproxy(用户态) + microsocks(内核态)
RUN ARCH=$(dpkg --print-architecture) && \
    curl -fsSL -o /usr/local/bin/wgcf \
        "https://github.com/ViRb3/wgcf/releases/download/v${WGCF_VERSION}/wgcf_${WGCF_VERSION}_linux_${ARCH}" && \
    chmod +x /usr/local/bin/wgcf && \
    curl -fsSL "https://github.com/pufferffish/wireproxy/releases/download/v${WIREPROXY_VERSION}/wireproxy_linux_${ARCH}.tar.gz" \
        | tar xz -C /usr/local/bin/ wireproxy && \
    chmod +x /usr/local/bin/wireproxy

COPY --from=microsocks-builder /src/microsocks /usr/local/bin/microsocks
RUN chmod +x /usr/local/bin/microsocks

WORKDIR /app

# 先复制依赖声明，利用 Docker 层缓存（源码变更不会使此层失效）
COPY pyproject.toml README.md LICENSE ./
COPY src/souwen/__init__.py ./src/souwen/__init__.py
RUN pip install ".[server]"

# 再复制全部源码（仅源码变更时重新执行此层）
COPY src/ ./src/
COPY --from=panel-builder /panel/dist/index.html ./src/souwen/server/panel.html
RUN pip install --no-deps ".[server]" \
    && python -c "import curl_cffi; print('curl_cffi OK')"

# 复制剩余文件
COPY cli.py souwen.example.yaml ./
COPY scripts/warp-init.sh /usr/local/bin/warp-init.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/warp-init.sh /usr/local/bin/entrypoint.sh

RUN mkdir -p /app/data

EXPOSE 49265

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:49265/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
