# panel/src/core navigation card

Type: Domain card.
This directory contains the generated TypeScript SDK, the minimal admin service, auth state,
shared types, styles and deterministic Panel tests. Read `sdk/index.ts`, `sdk-client.ts`,
`services/_base.ts`, `services/admin-client.ts`, `stores/authStore.ts`, `types/api.ts`, and
`core/test/` first. Read this card for SDK use, admin services, auth state, shared types, URL safety
or test behavior.

## Local invariants

- Data API requests must go through generated `sdk/index.ts`; do not hand edit that file.
- Admin requests must preserve timeout handling, auth header injection, error classification and baseUrl allow-list checks.
- Auth state spans Zustand plus sessionStorage/localStorage.
- Core code must not depend on page/layout modules.
- Generated SDK changes start in `tools/gen_typescript_sdk.py` and require `--write` plus `--check`.

## Do not

- Do not send Bearer tokens to unchecked third-party base URLs.
- Do not put page-specific layout/style into shared services or stores.
- Search, LLM Search, Fetch and Providers must go through `SouWenClient`; only admin control-plane
  calls may use a handwritten transport.
- Do not log, render, snapshot or persist unredacted secrets beyond the existing auth-store contract.

## Validation

- `npm test`
- `npm run build`
