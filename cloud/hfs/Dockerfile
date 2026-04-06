FROM python:3.11-slim

ARG SOUWEN_REPO=https://github.com/SkywalkerSpace/SouWen.git
ARG SOUWEN_REF=main

ENV PORT=49265 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates tzdata \
    && cp /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --depth 1 --branch "${SOUWEN_REF}" "${SOUWEN_REPO}" . \
    && pip install ".[server]"

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 49265

ENTRYPOINT ["entrypoint.sh"]
