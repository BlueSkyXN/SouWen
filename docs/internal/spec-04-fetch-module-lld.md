# SPEC-04：Fetch Module 执行与聚合

**状态**：Implemented target clarification for the frozen `2.0.0rc4` wire contract；RC6
沿用相同 wire shape

**范围**：`FetchRequest` 的 `fallback` / `fanout` 执行语义、结果顺序、partial/error 规则、
Browser Worker 边界与解压后响应大小上限

**上游契约**：[SPEC-01/API-006](./spec-01-external-api-canonical-dto.md#api-006fetch-contract)

## 1. 不变量

1. `targets` 保持 frozen DTO 的 1–20 个 `http/https` URL 上限。
2. `providers` 缺省时只使用部署注册的 default Fetch Provider；当前为 `builtin-fetch`。
3. 显式 Provider 必须声明 `kind=fetch`，必须解析到已登记的 Fetch adapter，且顺序保持不变。
4. Provider 只能执行单 target Fetch。选择、fallback、fanout、聚合和 Browser Worker 决策属于
   Fetch Module，不下放到 Provider。
5. 所有 attempt 共享调用方的 `ExecutionContext`；dispatch 前后都检查 cancellation/deadline。
6. SSRF、DNS binding、redirect、robots、media type 和大小策略不能被请求字段关闭。

## 2. fallback

`strategy` 缺省或等于 `fallback` 时，每个 target 独立按显式 Provider 顺序执行：

1. 获得非 low-quality 的成功结果后停止，不再调用后续 Provider。
2. `quality=low` 的成功结果暂存为候选，并继续寻找更好的成功结果；若没有更好结果，保留第一个
   low-quality 候选并将 batch 标记为 `partial=true`。
3. `invalid_request`、`policy_blocked`、`payload_too_large`、`unsupported_media_type` 是
   non-recoverable target outcome，不调用后续 Provider；若此前已有 low-quality 成功候选，则停止
   并返回该候选，同时在 provenance 中保留本次失败 attempt。
4. timeout、rate limit、provider unavailable 或 failed result 可以继续下一个 Provider。
5. 返回 item 的 provenance 按实际 attempt 顺序合并，不伪造未执行的 Provider。

不同 target 可并发；同一 target 内的 Provider attempt 按配置顺序串行。

## 3. fanout

`strategy=fanout` 时，Fetch Module 对每个 `target × provider` 组合并发执行，并返回每个组合的
独立 `FetchResult`。不选择“最佳正文”，不合并不同 Provider 的 content，也不把 fanout 静默降级
成 fallback。

结果顺序固定为 target-major、provider-minor：先按 `targets` 输入顺序，再按 `providers` 输入顺序。
因此两个 target、三个 Provider 最多返回六个 item。每个 item 的 target、status、content/error
和 provenance 都只描述该组合的真实 outcome。公开 provenance/error 中使用 `ProviderRef.id`，内部
adapter ID 只用于 runtime dispatch，不进入 wire result。

任一组合成功时 HTTP operation 返回 `FetchBatch`；存在 failed、blocked、缺 metadata 或
low-quality item 时 `meta.partial=true`。全部组合失败时抛出 canonical Provider error；只有单一
adapter 时可以保留其公开 provider/retry metadata，多 adapter 时不伪造单一失败归属。

`providers` 缺省且选择到一个 default Provider 时，`fanout` 退化为一个 Provider 的单次执行，
但仍是合法请求。

## 4. Browser Worker

Browser Worker 是 `builtin-fetch` 的第二 execution mode，不是第二个业务 Provider：

- 只有 default `builtin-fetch` adapter 可以触发 Browser Worker。
- 显式选择其他 Fetch Provider 时不触发 builtin Browser Worker。
- `respect_robots=true` 时不触发 Browser Worker。
- builtin 低质量或可恢复失败时可尝试 Worker；最终 provenance 同时记录 builtin 与 Worker attempt。
- fanout 中若某一组合是 `builtin-fetch`，该组合仍遵守上述规则；其他组合不受影响。

## 5. 解压后 10 MiB hard cap

IP-pinned target Fetch 使用 HTTPX raw streaming，只广告 `gzip, deflate`，并由 SouWen 对 raw stream
做增量解码。实现最多保留 `10 MiB + 1 byte` 的解压后数据：一旦读到第 `10 MiB + 1` 字节，立即
关闭响应 stream，返回 `PAYLOAD_TOO_LARGE`，不等待完整压缩体进入内存。

`Content-Length` 和完整缓冲后的检查保留为 defense in depth，但不能替代流式解压上限。未知或
组合 `Content-Encoding` fail closed，不作为文本渲染。多个合法 gzip member 共用同一个累计上限；
截断 stream 和非编码 member 的 trailing data 同样 fail closed。普通 pytest 使用分块高压缩比
fixture 证明读取会在 transport stream 完成前停止。

## 6. 验证映射

| 规则 | 代码 / 测试 |
|---|---|
| fallback 顺序、停止与 provenance | `src/souwen/modules/fetch/application/orchestration.py`；`tests/test_fetch_module_v2.py` |
| fanout 并发、结果基数与顺序 | `src/souwen/modules/fetch/application/orchestration.py`；`tests/test_fetch_module_v2.py` |
| 10 MiB 流式解压上限 | `src/souwen/common_runtime/provider_support/scraper/base.py`；`tests/test_web/test_ssrf_binding.py` |
| target DTO 与错误映射 | `src/souwen/platform/provider_spi/dto.py`；`tests/test_target_canonical_dto.py` |
| HFS 可读正文 smoke | `scripts/hf_space_smoke.py`；`tests/test_hf_space_smoke.py` |
