# SPEC-08: Directory and Dependency Rules

**Status**: Proposed; Phase 1 owner review required
**Date**: 2026-07-24
**Source baseline**: HLD v0.4, Phase 1 / T007
**Implementation baseline**: `main@4d05d7a414c820aad50416823b92692b95dc6e17`

## 1. Purpose and authority

This Directory SPEC turns HLD §§7–10 into testable repository boundaries. It does not move
production code. Phase 2 may create only the smallest skeleton and dependency gate needed to
prove these rules before behavior-preserving migrations begin.

Controlling inputs:

- HLD §§7–10, 19.2, 21 and 22.
- `pyproject.toml`, whose wheel target currently packages only `src/souwen`.
- `docs/architecture.md`, which describes the current registry-centered implementation.
- Root and directory-level `AGENTS.md` files, which remain operational instructions rather than
  application dependency rules.

The HLD's `src/<area>/` diagram is realized under the existing `souwen` distribution root as
`src/souwen/<area>/`. This preserves `project.name = "souwen"`, the current Hatch package root,
and the approved single-distribution boundary. It does not create unrelated top-level Python
packages named `delivery`, `modules`, or `providers`.

## 2. Slice routing

| Source | Slice | Reason | Priority | Blocks dev? |
|---|---|---|---|---:|
| HLD §§7–10 | DIR-001 | Target package layout and ownership | P0 | yes |
| HLD §10.1–10.3 | DIR-002 | Allowed/forbidden imports and automated gate | P0 | yes |
| HLD §§8.5–8.6 | DIR-003 | Contracts and Common Runtime anti-dumping rules | P0 | yes |
| HLD §21 Phase 2–5 | DIR-004 | Incremental migration and legacy exception lifecycle | P0 | yes |

Cross-document references use `SPEC-08/<ID>` (for example, `SPEC-08/DEP-001`).
Unqualified IDs in this file are local shorthand and do not alias another SPEC's `VAL-*` or
other local identifiers.

## 3. Current repository evidence

The current tree is capability-rich but does not yet implement the target module graph:

| Current evidence | Current meaning | Target treatment |
|---|---|---|
| `src/souwen/server/routes/fetch.py` imports `souwen.web.fetch` and registry views | Route currently reaches aggregation/provider implementation | Move orchestration behind Fetch module public interface |
| `src/souwen/server/app.py` loads plugins and lifecycle hooks | Delivery currently owns extension lifecycle | Move provider lifecycle to Platform / Provider Manager |
| `src/souwen/core/` contains HTTP, retry, browser pool, cache and parsing | Shared runtime and domain-adjacent utilities are mixed | Admit only qualified shared concerns to `common_runtime/` |
| `src/souwen/registry/` is the source/catalog truth | Stable current asset, but it combines manifest-like metadata and dispatch wiring | Evolve through adapters into Manifest Registry and Provider Manager; do not create a parallel source list |
| `src/souwen/paper/`, `patent/`, `web/`, `llm/` contain concrete clients | Providers are grouped primarily by historical surface | Migrate provider-by-provider after conformance exists |
| `panel/` is a React/Vite project and `panel.html` is a wheel artifact | Web source is separate, artifact remains coupled to wheel | Phase 7 separates Web release; no Phase 2 rename |
| `pyproject.toml` uses `packages = ["src/souwen"]` | One Python distribution/package root | New Python modules remain below `src/souwen/` |

This SPEC must not be used to claim the target directories or gates already exist.

## 4. DIR-001: Target package and artifact layout

- **Source IDs**: HLD ARCH-001–ARCH-010; HLD §§7–10.
- **Target repository**: `BlueSkyXN/SouWen`.
- **Existing convention**: Python package under `src/souwen`, tests under `tests`, generated or
  language-neutral artifacts outside the import package.
- **In scope**: ownership, names, public interfaces, dependency direction and migration seams.
- **Out of scope**: bulk file moves, public behavior changes, provider rewrites and Web redesign.

```text
contracts/
  openapi/
  schemas/
  errors/
  provider/
  security/
  fixtures/
  conformance/

src/souwen/
  delivery/
    api/
    client_sdk/
  modules/
    search/
      api/
      application/
      domain/
      infrastructure/
    llm_search/
      api/
      application/
      domain/
      infrastructure/
    fetch/
      api/
      application/
      domain/
      infrastructure/
  platform/
    provider_manager/
    provider_spi/
    manifest_registry/
  common_runtime/
    transport/
    resilience/
    security/
    observability/
    configuration/
    testing/
  providers/
    information_sources/
    llm_sources/
    fetch_sources/

web/
deploy/
  container/
  process/
  warp/
```

### Naming and ownership rules

| ID | Rule |
|---|---|
| DIR-001 | Each target module exposes a documented `api` or package-root public interface; an unlisted symbol is private even if Python can import it. |
| DIR-002 | Core module names are exactly `search`, `llm_search`, and `fetch`; historical domains are Provider packages, not additional Core modules. |
| DIR-003 | Concrete Provider code is grouped by provider/protocol below one of the three provider families; a package may expose multiple single-capability adapters. |
| DIR-004 | `contracts/` contains language-neutral source artifacts and fixtures; it is not a Python package and must not import `souwen`. |
| DIR-005 | `common_runtime/` names technical responsibilities, not business domains or miscellaneous helpers. |
| DIR-006 | Deployment process supervision belongs to `deploy/process/`; WARP remains `deploy/warp/` and cannot be imported by Core. |
| DIR-007 | Existing `panel/` remains until Phase 7 establishes the independent `web/` build; no compatibility symlink or duplicate frontend tree is created in Phase 2. |
| DIR-008 | Existing registry declarations remain the only source/catalog truth until an explicit migration step proves parity; target manifest files must be generated from or reconciled against that truth, never maintained as a silent parallel list. |

## 5. DIR-002: Dependency graph and public interfaces

### Allowed dependencies

```text
delivery.api              -> modules.*.api
delivery.client_sdk       -> generated bindings from contracts/openapi
modules.*                 -> own layers, contracts, declared provider ports, common_runtime
platform.provider_manager -> platform.provider_spi, platform.manifest_registry, provider factories
providers.*               -> platform.provider_spi, contracts, common_runtime
deploy                     -> build artifacts and runtime entry points
web                        -> generated TypeScript client only
```

Within a Core module, the default inward direction is:

```text
api -> application -> domain
infrastructure -> application/domain ports
```

`domain` must not import `api`, `infrastructure`, FastAPI, Pydantic transport schemas, registry
implementation, or concrete providers. Cross-Core orchestration is an application-level caller
concern; one Core module cannot import another module's `infrastructure`.

### Forbidden dependencies

| ID | Forbidden edge | Rationale |
|---|---|---|
| DEP-001 | `modules/** -> souwen.providers/**` | Core selects capabilities through ports/SPI, never implementation |
| DEP-002 | `providers/** -> souwen.delivery/**` | Provider cannot own HTTP/UI/CLI concerns |
| DEP-003 | `providers/<A>/** -> providers/<B>/**` | Cross-provider composition belongs to Core |
| DEP-004 | `common_runtime/** -> souwen.modules/**` or `souwen.providers/**` | Shared runtime cannot own domain behavior |
| DEP-005 | `modules/** -> fastapi`, Panel/Web, WARP manager or process supervisor | Core remains protocol/deployment independent |
| DEP-006 | `delivery/api/** -> concrete provider clients` | Routes translate protocol and invoke use cases only |
| DEP-007 | Web source -> Python internals or provider-specific business branches | Web consumes generated external contract |
| DEP-008 | Provider import side effects or monkey patching a global registry | Assembly must be explicit and auditable |
| DEP-009 | `contracts/**` -> runtime source | Contracts are language-neutral sources |
| DEP-010 | A new top-level Python package outside `src/souwen/` | Preserve the approved `souwen` distribution boundary |

### Public interface declarations

Each migrated package must include:

1. A small package-root `__init__.py` or `api/` export list.
2. `__all__` for supported Python-internal interfaces where applicable.
3. A short module README or docstring naming owner, inputs, outputs and allowed dependencies.
4. Contract/conformance tests that import only the declared interface.
5. A negative test preventing consumers from importing known internal implementation paths.

Public module interfaces are internal architecture contracts unless SPEC-01 explicitly promotes
them to an external API. They do not expand the end-user Python direct-import surface.

## 6. Automated architecture gate

Phase 2 shall add a repository-owned Python checker, proposed as
`scripts/ci/check_architecture_dependencies.py`, plus deterministic tests. An extra third-party
dependency is not required for the first gate.

| Gate requirement | Acceptance behavior |
|---|---|
| Parse Python imports | Inspect `ast.Import` and `ast.ImportFrom` below target packages |
| Detect obvious dynamic bypass | Inspect literal `importlib.import_module()` calls; non-literal dynamic imports in governed areas require an explicit reviewed adapter or fail |
| Resolve relative imports | Compare canonical module names, not raw syntax |
| Check graph rules | Enforce DEP-001–DEP-010 that are applicable to files already migrated |
| Report evidence | Stable file:line, importing module, imported module and violated rule ID |
| Test the gate | Fixture with at least one allowed edge and one intentional forbidden edge per rule family |
| Run in CI | Required in `ci.yml` and the trusted release evidence path after the checker is stable |

When the independent `web/` source exists, a separate JavaScript/TypeScript import rule must reject
Python-internal paths and Provider-specific business branches. The Python AST checker does not claim
to validate Web imports.

The checker must use an explicit, expiring migration exception file. Each exception entry contains:

```text
rule_id, importer, imported, owner, rationale, removal_phase, expiry_date
```

Wildcards that exempt an entire target layer are forbidden. New violations cannot be added merely
because an equivalent legacy violation exists.

## 7. DIR-003: Contracts and Common Runtime admission

### Contracts rules

| ID | Rule |
|---|---|
| CON-001 | OpenAPI/JSON Schema/error/provider/security artifacts have an explicit contract version and deterministic generation or validation command. |
| CON-002 | Pydantic and TypeScript types implement or are generated from contracts; neither language binding silently becomes the only truth. |
| CON-003 | Golden fixtures are immutable inputs/expected outputs with provenance and contain no production secret or private URL. |
| CON-004 | A contract change must run semantic diff and generated-client synchronization checks before merge. |

### Common Runtime admission test

A component may enter `common_runtime/` only when all are evidenced:

1. At least two real consumers.
2. One coherent technical responsibility and owner.
3. Explicit input, output, error, timeout and cancellation semantics.
4. Deterministic tests without network, browser runtime, production secret or HOME config.
5. No dependency on Delivery, Core modules or concrete Providers.

Failure of any criterion keeps the component inside its current module until a later extraction.
The directory name `common_runtime` is not sufficient evidence of reuse.

## 8. DIR-004: Incremental migration

| Step | Allowed change | Required evidence | Forbidden expansion |
|---|---|---|---|
| Phase 2A | Create contracts/module/platform/common/provider skeletons | Import surface test and checker self-tests | Moving concrete clients |
| Phase 2B | Enable gate for new target packages | CI failure on intentional violation | Blanket legacy enforcement without exception inventory |
| Phase 3 | Move qualified Common Runtime components behavior-preservingly | Old/new fixture parity; no Core/provider imports | Opportunistic behavior improvements |
| Phase 4 | Migrate OpenAlex, configured UniAPI LLM Search, builtin/Browser Fetch slice | Golden parity, rollback switch, deployment profile | Additional providers |
| Phase 5 | Migrate provider batches | Per-provider conformance and manifest parity | Cross-provider private calls |
| Phase 6–7 | Generated SDK and independent Web build | Contract diff/client sync; Web build | Python internals in Web |
| Phase 8 | Remove legacy paths | Usage/replacement/migration/RC/residue evidence | Unproven deletion |

No PR may combine contract redesign, auth changes, provider migration, deployment rewrite and UI
rewrite. Temporary adapters must declare their removal phase and cannot create a second source
catalog.

## 9. Acceptance criteria

| VAL ID | Acceptance criterion |
|---|---|
| VAL-DIR-001 | A Phase 2 skeleton remains within `src/souwen/` and the `souwen` wheel import surface; clean build/import tests pass. |
| VAL-DIR-002 | An intentional Core-to-concrete-Provider import fails the architecture gate with DEP-001 and file:line evidence. |
| VAL-DIR-003 | An allowed Provider-to-SPI/Common Runtime import passes. |
| VAL-DIR-004 | A Common Runtime-to-Core import fails with DEP-004. |
| VAL-DIR-005 | A provider-to-provider private import fails with DEP-003. |
| VAL-DIR-006 | Existing unmigrated code is either outside the governed target path or listed in a bounded, expiring exception; no wildcard exemption exists. |
| VAL-DIR-007 | Registry/manifest parity tests prove there is one source/catalog truth during migration. |
| VAL-DIR-008 | `contracts/` validation runs without importing or installing the SouWen Python package. |
| VAL-DIR-009 | Documentation and generated-client checks identify all declared public interfaces and contract versions. |

## 10. Traceability

| Slice | HLD | Related ADR/SPEC | Validation |
|---|---|---|---|
| DIR-001 | §§7–9 | SPEC-01, SPEC-05 | VAL-DIR-001, 007, 009 |
| DIR-002 | §10, §19.2 | ADR 0003 / HLD ADR-02 | VAL-DIR-002–006 |
| DIR-003 | §§8.5–8.6 | SPEC-01, SPEC-05 | VAL-DIR-007–009 |
| DIR-004 | §21 | all Phase 1 ADRs | all above |

## 11. Open questions

1. The exact legacy-exception file format and expiry duration are implementation details for the
   Phase 2 checker PR; the required fields and no-wildcard rule are fixed here.
2. Whether `panel/` is renamed to `web/` or retained as the independent Web source directory is
   deferred to SPEC-09; no duplicate tree is permitted.
3. The final generator/tooling choice for Python and TypeScript clients belongs to Phase 6. This
   SPEC requires deterministic generation and sync checks but does not select a generator.
