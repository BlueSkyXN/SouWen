# .github navigation card

Type: Domain card. Read when changing workflows.

- `ci.yml` — ruff + pytest (3.10/3.11) + root image smoke on `main`.
- `census.yml` — authoritative census on `agent-first` pushes (build image, WARP on/off
  legs, sources/domains/fetch + `/mcp` probe + `doctor --live`; report artifacts).
- `image.yml` — write-only release path (workflow_dispatch; not yet run; HFS secrets
  required and first run needs owner supervision).
