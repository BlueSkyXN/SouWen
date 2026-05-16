# panel/src/skins navigation card

Type: Domain card.
This directory contains panel skin modules, pages, layouts, styles, routes and skin config.
Read `docs/appearance.md`, `vite.config.ts`, `core/skin-registry.ts`, and an existing skin's `index.ts`, `routes.tsx`, `skin.config.ts` before editing.
Read this card for skin UI, adding skins, routing, skin exports, visual behavior or CSS isolation.

## Local invariants

- Every skin must export the complete `SkinModule`: `AppShell`, `LoginPage`, routes, config, boundary, toast, spinner and `bootstrap`.
- Skin CSS must be scoped with CSS Modules or `html[data-skin='<id>']`.
- New skins must be registered in `vite.config.ts` `ALL_SKINS` and i18n labels.
- Shared API/data behavior belongs in `panel/src/core`, not inside skins.

## Do not

- Do not import one skin from another.
- Do not duplicate API service logic inside skins.
- Do not let skin CSS leak globally without a `data-skin` or module boundary.

## Validation

- `npm run build`
- Single skin: `VITE_SKINS=<skin-id> npm run build`
