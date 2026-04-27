# WARP 代理方案

## 概述

SouWen 支持 5 种 Cloudflare WARP 代理模式：`wireproxy`、`kernel`、`usque`、`warp-cli`、`external`。这些模式覆盖了从无特权用户空间代理、Linux 内核高性能代理、MASQUE/QUIC 隧道，到官方客户端和外部 sidecar 代理的不同场景。

WARP 的核心目标不是替代系统代理，而是在 SouWen 抓取网页、论文、专利和调用外部网络资源时，提供一个可控的出口网络层。启用后，SouWen 会把内部代理配置指向 WARP 本地代理或外部代理地址，并通过 `https://1.1.1.1/cdn-cgi/trace` 检查代理是否返回 WARP 标记。

运行方式分为两类：

- **Docker 容器启动期自动初始化**：由 `entrypoint.sh` 调用 `scripts/warp-init.sh`，根据环境变量启动代理，并把状态写入 `/run/souwen-warp.json`。
- **直接运行 / API / CLI 动态管理**：由 Python `WarpManager` 管理生命周期，支持通过管理 API 和 `souwen warp` 命令启停、注册、测试和查看状态。

## 方案对比表

| 特性 | wireproxy | kernel | usque | warp-cli | external |
|---|---|---|---|---|---|
| 协议 | WireGuard | WireGuard | MASQUE/QUIC（RFC 9484） | Cloudflare 官方 WARP 协议栈 | 取决于外部服务 |
| 实现原理 | 用户空间 WireGuard 客户端直接暴露 SOCKS5 | Linux 内核 WireGuard 网卡 + microsocks | QUIC 隧道上运行 MASQUE 代理 | `warp-cli` 连接 WARP，GOST 转发本地代理 | SouWen 只连接已有代理，不启动本地 WARP 进程 |
| 代理类型 | SOCKS5 | SOCKS5 | SOCKS5；可选 HTTP | SOCKS5；可选 HTTP（经 GOST） | SOCKS5 或 HTTP |
| 默认端口 | `127.0.0.1:1080` | `127.0.0.1:1080` | SOCKS5 `127.0.0.1:1080`，HTTP 由 `warp_http_port` 控制 | SOCKS5 `127.0.0.1:1080`，HTTP 由 GOST 参数控制；上游为 `127.0.0.1:40000` | 由 `warp_external_proxy` 指定，如 `socks5://warp:1080` |
| 主要依赖 | `wgcf`、`wireproxy` | `wgcf`、`wg-quick`、`microsocks`、`/dev/net/tun` | `usque` 二进制和 `config.json` | `warp-cli`、`warp-svc`、`gost` | 外部 WARP 代理容器或服务 |
| 权限要求 | 无需特权 | 需要 Linux 网络能力，Docker 通常需 `NET_ADMIN` 和 `/dev/net/tun` | 无需特权 | 通常需要容器内运行官方守护进程，权限和镜像支持要求最高 | SouWen 侧无需特权 |
| Docker 支持 | 支持；默认镜像已预装 `wgcf`、`wireproxy` | 支持；需运行时授予网络能力 | 支持；默认镜像已预装 `usque` | 代码支持，但默认 Dockerfile 未预装 `warp-cli`/`gost`，需自定义镜像 | 非常适合 docker-compose sidecar |
| 直接运行支持 | 支持 Linux/macOS，只要安装二进制 | 仅适合 Linux，且需内核 WireGuard 能力 | 支持 Linux/macOS，只要安装 `usque` | 取决于官方客户端和 GOST 是否可用 | 支持，只需能访问外部代理地址 |
| 资源占用 | 低 | 低到中；性能最好 | 中；QUIC 加密和用户空间协议栈开销略高 | 中到高；官方服务 + GOST | 最低；SouWen 本地不维护 WARP 进程 |
| 优点 | 兼容性强、无特权、部署简单 | 吞吐高、延迟低、接近原生 WireGuard | 协议伪装能力强，适合受限网络；可同时提供 SOCKS5/HTTP | 功能最全，支持 WARP+、ZeroTrust 等官方能力 | 解耦彻底、适合多服务共享、升级和故障隔离好 |
| 缺点 | 仅 SOCKS5；依赖 WireGuard 配置注册 | 权限要求高，容器部署复杂 | 需单独维护 usque 配置，注册可能受限流影响 | 依赖多、资源占用高，默认镜像不包含全部组件 | 需要额外维护外部代理服务，健康状态取决于外部组件 |
| 推荐场景 | 默认无特权部署、macOS/Linux 本地运行 | Linux 服务器或特权 Docker，追求性能 | 网络限制较多、需要 MASQUE/QUIC 的环境 | 需要官方客户端特性、WARP+/ZeroTrust | docker-compose sidecar、多应用共享代理 |

## 各方案详解

### 1. wireproxy（用户空间 WireGuard）

**原理**：`wgcf` 生成 Cloudflare WARP WireGuard 配置，SouWen 将其转换为 `wireproxy` 配置；`wireproxy` 在用户空间实现 WireGuard，并在本地暴露 SOCKS5 代理。

**依赖**：

- `wgcf`：注册 WARP 账号并生成 WireGuard 配置。
- `wireproxy`：用户空间 WireGuard + SOCKS5 代理。

**端口**：仅 SOCKS5，默认 `127.0.0.1:1080`，由 `warp_socks_port` / `WARP_SOCKS_PORT` 控制。

**配置来源优先级**：

1. `WARP_CONFIG_B64`：Base64 编码的配置。
2. `/app/data/wireproxy.conf`：持久化配置。
3. 自动调用 `wgcf register` 和 `wgcf generate` 注册新配置。

**适用环境**：任何可运行 `wireproxy` 的 Linux/macOS 环境，不需要 `NET_ADMIN`、TUN 设备或 root 网络能力，因此是最稳妥的通用方案。

**配置示例（Docker 环境变量）**：

```bash
WARP_ENABLED=1
WARP_MODE=wireproxy
WARP_SOCKS_PORT=1080
# 可选：自定义 WARP Endpoint
WARP_ENDPOINT=162.159.192.1:4500
```

**配置示例（YAML）**：

```yaml
warp_enabled: true
warp_mode: wireproxy
warp_socks_port: 1080
warp_endpoint: 162.159.192.1:4500
```

**选择建议**：如果不确定用哪种模式，且不想给容器特权权限，优先选择 `wireproxy`。

### 2. kernel（内核 WireGuard）

**原理**：使用 Linux 内核 WireGuard 模块通过 `wg-quick up wg0` 创建 `wg0` 网卡，再启动 `microsocks` 在本地提供 SOCKS5 代理。SouWen 不直接把所有系统流量路由到 WARP，而是通过本地 SOCKS5 使用该网络出口。

**依赖**：

- `wgcf`：生成 WireGuard 配置。
- `wg-quick` / `wireguard-tools`：管理内核 WireGuard 接口。
- `microsocks`：轻量 SOCKS5 服务。
- `/dev/net/tun` 和网络管理权限。

**端口**：仅 SOCKS5，默认 `127.0.0.1:1080`。

**权限要求**：Linux 环境下需要内核 WireGuard 能力。Docker 中通常需要：

```yaml
cap_add:
  - NET_ADMIN
devices:
  - /dev/net/tun:/dev/net/tun
```

**配置来源优先级**：

1. `WARP_CONFIG_B64`。
2. `/app/data/wg0.conf`。
3. 自动调用 `wgcf` 注册生成。

启动前会规范化配置：保留 IPv4 `Address`，清理旧 `Address`/`AllowedIPs`/`DNS` 字段，向 `[Peer]` 注入 `AllowedIPs = 0.0.0.0/0`，并设置 `PersistentKeepalive = 15`。

**适用环境**：Linux 服务器、允许特权网络能力的 Docker 容器。适合追求吞吐和低延迟的部署。

**配置示例**：

```bash
WARP_ENABLED=1
WARP_MODE=kernel
WARP_SOCKS_PORT=1080
```

**参考**：MicroWARP（github.com/ccbkkb/MicroWARP）。

**选择建议**：如果你能控制 Docker 权限，并且希望获得更接近原生 WireGuard 的性能，可以选择 `kernel`。如果部署平台不允许 `NET_ADMIN`，不要选此模式。

### 3. usque（MASQUE/QUIC）

**原理**：`usque` 是 Cloudflare WARP MASQUE 协议的 Go 实现，基于 RFC 9484 MASQUE，在 QUIC 连接上建立代理隧道。相比传统 WireGuard，它更接近现代 HTTP/3/QUIC 网络形态，协议伪装能力更强。

**依赖**：

- `usque` 二进制。
- `usque` 配置文件，默认查找 `/app/data/usque-config.json` 或当前目录 `config.json`。

**端口**：

- SOCKS5：默认 `127.0.0.1:1080`。
- HTTP：可选，通过 `warp_http_port` / `WARP_HTTP_PORT` 启用。

**启动命令格式**：

```bash
usque -c config.json socks --bind 127.0.0.1 --port 1080
```

如启用 HTTP 代理，会额外启动：

```bash
usque -c config.json http-proxy --bind 127.0.0.1 --port 8080
```

**注册逻辑**：如果配置文件不存在，SouWen 会尝试执行 `usque -c /app/data/usque-config.json register` 自动注册。注册失败时通常是依赖缺失、网络受限或触发服务端速率限制。

**特色**：

- 支持 SOCKS5 + HTTP 双代理。
- 无需内核权限。
- 协议伪装能力强，适合传统 WireGuard 容易受限的网络环境。

**配置示例**：

```bash
WARP_ENABLED=1
WARP_MODE=usque
WARP_SOCKS_PORT=1080
WARP_HTTP_PORT=8080
WARP_USQUE_CONFIG=/app/data/usque-config.json
```

```yaml
warp_enabled: true
warp_mode: usque
warp_socks_port: 1080
warp_http_port: 8080
warp_usque_config: /app/data/usque-config.json
```

**参考**：usque（github.com/Diniboy1123/usque）。

**选择建议**：如果你的网络对 WireGuard UDP 特征不友好，或者希望同时提供 SOCKS5 和 HTTP 代理，优先尝试 `usque`。

### 4. warp-cli（官方客户端）

**原理**：启动 Cloudflare 官方 `warp-svc` 守护进程，使用 `warp-cli` 注册、切换到 `proxy` 模式并连接 WARP。官方客户端默认在 `127.0.0.1:40000` 暴露代理，上层再用 GOST 转发为 SouWen 需要的 SOCKS5/HTTP 端口。

**依赖**：

- `warp-cli` 和 `warp-svc`。
- `gost`。

**端口**：

- `warp-cli proxy` 上游：`socks5://127.0.0.1:40000`。
- SouWen SOCKS5：默认 `127.0.0.1:1080`，由 GOST 监听。
- SouWen HTTP：可选，由 GOST 额外监听。

**GOST 转发注意事项**：GOST 必须显式配置上游转发到 `warp-cli` 代理。例如：

```bash
gost -L socks5://127.0.0.1:1080 -F socks5://127.0.0.1:40000
```

同时启用 HTTP 时，Python 管理器会生成类似：

```bash
gost \
  -L socks5://127.0.0.1:1080 -F socks5://127.0.0.1:40000 \
  -L http://127.0.0.1:8080 -F socks5://127.0.0.1:40000
```

**特色**：

- 功能最全，贴近 Cloudflare 官方行为。
- 支持 `warp_license_key` / `WARP_LICENSE_KEY` 配置 WARP+ License。
- 支持 `warp_team_token` / `WARP_TEAM_TOKEN` 配置 ZeroTrust Team Token。
- 支持 `warp_gost_args` / `WARP_GOST_ARGS` 完全自定义 GOST 参数。

**重要限制**：当前默认 Dockerfile 预装的是 `wgcf`、`wireproxy`、`usque`、`microsocks` 和 `wireguard-tools`，并未预装 `warp-cli` 与 `gost`。如需使用 `warp-cli` 模式，应基于 SouWen 镜像自定义安装官方客户端和 GOST，或在宿主机直接安装后运行。

**配置示例**：

```bash
WARP_ENABLED=1
WARP_MODE=warp-cli
WARP_SOCKS_PORT=1080
WARP_HTTP_PORT=8080
WARP_LICENSE_KEY=xxxxx
# 或 ZeroTrust
WARP_TEAM_TOKEN=xxxxx
# 可选：完全自定义 GOST
WARP_GOST_ARGS='-L socks5://127.0.0.1:1080 -F socks5://127.0.0.1:40000'
```

**参考**：warp-docker（github.com/cmj2002/warp-docker）。

**选择建议**：仅当你明确需要 WARP+、ZeroTrust 或官方客户端特性时选择此模式。普通代理出口场景下，`wireproxy`、`kernel` 或 `usque` 更轻量。

### 5. external（外部代理）

**原理**：SouWen 不启动任何本地 WARP 进程，只读取 `warp_external_proxy` / `WARP_EXTERNAL_PROXY` 指向的外部代理地址，并把内部代理配置切换到该地址。外部代理可以是独立 WARP 容器、宿主机代理、同一 compose 网络里的 sidecar，或专门维护的代理服务。

**无需本地进程**：此模式不会启动 `wireproxy`、`wg-quick`、`usque`、`warp-cli` 或 GOST。Python 管理器只会做外部代理连通性验证，并记录状态。

**适用场景**：

- docker-compose sidecar 架构。
- 多个应用共享同一个 WARP 代理。
- 希望 WARP 组件独立升级、独立重启。
- 部署平台不允许主应用容器申请网络特权。

**配置示例**：

```bash
WARP_ENABLED=1
WARP_MODE=external
WARP_EXTERNAL_PROXY=socks5://warp:1080
```

```yaml
warp_enabled: true
warp_mode: external
warp_external_proxy: socks5://warp:1080
```

**docker-compose 示例片段**：

```yaml
services:
  souwen:
    image: your-souwen-image
    environment:
      WARP_ENABLED: "1"
      WARP_MODE: external
      WARP_EXTERNAL_PROXY: socks5://warp:1080
    depends_on:
      - warp

  warp:
    image: your-warp-proxy-image
    expose:
      - "1080"
```

**选择建议**：如果你的部署已经有成熟的 WARP sidecar，或者想让 SouWen 主容器保持最小权限，`external` 是最清晰的方案。

## Docker vs 直接运行

### Docker 环境

Docker 启动时，`entrypoint.sh` 会加载 `/usr/local/bin/warp-init.sh`。当 `WARP_ENABLED=1` 时，脚本会读取环境变量，选择或检测模式，并启动对应代理。启动成功后会写入状态文件：

```text
/run/souwen-warp.json
```

状态包含：`owner`、`mode`、`status`、`socks_port`、`http_port`、`pid`、`interface`、`ip`、`protocol`、`proxy_type` 等字段。`owner=shell` 表示代理由 shell 初始化脚本启动；后续 Python 管理器可读取该状态进行展示和协调。

默认 Dockerfile 已预装：

- `wgcf`
- `wireproxy`
- `usque`
- `microsocks`
- `wireguard-tools`

因此默认镜像最适合 `wireproxy`、`usque` 和在具备权限时的 `kernel`。`warp-cli` 模式需额外安装官方客户端和 GOST。

### 直接运行

直接运行 SouWen 时，WARP 生命周期由 Python `WarpManager` 管理，可通过 API 或 CLI 动态控制：

- API：`/api/v1/admin/warp/*`
- CLI：`souwen warp ...`

直接运行不会自动具备 Docker 中的数据卷路径和预装二进制，需确保相关命令已在 `PATH` 中，或通过配置项指定路径。例如 `usque` 可用 `warp_usque_path` 指定二进制路径。

## 自动模式选择

`auto` 模式会按可用性自动选择最优方案，降级链如下：

```text
external（如已配置 warp_external_proxy）
  → usque（usque 可执行文件可用）
  → wireproxy（wireproxy 可执行文件可用）
  → kernel（wg-quick + microsocks + /dev/net/tun 可用）
  → none（无可用组件）
```

选择逻辑强调“优先使用已显式配置的外部代理，其次选择 MASQUE/QUIC，再回落到最通用的 wireproxy，最后尝试内核模式”。如果你希望稳定固定某种方案，建议不要使用 `auto`，而是显式设置 `warp_mode`。

## 配置参数

以下字段来自 SouWen 配置模型，可通过 YAML、环境变量或相关配置加载机制使用：

| 配置字段 | 环境变量 | 类型 / 默认值 | 说明 |
|---|---|---|---|
| `warp_enabled` | `WARP_ENABLED` | `bool`，默认 `false` | 是否启用 WARP 代理。Docker 初始化脚本仅在 `WARP_ENABLED=1` 时启动。 |
| `warp_mode` | `WARP_MODE` | `str`，默认 `auto` | 模式：`auto`、`wireproxy`、`kernel`、`usque`、`warp-cli`、`external`。 |
| `warp_socks_port` | `WARP_SOCKS_PORT` | `int`，默认 `1080` | 本地 SOCKS5 监听端口。 |
| `warp_bind_address` | `WARP_BIND_ADDRESS` | `str`，默认 `127.0.0.1` | SOCKS5/HTTP 代理监听地址；`0.0.0.0` 允许外部访问，建议同时配置代理认证。 |
| `warp_startup_timeout` | `WARP_STARTUP_TIMEOUT` | `int`，默认 `15` | WARP 启动后的健康检查等待秒数。 |
| `warp_device_name` | `WARP_DEVICE_NAME` | `str | None` | 注册 WARP 账号时使用的设备名称或标识。 |
| `warp_endpoint` | `WARP_ENDPOINT` | `str | None` | 自定义 WARP Endpoint，例如 `162.159.192.1:4500`，用于规避特定网络限制。 |
| `warp_usque_path` | 可按配置映射 | `str | None` | `usque` 二进制路径；为空时从 `PATH` 查找。 |
| `warp_usque_config` | `WARP_USQUE_CONFIG` | `str | None` | `usque config.json` 路径；为空时查找 `/app/data/usque-config.json` 或当前目录 `config.json`。 |
| `warp_usque_transport` | `WARP_USQUE_TRANSPORT` | `str`，默认 `auto` | `usque` 传输模式：`auto`（QUIC 优先，失败回退 HTTP/2）、`quic`、`http2`。 |
| `warp_http_port` | `WARP_HTTP_PORT` | `int`，默认 `0` | HTTP 代理端口；`0` 表示不启用。适用于 `usque` 和 `warp-cli`。 |
| `warp_license_key` | `WARP_LICENSE_KEY` | `str | None` | WARP+ License Key，仅 `warp-cli` 注册流程使用。 |
| `warp_team_token` | `WARP_TEAM_TOKEN` | `str | None` | ZeroTrust Team Token（JWT），仅 `warp-cli` 注册组织时使用。 |
| `warp_proxy_username` / `warp_proxy_password` | `WARP_PROXY_USERNAME` / `WARP_PROXY_PASSWORD` | `str | None` | SOCKS5/HTTP 代理认证账号密码；绑定 `0.0.0.0` 时建议配置。 |
| `warp_gost_args` | `WARP_GOST_ARGS` | `str | None` | 自定义 GOST 启动参数；设置后会覆盖默认 GOST 监听和转发参数。 |
| `warp_external_proxy` | `WARP_EXTERNAL_PROXY` | `str | None` | 外部代理地址，如 `socks5://warp:1080` 或 `http://proxy:8080`。 |

## API 端点

WARP 管理端点挂载在 `/api/v1/admin` 下，需要管理认证：

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/admin/warp` | 获取当前 WARP 状态，包括模式、端口、PID、出口 IP、协议、代理类型和可用模式。 |
| `GET` | `/api/v1/admin/warp/modes` | 列出 5 种模式的可用性、协议、权限要求、代理类型和描述。 |
| `POST` | `/api/v1/admin/warp/enable` | 启用 WARP。查询参数：`mode`、`socks_port`、`http_port`、`endpoint`。 |
| `POST` | `/api/v1/admin/warp/register` | 注册新 WARP 账号。查询参数：`backend=wgcf|usque`。 |
| `POST` | `/api/v1/admin/warp/test` | 测试当前代理连通性，返回出口 IP、端口、模式、协议和代理类型。 |
| `GET` | `/api/v1/admin/warp/config` | 获取 WARP 相关配置；敏感值只返回是否存在或脱敏地址。 |
| `POST` | `/api/v1/admin/warp/disable` | 禁用 WARP，清理进程、接口和 SouWen 内部代理配置。 |

示例：

```bash
curl -X POST 'http://127.0.0.1:49265/api/v1/admin/warp/enable?mode=usque&socks_port=1080&http_port=8080'
```

## CLI 命令

SouWen 提供 `souwen warp` 子命令组：

| 命令 | 说明 |
|---|---|
| `souwen warp status` | 显示当前 WARP 状态、模式、端口、PID、协议、代理类型和可用模式。 |
| `souwen warp enable --mode auto --socks-port 1080` | 启用 WARP。`--mode` 支持 5 种模式和 `auto`；`--endpoint` 可指定自定义 Endpoint。 |
| `souwen warp disable` | 关闭 WARP，终止进程并清理代理配置。 |
| `souwen warp modes` | 以表格列出所有模式的安装状态、协议、权限要求和说明。 |
| `souwen warp register --backend wgcf` | 使用 `wgcf` 注册 WireGuard 配置。 |
| `souwen warp register --backend usque` | 使用 `usque` 注册 MASQUE 配置。 |
| `souwen warp test` | 测试当前 WARP SOCKS5 代理是否可用，并显示出口 IP。 |

常用示例：

```bash
# 查看可用模式
souwen warp modes

# 自动选择并启用
souwen warp enable --mode auto --socks-port 1080

# 使用 usque
souwen warp enable --mode usque --socks-port 1080

# 注册 wgcf 配置
souwen warp register --backend wgcf

# 测试代理
souwen warp test
```

## 选择建议

- **想要最省心**：选 `wireproxy`。
- **想要性能最好，且能给容器网络权限**：选 `kernel`。
- **网络限制较多或需要 HTTP 代理端口**：选 `usque`。
- **需要 WARP+ / ZeroTrust / 官方客户端行为**：选 `warp-cli`，但要准备自定义运行环境。
- **已有独立 WARP 服务或希望主容器零特权**：选 `external`。

生产环境建议优先从 `external` 或 `wireproxy` 开始，确认业务可用后再根据性能、网络限制和运维架构切换到 `kernel`、`usque` 或 `warp-cli`。
