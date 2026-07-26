# Calm Precision Panel

SouWen 的管理面板是单一的 Calm Precision 界面，不提供运行时视觉变体或按主题裁剪的
构建入口。

## 结构

- `src/CalmPrecisionApp.tsx` 包含登录、路由、页面和单一应用壳层。
- `src/CalmPrecisionApp.module.scss` 只包含该界面的 SCSS Module 布局与组件样式。
- `src/core/styles/calm-precision.scss` 定义 light/dark CSS variables；模式仅影响对比度，
  不改变产品结构。
- `src/core/sdk/` 是生成的 data-plane SDK。Search、LLM Search、Fetch 和 Providers
  必须经 `SouWenClient` 调用，不能新增手写 data API transport。
- 管理读取使用 `src/core/services/admin-client.ts`，仅用于已认证管理员的 Runtime /
  Settings 只读视图。

## 导航与权限

顶层导航只有 Search、LLM Search、Fetch、Providers、Runtime / Settings。最后一项只在
服务端 `whoami` 确认 admin 角色后显示；其路由同样有客户端守卫，后端仍是最终权限边界。

登录会先校验 base URL，令牌不会发送给未通过同源、loopback 或
`VITE_ALLOWED_API_HOSTS` allow-list 的主机。无令牌连接不会由 Panel 提升角色；是否开放
无密码管理员访问只由服务端 `SOUWEN_ADMIN_OPEN=1` 决定。

嵌入式 Panel 只支持同源 private-edge browser session/cookie 或普通单一 Bearer application token。
浏览器 cookie 由同源请求自动附带，Panel 不读取或保存；Bearer token 仅按 auth state 的最小生命周期
保存一个 app token。Panel 不采集、拼接或持久化 dual-token。edge token 加 `X-SouWen-Token` 的
dual-token 组合只属于 programmatic SDK 使用，不属于浏览器 Panel 登录模型。

## 交互与可访问性

- 每个输入都有稳定的 `label` 和 `id`，状态使用 `role=status` 或 `role=alert`。
- 所有异步页面都应显示 loading、empty、error 和成功反馈。
- 外部结果链接必须使用 `rel="noreferrer"`；在小屏幕上，导航横向滚动而非挤压内容。
- Runtime / Settings 只显示运行诊断和安全姿态投影；完整 server config 不进入 DOM，也不在
  Panel 中回显或写入 token、password、cookie、credential 或 API key。

## 验证

```bash
cd panel
npm test
npm run build
```

`npm run build:local` 是唯一允许更新嵌入式 Panel artifact 的方式；随后
`npm run check:artifact` 必须确认 `dist/index.html` 与 `../src/souwen/server/panel.html`
byte-identical。
