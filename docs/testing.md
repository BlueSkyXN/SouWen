# 测试策略

SouWen 将 deterministic pytest 与外部 runtime 证明分开。普通 pytest 不访问网络、浏览器、
真实 secret 或用户 HOME；它验证 canonical DTO、ProviderManifest/ManifestRegistry/ProviderManager、
auth、SSRF 和 target-only route contract。

常用本地检查：

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 tools/gen_docs.py --check
PYTHONPATH=src python3 tools/check_markdown_links.py
python3 -m ruff check src tests scripts
```

发布前可使用当前 CI 中保留的 server-contract 与 SDK contract 检查 OpenAPI、generated SDK、
probe、Provider Catalog 和 Admin fail-closed 行为。外部 provider/runtime 验证只在明确批准的
环境中执行，并将结构化结果作为证据；已删除的专用浏览器和 external-smoke workflows 不构成
当前产品或发布 contract。
