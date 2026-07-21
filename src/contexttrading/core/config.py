"""Layered, typed runtime configuration.

Layering (lowest to highest precedence):

    defaults < config file (YAML/JSON) < .env < environment variables

Environment variables use the ``CT_`` prefix with ``__`` as the section
separator, e.g. ``CT_SESSIONS__DEFAULT_TIMEZONE=America/New_York``.

Inject ``Settings`` instances into subsystems; do not read module-level
globals from engine code. ``get_settings()`` exists only for entrypoints
(API, CLI) that genuinely own process configuration.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from contexttrading.core.errors import ConfigurationError


class EngineConfig(BaseModel):
    """Engine-wide numeric behavior.

    All analysis thresholds live here so every module is config-driven and
    deterministic. Defaults follow common SMC practice; tune per market.
    """

    model_config = ConfigDict(extra="forbid")

    float_rel_tol: float = Field(default=1e-9, gt=0, description="Relative float tolerance.")
    float_abs_tol: float = Field(default=1e-12, gt=0, description="Absolute float tolerance.")
    swing_lookback: int = Field(default=5, ge=1, description="Default bars each side for swings.")
    min_candles: int = Field(
        default=50, ge=1, description="Minimum series length most modules require."
    )

    # -- swings ---------------------------------------------------------------
    internal_swing_lookback: int = Field(
        default=2, ge=1, description="Lookback for internal (noise-level) swings."
    )
    external_swing_lookback: int = Field(
        default=5, ge=1, description="Lookback for external (leg-level) swings."
    )

    # -- volatility / volume ----------------------------------------------------
    atr_period: int = Field(default=14, ge=1, description="Wilder ATR period.")
    volume_lookback: int = Field(
        default=20, ge=2, description="Rolling window for relative volume / z-scores."
    )
    volume_zscore_threshold: float = Field(
        default=2.0, gt=0, description="|z| above which a candle is volume-imbalanced."
    )

    # -- structure breaks ---------------------------------------------------------
    strength_atr_fraction: float = Field(
        default=0.25,
        ge=0,
        description="Close margin beyond the level (in ATRs) for a STRONG break.",
    )

    # -- liquidity ------------------------------------------------------------------
    equal_level_atr_fraction: float = Field(
        default=0.1,
        ge=0,
        description="Max price spread (in ATRs) for swings to count as equal levels.",
    )
    equal_level_min_separation: int = Field(
        default=3, ge=1, description="Min candles between members of an equal level."
    )
    sweep_grab_atr_fraction: float = Field(
        default=0.5,
        ge=0,
        description="Wick penetration (in ATRs) at which a sweep becomes a GRAB.",
    )

    # -- dealing range ---------------------------------------------------------------
    ote_fib_lower: float = Field(
        default=0.62, gt=0, lt=1, description="OTE zone near fib retracement."
    )
    ote_fib_upper: float = Field(
        default=0.79, gt=0, lt=1, description="OTE zone far fib retracement."
    )

    # -- fair value gaps ---------------------------------------------------------------
    fvg_min_atr_fraction: float = Field(
        default=0.05,
        ge=0,
        description="Minimum FVG gap size in ATRs (skipped during ATR warmup).",
    )
    fvg_stacked_lookback: int = Field(
        default=5,
        ge=1,
        description="Max candles between same-direction FVGs to link them as stacked.",
    )
    fvg_strength_half_life: int = Field(
        default=50, ge=1, description="Candles for the age-decay half-life in scoring."
    )
    fvg_gap_atr_cap: float = Field(
        default=3.0, gt=0, description="Gap ATR-multiple at which the gap score saturates."
    )
    fvg_weight_gap: float = Field(
        default=0.35, ge=0, le=1, description="Strength weight: gap size component."
    )
    fvg_weight_displacement: float = Field(
        default=0.25, ge=0, le=1, description="Strength weight: displacement linkage."
    )
    fvg_weight_freshness: float = Field(
        default=0.15, ge=0, le=1, description="Strength weight: mitigation freshness."
    )
    fvg_weight_age: float = Field(
        default=0.15, ge=0, le=1, description="Strength weight: age decay."
    )
    fvg_weight_structure: float = Field(
        default=0.10, ge=0, le=1, description="Strength weight: nested/stacked bonus."
    )

    # -- order blocks ---------------------------------------------------------------
    ob_max_lookback: int = Field(
        default=30,
        ge=1,
        description="Max candles searched back from a break for the OB candle "
        "(used when no opposite external swing bounds the search).",
    )
    ob_refine_atr_multiple: float = Field(
        default=2.0,
        gt=0,
        description="OB candle range (in ATRs) above which a refined zone is emitted.",
    )
    ob_refine_wick_fraction: float = Field(
        default=0.5,
        gt=0,
        le=1,
        description="Refined zone = this extreme fraction of the OB range "
        "(bullish: lowest part; bearish: highest).",
    )
    breaker_confirm_lookback: int = Field(
        default=20,
        ge=1,
        description="Candles after an OB violation within which a confirming "
        "counter-direction break must occur to emit a breaker block.",
    )

    # -- supply / demand ---------------------------------------------------------------
    sd_base_body_atr_fraction: float = Field(
        default=0.5,
        ge=0,
        description="Max candle body (in ATRs) for a candle to count as base.",
    )
    sd_max_base_candles: int = Field(
        default=3, ge=1, description="Max consecutive candles in a supply/demand base."
    )
    sd_departure_atr_multiple: float = Field(
        default=1.5,
        gt=0,
        description="Minimum departure-leg magnitude (in ATRs) for a valid zone.",
    )
    sd_departure_atr_cap: float = Field(
        default=3.0,
        gt=0,
        description="Departure ATR-multiple at which the departure score saturates.",
    )
    sd_duplicate_overlap_fraction: float = Field(
        default=0.8,
        gt=0,
        le=1,
        description="Zone overlap (intersection / smaller zone height) at which a "
        "pattern zone is marked duplicate of an order block.",
    )
    sd_strength_half_life: int = Field(
        default=50, ge=1, description="Candles for the age-decay half-life in scoring."
    )
    sd_weight_departure: float = Field(
        default=0.30, ge=0, le=1, description="Strength weight: departure magnitude."
    )
    sd_weight_tightness: float = Field(
        default=0.20, ge=0, le=1, description="Strength weight: base tightness."
    )
    sd_weight_freshness: float = Field(
        default=0.20, ge=0, le=1, description="Strength weight: zone freshness."
    )
    sd_weight_tests: float = Field(
        default=0.10, ge=0, le=1, description="Strength weight: per-test decay."
    )
    sd_weight_trend: float = Field(
        default=0.10, ge=0, le=1, description="Strength weight: external-trend alignment."
    )
    sd_weight_age: float = Field(
        default=0.10, ge=0, le=1, description="Strength weight: age decay."
    )

    # -- sessions ----------------------------------------------------------------------
    session_doji_body_fraction: float = Field(
        default=0.2,
        ge=0,
        le=1,
        description="Session body (|close-open| / range) below which the session "
        "direction is RANGING.",
    )

    # -- multi-timeframe -----------------------------------------------------------------
    mtf_include_incomplete_bar: bool = Field(
        default=True,
        description="Keep the still-forming last bar when resampling (is_closed=False).",
    )
    mtf_tf_weight_base: float = Field(
        default=2.0,
        gt=0,
        description="Weight of timeframe rank r in MTF aggregation: base ** r "
        "(rank 0 = base timeframe).",
    )
    mtf_moderate_share: float = Field(
        default=2.0 / 3.0,
        gt=0,
        le=1,
        description="Weighted agreement share at which MTF bias strength is at "
        "least MODERATE (STRONG requires full agreement).",
    )

    # -- confluence ------------------------------------------------------------------
    conf_weight_trend: float = Field(
        default=1.0, ge=0, description="Confluence weight: external trend direction."
    )
    conf_weight_mtf: float = Field(
        default=1.5, ge=0, description="Confluence weight: MTF bias alignment."
    )
    conf_weight_structure: float = Field(
        default=1.0, ge=0, description="Confluence weight: recent BOS/CHoCH direction."
    )
    conf_weight_liquidity: float = Field(
        default=1.0, ge=0, description="Confluence weight: recent sweep direction."
    )
    conf_weight_premium_discount: float = Field(
        default=0.5, ge=0, description="Confluence weight: premium/discount location."
    )
    conf_weight_fvg: float = Field(
        default=1.0, ge=0, description="Confluence weight: nearby active FVGs."
    )
    conf_weight_orderblock: float = Field(
        default=1.0, ge=0, description="Confluence weight: nearby valid order blocks."
    )
    conf_weight_supplydemand: float = Field(
        default=1.0, ge=0, description="Confluence weight: nearby fresh supply/demand zones."
    )
    conf_weight_session: float = Field(
        default=0.5, ge=0, description="Confluence weight: recent Judas-swing evidence."
    )
    conf_structure_lookback: int = Field(
        default=5, ge=1, description="Confirmed breaks inspected for the structure factor."
    )
    conf_sweep_lookback: int = Field(
        default=5, ge=1, description="Recent sweeps/Judas events inspected."
    )
    conf_proximity_atr: float = Field(
        default=1.0,
        ge=0,
        description="Max distance from the last close (in ATRs) for a zone to count "
        "as nearby evidence (0 = price must be inside the zone).",
    )
    conf_zone_min_factors: int = Field(
        default=2, ge=1, description="Min distinct factor kinds forming a confluence zone."
    )

    # -- trend / market phase -----------------------------------------------------------
    phase_lookback: int = Field(
        default=20, ge=2, description="Bars inspected for market-phase heuristics."
    )
    consolidation_range_atr_multiple: float = Field(
        default=3.0,
        gt=0,
        description="High-low range over phase_lookback below this ATR multiple "
        "implies CONSOLIDATION.",
    )
    strong_impulse_ratio: float = Field(
        default=1.5,
        gt=0,
        description="Impulse:correction ATR-magnitude ratio for a STRONG trend.",
    )
    swing_overlap_fraction: float = Field(
        default=0.5,
        gt=0,
        le=1,
        description="Leg overlap fraction above which swings count as overlapping "
        "(accumulation/distribution heuristic).",
    )


class SessionConfig(BaseModel):
    """Session/killzone configuration with explicit timezone handling.

    Default windows follow common ICT/SMC practice, expressed in UTC (the
    ``default_timezone``): Sydney and Tokyo accumulate the Asian range,
    London and New York are the main expansion sessions, and the kill zones
    are the windows where Judas swings are evaluated. Windows may wrap
    midnight; an instance belongs to the calendar date of its START bar.
    """

    model_config = ConfigDict(extra="forbid")

    default_timezone: str = Field(
        default="UTC",
        description="IANA timezone used to define session windows (e.g. 'America/New_York').",
    )
    sessions: dict[str, dict[str, str]] = Field(
        default_factory=lambda: {
            "sydney": {"start": "21:00", "end": "06:00"},
            "tokyo": {"start": "00:00", "end": "09:00"},
            "london": {"start": "07:00", "end": "16:00"},
            "new_york": {"start": "12:00", "end": "21:00"},
        },
        description="Named windows: {session: {start: 'HH:MM', end: 'HH:MM'}} in default_timezone.",
    )
    killzones: dict[str, dict[str, str]] = Field(
        default_factory=lambda: {
            "london": {"start": "07:00", "end": "10:00"},
            "new_york_am": {"start": "12:00", "end": "15:00"},
            "london_close": {"start": "15:00", "end": "17:00"},
            "new_york_pm": {"start": "18:00", "end": "20:00"},
        },
        description="Kill-zone windows in the same format as ``sessions``.",
    )

    @field_validator("default_timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value!r}") from exc
        return value

    @field_validator("sessions", "killzones")
    @classmethod
    def _validate_windows(cls, value: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        for name, window in value.items():
            for key in ("start", "end"):
                raw = window.get(key)
                if raw is None:
                    raise ValueError(f"Session {name!r} is missing {key!r}")
                parts = raw.split(":")
                if len(parts) != 2 or not all(p.isdigit() for p in parts):
                    raise ValueError(f"Session {name!r} {key!r} must be 'HH:MM', got {raw!r}")
                hour, minute = int(parts[0]), int(parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError(f"Session {name!r} {key!r} out of range: {raw!r}")
        return value

    def tzinfo(self) -> ZoneInfo:
        """Resolved tzinfo for ``default_timezone``."""
        return ZoneInfo(self.default_timezone)


class APIConfig(BaseModel):
    """FastAPI service configuration (Phase 10 in roadmap numbering).

    Secrets are never stored here: API keys arrive as a JSON array (or
    comma-separated string) via env (``CT_API__API_KEYS``). Auth is
    service-level, not multi-user IAM — deploy behind a reverse proxy for
    rate limiting (see ``docs/api/README.md``).
    """

    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=list)
    api_key_header: str = "X-API-Key"
    auth_enabled: bool = Field(
        default=True, description="Master switch for API-key authentication."
    )
    allow_anonymous: bool = Field(
        default=False,
        description="Local-dev escape hatch; MUST stay False in production profiles.",
    )
    api_keys: list[str] = Field(
        default_factory=list, description="Accepted API keys (from env, never hard-coded)."
    )
    max_candles_per_request: int = Field(
        default=20000, ge=1, description="Request size cap (413 above this)."
    )

    @field_validator("api_keys", mode="before")
    @classmethod
    def _split_keys(cls, value: Any) -> Any:
        """Accept comma-separated strings in addition to JSON arrays."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):  # JSON array form
                return value
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return value


class StorageConfig(BaseModel):
    """Result-store configuration (Phase 8)."""

    model_config = ConfigDict(extra="forbid")

    backend: Literal["sqlite", "postgresql", "redis"] = "sqlite"
    url: str = "sqlite:///contexttrading.db"
    echo: bool = False


class AIConfig(BaseModel):
    """Explain-only AI layer configuration (Phase 8).

    Secrets are never stored here: ``api_key_env`` names the environment
    variable that holds the provider key. Env layering works through
    ``Settings`` (e.g. ``CT_AI__PROVIDER=openai``).
    """

    model_config = ConfigDict(extra="forbid")

    provider: Literal["none", "mock", "openai", "anthropic", "local"] = "none"
    model: str = ""
    api_key_env: str = Field(
        default="CT_AI_API_KEY",
        description="Name of the env var holding the provider key (never the key itself).",
    )
    base_url: str = Field(
        default="", description="Optional endpoint override (self-hosted/local providers)."
    )
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1)
    max_retries: int = Field(default=2, ge=0, le=10)
    timeout_seconds: float = Field(default=30.0, gt=0)
    proximity_atr: float = Field(
        default=3.0, gt=0, description="Zones within this many ATRs of price are 'nearby'."
    )
    max_objects_per_category: int = Field(
        default=10, ge=1, description="Context truncation cap per object category."
    )


class VisualizationConfig(BaseModel):
    """Chart payload configuration (theme and layer visibility)."""

    model_config = ConfigDict(extra="forbid")

    theme: Literal["dark", "light"] = Field(
        default="dark", description="Color palette for the chart payload."
    )
    hidden_layers: list[str] = Field(
        default_factory=list,
        description="Layer names rendered but hidden by default (overrides defaults).",
    )
    shown_layers: list[str] = Field(
        default_factory=list,
        description="Layer names force-visible even when hidden by default.",
    )


class LoggingConfig(BaseModel):
    """Structured logging configuration."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_output: bool = Field(default=False, description="Emit single-line JSON log records.")


class Settings(BaseSettings):
    """Root application settings composed of per-subsystem sections."""

    model_config = SettingsConfigDict(
        env_prefix="CT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    engine: EngineConfig = Field(default_factory=EngineConfig)
    sessions: SessionConfig = Field(default_factory=SessionConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    visualization: VisualizationConfig = Field(default_factory=VisualizationConfig)

    @classmethod
    def from_file(cls, path: str | Path, **overrides: Any) -> Settings:
        """Load settings from a YAML or JSON file, then apply overrides.

        File values sit between built-in defaults and environment variables;
        pass ``_env_file=None`` semantics by constructing the class normally
        when env layering is not desired.

        Args:
            path: ``.yaml``/``.yml`` (requires PyYAML) or ``.json`` file.
            overrides: Keyword overrides applied last (e.g. for tests).

        Returns:
            A validated :class:`Settings` instance.

        Raises:
            ConfigurationError: On unknown suffix, missing file, or bad content.
        """
        path = Path(path)
        if not path.is_file():
            raise ConfigurationError("Config file not found", context={"path": str(path)})
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
            elif suffix in (".yaml", ".yml"):
                try:
                    import yaml
                except ImportError as exc:  # pragma: no cover - depends on env
                    raise ConfigurationError(
                        "PyYAML is required to read YAML config files",
                        context={"path": str(path)},
                    ) from exc
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            else:
                raise ConfigurationError(
                    "Unsupported config file suffix",
                    context={"path": str(path), "suffix": suffix},
                )
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ConfigurationError(
                "Failed to parse config file", context={"path": str(path), "error": str(exc)}
            ) from exc
        if not isinstance(data, dict):
            raise ConfigurationError(
                "Config file must contain a mapping at the top level",
                context={"path": str(path)},
            )
        data.update(overrides)
        return cls(**data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-level settings for entrypoints (API/CLI).

    Engine code must receive ``Settings`` via injection; this accessor exists
    for composition roots only. Tests should construct ``Settings`` directly.
    """
    return Settings()
