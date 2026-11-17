# cloud navigation card

Type: Domain card. Read when changing the HFS Space wrapper.

`hfs/` holds the Space Dockerfile and entrypoint. The entrypoint runs
`souwen serve`. The Space has been on 3.x since 2026-11-17 (deploy history lives in
the local runbook, not here). On config: `SOUWEN_CONFIG_B64` is **still a live
config carrier** — the root `entrypoint.sh` decodes it into `/app/souwen.yaml`
and the loader reads that file; only the retired fields inside it
(`SOUWEN_ADMIN_PASSWORD`-style admin/guest/LLM keys) are ignored. Do not treat
the secret as dead config or delete it without a replacement plan.

`hfs/Dockerfile` is not the root `Dockerfile`: it clones the source itself from
`ARG SOUWEN_REF` and then runs the root `entrypoint.sh`. It must keep the same
WARP components as the root image (`wgcf`, `wireproxy`, `usque`) — installing a
binary is not enough: `_start_mode("usque")` once called a `_start_usque` method
that did not exist anywhere, so the container logged an AttributeError and fell
back to wireproxy. Both start paths must really work. `libatomic1` is an
explicit dependency alignment with the root image (installed before
`playwright install --with-deps chromium`); Chromium already rendered pages
without it. `tests/test_dockerfiles.py` guards both.

Behind the HF reverse proxy the app must accept the platform-provided Host: the
Space runtime injects `SPACE_HOST`, and `server/mcp_server.py` resolves the
`/mcp` transport-security allowlist from loopback + `SPACE_HOST` (or explicit
`mcp_allowed_hosts` config). Container-local probes at 127.0.0.1 cannot catch a
too-narrow or too-wide allowlist — the `mcpproxy` probe covers that.

Verification: the `hfs-image` job in `.github/workflows/ci.yml` builds this file
from a minimal Space-shaped context and runs `scripts/hfs_image_check.py` inside
the container. A local build is not equivalent — the runner is where it is proven.
