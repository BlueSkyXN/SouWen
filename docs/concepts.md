# 核心概念

SouWen 的公开数据面只有 `search`、`llm_search` 和 `fetch`。domain、provider 和
capability 是请求中的选择条件，不是额外的公开 endpoint。

Provider 的唯一事实来源是 `ProviderManifest` catalog；`ManifestRegistry` 负责加载和
校验 manifest，`ProviderManager` 负责在当前配置中选择并执行 adapter。`/api/v1/providers`
返回安全 catalog 投影。不要使用固定 provider 列表、旧 SourceAdapter registry 或
旧 source-list endpoint 不作为产品 contract。

Admin 与 Data API 分离：Data API 使用 user credential；Admin 只读 config、doctor 和 ping。
