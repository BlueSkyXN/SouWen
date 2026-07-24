# Canonical Contracts

Owner: Architecture and contract owners.

This directory is the language-neutral contract source boundary defined by SPEC-08. It is not a
Python package and must not import or depend on `souwen` runtime code.

Phase 2A creates only the directory skeleton. No target OpenAPI document, schema, error catalog,
provider contract, security contract, golden fixture, or conformance suite is approved merely by
the presence of these directories. Target artifacts remain gated by their owning SPEC and open
decisions.

| Directory | Responsibility |
|---|---|
| `openapi/` | Versioned external HTTP contract sources |
| `schemas/` | Language-neutral JSON Schema sources |
| `errors/` | Canonical error identifiers and envelopes |
| `provider/` | Provider SPI and manifest contract artifacts |
| `security/` | Authentication, authorization, redaction, and trust-boundary contracts |
| `fixtures/` | Provenance-bearing language-neutral golden fixtures |
| `conformance/` | Contract validation inputs and expected results |

All future artifacts must declare a contract version and a deterministic generation or validation
command. Python and TypeScript bindings implement or are generated from these artifacts; neither
binding becomes the silent source of truth.
