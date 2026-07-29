# HFS 在线预览与功能验收

本文给出 `BlueSkyXN/SouWen` 当前 HFS 部署的浏览器入口、角色边界和逐项验收步骤。
它描述的是可变的 current-main deployment，不替代 immutable GitHub Release、tag 或一次性
workflow artifact。

## 入口与访问模型

- App：<https://blueskyxn-souwen.hf.space/>
- Panel：<https://blueskyxn-souwen.hf.space/panel#/>
- Swagger：<https://blueskyxn-souwen.hf.space/docs>
- Space 仓库：<https://huggingface.co/spaces/BlueSkyXN/SouWen>
- GitHub Release：<https://github.com/BlueSkyXN/SouWen/releases/tag/v2.0.0rc4>

Hugging Face 控制面的 Space 仓库保持 `private=true`。当前 App domain 允许匿名读取 Panel
shell、Swagger、OpenAPI 和 probes；这不代表 Data/Admin API 匿名开放。Search、LLM Search、
Fetch、Providers 和全部 Admin endpoint 仍由 SouWen application credential 保护。

部署或平台策略变化后，不应凭文档推测访问状态：以实际 HTTP 状态、`/api/v1/whoami` 和
deployment evidence 为准。Panel 登录框只接收 SouWen application token，不接收 HF write
token，也不会把两个 token 拼接或写入 URL。

## 完整功能矩阵

| 功能 | 直达地址 | 最低角色 | 验收内容 |
|---|---|---|---|
| Login | <https://blueskyxn-souwen.hf.space/panel#/login> | 无 | 同源 Server URL、application token、错误提示与会话选项 |
| Search | <https://blueskyxn-souwen.hf.space/panel#/search> | user | 单领域选择、请求状态、标题、snippet 与规范化结果 |
| LLM Search | <https://blueskyxn-souwen.hf.space/panel#/llm-search> | user | 单个 configured Provider ID、固定 `single`、综合回答与 evidence |
| Fetch | <https://blueskyxn-souwen.hf.space/panel#/fetch> | user | 最多 20 个 URL、fallback/fanout、SSRF/robots 保护结果 |
| Providers | <https://blueskyxn-souwen.hf.space/panel#/providers> | user | 104 个 Provider package 的能力、可用性和缺失配置 |
| Runtime | <https://blueskyxn-souwen.hf.space/panel#/runtime> | admin | 脱敏、只读的 Provider/runtime 诊断 |
| Settings | <https://blueskyxn-souwen.hf.space/panel#/settings> | admin | 访问策略、配置数量与 LLM Search 姿态摘要 |
| Swagger | <https://blueskyxn-souwen.hf.space/docs> | 无 | 当前 runtime OpenAPI 的交互式文档 |
| OpenAPI JSON | <https://blueskyxn-souwen.hf.space/openapi.json> | 无 | 8 条 canonical public contract paths |
| Health | <https://blueskyxn-souwen.hf.space/healthz> | 无 | version、source SHA、wrapper SHA、target rollout |
| Readiness | <https://blueskyxn-souwen.hf.space/readyz> | 无 | API、Provider、LLM Search 与 Browser Worker readiness |

`Runtime / Settings` 是一个顶层导航组，对应两个 admin-only hash route。普通 user token
会被送回 Search；这属于权限保护，不是路由故障。

## 浏览器验收顺序

1. 打开 Panel。根 App 当前跳转到 Swagger，所以产品界面应使用 `/panel#/` 直达链接。
2. 在 Login 页保留自动填入的同源 Server URL。输入获批的 SouWen user 或 admin token；不要
   在 URL、Issue、截图、日志或聊天中粘贴凭据。
3. 先打开 Providers，确认至少一个 `search`、一个 `llm_search` 和一个 `fetch` Provider 为
   available。LLM Search 页的 Provider ID 应从这里选择，不使用文档中的硬编码私有配置。
4. 在 Search 输入研究问题并选择一个领域。未显式指定 Provider 的 Server contract 一次只接受
   一个 domain；Panel 默认选择 `paper`，避免生成必然失败的多 domain 请求。成功状态应展示规范化结果；
   零结果应展示明确 empty state，而不是空白页面。
5. 在 LLM Search 输入问题和一个 available Provider ID。Target runtime 的策略固定为 `single`；
   成功状态应同时展示回答和 evidence，Provider 错误应进入可读 error state。
6. 在 Fetch 输入一个获准的公开 `http/https` URL。成功结果应显示 target、status、title/content；
   内网、非 HTTP scheme 或违反 server policy 的目标必须 fail closed。
7. 使用 admin token 打开 Runtime 和 Settings。两页都只能读取；页面不得显示 token、password、
   cookie、credential、API key 或完整私有 endpoint。
8. 切换 light/dark，并在窄屏下检查所有导航和表单；使用 `Tab` 验证 skip link、焦点环和按钮顺序。

## HTTP 快速核对

不带 application credential 的 surface 与负向鉴权检查：

```bash
BASE_URL=https://blueskyxn-souwen.hf.space
curl --fail-with-body "$BASE_URL/healthz"
curl --fail-with-body "$BASE_URL/readyz"
curl --fail-with-body "$BASE_URL/openapi.json"
curl -o /dev/null -sS -w '%{http_code}\n' "$BASE_URL/api/v1/providers"  # 期望 401
```

受保护接口的调用示例见 [api-reference.md](./api-reference.md)。不要把真实 token 写入 shell
history；交互测试应使用受控环境变量或 Panel password input。

## Release 与 deployment 边界

`v2.0.0rc4` tag 和 GitHub prerelease 是 immutable release baseline。`main` 可以包含 tag 后的
修复，HFS 也可以通过 `evidence_profile=deployment, publish=false` 部署 exact current main；
这样的 runtime 仍报告 package version `2.0.0rc4`，但不能描述为 tag-exact Release assets。

验收 current deployment 时至少同时回读：

1. GitHub `origin/main` 的完整 40 位 SHA。
2. `/healthz` 与 `/readyz` 的 `source_sha`。
3. HF Space repo SHA、`runtime.raw.sha` 与 probes 的 `wrapper_sha`。
4. exact-source deployment run 的 surface/capability reports 与 attestation。

只有这四层一致，才能说明当前 main 已部署并可预览；它们仍不移动既有 tag，也不替代下一版本
Release 的 publication gate。
