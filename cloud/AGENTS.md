# cloud navigation card

Type: Domain card. Read when changing the HFS Space wrapper.

`hfs/` holds the Space Dockerfile and entrypoint. The entrypoint runs
`souwen serve`; the Space is still on rc6 — deploying 3.x requires cleaning the
removed config fields (Admin passwords, `SOUWEN_CONFIG_B64`) from Space secrets.
