# core.config

Layered, typed runtime configuration.

- **Model:** `Settings` (pydantic-settings `BaseSettings`), composed of
  `EngineConfig`, `SessionConfig`, `APIConfig`, `StorageConfig`, `AIConfig`.
- **Layering:** defaults < YAML/JSON config file (`Settings.from_file`) <
  `.env` < environment variables (`CT_` prefix, `__` separator).
- **Timezone handling:** `SessionConfig.default_timezone` is an IANA name
  validated via `zoneinfo.ZoneInfo` at load; session windows are defined in
  that zone and converted to UTC by the sessions engine (Phase 6).
- **Determinism note:** config load order is fixed and total; no runtime
  mutation — inject `Settings` instances, never read globals in engine code.

Migration history: v1.0.0 (Phase 2) — initial.
