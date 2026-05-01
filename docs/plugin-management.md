# 插件管理使用指南 (Plugin Management)

> 面向**部署/运维/普通用户**的插件管理说明。如果你是**插件作者**，请阅读
> [plugin-integration-spec.md](./plugin-integration-spec.md) 了解对接契约与脚手架。

SouWen 提供三种等价入口管理插件：

| 入口 | 适用场景 | 进程位置 |
|---|---|---|
| **Web Panel** (`/plugins`) | 日常运维、图形化管理 | 浏览器调用服务端 API |
| **CLI**（`souwen plugins ...`） | 脚本、CI、SSH 远程 | 直接 import `souwen.plugin_manager` |
| **HTTP API**（`/api/v1/admin/plugins/...`） | 自动化集成、第三方面板 | 服务端 |

三者背后**共用同一份状态文件**与同一组管理函数，行为完全一致；详见
[api-reference.md#插件管理端点](./api-reference.md#插件管理端点-apiv1adminplugins)。

---

## 1. 状态机与生命周期

```
                ┌──── reload ────┐
                │                ▼
   discover ─► loaded  ◄──► disabled  (write disabled list)
                │   ▲           │
       on_shutdown   ├── enable │
       remove h.     │          │
       remove a. ────┘          ▼
                            available  (catalog only, not imported)
                                │
                                ▼
                            install / uninstall
                            (SOUWEN_ENABLE_PLUGIN_INSTALL=1)
```

| 状态 | 含义 |
|---|---|
| `loaded` | 当前进程已通过 entry-point / 配置 / 目录加载，并注册了 adapter / fetch handler |
| `available` | 目录中可发现，但尚未在当前进程加载（通常因为包未安装或被禁用） |
| `disabled` | 已写入禁用列表，重启后会被启动流程跳过 |
| `error` | 加载或卸载过程中抛出异常，详情见服务端日志 |

**重要**：所有改动状态的操作都是**幂等**的，并且需要**重启**才能完全生效。
管理工具会在响应里返回 `restart_required`，UI 会展示横幅提醒。

---

## 2. 通过 Web Panel 管理

1. 用 admin 凭据登录面板
2. 左侧导航选择 **插件**（`/plugins`）
3. 在表格中可见每个插件的 **状态 / 来源 / 版本 / 健康** 与操作按钮：
   - **启用/禁用**：写入持久化状态文件，立即在运行时移除 adapter 与 fetch handler
   - **健康检查**：调用插件 `health_check()`（与 API 同源），结果写入"详情"面板
   - **详情**：展示 adapter、fetch handler、health 历史记录
4. 顶部 **重新扫描** 按钮触发 `reload`，按需追加加载
5. 底部 **安装 / 卸载** 卡片：
   - 服务端启用 `SOUWEN_ENABLE_PLUGIN_INSTALL=1` 时输入框可用
   - 包名必须在允许列表（`PLUGIN_CATALOG`）或动态目录中
6. 任何状态变化后，顶部会出现 **黄色横幅** 提示重启服务

> **权限**：路由受 `config_write` feature 保护，只有 admin 角色或显式拥有该 feature 的 user 才能访问。

---

## 3. 通过 CLI 管理

CLI 命令组 `souwen plugins`：

```bash
souwen plugins list                       # 列出所有插件
souwen plugins list --health              # 附带健康检查列（并发调用 health_check）
souwen plugins info <name>                # 详情
souwen plugins enable <name>              # 启用（重启后生效）
souwen plugins disable <name>             # 禁用 + 运行时尽力卸载
souwen plugins health <name>              # 单插件健康检查
souwen plugins reload                     # 重新扫描 entry-point 插件
souwen plugins install <package>          # pip 安装（需开关）
souwen plugins uninstall <package>        # 卸载（同上）
souwen plugins new <name>                 # 生成插件项目骨架
```

CLI 命令直接 import 主进程的 `souwen.plugin_manager`，因此：
- **可在没有运行 server 时使用**（适合 CI / Docker entrypoint 调度）
- **不会触碰其他进程的运行时状态**：禁用/启用写入状态文件后，其他进程下次启动才会看到

---

## 4. 通过 HTTP API 管理

详见 [api-reference.md#插件管理端点](./api-reference.md#插件管理端点-apiv1adminplugins)。

最常用的快速测试：

```bash
# 假设服务在 localhost:8000，admin_password=secret
export AUTH="Authorization: Bearer secret"

curl -s -H "$AUTH" http://localhost:8000/api/v1/admin/plugins | jq .
curl -s -X POST -H "$AUTH" http://localhost:8000/api/v1/admin/plugins/superweb2pdf/disable | jq .
curl -s -X POST -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"package": "superweb2pdf"}' \
  http://localhost:8000/api/v1/admin/plugins/install | jq .
```

---

## 5. 安全门禁

| 操作 | 默认行为 | 显式开启 |
|---|---|---|
| 列表 / 详情 / 健康检查 | 受 admin 鉴权保护 | — |
| 启用 / 禁用 / 重新扫描 | 受 admin 鉴权保护 | — |
| **安装 / 卸载** | **拒绝**，返回 `success=false` | 在容器/进程环境设置 `SOUWEN_ENABLE_PLUGIN_INSTALL=1` |

**为什么 install 默认关？**
- pip 安装本身可执行任意 setup.py 代码，相当于以 SouWen 进程的权限执行第三方代码；
- 防止恶意客户端通过被攻破的 admin 凭据扩大破坏面；
- 在生产/共享部署上，插件管理建议走镜像构建或 sidecar 流程，而非运行时 pip。

**允许列表**（`src/souwen/plugin_manager.py::ALLOWED_PACKAGES`）：

```python
ALLOWED_PACKAGES = frozenset({"superweb2pdf", "souwen-example-plugin"})
```

外加任何通过 `souwen.plugin_catalog` entry point 动态注册的目录条目。
不在允许列表中的包名会被直接拒绝，pip 永远不会被调用。

---

## 6. 状态文件

插件管理在 `data_dir/plugins.state.json` 持久化：

```json
{
  "disabled_plugins": ["legacy_plugin"],
  "installed_via_api": ["superweb2pdf"]
}
```

- **`disabled_plugins`**：启动时被 `discover_entrypoint_plugins(skip_names=...)` 跳过
- **`installed_via_api`**：仅做记账用途，便于运维审计哪些包是通过 API 安装的

文件路径取自 `config.data_path`（默认 `~/.local/share/souwen/`），原子写入，
由 `souwen.plugin_manager._save_state` 写出，反复读写不会丢数据。

---

## 7. 故障排查

### 插件状态显示 `error`
1. 查服务端日志中的 `event=plugin_load_failed` 记录
2. 临时 `souwen plugins disable <name>` 让服务可启动
3. 修复后 `souwen plugins enable <name>` 并重启

### `disable` 后插件仍能响应请求
- 这是**预期行为**：禁用是"重启后跳过 + 运行时尽力清理"。某些 adapter 的引用可能被
  其他模块缓存（例如 fetch 调度器在 worker 内持有的引用），需要重启彻底释放。
- 检查日志中的 `event=plugin_disabled`：`removed_adapters` / `removed_handlers` 列出真正被移除的资源。

### `install` 返回 `success=false`，message 显示 "未启用"
- 服务端缺 `SOUWEN_ENABLE_PLUGIN_INSTALL=1`。Docker 用户在 `docker-compose.yml` 的 `environment` 段加上即可。
- 容器内的 admin 命令也建议跑前 `export SOUWEN_ENABLE_PLUGIN_INSTALL=1`，确保 CLI 与 API 行为一致。

### 安装成功但插件不出现在列表
- entry-point 缓存：`souwen plugins reload` 显式触发追加扫描；仍不行需重启进程。
- 包未声明 `souwen.plugins` entry point，参见 [plugin-integration-spec.md](./plugin-integration-spec.md)。

### `health_check` 返回 `degraded` 但功能可用
- 插件作者通常用 `degraded` 表示"自降级/部分能力受限"。不影响 list 中的 `loaded` 状态，
  但前端面板会展示警告颜色，提示运维关注外部依赖（如：浏览器内核未安装、可选 API key 未配置）。

---

## 8. 相关文档

- [plugin-integration-spec.md](./plugin-integration-spec.md) — 给插件作者的对接契约
- [api-reference.md](./api-reference.md) — 完整 HTTP API 参考
- [architecture.md](./architecture.md) — 注册表、Plugin 信封、生命周期钩子的内部机制
