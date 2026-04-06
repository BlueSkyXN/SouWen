FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl tzdata \
    && cp /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖声明，利用 Docker 层缓存（源码变更不会使此层失效）
COPY pyproject.toml README.md LICENSE ./
COPY src/souwen/__init__.py ./src/souwen/__init__.py
RUN pip install ".[server]"

# 再复制全部源码（仅源码变更时重新执行此层）
COPY src/ ./src/
RUN pip install --no-deps ".[server]"

# 复制剩余文件
COPY cli.py souwen.example.yaml ./

RUN mkdir -p /app/data

EXPOSE 49265

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:49265/health || exit 1

CMD ["uvicorn", "souwen.server.app:app", \
     "--host", "0.0.0.0", \
     "--port", "49265", \
     "--workers", "1", \
     "--log-level", "info", \
     "--access-log", \
     "--timeout-keep-alive", "120"]
