# SouWen 搜文

中文 | **English**

> A unified search, fetching, and archive toolkit for AI Agents and automation scripts.

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0rc2-orange)](CHANGELOG.md)

> The current candidate is **Souwen v2rc2** (Python/runtime `2.0.0rc2`). It is
> not the `2.0.0` GA and does not imply that the tag, GitHub Release, or HFS RC2
> deployment already exists.

**Author**: [@BlueSkyXN](https://github.com/BlueSkyXN) · **Repository**: [github.com/BlueSkyXN/SouWen](https://github.com/BlueSkyXN/SouWen) · **License**: [GPLv3](LICENSE)

> **⚠️ Disclaimer: This project is for Python learning and technical research only.** It covers API aggregation, full-stack development (FastAPI + React), web scraping (TLS fingerprinting / anti-bot bypass), and async programming. Do not use it in ways that violate laws or third-party terms of service.

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

SouWen provides AI Agents, Python integrations, and server applications with a unified multi-source search interface. **All data sources are declared through a single `SourceAdapter` registry**, normalized into Pydantic v2 data models.

The registry architecture reduces the cost of adding a new source to **1-2 code changes**; Python API / REST API / Panel are organized by domain, capability, and Source Catalog.

### Features

<!-- BEGIN AUTO: SOURCE METRICS -->
- **110 registered built-in sources**: **109 public** Source Catalog entries and **1 hidden/internal** entry.
  - Public sources by primary domain: `paper` 21 · `patent` 8 · `web` 32 · `social` 5 · `video` 2 · `knowledge` 1 · `developer` 2 · `cn_tech` 9 · `office` 1 · `archive` 1 · `book` 9 · `research_output` 2
  - `fetch` cross-cutting view: **23 providers** = **16 primary fetch-domain** + **7 cross-domain** sources.
<!-- END AUTO: SOURCE METRICS -->
- **Unified Pydantic v2 models**: `PaperResult` / `PatentResult` / `WebSearchResult` / `FetchResult` / `WaybackCDXResponse` / …
- **Async-first**: httpx + asyncio, per-loop Semaphore concurrency control
- **Smart rate limiting**: Token Bucket + sliding window, per-source isolation
- **curl_cffi TLS fingerprinting**: 15+ scraper sources use browser fingerprints to bypass anti-bot
- **WARP five-mode proxy**: wireproxy / kernel / usque / warp-cli / external, with runtime install and management support
- **Calm Precision Panel**: one responsive management surface for Search / LLM Search / Fetch / Providers / Runtime/Settings, with all Data API calls going through the generated TypeScript client

## 📦 Installation

```bash
# Install the current main source line
git clone https://github.com/BlueSkyXN/SouWen.git
cd SouWen
pip install -e .

# Default SDK/core install
pip install -e .

# Server runtime
pip install -e ".[server,tls,web,robots,scraper]"

# Optional providers; crawl4ai and scrapling are mutually exclusive.
pip install -e ".[server,tls,web,robots,scraper,newspaper,readability]"
pip install -e ".[server,tls,web,robots,scraper,crawl4ai]"
pip install -e ".[server,tls,web,robots,scraper,scrapling]"
```

## 🚀 Quick Start

### Python REST SDK

```python
from souwen import SouWenClient
from souwen.delivery.client_sdk import SearchRequest

with SouWenClient("http://127.0.0.1:8000", token="your-user-token") as client:
    page = client.search(SearchRequest(query="quantum computing", domains=["paper"]))
    for item in page.items:
        print(item.title, item.url)
```

`AsyncSouWenClient` provides the async surface. Before the first business request, both clients
verify API major 2 and target rollout through `/healthz`. See the
[Python SDK guide](docs/python-sdk.md) for authentication, HFS dual-token use, and errors.
The Panel uses the [TypeScript SDK](docs/typescript-sdk.md) generated from the same OpenAPI artifact.

### API Server

```bash
SOUWEN_V2_ROLLOUT=target SOUWEN_USER_PASSWORD=userpass SOUWEN_ADMIN_PASSWORD=adminpass \
  uvicorn souwen.server.app:app --host 0.0.0.0 --port 8000
```

Main endpoints:

```bash
curl "http://localhost:8000/api/v1/search" \
  -H "Authorization: Bearer userpass" \
  -H "X-SouWen-API-Major: 2" \
  -H "Content-Type: application/json" \
  -d '{"query":"transformer","domains":["paper"]}'
curl "http://localhost:8000/api/v1/wayback/cdx?url=https://example.com"
curl "http://localhost:8000/api/v1/sources"
```

`/api/v1/fetch`, `/api/v1/links`, and `/api/v1/sitemap` are admin-protected fetch capabilities and require an Admin Bearer token. Search endpoints and `/api/v1/sources` can be protected separately with `SOUWEN_USER_PASSWORD`.

Visit `/docs` for the full OpenAPI documentation; visit `/panel#/` to enter the single Calm Precision management surface. `/` redirects to `/docs` with the default configuration.

## ⚙️ Configuration

Config priority: env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > defaults.

Create project configuration from `souwen.example.yaml`. Copy it to `~/.config/souwen/config.yaml` if you want a user-level config.

## 🏗 Architecture

Three-layer separation: **Presentation (Server / Panel / Integrations) → Application API (`souwen.search` / `souwen.web.fetch` / `souwen.web.wayback`) → Registry + concrete client modules + Platform (`core`)**.

See [docs/architecture.md](docs/architecture.md) for details.

```
src/souwen/
├── core/              Platform: http_client / scraper / rate_limiter / retry / …
├── registry/          Single source of truth: adapter / sources / loader / views
├── paper/             Paper clients
├── patent/            8 patent clients
├── web/               Search, social, video, knowledge, office, fetch, and archive clients
└── server/            FastAPI application
```

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
- [docs/appearance.md](docs/appearance.md) — Calm Precision Panel
- [docs/adding-a-source.md](docs/adding-a-source.md) — Adding a new source guide
- [docs/contributing.md](docs/contributing.md) — Developer guide
- [docs/internal/rc-readiness-gates.md](docs/internal/rc-readiness-gates.md) — Fixed v2.0.0rc2 gates and evidence manifest contract
- [docs/internal/](docs/internal/) — Maintainer ADRs, branching policy, and pre-release baselines
- [CHANGELOG.md](CHANGELOG.md) — Changelog

## 🤝 Contributing

- Add a data source: see [docs/adding-a-source.md](docs/adding-a-source.md) (just add one `_reg(...)` call in `registry/sources/`)
- Code style: `ruff format && ruff check`
- Tests: `pytest tests/`

## 📄 License

[GPLv3](LICENSE) · For learning and research purposes only
