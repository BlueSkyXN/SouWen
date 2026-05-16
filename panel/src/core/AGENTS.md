# panel/src/core navigation card

Type: Domain card.
This directory is the frontend shared layer for services, stores, hooks, types, i18n, tests and skin registry.
Read `services/_base.ts`, `services/index.ts`, `stores/authStore.ts`, `types/api.ts`, `skin-registry.ts`, and `core/test/` first.
Read this card for API services, auth store, shared hooks/types, i18n, URL safety or cross-skin behavior.

## Local invariants

- API requests must preserve timeout handling, auth header injection, error classification and baseUrl allow-list checks.
- Auth state spans Zustand plus sessionStorage/localStorage.
- Core code must not depend on skin modules.
- i18n key changes need matching translations and tests where behavior changes.

## Do not

- Do not send Bearer tokens to unchecked third-party base URLs.
- Do not put skin-specific layout/style into shared services or stores.
- Do not duplicate route/page UI logic that belongs in skins.

## Validation

- `npm test`
- `npm run build`
