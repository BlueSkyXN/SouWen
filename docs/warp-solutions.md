# WARP runtime guidance

WARP is an optional deployment/runtime network concern. Configure it through the
deployment environment and configuration file, not through public or admin HTTP endpoints.
The target-only API remains Search, LLM Search, Fetch, Providers, probes, and the
read-only admin config/doctor/ping surface.
