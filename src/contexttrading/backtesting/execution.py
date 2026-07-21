"""Deterministic fill, cost, and position-management models.

Fill rules (all prices derive from candle data only — no randomness):

- **Spread**: ``spread_bps`` is the full bid/ask spread; each fill pays half
  of it against the trade direction (buys pay up, sells receive less).
- **Slippage**: ``slippage_bps`` moves the fill against the direction on
  market and stop fills. Limit fills (incl. take-profits) get NO slippage —
  resting limit orders fill at their price or better.
- **Market entry**: next bar OPEN + half-spread + slippage.
- **Limit entry**: fills when the next bar's range TOUCHES the price
  (``low <= P`` for buys; ties count as filled — conservative). A gap
  through the level fills at the bar open (better price), never beyond.
- **Stop entry**: fills when the next bar's range touches the trigger; a
  gap through fills at the bar open (worse price).
- **Stop-loss exit** (a stop order): fills at the SL price + slippage; if
  the bar OPENS beyond the SL (gap-through), fills at the open.
- **Take-profit exit** (a limit order): fills at the TP price, no
  slippage; if the bar opens beyond the TP, fills at the open.
- **Intrabar ambiguity**: when SL and TP both lie inside one bar's range,
  the SL is assumed hit FIRST (conservative). This is a fixed rule, not a
  config flag.
- A position filled at bar ``i``'s open can be stopped out on bar ``i``
  itself (same-bar SL/TP check after the fill).

Commission: ``commission_bps`` of notional, charged on entry and exit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from contexttrading.core.config import BacktestConfig
from contexttrading.core.constants import TrendDirection
from contexttrading.core.errors import BacktestError
from contexttrading.models.backtest import OrderIntent, TradeRecord

if TYPE_CHECKING:
    import datetime

    from contexttrading.models.candle import Candle

_BPS = 1e-4


def _half_spread(config: BacktestConfig) -> float:
    return config.spread_bps * _BPS / 2.0


def _slippage(config: BacktestConfig) -> float:
    return config.slippage_bps * _BPS


def adverse(price: float, fraction: float, sign: int) -> float:
    """Move ``price`` against the trader: buys pay more, sells receive less."""
    return price * (1.0 + sign * fraction)


def commission(price: float, units: float, config: BacktestConfig) -> float:
    """Commission on one fill (per side), in currency."""
    return price * units * config.commission_bps * _BPS


def market_fill(sign: int, ref_price: float, config: BacktestConfig, *, slippage: bool) -> float:
    """Fill price for a market/stop order at ``ref_price`` (open or trigger)."""
    fraction = _half_spread(config) + (_slippage(config) if slippage else 0.0)
    return adverse(ref_price, fraction, sign)


def try_fill_intent(intent: OrderIntent, bar: Candle, config: BacktestConfig) -> float | None:
    """Attempt to fill an entry intent on ``bar`` (the bar AFTER the decision).

    Returns the fill price (spread/slippage applied) or None when a
    limit/stop trigger was not touched. ``close`` intents are handled by
    the replay loop, not here.
    """
    sign = intent.direction.sign
    if sign == 0:
        raise BacktestError(
            "Entry intents require BULLISH or BEARISH direction",
            context={"kind": intent.kind, "created_index": intent.created_index},
        )
    if intent.kind == "market":
        return market_fill(sign, bar.open, config, slippage=True)
    if intent.price is None:
        raise BacktestError(
            "limit/stop intents require a trigger price",
            context={"kind": intent.kind, "created_index": intent.created_index},
        )
    price = intent.price
    if intent.kind == "limit":
        if sign > 0 and bar.low <= price:
            ref = min(bar.open, price)  # gap through -> open (better for the buyer)
            return adverse(ref, _half_spread(config), sign)
        if sign < 0 and bar.high >= price:
            ref = max(bar.open, price)
            return adverse(ref, _half_spread(config), sign)
        return None
    if intent.kind == "stop":
        if sign > 0 and bar.high >= price:
            ref = max(bar.open, price)  # gap through -> open (worse for the buyer)
            return market_fill(sign, ref, config, slippage=True)
        if sign < 0 and bar.low <= price:
            ref = min(bar.open, price)
            return market_fill(sign, ref, config, slippage=True)
        return None
    raise BacktestError(
        f"Unsupported intent kind for entry fill: {intent.kind}",
        context={"kind": intent.kind},
    )


def size_position(
    intent: OrderIntent, equity: float, entry_fill: float, config: BacktestConfig
) -> float:
    """Position size in units.

    Explicit ``intent.size_units`` wins; otherwise the configured mode:
    ``fixed_units`` or ``risk_percent`` (equity % at risk via SL distance).
    """
    if intent.size_units is not None:
        return intent.size_units
    if config.position_sizing == "fixed_units":
        return config.fixed_units
    if intent.stop_loss is None:
        raise BacktestError(
            "risk_percent sizing requires a stop_loss on the intent",
            context={"created_index": intent.created_index},
        )
    risk_distance = abs(entry_fill - intent.stop_loss)
    if risk_distance <= 0:
        raise BacktestError(
            "stop_loss must differ from the entry fill for risk sizing",
            context={"entry_fill": entry_fill, "stop_loss": intent.stop_loss},
        )
    return (equity * config.risk_percent / 100.0) / risk_distance


@dataclass
class PositionState:
    """Mutable runtime position (NOT a wire model — TradeRecord is the output)."""

    direction: TrendDirection
    sign: int
    size_units: float
    entry_index: int
    entry_timestamp: datetime.datetime
    entry_price: float
    stop_loss: float
    take_profit: float | None
    initial_risk_distance: float
    commission_entry: float
    evidence_ids: list[str] = field(default_factory=list)
    tag: str = ""
    min_price: float = 0.0  # lowest low since entry (incl. entry bar)
    max_price: float = 0.0  # highest high since entry

    def update_excursion(self, bar: Candle) -> None:
        self.min_price = bar.low if self.min_price == 0.0 else min(self.min_price, bar.low)
        self.max_price = max(self.max_price, bar.high)

    def open_pnl(self, price: float) -> float:
        return (price - self.entry_price) * self.sign * self.size_units

    def mfe_r(self) -> float:
        favorable = (
            (self.max_price - self.entry_price)
            if self.sign > 0
            else (self.entry_price - self.min_price)
        )
        return max(0.0, favorable) / self.initial_risk_distance

    def apply_breakeven(self) -> None:
        """Move the stop to the entry price (never backwards)."""
        if self.sign > 0:
            self.stop_loss = max(self.stop_loss, self.entry_price)
        else:
            self.stop_loss = min(self.stop_loss, self.entry_price)


def manage_position(
    position: PositionState, bar: Candle, config: BacktestConfig
) -> tuple[float, str] | None:
    """SL/TP check for one bar. Returns (exit_fill, reason) or None.

    Gap-through at the open takes precedence over both levels; the
    SL-first rule resolves intrabar ambiguity conservatively.
    """
    sign = position.sign
    exit_sign = -sign  # closing a long sells, closing a short buys
    sl = position.stop_loss
    tp = position.take_profit

    sl_hit = bar.low <= sl if sign > 0 else bar.high >= sl
    tp_hit = tp is not None and (bar.high >= tp if sign > 0 else bar.low <= tp)
    sl_gapped = bar.open <= sl if sign > 0 else bar.open >= sl
    tp_gapped = tp is not None and (bar.open >= tp if sign > 0 else bar.open <= tp)

    if sl_hit and sl_gapped:
        return market_fill(exit_sign, bar.open, config, slippage=True), "stop_loss"
    if tp_hit and tp_gapped:
        # The bar OPENED beyond the TP: the resting limit fills at the open,
        # chronologically before anything else in the bar.
        return adverse(bar.open, _half_spread(config), exit_sign), "take_profit"
    if sl_hit:  # includes the ambiguous (SL and TP in range) case -> SL first
        return market_fill(exit_sign, sl, config, slippage=True), "stop_loss"
    if tp_hit and tp is not None:
        return adverse(tp, _half_spread(config), exit_sign), "take_profit"
    return None


def close_trade(
    position: PositionState,
    *,
    exit_price: float,
    exit_index: int,
    exit_timestamp: datetime.datetime,
    reason: str,
    sequence: int,
    config: BacktestConfig,
) -> TradeRecord:
    """Build the immutable TradeRecord for a closed position."""
    commission_exit = commission(exit_price, position.size_units, config)
    gross = (exit_price - position.entry_price) * position.sign * position.size_units
    net = gross - position.commission_entry - commission_exit
    risk = position.initial_risk_distance
    r_multiple = (exit_price - position.entry_price) * position.sign / risk
    if position.sign > 0:
        mae_price = max(0.0, position.entry_price - position.min_price)
        mfe_price = max(0.0, position.max_price - position.entry_price)
    else:
        mae_price = max(0.0, position.max_price - position.entry_price)
        mfe_price = max(0.0, position.entry_price - position.min_price)
    return TradeRecord(
        sequence=sequence,
        direction=position.direction,
        tag=position.tag,
        entry_index=position.entry_index,
        entry_timestamp=position.entry_timestamp,
        entry_price=position.entry_price,
        exit_index=exit_index,
        exit_timestamp=exit_timestamp,
        exit_price=exit_price,
        size_units=position.size_units,
        stop_loss=position.stop_loss,
        take_profit=position.take_profit,
        initial_risk_distance=risk,
        exit_reason=reason,  # type: ignore[arg-type]
        gross_pnl=gross,
        commission_paid=position.commission_entry + commission_exit,
        net_pnl=net,
        r_multiple=r_multiple,
        mae_price=mae_price,
        mfe_price=mfe_price,
        mae_r=mae_price / risk,
        mfe_r=mfe_price / risk,
        holding_bars=exit_index - position.entry_index,
        evidence_ids=list(position.evidence_ids),
    )
