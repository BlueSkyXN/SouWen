FROM modelscope-registry.cn-beijing.cr.aliyuncs.com/modelscope-repo/python:3.10

# 可通过 --build-arg 固定到特定 commit/tag 以获得可复现构建
ARG SOUWEN_REPO=https://github.com/SkywalkerSpace/SouWen.git
ARG SOUWEN_REF=main

ENV PORT=7860 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /home/user/app

RUN git clone --depth 1 --branch "${SOUWEN_REF}" "${SOUWEN_REPO}" . \
    && pip install ".[server]"

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

RUN mkdir -p /home/user/app/data

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
