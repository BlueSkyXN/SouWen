# .github navigation card

Type: Domain card. Read when changing workflows.

- `ci.yml` — ruff + pytest (3.10/3.11) + root image smoke, on `main` and
  `agent-first` pushes; plus `hfs-image`, the deploy-time check of the image the
  Space actually builds (see `cloud/AGENTS.md`). `hfs-image` only runs on push,
  because its Dockerfile fetches the source by SHA from the public repo.
- `census.yml` — authoritative census on `agent-first` pushes (build image, WARP on/off
  legs, sources/domains/fetch + `/mcp` probe + `doctor --live`; report artifacts).
- `image.yml` — write-only release path (workflow_dispatch; not yet run; HFS secrets
  required and first run needs owner supervision).

`hfs-image` does not replace `census.yml`: census measures source success rates
against the root image, `hfs-image` proves the Space image builds, boots and answers
on HTTP, MCP, auth, browser and WARP. It never pushes, deploys or restarts anything.
