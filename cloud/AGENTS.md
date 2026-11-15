# cloud navigation card

Type: Domain card. Read when changing the HFS Space wrapper.

`hfs/` holds the Space Dockerfile and entrypoint. The entrypoint runs
`souwen serve`; the Space is still on rc6 — deploying 3.x requires cleaning the
removed config fields (Admin passwords, `SOUWEN_CONFIG_B64`) from Space secrets.

`hfs/Dockerfile` is not the root `Dockerfile`: it clones the source itself from
`ARG SOUWEN_REF` and then runs the root `entrypoint.sh`. It must keep the same
WARP components as the root image (`wgcf`, `wireproxy`, `usque`) — WarpManager's
auto chain is usque > wireproxy, and with only wireproxy the proxy never came up
in this image. `libatomic1` must be installed before `playwright install
--with-deps chromium`, same as the root image. `tests/test_dockerfiles.py` guards
both.

Verification: the `hfs-image` job in `.github/workflows/ci.yml` builds this file
from a minimal Space-shaped context and runs `scripts/hfs_image_check.py` inside
the container. A local build is not equivalent — the runner is where it is proven.
