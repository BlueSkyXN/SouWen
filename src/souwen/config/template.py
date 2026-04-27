"""默认配置模板

涵盖主要字段，详见 souwen.example.yaml 获取完整示例。
"""

from __future__ import annotations

_DEFAULT_CONFIG_TEMPLATE = """\
# SouWen 配置文件(自动生成)
# 优先级:环境变量 > ./souwen.yaml > ~/.config/souwen/config.yaml > .env > 默认值

# ===== 论文数据源 =====
paper:
  openalex_email: ~
  semantic_scholar_api_key: ~
  core_api_key: ~
  pubmed_api_key: ~
  unpaywall_email: ~
  ieee_api_key: ~
  openaire_api_key: ~
  doaj_api_key: ~
  zenodo_access_token: ~

# ===== 专利数据源 =====
patent:
  uspto_api_key: ~
  epo_consumer_key: ~
  epo_consumer_secret: ~
  cnipa_client_id: ~
  cnipa_client_secret: ~
  lens_api_token: ~
  patsnap_api_key: ~

# ===== 常规搜索 =====
web:
  searxng_url: ~
  tavily_api_key: ~
  exa_api_key: ~
  serper_api_key: ~
  brave_api_key: ~
  serpapi_api_key: ~
  firecrawl_api_key: ~
  perplexity_api_key: ~
  linkup_api_key: ~
  scrapingdog_api_key: ~
  metaso_api_key: ~
  whoogle_url: ~
  websurfx_url: ~
  zhipuai_api_key: ~
  aliyun_iqs_api_key: ~
  github_token: ~
  stackoverflow_api_key: ~
  youtube_api_key: ~
  bilibili_sessdata: ""
  jina_api_key: ~
  scrapfly_api_key: ~
  diffbot_api_token: ~
  scrapingbee_api_key: ~
  zenrows_api_key: ~
  scraperapi_api_key: ~
  apify_api_token: ~
  cloudflare_api_token: ~
  cloudflare_account_id: ~
  feishu_app_id: ~
  feishu_app_secret: ~

# ===== 通用设置 =====
general:
  proxy: ~
  proxy_pool: []
  timeout: 30
  max_retries: 3
  data_dir: ~/.local/share/souwen
  default_http_backend: auto
  http_backend: {}

# ===== 服务 =====
server:
  # 旧版统一密码（同时作用于用户和管理端点，向后兼容）
  api_password: ~
  # 用户密码（保护搜索+只读管理端点，优先于 api_password）
  user_password: ~
  # 管理密码（保护全部管理端点，优先于 api_password）
  admin_password: ~
  # 旧版访客密码（已映射为 user_password 别名，向后兼容）
  # visitor_password: ~
  # 是否启用游客访问（无 Token 也可访问搜索端点，受限源+限速）
  guest_enabled: false
  # 允许跨域的来源列表（CORS Origins），留空表示不启用 CORS
  cors_origins: []
  # 受信反向代理 IP/CIDR 列表;只有来自这些地址的请求才会读取 X-Forwarded-For
  # 解析真实客户端 IP.不在此列表的直连客户端的 XFF 头将被忽略,避免伪造.
  # 示例: ["10.0.0.0/8", "172.16.0.0/12", "127.0.0.1"]
  trusted_proxies: []
  # 是否暴露 /docs、/redoc、/openapi.json;生产建议设为 false
  expose_docs: true

# ===== WARP 代理 =====
# 内嵌 Cloudflare WARP 代理(Docker 部署专用)
# 详见 scripts/warp-init.sh
warp:
  warp_enabled: false
  warp_mode: auto         # auto | wireproxy | kernel | usque | warp-cli | external
  warp_socks_port: 1080
  warp_endpoint: ~        # 自定义 Endpoint (如 162.159.192.1:4500)
  warp_bind_address: 127.0.0.1  # 代理绑定地址
  warp_startup_timeout: 15      # 启动健康检查超时(秒)
  warp_device_name: ~           # 注册设备名
  warp_proxy_username: ~        # SOCKS5/HTTP 代理认证用户名
  warp_proxy_password: ~        # SOCKS5/HTTP 代理认证密码
  # usque 模式
  warp_usque_path: ~      # usque 二进制路径(默认从 PATH 查找)
  warp_usque_config: ~    # usque config.json 路径
  warp_usque_transport: auto  # auto | quic | http2
  warp_usque_system_dns: false    # 使用系统 DNS（不走隧道 DNS）
  warp_usque_on_connect: ~        # 连接成功后执行的脚本路径
  warp_usque_on_disconnect: ~     # 连接断开后执行的脚本路径
  warp_http_port: 0       # HTTP 代理端口(usque/warp-cli 模式,0=不启用)
  # warp-cli 模式
  warp_license_key: ~     # WARP+ License Key
  warp_team_token: ~      # ZeroTrust Team Token (JWT)
  warp_gost_args: ~       # 自定义 GOST 启动参数
  # external 模式
  warp_external_proxy: ~  # 外部 WARP 代理地址(如 socks5://warp:1080)

# ===== 数据源频道配置 =====
# 按源名称配置,覆盖全局默认值.
# 可用字段: enabled, proxy, http_backend, base_url, api_key, headers, params
# proxy 取值: inherit(继承全局) | none | warp | socks5://... | http://...
# 示例:
# sources:
#   duckduckgo:
#     enabled: true
#     proxy: warp
#     http_backend: curl_cffi
#   tavily:
#     api_key: tvly-xxxx
#     params:
#       search_depth: advanced
#   google_patents:
#     enabled: false
sources: {}
"""
