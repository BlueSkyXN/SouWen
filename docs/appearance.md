# Calm Precision 管理面板

SouWen 管理面板位于 `panel/`，是一个固定的 React/Vite 管理界面，不提供运行时视觉
变体或按主题裁剪的构建入口。

## 顶层功能

面板只提供以下顶层工作区：

1. **Search**：从 13 个领域中选择一个，使用 Server 默认 Provider 完成规范化检索；多 Provider
   fanout 由显式 SDK/API 请求承担。
2. **LLM Search**：选择一个当前部署 configured provider，使用固定 `single` 策略完成带证据综合检索。
3. **Fetch**：受服务端 SSRF、robots 和 provider 策略保护的内容获取。
4. **Providers**：只读 provider 可用性、能力与缺失配置字段。
5. **Runtime / Settings**：仅 admin 可见的只读运行诊断和安全姿态摘要。

没有 Paper、Patent、Books、Video、Wayback、Bilibili、Proxy 或 WARP 的独立产品入口。

## 在线预览

当前 HFS Panel 入口为 <https://blueskyxn-souwen.hf.space/panel#/>。五个顶层工作区对应
六个直达 route：

| Workspace | Route | 角色 |
|---|---|---|
| Login | `/panel#/login` | 无 |
| Search | `/panel#/search` | user / admin |
| LLM Search | `/panel#/llm-search` | user / admin |
| Fetch | `/panel#/fetch` | user / admin |
| Providers | `/panel#/providers` | user / admin |
| Runtime | `/panel#/runtime` | admin |
| Settings | `/panel#/settings` | admin |

Space 仓库保持 private，但当前 App domain 的 Panel/docs/probes surface 可匿名打开；业务与管理
API 仍要求 SouWen application credential。完整登录、逐页操作、light/dark、窄屏、键盘和
release/deployment 证据边界见 [HFS 在线预览与功能验收](./live-preview.md)。

## 数据与权限边界

Search、LLM Search、Fetch 与 Providers 均使用生成的 `@core/sdk` `SouWenClient`，不在
Panel 中手写这些 data API 的请求。该客户端会在业务请求前校验 target API major 和 rollout
contract。

登录和 admin 权限由服务端 `/api/v1/whoami` 决定。Panel 会在发送令牌前检查 base URL：只允许
同源、loopback 或 `VITE_ALLOWED_API_HOSTS` 明确列出的主机。无令牌不会由 Panel 提升访问；
无密码管理员访问只由服务端的 `SOUWEN_ADMIN_OPEN=1` 决定。

Runtime / Settings 仅使用必要的 admin 读取接口。Settings 只投影访问策略、Provider 配置
数量和 LLM Search 姿态，不把完整 server config 发送到 DOM。面板不提供 token、password、
cookie、credential 或 API key 的回显和保存。

嵌入式 Panel 的认证只支持两种单一浏览器场景：同源 private-edge browser session/cookie，或普通的
单一 Bearer application token。前者由浏览器自动携带，Panel 不读取、采集或持久化 cookie；后者只按
现有 auth state 的最小生命周期保存一个 app token。Panel 不采集、拼接或持久化 dual-token。需要
edge token 与 `X-SouWen-Token` 同时存在的 dual-token 调用是 programmatic SDK 场景，不是 embedded
Panel 的登录或存储模型。

## 本地开发与验证

```bash
cd panel
npm test
npm run build
```

`npm run build` 会执行 TypeScript 检查和 Vite 单文件构建。更新嵌入式 artifact 时使用
`npm run build:local && npm run check:artifact`；后者要求 `panel/dist/index.html` 与
`src/souwen/server/panel.html` byte-identical。不要手工修改 `panel/dist/` 或
`src/souwen/server/panel.html`。
