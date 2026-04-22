# SouWen 搜文

中文 | **English**

> A **unified search library** for AI Agents: academic papers + patents + web + social + video + knowledge + developer communities + Chinese tech + enterprise + archives + content fetching

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-orange)](CHANGELOG.md)

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

SouWen provides AI Agents with a unified multi-source search interface. **All data sources are declared through a single `SourceAdapter` registry**, normalized into Pydantic v2 data models.

The registry architecture reduces the cost of adding a new source to **1–2 code changes**; CLI / API / frontend are all organized by 10 domains.

### Features

- **83 heterogeneous data sources** (derived from a unified `registry`):
  - `paper` 17 · `patent` 8 · `web` 28 (engines/api/self_hosted)
  - `social` 5 · `video` 2 · `knowledge` 1
  - `developer` 2 · `cn_tech` 3 · `office` 1 · `archive` 1
  - `fetch` cross-cutting: 15 fetch providers + 4 cross-domain providers
- **Unified Pydantic v2 models**: `PaperResult` / `PatentResult` / `WebSearchResult` / `FetchResult` / `WaybackCDXResponse` / …
- **Async-first**: httpx + asyncio, per-loop Semaphore concurrency control
- **Smart rate limiting**: Token Bucket + sliding window, per-source isolation
- **curl_cffi TLS fingerprinting**: 15+ scraper sources use browser fingerprints to bypass anti-bot
- **WARP dual-mode proxy**: kernel mode (wireguard-go + microsocks) / wireproxy mode (pure userspace)
- **MCP protocol**: callable by Claude Code / Cursor / Windsurf and other AI assistants
- **Multi-skin Web UI**: souwen-google (default) / souwen-nebula / carbon / apple / ios (SCSS Modules + Zustand)

## 📦 Installation

```bash
# Core: Python library + CLI
pip install souwen

# API server (FastAPI) + TLS fingerprinting + web search
pip install "souwen[server,tls,web,scraper]"

# Full install (includes PDF / Crawl4AI / newspaper, etc.)
pip install "souwen[server,tls,web,scraper,pdf,crawl4ai,newspaper,readability,robots,mcp]"
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
souwen sources                          # List all data sources
souwen serve                             # Start API server (default :8000)
souwen doctor                            # Health check
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

    # Facade API (recommended)
    from souwen.facade import search, search_all, fetch_content, archive_lookup

    # Dispatch by domain + capability
    papers = await search("transformer", domain="paper", limit=5)
    articles = await search("AI news", domain="web", capability="search_news")
    results = await search_all("quantum", domains=["paper", "web", "knowledge"])

    # Fetch
    resp = await fetch_content(["https://example.com"], provider="builtin")

    # Wayback archive
    snapshots = await archive_lookup("https://example.com")

asyncio.run(main())
```

### API Server

```bash
souwen serve --host 0.0.0.0 --port 8000
```

Main endpoints:

```bash
# Top-level verb form
curl "http://localhost:8000/api/v1/search/paper?q=transformer&per_page=5"
curl "http://localhost:8000/api/v1/search/web?q=python"
curl "http://localhost:8000/api/v1/fetch" -X POST -d '{"urls":["https://example.com"]}'

# Domain form (planned, available after backend route split)
curl "http://localhost:8000/api/v1/paper/search?q=transformer"
curl "http://localhost:8000/api/v1/archive/cdx?url=https://example.com"
```

Visit `/docs` for the full OpenAPI documentation; visit `/` to enter the Web UI (default: souwen-google skin).

## ⚙️ Configuration

Config priority: env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > defaults.

Run `souwen config init` to generate a template at `~/.config/souwen/config.yaml`.

## 🏗 Architecture

Three-layer separation: **Presentation (CLI / Server / Panel / Integrations) → Facade (facade/) → Registry (registry/) + Domain (paper/patent/…) + Platform (core/)**.

See [docs/architecture.md](docs/architecture.md) for details.

```
src/souwen/
├── core/              Platform: http_client / scraper / rate_limiter / retry / …
├── registry/          Single source of truth: adapter / sources / loader / views
├── facade/            Facade: search / fetch / archive / aggregate
├── paper/             17 paper clients
├── patent/            8 patent clients
├── web/               30 web-related (engines / api / self_hosted)
├── social/ video/ knowledge/ developer/ cn_tech/ office/ archive/ fetch/
├── cli/ (subpackage)  CLI commands (organized by domain)
└── server/            FastAPI application
```

## 🚢 Deployment

**Docker** (recommended):

```bash
docker build -t souwen .
docker run -p 8000:8000 \
  -e SOUWEN_API_PASSWORD=your-password \
  -v ~/.config/souwen:/app/data \
  souwen
```

**HuggingFace Spaces**: see `cloud/hfs/`.
**ModelScope**: see `cloud/modelscope/`.

**WARP proxy embedding** (optional, bypass network restrictions): see the WARP section in `docs/anti-scraping.md`.

## 📚 Documentation

- [docs/architecture.md](docs/architecture.md) — Architecture overview
- [docs/data-sources.md](docs/data-sources.md) — Full data source list (auto-generated from registry)
- [docs/configuration.md](docs/configuration.md) — Configuration hierarchy / WARP / HTTP backend
- [docs/api-reference.md](docs/api-reference.md) — REST API reference
- [docs/anti-scraping.md](docs/anti-scraping.md) — TLS fingerprinting / WARP / rate limiting
- [docs/appearance.md](docs/appearance.md) — Multi-skin frontend
- [docs/adding-a-source.md](docs/adding-a-source.md) — Adding a new source guide
- [docs/contributing.md](docs/contributing.md) — Developer guide
- [CHANGELOG.md](CHANGELOG.md) — Changelog

## 🤝 Contributing

- Add a data source: see [docs/adding-a-source.md](docs/adding-a-source.md) (just add one `_reg(...)` call in `registry/sources.py`)
- Code style: `ruff format && ruff check`
- Tests: `pytest tests/`

## 📄 License

[GPLv3](LICENSE) · For learning and research purposes only
