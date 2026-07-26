# Provider Catalog

`GET /api/v1/providers` 是 target-only v2 的公开 Provider Catalog。它安全投影
`ProviderManifest` catalog、`ManifestRegistry` 与 `ProviderManager` 的当前 runtime 状态；
不是旧 source-list endpoint 的 alias，也不回显凭据或管理配置。

每个条目至少包含 provider id、capabilities、availability、reason、缺失配置字段和
provenance。调用方应按 capability 选择候选项，并把 `unavailable` 当作本地配置或 runtime
状态，不把它解释为上游实时可达性证明。

完整 provider 表由 `tools/gen_docs.py` 从 manifest registry 生成到
[data-sources.md](./data-sources.md)。
