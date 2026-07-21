"""Deterministic context builder: engine results -> compact AI-ready JSON.

This is pure Python — no AI involvement. It assembles the COMPLETE engine
state into one versioned document so the LLM only interprets, never
recomputes. The ``evidence_index`` covers EVERY detected object (never
truncated) so any id the AI cites can be validated; display sections may
be truncated deterministically per :class:`AIConfig`.

Truncation rules (all deterministic, documented in
``docs/modules/ai-layer.md``):

- swings/legs/breaks: most recent by candle index;
- pools: untapped first, then nearest to current price;
- sweeps/judas/sessions: most recent;
- zones (FVG/OB/SD): only zones within ``proximity_atr`` ATRs of price,
  ordered by (distance, -strength);
- confluence factors and the evidence index: NEVER truncated.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from contexttrading.analysis.indicators import latest_atr
from contexttrading.core.config import AIConfig, EngineConfig
from contexttrading.core.constants import PoolStatus
from contexttrading.core.errors import InsufficientDataError
from contexttrading.core.versioning import SCHEMA_VERSION_AI
from contexttrading.models.base import VersionedModel
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult, DataWindow

_ALL_MODULES = (
    "structure",
    "trend",
    "liquidity",
    "premium_discount",
    "fvg",
    "orderblocks",
    "supplydemand",
    "sessions",
    "confluence",
    "mtf",
)


class EvidenceEntry(VersionedModel):
    """One citable object: id -> compact digest of engine-computed fields."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    id: str = Field(min_length=1)
    kind: str = Field(min_length=1, description="Object type, e.g. 'swing', 'pool', 'factor'.")
    digest: dict[str, Any] = Field(default_factory=dict)


class TruncationEntry(VersionedModel):
    """Record of one truncated category (transparency for the AI)."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    category: str
    shown: int = Field(ge=0)
    total: int = Field(ge=0)
    keep_rule: str = Field(min_length=1)


class DataQualityFlags(VersionedModel):
    """Deterministic data-quality assessment of the context inputs."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    level: Literal["good", "fair", "poor"]
    flags: list[str] = Field(default_factory=list)


class AnalysisContext(VersionedModel):
    """Complete, compact engine state handed to the analyst LLM."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    symbol: str
    timeframe: str
    generated_from: DataWindow
    current_price: float = Field(gt=0)
    atr: float | None = None
    structure: dict[str, Any] = Field(default_factory=dict)
    trend: dict[str, Any] | None = None
    liquidity: dict[str, Any] = Field(default_factory=dict)
    zones_nearby: list[dict[str, Any]] = Field(default_factory=list)
    premium_discount: dict[str, Any] | None = None
    sessions: dict[str, Any] = Field(default_factory=dict)
    mtf: dict[str, Any] | None = None
    confluence: dict[str, Any] | None = None
    setup: dict[str, Any] | None = Field(
        default=None, description="Proposed trade setup (trade evaluation only)."
    )
    data_quality: DataQualityFlags
    truncation: list[TruncationEntry] = Field(default_factory=list)
    evidence_index: dict[str, EvidenceEntry] = Field(default_factory=dict)


class JournalContext(VersionedModel):
    """Provided journal/performance statistics wrapped for interpretation."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    kind: Literal["journal", "performance"]
    period: str = Field(default="")
    statistics: dict[str, Any] = Field(default_factory=dict)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    data_quality: DataQualityFlags
    evidence_index: dict[str, EvidenceEntry] = Field(default_factory=dict)


def _digest(obj: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    """Compact JSON-able projection of a model's fields."""
    dumped = obj.model_dump(mode="json")
    return {key: dumped[key] for key in keys if key in dumped}


def _truncate(
    items: list[Any], category: str, keep_rule: str, cap: int, notes: list[TruncationEntry]
) -> list[Any]:
    if len(items) > cap:
        notes.append(
            TruncationEntry(category=category, shown=cap, total=len(items), keep_rule=keep_rule)
        )
    return items[:cap]


def _zone_distance(price: float, bottom: float, top: float) -> float:
    """Distance from price to a zone (0 when inside)."""
    if bottom <= price <= top:
        return 0.0
    return min(abs(price - bottom), abs(price - top))


def build_analysis_context(
    series: CandleSeries,
    results: dict[str, AnalysisResult],  # type: ignore[type-arg]
    ai_config: AIConfig | None = None,
    engine_config: EngineConfig | None = None,
) -> AnalysisContext:
    """Assemble the complete engine state into an AI-ready context document.

    Args:
        series: Input candles (same window the results were computed from).
        results: ``AnalysisResult`` envelopes keyed by module name.
        ai_config: Proximity/truncation knobs (defaults when None).
        engine_config: ATR period source (defaults when None).

    Returns:
        Versioned :class:`AnalysisContext` with a complete evidence index.
    """
    ai_config = ai_config or AIConfig()
    engine_config = engine_config or EngineConfig()
    cap = ai_config.max_objects_per_category
    notes: list[TruncationEntry] = []
    evidence: dict[str, EvidenceEntry] = {}
    flags: list[str] = []

    price = series.candles[-1].close
    try:
        atr: float | None = latest_atr(series.candles, engine_config.atr_period)
    except InsufficientDataError:
        atr = None
        flags.append("atr_unavailable")

    gaps = series.gaps()
    if gaps:
        flags.append(f"data_gaps:{len(gaps)}")
    for module in _ALL_MODULES:
        if module not in results:
            flags.append(f"module_not_provided:{module}")

    def add(kind: str, obj_id: str, digest: dict[str, Any]) -> None:
        evidence[obj_id] = EvidenceEntry(id=obj_id, kind=kind, digest=digest)

    # --- structure -----------------------------------------------------
    structure_section: dict[str, Any] = {}
    structure = results.get("structure")
    if structure is not None:
        p = structure.payload
        for swing in p.swings:
            add("swing", swing.id, _digest(swing, ("index", "price", "swing_type", "swing_class")))
        for brk in p.breaks:
            add(
                "break",
                brk.id,
                _digest(
                    brk,
                    ("break_type", "direction", "strength", "break_index", "break_price"),
                ),
            )
        for leg in p.legs:
            add(
                "leg",
                leg.id,
                _digest(leg, ("start_index", "end_index", "direction", "kind", "magnitude")),
            )
        recent_swings = sorted(p.swings, key=lambda s: s.index, reverse=True)
        recent_breaks = sorted(p.breaks, key=lambda b: b.break_index, reverse=True)
        recent_legs = sorted(p.legs, key=lambda lg: lg.end_index, reverse=True)
        structure_section = {
            "swing_count": len(p.swings),
            "break_count": len(p.breaks),
            "leg_count": len(p.legs),
            "recent_swings": [
                evidence[s.id].digest | {"id": s.id}
                for s in _truncate(
                    recent_swings, "structure.swings", "most recent by index", cap, notes
                )
            ],
            "recent_breaks": [
                evidence[b.id].digest | {"id": b.id}
                for b in _truncate(
                    recent_breaks, "structure.breaks", "most recent by break index", cap, notes
                )
            ],
            "recent_legs": [
                evidence[lg.id].digest | {"id": lg.id}
                for lg in _truncate(
                    recent_legs, "structure.legs", "most recent by end index", cap, notes
                )
            ],
            "protected_high": (
                _digest(p.protected_high, ("index", "price")) | {"id": p.protected_high.id}
                if p.protected_high is not None
                else None
            ),
            "protected_low": (
                _digest(p.protected_low, ("index", "price")) | {"id": p.protected_low.id}
                if p.protected_low is not None
                else None
            ),
        }
        if p.protected_high is not None:
            evidence.setdefault(
                p.protected_high.id,
                EvidenceEntry(
                    id=p.protected_high.id,
                    kind="swing",
                    digest=_digest(p.protected_high, ("index", "price")),
                ),
            )
        if p.protected_low is not None:
            evidence.setdefault(
                p.protected_low.id,
                EvidenceEntry(
                    id=p.protected_low.id,
                    kind="swing",
                    digest=_digest(p.protected_low, ("index", "price")),
                ),
            )

    # --- trend ----------------------------------------------------------
    trend_section: dict[str, Any] | None = None
    trend = results.get("trend")
    if trend is not None:
        state = trend.payload.state
        trend_section = state.model_dump(mode="json")
        add("trend", "trend:state", trend_section)
        if state.bos_follow_through is None:
            flags.append("insufficient_confirmed_breaks")
        if state.direction.value in ("ranging", "unknown") or state.strength.value == "weak":
            flags.append("trend_weak_or_undecided")

    # --- liquidity ------------------------------------------------------
    liquidity_section: dict[str, Any] = {}
    liquidity = results.get("liquidity")
    if liquidity is not None:
        p = liquidity.payload
        for pool in p.pools:
            add(
                "pool",
                pool.id,
                _digest(pool, ("price", "side", "kind", "pool_class", "status", "formed_at_index")),
            )
        for sweep in p.sweeps:
            add(
                "sweep",
                sweep.id,
                _digest(
                    sweep,
                    (
                        "pool_id",
                        "pool_price",
                        "side",
                        "candle_index",
                        "wick_extreme",
                        "penetration_atr",
                    ),
                ),
            )
        for level in p.equal_levels:
            add("equal_level", level.id, _digest(level, ("price", "side", "count")))
        untapped = [pl for pl in p.pools if pl.status is PoolStatus.UNTAPPED]
        other = [pl for pl in p.pools if pl.status is not PoolStatus.UNTAPPED]
        pools_ordered = sorted(untapped, key=lambda pl: abs(pl.price - price)) + sorted(
            other, key=lambda pl: abs(pl.price - price)
        )
        sweeps_recent = sorted(p.sweeps, key=lambda s: s.candle_index, reverse=True)
        levels_near = sorted(p.equal_levels, key=lambda lv: abs(lv.price - price))
        stale = [
            pl for pl in untapped if pl.formed_at_index < len(series) // 2 and len(series) >= 4
        ]
        if stale:
            flags.append(f"stale_untapped_pools:{len(stale)}")
        liquidity_section = {
            "pools": [
                evidence[pl.id].digest | {"id": pl.id}
                for pl in _truncate(
                    pools_ordered, "liquidity.pools", "untapped first, then nearest", cap, notes
                )
            ],
            "recent_sweeps": [
                evidence[s.id].digest | {"id": s.id}
                for s in _truncate(
                    sweeps_recent, "liquidity.sweeps", "most recent by candle index", cap, notes
                )
            ],
            "equal_levels": [
                evidence[lv.id].digest | {"id": lv.id}
                for lv in _truncate(
                    levels_near, "liquidity.equal_levels", "nearest to price", cap, notes
                )
            ],
            "untapped_count": len(untapped),
        }

    # --- zones near price (FVG / OB / SD) --------------------------------
    zone_candidates: list[dict[str, Any]] = []
    zone_sources = (
        (
            "fvg",
            results.get("fvg"),
            "fvgs",
            ("direction", "status", "strength", "rank", "is_inverse"),
        ),
        (
            "orderblock",
            results.get("orderblocks"),
            None,
            ("direction", "status", "touches"),
        ),
        (
            "supplydemand",
            results.get("supplydemand"),
            "zones",
            ("kind", "status", "strength", "tests", "trend_aligned"),
        ),
    )
    for kind, result, attr, keys in zone_sources:
        if result is None:
            continue
        if attr is not None:
            objects = list(getattr(result.payload, attr))
        else:  # order blocks: three block lists
            p = result.payload
            objects = list(p.order_blocks) + list(p.breaker_blocks) + list(p.mitigation_blocks)
        for obj in objects:
            digest = _digest(obj, ("zone_bottom", "zone_top", *keys))
            add(kind, obj.id, digest)
            distance = _zone_distance(price, obj.zone_bottom, obj.zone_top)
            strength = float(getattr(obj, "strength", 0.0) or 0.0)
            zone_candidates.append(
                {
                    "id": obj.id,
                    "kind": kind,
                    "distance": distance,
                    "strength": strength,
                    "digest": digest,
                }
            )
    proximity = ai_config.proximity_atr * atr if atr is not None else None
    if proximity is not None:
        nearby = [z for z in zone_candidates if z["distance"] <= proximity]
    else:
        nearby = zone_candidates
    nearby.sort(key=lambda z: (z["distance"], -z["strength"], z["id"]))
    zones_nearby = [
        {
            "id": z["id"],
            "kind": z["kind"],
            "distance_atr": round(z["distance"] / atr, 3) if atr else None,
            **z["digest"],
        }
        for z in _truncate(
            nearby,
            "zones_nearby",
            "within proximity ATR, nearest/strongest",
            cap * 3,
            notes,
        )
    ]

    # --- premium / discount ----------------------------------------------
    pd_section: dict[str, Any] | None = None
    dealing = results.get("premium_discount")
    if dealing is not None and dealing.payload.dealing_range is not None:
        dr = dealing.payload.dealing_range
        pd_section = _digest(
            dr,
            (
                "high",
                "low",
                "direction",
                "equilibrium",
                "ote_low",
                "ote_high",
                "ote_fibs",
                "reference_price",
                "price_location",
            ),
        )
        add("dealing_range", "range:dealing", pd_section)

    # --- sessions ---------------------------------------------------------
    sessions_section: dict[str, Any] = {}
    sessions = results.get("sessions")
    if sessions is not None:
        p = sessions.payload
        for stats in p.sessions:
            add(
                "session",
                stats.id,
                _digest(
                    stats,
                    (
                        "session",
                        "trading_date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "direction",
                        "is_killzone",
                        "forms_day_high",
                        "forms_day_low",
                    ),
                ),
            )
        for pool in p.pools:
            add(
                "session_pool",
                pool.id,
                _digest(pool, ("price", "side", "kind", "status")),
            )
        for event in p.session_sweeps:
            add(
                "session_sweep",
                event.id,
                _digest(event, ("swept_group", "swept_price", "sweeping_window", "side")),
            )
        recent_sessions = sorted(
            p.sessions, key=lambda s: (s.trading_date, str(s.session)), reverse=True
        )
        judas_recent = sorted(p.session_sweeps, key=lambda e: e.timestamp, reverse=True)
        session_pools = sorted(
            p.pools,
            key=lambda pl: (pl.status is not PoolStatus.UNTAPPED, abs(pl.price - price)),
        )
        sessions_section = {
            "recent_sessions": [
                evidence[s.id].digest | {"id": s.id}
                for s in _truncate(
                    recent_sessions, "sessions.instances", "most recent by date", cap, notes
                )
            ],
            "pools": [
                evidence[pl.id].digest | {"id": pl.id}
                for pl in _truncate(
                    session_pools, "sessions.pools", "untapped first, then nearest", cap, notes
                )
            ],
            "judas_events": [
                evidence[e.id].digest | {"id": e.id}
                for e in _truncate(judas_recent, "sessions.judas", "most recent", cap, notes)
            ],
        }

    # --- MTF --------------------------------------------------------------
    mtf_section: dict[str, Any] | None = None
    mtf = results.get("mtf")
    if mtf is not None:
        p = mtf.payload
        contexts = [c.model_dump(mode="json") for c in p.contexts]
        unknown = [c for c in p.contexts if c.direction.value == "unknown"]
        if unknown:
            flags.append(f"mtf_unknown_contexts:{len(unknown)}")
        conflicts = [
            c.timeframe.value
            for c in p.contexts[1:]
            if c.direction.value not in ("unknown", p.bias.direction.value)
        ]
        mtf_section = {
            "bias": p.bias.model_dump(mode="json"),
            "contexts": contexts,
            "conflicting_timeframes": conflicts,
        }
        add("mtf_bias", "mtf:bias", mtf_section["bias"])

    # --- confluence (never truncated) --------------------------------------
    confluence_section: dict[str, Any] | None = None
    confluence = results.get("confluence")
    if confluence is not None:
        p = confluence.payload
        factors = []
        for i, factor in enumerate(p.factors):
            key = f"factor:{i:02d}:{factor.factor}"
            digest = _digest(
                factor,
                ("factor", "source_id", "direction", "weight", "raw", "contribution", "detail"),
            )
            add("factor", key, digest)
            factors.append({"id": key, **digest})
        for zone in p.zones:
            add(
                "confluence_zone",
                zone.id,
                _digest(
                    zone,
                    ("direction", "score", "zone_bottom", "zone_top", "member_kinds", "member_ids"),
                ),
            )
        confluence_section = {
            "bias": p.bias.value,
            "score": p.score,
            "bullish_score": p.bullish_score,
            "bearish_score": p.bearish_score,
            "reference_price": p.reference_price,
            "agreeing_factors": p.agreeing_factors,
            "conflicting_factors": p.conflicting_factors,
            "factors": factors,
            "zones": [evidence[z.id].digest | {"id": z.id} for z in p.zones],
        }

    # --- data quality level -------------------------------------------------
    if gaps or len(flags) >= 3:
        level: Literal["good", "fair", "poor"] = "poor"
    elif flags:
        level = "fair"
    else:
        level = "good"

    return AnalysisContext(
        symbol=series.symbol,
        timeframe=str(series.timeframe),
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        current_price=price,
        atr=atr,
        structure=structure_section,
        trend=trend_section,
        liquidity=liquidity_section,
        zones_nearby=zones_nearby,
        premium_discount=pd_section,
        sessions=sessions_section,
        mtf=mtf_section,
        confluence=confluence_section,
        data_quality=DataQualityFlags(level=level, flags=flags),
        truncation=notes,
        evidence_index=evidence,
    )


def _stat_entry(key: str, value: Any) -> EvidenceEntry:
    return EvidenceEntry(id=key, kind="statistic", digest={"value": value})


def build_journal_context(
    trades: list[dict[str, Any]],
    *,
    period: str = "",
) -> JournalContext:
    """Wrap caller-provided journal trades + Python-computed statistics.

    Statistics are computed HERE (deterministic Python over caller data) so
    the AI still never calculates — it interprets provided numbers. Every
    trade id and every ``stat:*`` key is citable.
    """
    cleaned = [dict(t) for t in trades]
    evidence: dict[str, EvidenceEntry] = {}
    pnls: list[float] = []
    for i, trade in enumerate(cleaned):
        trade_id = str(trade.get("id") or f"trade:{i:03d}")
        trade["id"] = trade_id
        evidence[trade_id] = EvidenceEntry(id=trade_id, kind="journal_trade", digest=trade)
        pnl = trade.get("pnl")
        if isinstance(pnl, (int, float)):
            pnls.append(float(pnl))

    wins = [v for v in pnls if v > 0]
    losses = [v for v in pnls if v < 0]
    statistics: dict[str, Any] = {
        "trade_count": len(cleaned),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": (len(wins) / len(pnls)) if pnls else None,
        "avg_win": (sum(wins) / len(wins)) if wins else None,
        "avg_loss": (sum(losses) / len(losses)) if losses else None,
        "profit_factor": (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else None,
        "total_pnl": sum(pnls) if pnls else None,
    }
    for key, value in statistics.items():
        evidence[f"stat:{key}"] = _stat_entry(f"stat:{key}", value)

    flags: list[str] = []
    if len(cleaned) < 10:
        flags.append(f"small_sample:{len(cleaned)}")
    if not pnls:
        flags.append("no_pnl_fields")
    level: Literal["good", "fair", "poor"] = "poor" if not pnls else ("fair" if flags else "good")
    return JournalContext(
        kind="journal",
        period=period,
        statistics=statistics,
        trades=cleaned,
        data_quality=DataQualityFlags(level=level, flags=flags),
        evidence_index=evidence,
    )


def build_performance_context(
    statistics: dict[str, Any],
    *,
    period: str,
    trades: list[dict[str, Any]] | None = None,
) -> JournalContext:
    """Wrap caller-provided period statistics (weekly/monthly) as-is.

    The AI interprets provided numbers; nothing is recomputed. Every
    ``stat:*`` key and provided trade id is citable.
    """
    evidence: dict[str, EvidenceEntry] = {}
    for key, value in statistics.items():
        evidence[f"stat:{key}"] = _stat_entry(f"stat:{key}", value)
    cleaned = [dict(t) for t in (trades or [])]
    for i, trade in enumerate(cleaned):
        trade_id = str(trade.get("id") or f"trade:{i:03d}")
        trade["id"] = trade_id
        evidence[trade_id] = EvidenceEntry(id=trade_id, kind="journal_trade", digest=trade)
    flags: list[str] = []
    count = statistics.get("trade_count")
    if isinstance(count, (int, float)) and count < 10:
        flags.append(f"small_sample:{int(count)}")
    level: Literal["good", "fair", "poor"] = "fair" if flags else "good"
    return JournalContext(
        kind="performance",
        period=period,
        statistics=dict(statistics),
        trades=cleaned,
        data_quality=DataQualityFlags(level=level, flags=flags),
        evidence_index=evidence,
    )
