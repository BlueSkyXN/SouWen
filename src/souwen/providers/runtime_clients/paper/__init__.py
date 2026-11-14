"""Runtime helpers for this provider group.

Source clients live in each source package's ``source.py``; the shared
extraction/transport helpers used across groups stay here. This package keeps
no re-exports of source classes so the dependency direction stays
source -> shared helper.
"""
