# src/souwen/server/schemas navigation card

Type: Domain card. Read when changing the host error response schema.

Holds `ErrorResponse` for non-agent error bodies. Agent route errors are flat
(`{"detail": ...}` via HTTPException); keep it that way.
