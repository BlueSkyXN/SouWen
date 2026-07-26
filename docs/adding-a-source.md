# 添加 Provider

Provider catalog 的 source of truth 是 `ProviderManifest`、`ManifestRegistry` 和
`ProviderManager`。新增 provider 时添加 manifest/spec、adapter 和 deterministic conformance
测试；不要向旧 `registry/sources/`、route handler、Panel 或 docs 维护并行清单。

manifest 应声明 id、capabilities、credential requirements、risk/default metadata 和运行时
adapter。随后运行：

```bash
PYTHONPATH=src python3 tools/gen_docs.py --write
PYTHONPATH=src python3 tools/gen_docs.py --check
```

公开使用者通过 `GET /api/v1/providers` 发现 provider；该 endpoint 不暴露配置值或 secret。
Search、LLM Search 和 Fetch 以 canonical request DTO 选择 provider，已退休的 `/sources` 和
`/search/*` 不应重新引入。
