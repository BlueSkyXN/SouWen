# panel navigation card

Type: Domain card.
This directory is the React/Vite/TypeScript management panel and embedded artifact source.
Read `package.json`, `vite.config.ts`, `tsconfig*.json`, `docs/appearance.md`, and `src/App.tsx` before editing.
Read this card for frontend build config, dependencies, npm scripts, Vite behavior or embedded panel artifact changes.

## Local invariants

- Use npm and `package-lock.json`; do not add pnpm/yarn/bun lockfiles.
- `npm run build` runs `tsc -b && vite build`.
- `npm run build:local` copies `dist/index.html` to `../src/souwen/server/panel.html`.
- Shared behavior belongs in `src/core`; skin-specific UI belongs in `src/skins`.

## Do not

- Do not hand edit `panel/dist/` or `src/souwen/server/panel.html`.
- Do not let skins import each other.
- Do not introduce Tailwind; this panel uses SCSS Modules and CSS variables.
- Do not send auth tokens to unchecked third-party base URLs.

## Validation

- `npm test`
- `npm run build`
- Embedded artifact: `npm run build:local && npm run check:artifact`
