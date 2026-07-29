# SouWen 搜文

中文 | **English**

> A target-only Search, LLM Search, and Fetch API for AI Agents and automation scripts.

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0rc4-orange)](CHANGELOG.md)

> The current candidate is **Souwen v2rc4** (Python/runtime `2.0.0rc4`). The
> `v2.0.0rc4` tag, GitHub prerelease, and HFS promotion may be created only after
> all exact-candidate release gates pass. The published
> [`v2.0.0rc3`](https://github.com/BlueSkyXN/SouWen/releases/tag/v2.0.0rc3) remains
> the previous immutable baseline; use GitHub Releases and live HFS readback for current status.
> This is not the `2.0.0` GA and is not published on PyPI.

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

SouWen exposes only Search, LLM Search, and Fetch as public data operations. Provider facts come
from the `ProviderManifest` catalog, `ManifestRegistry`, and `ProviderManager`; `/api/v1/providers`
is their safe runtime projection.

### Features

<!-- BEGIN AUTO: SOURCE METRICS -->
- **104 built-in Provider v2 packages** and **110 capability adapters**.
  - Search: **88** packages · LLM Search: **2** · Fetch: **20**.
<!-- END AUTO: SOURCE METRICS -->
- **Frozen OpenAPI and generated SDKs**: the Python root exposes generated sync/async SDK clients; Panel uses the generated TypeScript SDK
- **Canonical DTOs** for Search, LLM Search, Fetch, Provider Catalog, and probes
- **Read-only admin boundary**: config, doctor, and ping only

## 📦 Installation

```bash
# Install the current main source line
git clone https://github.com/BlueSkyXN/SouWen.git
cd SouWen
pip install -e .

# Server runtime
pip install -e ".[server,tls,web,robots,scraper]"
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
verify API major 2 through `/healthz`. See the
[Python SDK guide](docs/python-sdk.md) for authentication, HFS dual-token use, and errors.
The Panel uses the [TypeScript SDK](docs/typescript-sdk.md) generated from the same OpenAPI artifact.

### API Server

```bash
SOUWEN_USER_PASSWORD=userpass SOUWEN_ADMIN_PASSWORD=adminpass \
  uvicorn souwen.server.app:app --host 0.0.0.0 --port 8000
```

Main endpoints:

```bash
curl "http://localhost:8000/api/v1/search" \
  -H "Authorization: Bearer userpass" \
  -H "X-SouWen-API-Major: 2" \
  -H "Content-Type: application/json" \
  -d '{"query":"transformer","domains":["paper"]}'
curl "http://localhost:8000/api/v1/providers" \
  -H "Authorization: Bearer userpass" \
  -H "X-SouWen-API-Major: 2"
```

`POST /api/v1/fetch` is a target Data API operation and uses a user credential. Admin retains only
read-only `GET /api/v1/admin/config`, `/doctor`, and `/ping`; there is no rollout switch, `/sources`,
citation/detail/archive-save, recursive crawl, browser-fetch product entry, or legacy enriched-search endpoint.

Visit `/docs` for the full OpenAPI documentation; visit `/panel#/` to enter the single Calm Precision management surface. `/` redirects to `/docs` with the default configuration.

## ⚙️ Configuration

Config priority: env > `./souwen.yaml` > `~/.config/souwen/config.yaml` > `.env` > defaults.

Create project configuration from `souwen.example.yaml`. Copy it to `~/.config/souwen/config.yaml` if you want a user-level config.

## 🏗 Architecture

Three-layer separation: **Presentation (Server / Panel) → generated SDK and module APIs → Provider manifest catalog, registry, manager, and runtime clients**.

See [docs/architecture.md](docs/architecture.md) for details.

```
src/souwen/
├── delivery/          Frozen OpenAPI, generated Python SDK, and HTTP adapters
├── platform/          Provider SPI, manifest registry, specs, and manager
├── providers/         Provider manifests, adapters, and private runtime clients
├── modules/           Search, LLM Search, and Fetch application services
├── common_runtime/    Shared transport, security, resilience, and observability
└── server/            FastAPI host and embedded Panel boundary
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
The root [`hfs-dev.toml`](hfs-dev.toml) is a registry-only deployment record for the
source lane, Space ID, workflow ownership, and current Space-setting names. It stores
no credential values and does not authorize a generic sync tool to change remote settings;
the current reference `hf_space_sync.py` rejects it before reading `.env` or using the network.
**ModelScope**: see `cloud/modelscope/`.

**WARP proxy embedding** (optional, bypass network restrictions): see the WARP section in `docs/anti-scraping.md`.

## 📚 Documentation

- [docs/README.md](docs/README.md) — Technical documentation index and reading guide
- [docs/getting-started.md](docs/getting-started.md) — Getting started
- [docs/concepts.md](docs/concepts.md) — Core concepts
- [docs/python-api.md](docs/python-api.md) — Python API
- [docs/source-catalog.md](docs/source-catalog.md) — Provider Catalog contract
- [docs/architecture.md](docs/architecture.md) — Architecture overview
- [docs/data-sources.md](docs/data-sources.md) — Full Provider guide and list (auto-generated from manifests)
- [docs/configuration.md](docs/configuration.md) — Configuration hierarchy / WARP / HTTP backend
- [docs/api-reference.md](docs/api-reference.md) — REST API reference
- [docs/hf-space-cd.md](docs/hf-space-cd.md) — Hugging Face Space CD / local gates / post-deploy validation
- [docs/deployment.md](docs/deployment.md) — Deployment
- [docs/anti-scraping.md](docs/anti-scraping.md) — TLS fingerprinting / WARP / rate limiting
- [docs/appearance.md](docs/appearance.md) — Calm Precision Panel
- [docs/adding-a-source.md](docs/adding-a-source.md) — Adding a new source guide
- [docs/contributing.md](docs/contributing.md) — Developer guide
- [docs/internal/rc-readiness-gates.md](docs/internal/rc-readiness-gates.md) — Fixed v2.0.0rc4 gates and evidence manifest contract
- [docs/internal/](docs/internal/) — Maintainer ADRs, branching policy, and pre-release baselines
- [CHANGELOG.md](CHANGELOG.md) — Changelog

## 🤝 Contributing

- Add a Provider: see [docs/adding-a-source.md](docs/adding-a-source.md) (add manifest/spec/adapter and conformance tests)
- Code style: `ruff format && ruff check`
- Tests: `pytest tests/`

## 📄 License

[GPLv3](LICENSE) · For learning and research purposes only
