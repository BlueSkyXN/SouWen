# ADR 0003: Browser Fetch Worker in the Same Deployment Unit

**HLD register ID**: ADR-02
**Status**: Accepted
**Date**: 2026-07-24
**Owner**: SouWen project owner
**Implementation state**: Not implemented; Phase 1 contract baseline

## Context

SouWen currently runs one Uvicorn process from `entrypoint.sh`. The public Fetch route in
`src/souwen/server/routes/fetch.py` calls `souwen.web.fetch.fetch_content()` in that process, and
browser-capable implementations such as Crawl4AI, Scrapling and the Playwright pool execute in the
same event loop/process boundary. `src/souwen/core/browser_pool.py` limits pages per event loop but
does not isolate browser crashes, native dependencies or memory pressure from the API Runtime.

The approved HLD keeps a modular monolith and one default deployment unit. The project owner has
also fixed the first deployment topology: API Runtime and Browser Fetch Worker are separate
processes inside the same HFS Space. This round does not create a second Worker Space or split
Search/LLM Search into services.

Forces:

- Browser runtimes have materially different dependencies, startup cost, memory use and failure
  modes from ordinary HTTP Search/Fetch.
- Fetch URL, DNS and redirect checks must not weaken across a process boundary.
- HFS currently provides one container/Space boundary; adding a second Space would add credentials,
  provenance, deployment and rollback coordination before load evidence justifies it.
- The target must also work in the four planned PyInstaller server bundles, including Windows,
  making a Unix-domain-socket-only protocol unsuitable.
- Provider selection, fallback and canonical result semantics remain Core responsibilities; the
  Worker must not become another product API or orchestration service.

## Options considered

### Option A: Keep browser execution in the API process

Advantages: no IPC or supervisor; closest to current behavior.

Rejected because browser dependency/crash/memory isolation and independently bounded concurrency
are explicit goals. It also makes readiness unable to distinguish API health from browser runtime
health.

### Option B: Separate process over loopback HTTP in the same deployment unit

Advantages: cross-platform protocol, explicit health/contract boundary, independent concurrency and
restart, one image/Space and one deployment provenance chain.

Selected.

### Option C: Separate process over Unix domain socket

Advantages: narrow local transport and filesystem permissions.

Rejected as the only transport because Windows parity and PyInstaller bundles would require a
second protocol. A future Unix optimization may be added only if it preserves the same contract and
tests.

### Option D: Dedicated remote Worker service or second HFS Space

Advantages: independent scaling and stronger deployment failure-domain isolation.

Deferred. Current load, ownership and independent-release evidence do not satisfy the HLD service
extraction triggers. This would require a new ADR/change control.

## Decision

### Process and network boundary

1. The all-in-one deployment starts two application processes under one Deployment-owned
   supervisor: `api-runtime` and `browser-fetch-worker`.
2. The Worker binds loopback only, never `0.0.0.0`. The default internal address is
   `127.0.0.1:${SOUWEN_BROWSER_WORKER_PORT:-49266}`; ordinary clients and the React Web never receive
   this address.
3. The supervisor generates a high-entropy per-start capability token and passes it to both child
   processes without persisting it to YAML, logs, provenance, `/health`, `/readiness` or Panel
   readback. A configured secret reference may replace generation in split deployments.
4. Every Worker request requires the internal bearer token, contract-major header, request ID and
   bounded deadline. The Worker rejects missing/mismatched contract major before provider work.
5. The internal API uses versioned loopback HTTP endpoints:

```text
GET  /internal/v1/health
GET  /internal/v1/readiness
POST /internal/v1/fetch
```

These paths are not mounted on the external FastAPI app and are not part of `/api/v1`.

### Responsibility boundary

The API Runtime owns:

- external auth, rate limiting and request validation;
- Core Fetch provider selection, ordered fallback/fanout and canonical aggregation;
- overall timeout budget and canonical external error mapping;
- public response and provenance assembly.

The Browser Worker owns:

- one selected browser-capable Fetch Provider execution per internal request;
- browser process/pool lifecycle, page concurrency and resource limits;
- independent URL/DNS validation before navigation and every redirect/subresource policy decision;
- canonical Provider result/error serialization and Provider-local timing;
- its health, readiness and effective non-secret config revision.

The Worker does not own Search, LLM Search, provider ordering, multi-provider fallback, user auth,
Admin API, WARP process management, configuration persistence or public response formatting.

### Internal contract rules

| ID | Rule |
|---|---|
| BFW-001 | Requests identify exactly one browser-capable Provider and a bounded URL batch; the Worker cannot select another Provider. |
| BFW-002 | External caller identity/credential is not forwarded; only request ID, deadline, canonical Fetch request fields and internal capability auth cross the boundary. |
| BFW-003 | The Worker independently applies the same Security Contract. An API-side validation result or policy token never authorizes skipping Worker URL/redirect/DNS checks. |
| BFW-004 | `skip_ssrf_check` and equivalent implementation escape hatches are not representable in the protocol. |
| BFW-005 | Browser output is bounded by response-size/content limits before IPC serialization; raw page bodies, cookies and secrets are not logged. |
| BFW-006 | The Worker advertises contract major, source SHA, runtime version, provider inventory digest and config revision in readiness metadata. |
| BFW-007 | The API fails closed on protocol-major mismatch, invalid provenance metadata or non-loopback Worker configuration. |
| BFW-008 | No persistent job queue is introduced. In-flight work may fail on Worker restart and is mapped to a retryability-aware canonical error. |
| BFW-009 | Automatic retry after a Provider attempt begins is disabled unless the Provider contract proves idempotency/cost safety; transport connect failure before dispatch may be retried once within the original deadline. |
| BFW-010 | Cancellation and the absolute deadline propagate to browser navigation; timeout does not leave an unbounded page/task running. |

### Capacity and failure semantics

- Worker concurrency and queue length are explicit bounded settings with safe defaults. Queue
  overflow returns `worker_overloaded`; it cannot grow memory without bound.
- API mappings distinguish `worker_unavailable`, `worker_not_ready`, `worker_overloaded`,
  `worker_timeout`, `worker_protocol_mismatch` and Provider-origin canonical errors.
- Error responses include request/provider identifiers and retryability but no token, cookie,
  private target detail or unredacted upstream body.
- Browser-provider failure does not crash Search/LLM Search or ordinary HTTP Fetch. Core fallback may
  continue only within the original request policy and deadline.

### Health, readiness and supervision

1. The supervisor starts the Worker before declaring the API deployment ready and forwards
   termination signals to both processes.
2. Worker liveness reports process/event-loop availability. Readiness additionally requires browser
   dependency initialization, contract-major match, accepted config revision and provider inventory.
3. If Browser Worker is enabled/required and not ready, aggregate `/readiness` returns `ready=false`.
   If it is explicitly disabled and no selected Provider requires it, readiness may remain true and
   reports `browser_worker.status=disabled`.
4. Aggregate runtime evidence separates Deployment wrapper SHA, API source SHA and Worker source
   SHA. A source mismatch is not healthy.
5. Restart policy is bounded with backoff and a crash-loop terminal state; the supervisor cannot
   conceal repeated failures by endlessly reporting API readiness.

### Configuration and WARP

- Deployment chooses process ports, token source, restart policy and WARP/proxy wiring.
- Provider/browser settings come from the accepted YAML configuration revision and secret resolver;
  the Worker receives only its validated effective subset.
- WARP or proxy changes egress only. Both API-side and Worker-side Security Contract checks still
  execute and cannot be disabled by deployment profile.

## Consequences

Positive:

- Browser crashes, native dependencies and memory/concurrency pressure are isolated from the API
  process while preserving one Space/image and one deployment transaction.
- Health, source provenance, config revision and protocol compatibility become observable per
  process.
- The internal boundary can later move to a remote Worker without changing Core Provider semantics,
  if a future ADR proves the service extraction triggers.

Costs and risks:

- A supervisor, IPC client/server, internal authentication, cancellation and additional contract
  tests are required.
- Loopback is a process boundary, not a tenant/security perimeter; binding and token handling must
  fail closed.
- One container still shares machine-level CPU/memory and the HFS deployment failure domain.
- Browser requests incur serialization and loopback overhead; budgets and measurements must include
  it.
- During migration, an explicit rollback switch may route the selected vertical slice to the old
  in-process path. It must be deployment-scoped, observable and removed by Phase 8; it cannot become
  a silent per-request bypass.

## Validation

| VAL ID | Evidence required before the ADR is implemented |
|---|---|
| VAL-BFW-001 | Process-level integration test proves API stays healthy when Worker crashes and readiness becomes false when required. |
| VAL-BFW-002 | Worker rejects non-loopback bind, missing/invalid token and contract-major mismatch. |
| VAL-BFW-003 | Golden Fetch fixtures produce equivalent canonical results through old in-process and new Worker paths. |
| VAL-BFW-004 | SSRF tests cover direct IP, DNS binding, redirect and browser subrequest behavior on both sides; protocol has no bypass field. |
| VAL-BFW-005 | Deadline/cancellation test leaves no live page/task after timeout. |
| VAL-BFW-006 | Queue/concurrency overload returns bounded canonical error without unbounded growth. |
| VAL-BFW-007 | HFS deployment profile proves two-process readiness, matching source SHA/config revision and rollback evidence in one Space. |
| VAL-BFW-008 | Linux/macOS/Windows target-native smoke proves the loopback contract in the planned PyInstaller server bundles. |

Ordinary pytest uses fakes and local loopback only; real browser/package/HFS evidence remains in
functional scripts and GitHub Actions, consistent with repository test policy.

## Related artifacts

- HLD §§6.1, 8.2, 8.5–8.7, 14.3, 15.2–15.3, 16, 21–23.
- `docs/internal/spec-01-external-api-canonical-dto.md`.
- `docs/internal/spec-05-provider-spi-manifest-conformance.md`.
- `docs/internal/spec-08-directory-dependency.md`.
- Future Browser Worker LLD and deployment validation plan.

## Review condition

Create a new ADR/change control before any of the following:

- exposing the Worker outside loopback or mounting its internal API on `/api/v1`;
- moving it to a second Space/host or introducing a persistent queue;
- allowing the Worker to select/fallback across Providers;
- giving Search or LLM Search independent service processes;
- changing the security rule that both API Runtime and Worker validate browser destinations.

The remote-service option should be reconsidered only when measured scaling, failure isolation,
security/dependency isolation, independent ownership/release cadence or SLO evidence satisfies
multiple HLD §22 extraction triggers.
