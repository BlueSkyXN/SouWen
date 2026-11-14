# SouWen 架构概览

SouWen 3.x 是给 AI Agent 用的免费搜索与抓取工具：只有 `search` 和 `fetch` 两个动作，
入口是 MCP（stdio 与 `/mcp`）和一个扁平 HTTP API。看家本领是出口阶梯——让零 Key 源
在 WARP、代理和无头浏览器下确实能用。

<!-- BEGIN AUTO: REGISTRY SUMMARY -->
**Provider v2 摘要**：Manifest Registry 从内置 package 发现 **36** 份 manifest、**36** 个 adapter。

Provider Manager 对 manifest、configuration、secret reference 和显式 factory 做 preflight，并按需构造 provider；旧 source registry 不参与启动、路由或文档生成。
<!-- END AUTO: REGISTRY SUMMARY -->

## 1. 分层与依赖方向

```text
MCP client (stdio) │ HTTP client (/search /fetch /mcp) │ Python (souwen.search/fetch)
                         │
                         ▼
agent.py 门面 ── server/（app、auth、限流、MCP server、doctor）
                         │
                         ▼
modules/search（领域选源、并发、回退、紧凑投影）
modules/fetch（站点处理器 → 通用抓取 → 提取链 → 分页缓存）
                         │
                         ▼
platform/（provider SPI、manifest registry、manager）
                         │
                         ▼
providers/*（一个源一个包：manifest + spec + adapter）+ runtime_clients（私有 client）
common_runtime/（transport、egress 阶梯、SSRF、限流、WARP 支持）
```

- `agent.py` 是唯一门面：MCP、HTTP、Python 三入口共用同一 runtime 与投影。
- `server/` 组装 FastAPI 应用、user 凭据鉴权、限流与 MCP streamable app（挂载在 `/mcp`）。
- `modules/` 只做编排：搜索的候选批、失败降级与 RRF 合并；抓取的处理器链与分页缓存。
- `common_runtime/egress/` 实现四级出口阶梯（下文第 3 节）；它不能反向依赖 modules 或
  具体源。
- 依赖方向由 `scripts/ci/check_architecture_dependencies.py` 门禁执行。

## 2. Provider 与源声明

每个源一个 package（`providers/information_sources/<id>/` 或 `fetch_sources/<id>/`）：

- `manifest.py` 是身份唯一事实源：id、capability、adapter、可选 Key，以及
  `min_egress`/`max_egress`（出口阶梯边界，SPEC 5.2）。
- `providers/catalog.py` 只做目录发现（导入各包的 manifest），不导入 adapter 或 client。
- 私有传输与解析在 `providers/runtime_clients/`，不属于公共 API。

## 3. 出口阶梯（核心能力）

四级：`direct`（httpx）→ `impersonate`（curl_cffi 指纹）→ `proxy`（WARP/用户代理）→
`browser`（Playwright Chromium）。要点：

- 每个源用 manifest 声明起步级与最高级；进程内按（主机，级别）记忆最近成败，失败爬级。
- 未到天花板的级别限时 4 秒快速失败，把预算留给更高级别；天花板级别保留完整重试语义。
- 抓取正文路径（IP-pin 的 SSRF 安全请求）同样接入阶梯：direct 被拒升级 proxy，
  内容判定为验证页/JS 空壳/<200 字短正文时由编排层升级 browser。
- 浏览器级双重安全：页面级 route 策略（每个 URL 先过 SSRF 校验）+ 连接级
  `PinnedLoopbackProxy`（回环代理把流量 pin 到已校验 IP；配置了 WARP/用户代理时
  经上游代理转发，上游只见到 IP 字面量）。
- 未安装 Chromium 或未配置代理时对应级别自动跳过，不报启动错误。

## 4. MCP 与 HTTP API

MCP 恰好两个工具：`search(query, domain, limit)`、`fetch(url, max_chars, start)`；源清单
走 `souwen://sources` 资源。HTTP 侧是 `POST /search`、`POST /fetch`、`GET /sources`、
`GET /healthz` 与 `/mcp`（streamable HTTP）。鉴权配置 `user_password` 后全部入口要求
Bearer/token；未配置则开放（沿用既有行为，不放宽）。

## 5. 体检与判定

`scripts/census.py`（固定查询）+ `census.yml`（权威环境：根镜像、WARP 双腿、零 Key）
每周运行；PASS/WARN/FAIL 判定，FAIL 源按 SPEC 6.3 规则删除。`souwen doctor --live`
在进程内逐出口级别点名探测（搜索源 + 三类抓取 URL），报告记录实际使用的级别；
程序错误（ERROR）与上游失败（FAIL）分开呈现。

<!-- BEGIN AUTO: CROSS-DOMAIN FETCH SOURCES -->
以下 package 通过独立 adapter 提供多个公开能力：

| Provider package | Capabilities | Adapter IDs |
|---|---|---|
<!-- END AUTO: CROSS-DOMAIN FETCH SOURCES -->

## 6. 新增一个源

1. 在 `providers/<namespace>/<id>/` 增加 `manifest.py`（声明领域、主机、egress 边界、
   可选 Key）与 adapter；需要私有传输时放 `runtime_clients/`。
2. 为解析函数补真实响应夹具测试（`tests/fixtures/`）。
3. 跑 `pytest`、`gen_docs --check`、架构与残留门禁；push 后由 census 验证真实可用性，
   连续 FAIL 会被删除——本仓库不保留没验证过能用的源。

## 7. 验证护栏

- `ruff check src tests scripts tools && ruff format --check src tests scripts tools`
- `python3 -m pytest tests/ -q`
- `python3 tools/gen_docs.py --check`
- `python3 scripts/ci/check_no_legacy_terms.py`
- `python3 scripts/ci/check_architecture_dependencies.py`
- push `agent-first` 触发 `census.yml`（权威环境体检）
