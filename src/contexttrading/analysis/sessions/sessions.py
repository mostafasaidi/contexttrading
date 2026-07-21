"""Sessions module orchestrator.

Pipeline: resolve configured windows (SessionConfig) -> track instances and
calendar-day levels -> accumulate per-session statistics -> synthesize
session/Asian-range/previous-day liquidity pools -> run the standard sweep
scan -> classify Judas swings -> summarize which window forms day extremes.

Deviation from the strict one-config module contract: session windows live
in :class:`SessionConfig` (a separate settings section), so the entrypoint
takes it as a second optional parameter. Both configs default to the
documented UTC windows, keeping the call deterministic.
"""

from __future__ import annotations

from contexttrading.analysis.liquidity.sweeps import scan_sweeps
from contexttrading.analysis.sessions.definitions import resolve_windows
from contexttrading.analysis.sessions.tracker import (
    _track_instances,
    build_session_pools,
    build_session_stats,
    compute_asian_ranges,
    compute_day_levels,
    detect_judas_swings,
)
from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.core.config import EngineConfig, SessionConfig
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult, DataWindow
from contexttrading.models.session import SessionResult


def analyze_sessions(
    series: CandleSeries,
    engine_config: EngineConfig | None = None,
    session_config: SessionConfig | None = None,
) -> AnalysisResult[SessionResult]:
    """Run the full session pipeline over a series.

    Args:
        series: Input candles (UTC timestamps).
        engine_config: Engine thresholds (ATR, sweep classification, doji).
        session_config: Session/killzone windows and timezone (defaults to
            the documented UTC windows).

    Returns:
        Envelope with per-instance stats, session-derived pools and sweeps,
        Judas swings, and day-extreme summary counts.
    """
    engine_config = engine_config or EngineConfig()
    session_config = session_config or SessionConfig()
    tz = session_config.tzinfo()
    windows = resolve_windows(session_config)

    scan = StructureScanner(engine_config).run(series)
    instances = []
    for window in windows:
        instances.extend(_track_instances(series, window, tz))
    asian_ranges = compute_asian_ranges(series, windows, tz)
    day_levels = compute_day_levels(series, tz)

    all_instances = [*instances, *asian_ranges]
    stats = build_session_stats(
        all_instances, series, day_levels, scan.atr_values, engine_config, tz
    )
    stats_ids = {
        (s.session, s.trading_date, inst.start_index): s.id
        for s, inst in zip(stats, all_instances, strict=True)
    }
    stats.sort(key=lambda s: (s.start_time, s.session))

    pools, pool_groups = build_session_pools(instances, asian_ranges, day_levels, stats_ids)
    updated_pools, sweeps = scan_sweeps(series, pools, scan.breaks, scan.atr_values, engine_config)
    killzones = [w for w in windows if w.is_killzone]
    session_sweeps = detect_judas_swings(sweeps, pool_groups, killzones, tz)

    day_high_counts: dict[str, int] = {}
    day_low_counts: dict[str, int] = {}
    for s in stats:
        if s.is_killzone:
            continue
        if s.forms_day_high:
            day_high_counts[s.session] = day_high_counts.get(s.session, 0) + 1
        if s.forms_day_low:
            day_low_counts[s.session] = day_low_counts.get(s.session, 0) + 1

    def _dominant(counts: dict[str, int]) -> str | None:
        if not counts:
            return None
        return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]

    payload = SessionResult(
        sessions=stats,
        pools=updated_pools,
        sweeps=sweeps,
        session_sweeps=session_sweeps,
        day_high_counts=day_high_counts,
        day_low_counts=day_low_counts,
        dominant_high_session=_dominant(day_high_counts),
        dominant_low_session=_dominant(day_low_counts),
    )
    return AnalysisResult[SessionResult](
        module="sessions",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=payload,
    )
