# cloud navigation card

Type: Guardrail card.
This directory contains Hugging Face Space and ModelScope deployment wrappers.
Read `docs/hf-space-cd.md`, `docs/deployment.md`, platform README, Dockerfile and entrypoint for the target platform before editing.
Read this card for cloud Dockerfiles, entrypoints, platform docs, deployment assumptions or container-port behavior.

## Why this is high-risk

- Changes affect deployable images and platform startup behavior.
- Platform wrappers need to track root Dockerfile behavior for panel build, WARP, auth env vars and optional web2pdf.
- Docker validation usually needs a Docker daemon and network.

## Required before changes

- Confirm whether the target is Hugging Face Space, ModelScope or shared Docker behavior.
- Keep platform ports explicit: Hugging Face uses `app_port: 49265`; ModelScope expects container port `7860`.
- Keep secrets/configuration in runtime environment variables, not image files.

## Do not

- Do not hard-code real secrets in images, entrypoints or README files.
- Do not default-enable privileged WARP kernel mode.
- Do not silently diverge cloud wrappers from the root Dockerfile without documenting why.

## Validation

- `pytest tests/test_dockerfiles.py tests/test_web2pdf_packaging.py -v --tb=short`
- Docker builds may need Docker daemon and network.
