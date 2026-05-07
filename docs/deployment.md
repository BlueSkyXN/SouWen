# 部署

本文记录仓库内可直接复用的部署方式。更多 Hugging Face Space 细节见
[hf-space-cd.md](./hf-space-cd.md)，WARP 细节见
[warp-solutions.md](./warp-solutions.md)。

## Docker

```bash
docker build -t souwen .
docker run -p 8000:8000 \
  -e SOUWEN_ADMIN_PASSWORD=change-me \
  -e SOUWEN_USER_PASSWORD=change-me-user \
  -v ~/.config/souwen:/app/data \
  souwen
```

启动后检查：

```bash
curl http://localhost:8000/health
curl -H "Authorization: Bearer change-me-user" \
  http://localhost:8000/api/v1/sources
```

## 本地服务

```bash
pip install -e ".[server,tls,web,scraper]"
SOUWEN_ADMIN_PASSWORD=change-me souwen serve --host 0.0.0.0 --port 8000
```

## Hugging Face Spaces

仓库的 `cloud/hfs/` 保存 Space 部署资源。部署前先本地跑：

```bash
PYTHONPATH=src SOUWEN_PLUGIN_AUTOLOAD=0 \
  python3 scripts/ci/run_profile.py --profile server --profile minimal
```

部署后按 [hf-space-cd.md](./hf-space-cd.md) 中的只读状态端点做回读，再决定是否执行
外部 smoke。

## 运行时保护

- 生产环境设置 `SOUWEN_ADMIN_PASSWORD`；
- 需要开放搜索时设置 `SOUWEN_USER_PASSWORD`，或明确启用 `SOUWEN_GUEST_ENABLED=true`；
- 反向代理后方设置 `SOUWEN_TRUSTED_PROXIES`；
- 需要关闭 OpenAPI 页面时设置 `SOUWEN_EXPOSE_DOCS=false`；
- 高风险网页源建议配置 WARP 或显式代理。
