# SouWen

中文 | **[English](README.en.md)**

> Free search & fetch for AI agents: two actions (`search`, `fetch`), two entries
> (MCP + HTTP API), and one core skill — making free sources actually work behind
> WARP, proxies, and a headless browser.

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-3.0.0a1-orange)](CHANGELOG.md)

**Author**: [@BlueSkyXN](https://github.com/BlueSkyXN) · **Repository**: [github.com/BlueSkyXN/SouWen](https://github.com/BlueSkyXN/SouWen) · **License**: [GPLv3](LICENSE)

> **Disclaimer: for learning and technical research only.** Do not use it in violation of
> applicable laws or third-party terms of service. All data comes from the public endpoints
> of each source; SouWen never proxies credential-gated content.

---

## Overview

SouWen does exactly two things:

- **`search(query, domain, limit)`** — concurrently queries several free sources in one
  domain, merges and dedupes by normalized URL, and falls through to the next batch of
  sources on failure. Domains: `web`, `news`, `paper`, `patent`, `book`, `code`,
  `community`, `wiki`, `images`, `videos`.
- **`fetch(url, max_chars, start)`** — retrieves a page's main content (Markdown); long
  pages continue via `start`. A site handler (arxiv paper pages) runs first, then generic
  fetch, with wayback as the unreachable-page fallback.

Underneath sits an egress ladder: `direct → impersonate (curl_cffi fingerprints) →
proxy (WARP / user proxy) → browser (Playwright Chromium)`. The most common death of a
free source is a datacenter-IP block — the ladder escalates within a single request and
the process remembers the last working level per host. Missing Chromium or a proxy simply
skips that level.

<!-- BEGIN AUTO: SOURCE METRICS -->
- **36 built-in Provider v2 packages** and **36 capability adapters**.
  - Search: **32** packages · LLM Search: **0** · Fetch: **4**.
<!-- END AUTO: SOURCE METRICS -->

## MCP

stdio (Claude Code, Codex, and other hosts):

```json
{
  "mcpServers": {
    "souwen": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/BlueSkyXN/SouWen@agent-first", "souwen", "mcp"]
    }
  }
}
```

The MCP server exposes exactly two tools: `search(query, domain="web", limit=8)` and
`fetch(url, max_chars=20000, start=0)`. Source status travels as the `souwen://sources`
resource.

## HTTP API

```bash
pip install "souwen[server,mcp]"   # or docker (below)
souwen serve --port 8000
```

| Route | Description |
|---|---|
| `POST /search` | `{"query": "...", "domain": "web", "limit": 8}` → `{"results": [...], "sources": [...], "partial": bool}` |
| `POST /fetch` | `{"url": "...", "max_chars": 20000, "start": 0}` → `{"title", "url", "content", "total_chars", "start", "next_start", "egress"}` |
| `GET /sources` | per-source domain and availability |
| `GET /healthz` | probe |
| `/mcp` | MCP streamable HTTP |

Auth: set `user_password` (env `SOUWEN_USER_PASSWORD`) and send
`Authorization: Bearer <password>` or `X-SouWen-Token`. Unset or invalid credentials
get 401 (fail-closed); set `user_password` to an empty string `""` to open the
endpoint explicitly.

## Python

```python
from souwen import search, fetch

results = await search("attention is all you need", domain="paper", limit=8)
page = await fetch("https://arxiv.org/abs/1706.03762", max_chars=20000)
```

## Install & deploy

```bash
pip install "souwen[tls,web]"          # library
pip install "souwen[mcp]"              # MCP server
pip install "souwen[server,tls,web,robots,scraper]"  # HTTP service (incl. /mcp)
pip install "souwen[browser]" && playwright install chromium  # browser egress

docker build -t souwen . && docker run -p 49265:49265 -e SOUWEN_USER_PASSWORD=... souwen
```

## Configuration

Zero-key sources run with no configuration. `souwen.example.yaml` is the full template:
search candidate order (`search_defaults`, refreshed from the census), WARP modes
(wireproxy / usque / external), and per-source overrides
(`sources.<id>.{enabled, proxy, timeout, api_key, ...}`).
Needs-free-key sources (patentsview, epo_ops, uspto_odp, youtube) ship disabled and
activate once their key is configured.

## Sources & census

36 surviving sources (32 search + 4 fetch) are probed weekly by `census.yml` in the
authoritative environment (image build, WARP on, zero keys): sources / domains / fetch
modes with PASS/WARN/FAIL verdicts; the reports feed
[docs/sources.md](docs/sources.md). Sources that fail their retests are deleted — this
repository does not keep sources it has not verified.

## Architecture

```
src/souwen/
  agent.py          facade: search / fetch / sources (shared by MCP, HTTP, Python)
  cli.py            souwen mcp | serve | doctor
  modules/search    domain selection, concurrency, dedupe, fallback, compact projection
  modules/fetch     site handlers → generic fetch → extractor chain → paginated cache
  common_runtime/   transport, egress ladder, SSRF, rate limiting, WARP support
  providers/        one package per source (declaration + spec + adapter) + private clients
  server/           FastAPI routes, auth, limiter, MCP server, doctor
```

SSRF validation (`common_runtime/security/fetch_target.py`) is non-negotiable: HTTP and
browser traffic (every redirect hop) is validated before connecting, and browser traffic
is pinned to the validated IP through a loopback proxy.

## License

[GPLv3](LICENSE)
