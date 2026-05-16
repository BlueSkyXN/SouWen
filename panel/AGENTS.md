# panel navigation card

This directory is the React/Vite/TypeScript web panel.
Read `package.json`, `vite.config.ts`, `docs/appearance.md`, and `panel/src/App.tsx` first.
Read this card for frontend build, package scripts, Vite, dependency or embedded panel artifact changes.

## Local invariants

- Use npm and `package-lock.json`; do not add pnpm/yarn lockfiles.
- `npm run build` runs TypeScript build plus Vite.
- `npm run build:local` copies `dist/index.html` to `src/souwen/server/panel.html`.
- Shared behavior belongs in `src/core`; skin-specific UI belongs in `src/skins`.

## Do not

- Do not hand edit `panel/dist/` or `src/souwen/server/panel.html`.
- Do not let skins import each other.
- Do not introduce Tailwind; this panel uses SCSS Modules and CSS variables.

## Validation

- `npm test`
- `npm run build`
- Embedded artifact: `npm run build:local && npm run check:artifact`
