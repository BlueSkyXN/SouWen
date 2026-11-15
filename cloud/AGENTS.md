# cloud navigation card

Type: Domain card. Read when changing the HFS Space wrapper.

`hfs/` holds the Space Dockerfile and entrypoint. The entrypoint runs
`souwen serve`; the Space is still on rc6 — deploying 3.x requires cleaning the
removed config fields (Admin passwords, `SOUWEN_CONFIG_B64`) from Space secrets.

`hfs/Dockerfile` is not the root `Dockerfile`: it clones the source itself from
`ARG SOUWEN_REF` and then runs the root `entrypoint.sh`. It must keep the same
WARP components as the root image (`wgcf`, `wireproxy`, `usque`) — installing a
binary is not enough: `_start_mode("usque")` once called a `_start_usque` method
that did not exist anywhere, so the container logged an AttributeError and fell
back to wireproxy. Both start paths must really work. `libatomic1` is an
explicit dependency alignment with the root image (installed before
`playwright install --with-deps chromium`); Chromium already rendered pages
without it. `tests/test_dockerfiles.py` guards both.

Verification: the `hfs-image` job in `.github/workflows/ci.yml` builds this file
from a minimal Space-shaped context and runs `scripts/hfs_image_check.py` inside
the container. A local build is not equivalent — the runner is where it is proven.
