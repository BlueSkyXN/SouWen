/**
 * 文件用途：可视化编辑器的字段/节定义 Schema。
 * 定义所有 souwen.yaml 可编辑节（paper/patent/web/mcp/general/server/warp）
 * 及其字段（key、类型、标签、占位符）。
 */

export type FieldType = 'text' | 'password' | 'number' | 'boolean' | 'url' | 'email' | 'yaml'

export interface FieldDef {
  key: string
  type: FieldType
  label: string
  placeholder?: string
}

export interface SectionDef {
  key: string
  titleI18nKey: string
  fields: FieldDef[]
}

export const YAML_SECTIONS: SectionDef[] = [
  {
    key: 'paper',
    titleI18nKey: 'config.visualSectionPaper',
    fields: [
      { key: 'openalex_email', type: 'email', label: 'OpenAlex Email' },
      { key: 'semantic_scholar_api_key', type: 'password', label: 'Semantic Scholar API Key' },
      { key: 'core_api_key', type: 'password', label: 'CORE API Key' },
      { key: 'openaire_api_key', type: 'password', label: 'OpenAIRE API Key' },
      { key: 'doaj_api_key', type: 'password', label: 'DOAJ API Key' },
      { key: 'zenodo_access_token', type: 'password', label: 'Zenodo Access Token' },
      { key: 'pubmed_api_key', type: 'password', label: 'PubMed API Key' },
      { key: 'unpaywall_email', type: 'email', label: 'Unpaywall Email' },
      { key: 'ieee_api_key', type: 'password', label: 'IEEE API Key' },
    ],
  },
  {
    key: 'patent',
    titleI18nKey: 'config.visualSectionPatent',
    fields: [
      { key: 'uspto_api_key', type: 'password', label: 'USPTO API Key' },
      { key: 'epo_consumer_key', type: 'password', label: 'EPO Consumer Key' },
      { key: 'epo_consumer_secret', type: 'password', label: 'EPO Consumer Secret' },
      { key: 'cnipa_client_id', type: 'password', label: 'CNIPA Client ID' },
      { key: 'cnipa_client_secret', type: 'password', label: 'CNIPA Client Secret' },
      { key: 'lens_api_token', type: 'password', label: 'The Lens API Token' },
      { key: 'patsnap_api_key', type: 'password', label: 'PatSnap API Key' },
    ],
  },
  {
    key: 'web',
    titleI18nKey: 'config.visualSectionWeb',
    fields: [
      { key: 'searxng_url', type: 'url', label: 'SearXNG URL', placeholder: 'http://localhost:8080' },
      { key: 'tavily_api_key', type: 'password', label: 'Tavily API Key' },
      { key: 'exa_api_key', type: 'password', label: 'Exa API Key' },
      { key: 'serper_api_key', type: 'password', label: 'Serper API Key' },
      { key: 'brave_api_key', type: 'password', label: 'Brave Search API Key' },
      { key: 'serpapi_api_key', type: 'password', label: 'SerpAPI API Key' },
      { key: 'firecrawl_api_key', type: 'password', label: 'Firecrawl API Key' },
      { key: 'perplexity_api_key', type: 'password', label: 'Perplexity API Key' },
      { key: 'linkup_api_key', type: 'password', label: 'Linkup API Key' },
      { key: 'scrapingdog_api_key', type: 'password', label: 'ScrapingDog API Key' },
      { key: 'metaso_api_key', type: 'password', label: 'Metaso (秘塔) API Key' },
      { key: 'zhipuai_api_key', type: 'password', label: '智谱 AI API Key' },
      { key: 'aliyun_iqs_api_key', type: 'password', label: '阿里云 IQS API Key' },
      { key: 'whoogle_url', type: 'url', label: 'Whoogle URL', placeholder: 'http://localhost:5000' },
      { key: 'websurfx_url', type: 'url', label: 'Websurfx URL', placeholder: 'http://localhost:8080' },
      { key: 'github_token', type: 'password', label: 'GitHub Token' },
      { key: 'stackoverflow_api_key', type: 'password', label: 'StackOverflow API Key' },
      { key: 'youtube_api_key', type: 'password', label: 'YouTube Data API Key' },
      { key: 'jina_api_key', type: 'password', label: 'Jina Reader API Key' },
      { key: 'scrapfly_api_key', type: 'password', label: 'Scrapfly API Key' },
      { key: 'diffbot_api_token', type: 'password', label: 'Diffbot API Token' },
      { key: 'scrapingbee_api_key', type: 'password', label: 'ScrapingBee API Key' },
      { key: 'zenrows_api_key', type: 'password', label: 'ZenRows API Key' },
      { key: 'scraperapi_api_key', type: 'password', label: 'ScraperAPI API Key' },
      { key: 'apify_api_token', type: 'password', label: 'Apify API Token' },
      { key: 'cloudflare_api_token', type: 'password', label: 'Cloudflare API Token' },
      { key: 'cloudflare_account_id', type: 'text', label: 'Cloudflare Account ID' },
      { key: 'feishu_app_id', type: 'text', label: '飞书 App ID' },
      { key: 'feishu_app_secret', type: 'password', label: '飞书 App Secret' },
      { key: 'twitter_bearer_token', type: 'password', label: 'Twitter Bearer Token' },
      { key: 'reddit_client_id', type: 'text', label: 'Reddit Client ID' },
      { key: 'reddit_client_secret', type: 'password', label: 'Reddit Client Secret' },
    ],
  },
  {
    key: 'mcp',
    titleI18nKey: 'config.visualSectionMcp',
    fields: [
      { key: 'mcp_server_url', type: 'url', label: 'MCP Server URL', placeholder: 'https://mcp.example.com/mcp' },
      { key: 'mcp_transport', type: 'text', label: 'MCP Transport', placeholder: 'streamable_http' },
      { key: 'mcp_fetch_tool_name', type: 'text', label: 'MCP Fetch Tool Name', placeholder: 'fetch' },
    ],
  },
  {
    key: 'general',
    titleI18nKey: 'config.visualSectionGeneral',
    fields: [
      { key: 'proxy', type: 'url', label: 'HTTP 代理', placeholder: 'http://127.0.0.1:7890' },
      { key: 'timeout', type: 'number', label: '请求超时 (秒)' },
      { key: 'max_retries', type: 'number', label: '最大重试次数' },
      { key: 'data_dir', type: 'text', label: '数据目录', placeholder: '~/.local/share/souwen' },
      { key: 'default_http_backend', type: 'text', label: '默认 HTTP 后端', placeholder: 'auto' },
    ],
  },
  {
    key: 'server',
    titleI18nKey: 'config.visualSectionServer',
    fields: [
      { key: 'api_password', type: 'password', label: 'API 密码（旧版）' },
      { key: 'user_password', type: 'password', label: '用户密码' },
      { key: 'admin_password', type: 'password', label: '管理密码' },
      { key: 'guest_enabled', type: 'boolean', label: '允许游客访问' },
      { key: 'expose_docs', type: 'boolean', label: '暴露 API 文档' },
    ],
  },
  {
    key: 'warp',
    titleI18nKey: 'config.visualSectionWarp',
    fields: [
      { key: 'warp_enabled', type: 'boolean', label: '启用 WARP' },
      { key: 'warp_mode', type: 'text', label: 'WARP 模式', placeholder: 'auto' },
      { key: 'warp_socks_port', type: 'number', label: 'WARP SOCKS5 端口' },
      { key: 'warp_endpoint', type: 'text', label: 'WARP 端点', placeholder: '162.159.192.1:4500' },
    ],
  },
]
