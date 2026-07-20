# SouWen 搜文

中文 | **English**

> A unified search, fetching, and archive toolkit for AI Agents and automation scripts.

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0rc1-orange)](CHANGELOG.md)

**Author**: [@BlueSkyXN](https://github.com/BlueSkyXN) · **Repository**: [github.com/BlueSkyXN/SouWen](https://github.com/BlueSkyXN/SouWen) · **License**: [GPLv3](LICENSE)

> **⚠️ Disclaimer: This project is for Python learning and technical research only.** It covers API aggregation, full-stack development (FastAPI + React), web scraping (TLS fingerprinting / anti-bot bypass), CLI, and async programming. Do not use it in ways that violate laws or third-party terms of service.

---

## 📖 Table of Contents

- [Introduction](#-introduction)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Configuration](#️-configuration)
- [Architecture](#-architecture)
- [Deployment](#-deployment)
- [Documentation](#-documentation)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🎯 Introduction

SouWen provides AI Agents, CLI scripts, and server applications with a unified multi-source search interface. **All data sources are declared through a single `SourceAdapter` registry**, normalized into Pydantic v2 data models.

The registry architecture reduces the cost of adding a new source to **1-2 code changes**; CLI / API / Panel are organized by domain, capability, and Source Catalog.

### Features

<!-- BEGIN AUTO: SOURCE METRICS -->
- **95 registered built-in sources**: **94 public** Source Catalog entries and **1 hidden/internal** entry. Runtime plugins may append additional entries.
  - Public sources by primary domain: `paper` 18 · `patent` 8 · `web` 30 · `social` 5 · `video` 2 · `knowledge` 1 · `developer` 2 · `cn_tech` 9 · `office` 1 · `archive` 1
  - `fetch` cross-cutting view: **24 providers** = **17 primary fetch-domain** + **7 cross-domain** sources.
<!-- END AUTO: SOURCE METRICS -->
- **Unified Pydantic v2 models**: `PaperResult` / `PatentResult` / `WebSearchResult` / `FetchResult` / `WaybackCDXResponse` / …
- **Async-first**: httpx + asyncio, per-loop Semaphore concurrency control
- **Smart rate limiting**: Token Bucket + sliding window, per-source isolation
- **curl_cffi TLS fingerprinting**: 15+ scraper sources use browser fingerprints to bypass anti-bot
- **WARP five-mode proxy**: wireproxy / kernel / usque / warp-cli / external, with runtime install and management support
- **MCP protocol**: callable by Claude Code / Cursor / Windsurf and other AI assistants
- **Multi-skin Web UI**: souwen-google (default) / souwen-nebula / carbon / apple / ios (SCSS Modules + Zustand)

## 📦 Installation

```bash
# Install the current main source line
git clone https://github.com/BlueSkyXN/SouWen.git
cd SouWen
pip install -e .

# Zero-key / minimal dependency experience (includes MCP client and stdio server)
pip install -e ".[edition-basic]"

# Default API server + MCP + TLS fingerprinting + web search
pip install -e ".[edition-pro]"

# Full public heavy runtime; crawl4ai and scrapling are currently mutually exclusive.
pip install -e ".[edition-full-crawl4ai]"
pip install -e ".[edition-full-scrapling]"
```

## 🚀 Quick Start

### CLI

```bash
# Multi-source search
souwen search paper "transformer"
souwen search patent "quantum computing"
souwen search web "python asyncio"

# Fetch & platform commands
souwen fetch https://example.com
souwen youtube trending
souwen bilibili search "programming"
souwen wayback cdx https://example.com

# Management
souwen sources --available-only          # Require both the static gate and current runtime
souwen sources --json                    # Output the same Source Catalog shape as /api/v1/sources
souwen serve                             # Start API server (default :8000)
souwen doctor                            # Static check (live=false by default; no network)
souwen mcp                               # MCP server info
```

### Python Library

```python
import asyncio
from souwen import search_papers, search_patents

async def main():
    # Convenience entry point
    resp = await search_papers("quantum computing", per_page=5)
    for r in resp[0].results:
        print(r.title, "—", r.doi)

    # Application API
    from souwen.search import search, search_all
    from souwen.web.fetch import fetch_content
    from souwen.web.wayback import WaybackClient

    # Dispatch by domain + capability
    papers = await search("transformer", domain="paper", limit=5)
    articles = await search("AI news", domain="web", capability="search_news")
    results = await search_all("quantum", domains=["paper", "web", "knowledge"])

    # Fetch
    resp = await fetch_content(["https://example.com"], providers=["builtin"])

    # Wayback archive
    async with WaybackClient() as wayback:
        snapshots = await wayback.query_snapshots("https://example.com")

asyncio.run(main())
```

### API Server

```bash
SOUWEN_ADMIN_PASSWORD=adminpass souwen serve --host 0.0.0.0 --port 8000
```

Main endpoints:

```bash
curl "http://localhost:8000/api/v1/search/paper?q=transformer&per_page=5"
curl "http://localhost:8000/api/v1/search/web?q=python"
curl "http://localhost:8000/api/v1/fetch" \
  -H "Authorization: Bearer adminpass" \
  -H "Content-Type: application/json" \
  -d '{"urls":["https://example.com"]}'
curl "http://localhost:8000/api/v1/wayback/cdx?url=https://example.com"
curl "http://localhost:8000/api/v1/sources"
```

`/api/v1/fetch`, `/api/v1/links`, and `/api/v1/sitemap` are admin-protected fetch capabilities and require an Admin Bearer token. Search endpoints and `/api/v1/sources` can be protected separately with `SOUWEN_USER_PASSWORD`.

Visit `/docs` for the full OpenAPI documentation; visit `/panel#/` to enter the Web UI (default: souwen-google skin). `/` redirects to `/docs` with the default configuration.

## ⚙️ Configuration

Config priority: env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > defaults.

Run `souwen config init` to generate a `./souwen.yaml` template in the current directory. Copy it to `~/.config/souwen/config.yaml` if you want a user-level config.

## 🏗 Architecture

Three-layer separation: **Presentation (CLI / Server / Panel / Integrations) → Application API (`souwen.search` / `souwen.web.fetch` / `souwen.web.wayback`) → Registry + concrete client modules + Platform (`core`)**.

See [docs/architecture.md](docs/architecture.md) for details.

```
src/souwen/
├── core/              Platform: http_client / scraper / rate_limiter / retry / …
├── registry/          Single source of truth: adapter / sources / loader / views
├── paper/             Paper clients
├── patent/            8 patent clients
├── web/               Search, social, video, knowledge, office, fetch, and archive clients
├── cli/ (subpackage)  CLI commands (organized by domain)
└── server/            FastAPI application
```

## 🧩 Plugin System

SouWen supports extending data sources and fetch providers via external Python packages.
Plugins integrate through setuptools `entry_points` or the `plugins` field in `souwen.yaml`,
without modifying SouWen's codebase.

Three equivalent entry points are provided for managing plugins at runtime:

- **Web Panel** — `/plugins` route: list, enable/disable, run `health_check`, install/uninstall
- **CLI** — `souwen plugins list/info/enable/disable/health/reload/install/uninstall/new`
- **HTTP API** — `/api/v1/admin/plugins/*` (see [docs/api-reference.md](docs/api-reference.md))

> Install/uninstall is gated by `SOUWEN_ENABLE_PLUGIN_INSTALL=1`; disabled by default.

Docs:

- Integration spec (plugin authors): [docs/plugin-integration-spec.md](docs/plugin-integration-spec.md)
- Operations guide: [docs/plugin-management.md](docs/plugin-management.md)

## 🚢 Deployment

**Docker** (recommended):

```bash
docker build -t souwen .
docker run -p 8000:49265 \
  -e SOUWEN_ADMIN_PASSWORD=your-admin-password \
  -e SOUWEN_USER_PASSWORD=your-user-password \
  -v ~/.config/souwen:/app/data \
  souwen
```

**HuggingFace Spaces**: see `cloud/hfs/` and [docs/hf-space-cd.md](docs/hf-space-cd.md).
**ModelScope**: see `cloud/modelscope/`.

**WARP proxy embedding** (optional, bypass network restrictions): see the WARP section in `docs/anti-scraping.md`.

## 📚 Documentation

- [docs/README.md](docs/README.md) — Technical documentation index and reading guide
- [docs/getting-started.md](docs/getting-started.md) — Getting started
- [docs/concepts.md](docs/concepts.md) — Core concepts
- [docs/python-api.md](docs/python-api.md) — Python API
- [docs/source-catalog.md](docs/source-catalog.md) — Source Catalog contract
- [docs/architecture.md](docs/architecture.md) — Architecture overview
- [docs/data-sources.md](docs/data-sources.md) — Full data source guide and list (auto-generated from registry)
- [docs/configuration.md](docs/configuration.md) — Configuration hierarchy / WARP / HTTP backend
- [docs/api-reference.md](docs/api-reference.md) — REST API reference
- [docs/hf-space-cd.md](docs/hf-space-cd.md) — Hugging Face Space CD / local gates / post-deploy validation
- [docs/deployment.md](docs/deployment.md) — Deployment
- [docs/anti-scraping.md](docs/anti-scraping.md) — TLS fingerprinting / WARP / rate limiting
- [docs/appearance.md](docs/appearance.md) — Multi-skin frontend
- [docs/adding-a-source.md](docs/adding-a-source.md) — Adding a new source guide
- [docs/plugin-integration-spec.md](docs/plugin-integration-spec.md) — External plugin integration spec
- [docs/plugin-management.md](docs/plugin-management.md) — Plugin management (Web Panel / CLI / API)
- [docs/contributing.md](docs/contributing.md) — Developer guide
- [docs/internal/rc-readiness-gates.md](docs/internal/rc-readiness-gates.md) — Fixed v2.0.0rc1 gates and evidence manifest contract
- [docs/internal/](docs/internal/) — Maintainer ADRs, branching policy, and pre-release baselines
- [CHANGELOG.md](CHANGELOG.md) — Changelog

## 🤝 Contributing

- Add a data source: see [docs/adding-a-source.md](docs/adding-a-source.md) (just add one `_reg(...)` call in `registry/sources/`)
- Build an external plugin: see [docs/plugin-integration-spec.md](docs/plugin-integration-spec.md)
- Code style: `ruff format && ruff check`
- Tests: `pytest tests/`

## 📄 License

[GPLv3](LICENSE) · For learning and research purposes only
