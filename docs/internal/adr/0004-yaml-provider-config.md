# ADR 0004: YAML as the Durable Provider Configuration Source

**Status**: Accepted
**Date**: 2026-07-24
**Scope**: Target Provider Extension v2 configuration and authenticated Admin/Panel editing
**HLD register ID**: ADR-03
**Related decision**: Q-003 closed on 2026-07-24
**Related artifacts**: HLD §13, §15.3, §21, §27; [SPEC-05](../spec-05-provider-spi-manifest-conformance.md); future SPEC-06 and SPEC-07.

## Context

Provider Extension v2 needs one durable, reviewable record for provider
namespaces, non-secret options, and enabled/eligibility state. Multiple durable
sources make revision, operator readback, rollback, and provenance unreliable.

This is target state, not present implementation:

- SouWenConfig currently loads env, project YAML, user YAML, .env, and defaults.
- Current GET/PUT admin config YAML reads/writes selected YAML, validates/reloads,
  atomically replaces it, and retains .bak; it has no target revision or
  optimistic-concurrency contract.
- Current source config update mutates in-memory SouWenConfig.sources; it is not
  durable revisioned Provider v2 editing.
- Existing plugin config/state are legacy lifecycle surfaces, not v2 Provider
  configuration sources.

## Decision

### 1. YAML is the sole durable record

YAML is sole durable truth for target Provider Extension v2 configuration. It
stores versioned provider-namespaced non-secret configuration and approved secret
**references** only. Configuration/Provider Manager reads committed revision and
validates namespaces against Provider manifest config schema.

Raw request bodies, editor drafts, Panel stores, in-memory config, environment
mappings, cached Provider instances, and route-local mutations are
derived/ephemeral state; none can become a competing durable source. Provider
code receives only its resolved namespace and never scans raw YAML or another
Provider namespace.

### 2. Environment and secrets remain non-durable

Environment and future Secret Resolver may resolve runtime secrets and implement
an explicitly specified transient override policy; they are not another persisted
record. Target YAML, manifests, revision history, diff/audit data, static Panel
bundles, logs, metrics, exceptions, and provenance MUST NOT contain literal API
keys, passwords, cookies, bearer tokens, client secrets, or credential-bearing
URLs.

YAML may contain approved secret reference/name. It resolves only at runtime for
the needing Provider and receives redacted diagnostic form. Missing/inaccessible
or malformed references make only that Provider ineligible; they never justify
value logging or cross-namespace fallback.

### 3. Source and visual online editing share one write path

Future authenticated Admin source editing and Panel visual editing are views of
the same YAML record. One server-side editor/service path MUST:

1. return redacted representation plus current revision identifier;
2. validate YAML syntax, root/config model, Provider manifest schema,
   secret-reference rules, and authorization;
3. calculate redacted semantic diff from requested base revision;
4. reject stale writes by optimistic concurrency;
5. atomically persist new YAML revision only after validation;
6. reload/reconcile Provider eligibility through approved config flow; and
7. return new revision plus redacted readback.

Source editing means authorized Provider configuration fields; visual online
editing means Panel graphical editor. Neither permits browser direct-file writes,
browser-held server secrets, or manifest/package-code edits. Final paths,
payloads, roles, edit granularity, and UI states remain SPEC-07/UI SPEC work.

### 4. Revision, diff, concurrency, rollback

Every accepted write gets monotonic opaque revision identifier bound to exact
content or approved canonical form. Reads expose current revision and
caller-appropriate redacted representation.

- Writes MUST carry base revision. Mismatch returns conflict without writing and
  cannot disclose another editor's secrets.
- Service MUST retain redacted semantic diff: changed paths and secret-reference
  identity changes, never secret values.
- Validation, persistence, reload, or reconciliation failure leaves prior
  accepted revision active; partial write never becomes accepted revision.
- Rollback validates/authorizes a prior revision and creates new forward
  revision. It cannot bypass audit/concurrency as raw filesystem copy.
- History storage, retention, backing medium, rollback roles need owner
  confirmation; required semantics are atomic, revisioned, auditable, redacted.

### 5. Manifest versus YAML

Manifest declares package identity, capabilities, config schema, network/risk,
and secret field/reference names. YAML selects values and eligibility. YAML
cannot claim absent capability or arbitrary implementation class; manifest cannot
embed environment-specific config/secrets. Mismatch makes only affected Provider
ineligible and emits redacted local diagnostic.

## Options considered

| Option | Decision | Rationale |
|---|---|---|
| YAML sole durable config; controlled server edit; secret refs | **Accepted** | Reviewable, supports one source/Panel flow, diff/revision/rollback, keeps secrets server-side. Requires explicit revision/history implementation. |
| Environment-only | Rejected | Good for injected secrets, not durable reviewed options, UI editing, diff, or rollback. |
| Database durable config | Rejected for target | Adds migration/backup/availability boundary without current evidence of need. |
| Independent YAML, Panel, route-local, plugin stores | Rejected | Divergent truth and non-auditable conflict/provenance. |
| Literal secrets in YAML/history | Rejected | Violates HLD secret/redaction controls. |
| Current endpoints unchanged as v2 solution | Rejected | No target revision/conflict/diff/secret-reference semantics. |

## Consequences

**Positive**

- One durable record and state transition for text/source and visual Panel edits.
- Provider inventory/safe diagnostics bind to known configuration revision.
- Concurrent edits conflict visibly rather than silent last-write-wins.
- Rollback creates audit-preserving forward history without secret exposure.

**Costs and migration constraints**

- Revision/diff/concurrency/rollback needs implementation; current lock, atomic
  replace, and .bak are insufficient.
- Current precedence and legacy source/plugin mutations need explicit migration;
  no code may silently make them v2 durable truth.
- Authorization, redacted readback, audit retention, recovery require SPEC-07
  and validation before visible management changes.
- File permissions, backup encryption, history storage, reference grammar,
  reload failure semantics, retention are not decided here.
- Preserve current behavior until reviewed replacement; migrate one Provider
  namespace at a time with deterministic validation, redaction/conflict/
  reconciliation tests, and rollback demonstration.

## Verification and acceptance evidence

These are future gates, not current results.

| ID | Required proof |
|---|---|
| VAL-YAML-001 | One persisted YAML representation per Provider namespace; route-local/in-memory/plugin state is not durable truth. |
| VAL-YAML-002 | Authorized text/source and Panel edits use same service and yield equal revision outcome for equal change. |
| VAL-YAML-003 | Invalid YAML/provider config, literal secret, malformed ref, unauthorized write create no active revision. |
| VAL-YAML-004 | Stale base revision rejected without overwrite; refresh supports redacted diff. |
| VAL-YAML-005 | Persistence/reload/reconciliation fault preserves prior active revision with safe audit. |
| VAL-YAML-006 | Rollback validates and creates forward revision without secret exposure. |
| VAL-YAML-007 | Reads, diffs, audits, logs, metrics, errors redact secrets and credential-bearing URLs. |
| VAL-YAML-008 | Provider-specific config/secret fault affects only that Provider. |

Ordinary tests use deterministic fixtures and fake Secret Resolver. Real
secret/deployment checks are approved functional/deployment work, not pytest.

## Related artifacts and owner confirmations

| Need | Owner/artifact | Status |
|---|---|---|
| Manifest/config schema and namespace rules | SPEC-05 / Provider Manager LLD | Required |
| Loader/reconciliation and revision storage detail | SPEC-06 Common Runtime LLD | Required |
| Admin auth, redacted readback, audit roles | SPEC-07 Auth/Permission | Required |
| Panel editor states/conflict presentation | React IA/UI SPEC | Required |
| Revision storage/retention/backup/permissions/encryption | Security/operations owner | Confirmation required |
| Secret-reference grammar/resolver integration | Security/config owner | Confirmation required |
| Numeric reload/concurrency targets | NFR SPEC, Q-008 | Open |

## Review condition

Review/supersede if verified multi-writer requirements exceed controlled YAML
revision semantics, secret management needs materially different reference or
authorization model, a database persistence boundary is independently approved,
or SPEC-06/07 conflicts with one-record/revision/redaction rules. Until then,
preserve distinction between current configuration behavior and target contract.
