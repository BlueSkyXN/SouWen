# panel/src/core navigation card

This directory is the frontend shared layer.
Read `services/_base.ts`, `services/index.ts`, `stores/authStore.ts`, `types/api.ts`, and `core/test/` first.
Read this card for API services, auth store, shared hooks, shared types or i18n changes.

## Local invariants

- API requests must preserve timeout handling, auth header injection, error classification and baseUrl allow-list checks.
- Auth state spans Zustand plus sessionStorage/localStorage.
- Core code must not depend on skin modules.
- i18n key changes need matching translations.

## Do not

- Do not send Bearer tokens to unchecked third-party base URLs.
- Do not put skin-specific layout/style into shared services or stores.

## Validation

- `npm test`
- `npm run build`
