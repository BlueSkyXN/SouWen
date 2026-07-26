# panel navigation card

Type: Domain card.
This directory is the single Calm Precision React/Vite/TypeScript management panel and embedded artifact source.
Read `package.json`, `vite.config.ts`, `tsconfig*.json`, `docs/appearance.md`, `src/App.tsx`, and
`src/CalmPrecisionApp.tsx` before editing. Read this card for Panel UI, frontend build config,
dependencies, npm scripts, Vite behavior or embedded artifact changes.

## Local invariants

- Use npm and `package-lock.json`; do not add pnpm/yarn/bun lockfiles.
- `npm run build` runs `tsc -b && vite build`.
- `npm run build:local` copies `dist/index.html` to `../src/souwen/server/panel.html`.
- Shared transport, authentication and generated SDK code belongs in `src/core`; the single
  Calm Precision interface lives in `src/CalmPrecisionApp.tsx` and its SCSS Module.
- The top-level navigation remains Search, LLM Search, Fetch, Providers and Runtime / Settings.

## Do not

- Do not hand edit `panel/dist/` or `src/souwen/server/panel.html`.
- Do not introduce Tailwind; this panel uses SCSS Modules and CSS variables.
- Do not send auth tokens to unchecked third-party base URLs.
- Search, LLM Search, Fetch and Providers must use the generated `@core/sdk` client.
- Do not add runtime visual variants or duplicate Data API clients.

## Validation

- `npm test`
- `npm run build`
- Embedded artifact: `npm run build:local && npm run check:artifact`
