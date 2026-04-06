FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
    && cp /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖声明，利用 Docker 层缓存
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install ".[server]"

# 复制剩余文件
COPY cli.py souwen.example.yaml ./

RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 49265

# 默认启动 API 服务，可通过 CMD 覆盖为 CLI 命令
# docker run souwen                        → 启动 API 服务
# docker run souwen python cli.py --help   → 使用 CLI
CMD ["uvicorn", "souwen.server.app:app", \
     "--host", "0.0.0.0", \
     "--port", "49265", \
     "--workers", "1", \
     "--log-level", "info", \
     "--access-log"]
