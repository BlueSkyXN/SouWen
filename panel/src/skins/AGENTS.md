# panel/src/skins navigation card

This directory contains the panel skin modules.
Read `docs/appearance.md`, `vite.config.ts`, `core/skin-registry.ts`, and an existing skin's `index.ts`, `routes.tsx`, `skin.config.ts` first.
Read this card for skin UI, adding skins, skin routing, skin exports or CSS isolation.

## Local invariants

- Every skin must export the complete `SkinModule`: `AppShell`, `LoginPage`, routes, config, boundary, toast, spinner and `bootstrap`.
- Skin CSS must be scoped with CSS Modules or `html[data-skin='<id>']`.
- New skins must be registered in `vite.config.ts` `ALL_SKINS` and i18n labels.

## Do not

- Do not import one skin from another.
- Do not duplicate API service logic inside skins.

## Validation

- `npm run build`
- Single skin: `VITE_SKINS=<skin-id> npm run build`
