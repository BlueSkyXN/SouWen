# .github navigation card

Type: Domain card. Read when changing workflows.

- `ci.yml` — ruff + pytest (3.10/3.11) + root image smoke, on `main` and
  `agent-first` pushes; plus `hfs-image`, the deploy-time check of the image the
  Space actually builds (see `cloud/AGENTS.md`). `hfs-image` runs on branch pushes,
  because its Dockerfile fetches the source by SHA from the public repo.
- `census.yml` — authoritative census on `agent-first` pushes (build image, WARP on/off
  legs, sources/domains/fetch + `/mcp` probe + `doctor --live`; report artifacts).
- `release.yml` — push `v<version>` on the reviewed commit, matching `pyproject.toml`.
  It runs CI, builds and smoke-tests the wheel, and publishes the wheel, sdist and
  `SHA256SUMS` to GitHub Releases. The annotated tag supplies the release notes.
  PRs that change the release flow run the build checks. Alpha, beta and release
  candidate tags publish as prereleases.
- `image.yml` — manual Space deployment (`workflow_dispatch`; requires the
  `HFS_TOKEN` secret and `HFS_SPACE` variable). First real runs happened 2026-11-17
  (details in the local runbook); every dispatch is a live deployment of the given
  `souwen_ref` — never trigger it casually. Without the secret/variable it silently
  skips the sync step and exits green, so a green run alone is not evidence of
  deployment; check the log for the Space push line.

`hfs-image` does not replace `census.yml`: census measures source success rates
against the root image, `hfs-image` proves the Space image builds, boots and answers
on HTTP, MCP (loopback and reverse-proxy Host), auth, browser and WARP. It never
pushes, deploys or restarts anything.
