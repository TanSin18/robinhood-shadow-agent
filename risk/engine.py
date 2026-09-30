from __future__ import annotations

from decimal import Decimal

from agents.schemas import TradeProposal
from config.loader import RiskConfig
from risk.models import RiskContext, RiskReason, RiskVerdict


class RiskEngine:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def sized_notional(self, account_value: Decimal, realized_vol: Decimal) -> Decimal:
        if not realized_vol.is_finite() or realized_vol <= 0:
            raise ValueError('positive finite realized volatility required')
        return account_value * min(self.config.max_position_fraction, self.config.target_position_fraction * self.config.target_volatility_fraction / realized_vol)

    def evaluate(self, proposal: TradeProposal, context: RiskContext, *,
                 etf_entry_reference: Decimal | None = None) -> RiskVerdict:
        reasons: list[RiskReason] = []
        actions: list[str] = []
        if proposal.asset_class != 'option' and proposal.multiplier != 1:
            reasons.append(RiskReason.INVALID_MULTIPLIER)
        if context.missing_position_marks and proposal.side == 'buy':
            reasons.append(RiskReason.MISSING_POSITION_MARK)
        held = context.position_quantities.get(proposal.ticker, Decimal(0))
        closing = proposal.side == 'sell' and proposal.quantity <= held
        if proposal.side == 'sell' and not closing:
            reasons.append(RiskReason.INSUFFICIENT_POSITION)
        if proposal.is_closing and not closing:
            reasons.append(RiskReason.INVALID_CLOSING)
        multiplier = 100 if proposal.asset_class == 'option' else 1
        proposed_value = proposal.quantity * proposal.limit_price * multiplier
        if proposal.side == 'buy' and proposed_value > context.settled_cash:
            reasons.append(RiskReason.INSUFFICIENT_SETTLED_CASH)

        if proposal.account_id != self.config.agentic_account_id:
            reasons.append(RiskReason.WRONG_ACCOUNT)
        if (proposal.underlying_ticker if proposal.asset_class == 'option' else proposal.ticker) not in self.config.instrument_whitelist:
            reasons.append(RiskReason.NOT_WHITELISTED)
        if proposal.order_type != "limit":
            reasons.append(RiskReason.LIMIT_ONLY)

        quote_age = (context.now - context.quote_timestamp).total_seconds()
        if quote_age < 0 or quote_age > self.config.max_quote_age_seconds:
            reasons.append(RiskReason.STALE_QUOTE)
        reference = context.ask if proposal.side == "buy" else context.bid
        if etf_entry_reference is not None:
            # The inactive v1.5 desk planner supplies its immutable first-fresh
            # midpoint. Do not chase a later ask or alter other risk checks.
            if proposal.asset_class != 'etf' or proposal.side != 'buy':
                reasons.append(RiskReason.LIMIT_TOO_FAR)
            reference = etf_entry_reference
        if not reference.is_finite() or reference <= 0 or (
            abs(proposal.limit_price - reference) / reference
            > self.config.max_limit_distance_fraction
        ):
            reasons.append(RiskReason.LIMIT_TOO_FAR)

        if not closing:
            existing_value = context.position_values.get(proposal.ticker, Decimal("0"))
            vol = context.realized_volatility_20d
            vol_age = (context.now - context.volatility_as_of).total_seconds() if context.volatility_as_of else -1
            if vol is None or not vol.is_finite() or vol <= 0 or vol_age < 0 or vol_age > 7 * 86400:
                reasons.append(RiskReason.INVALID_REALIZED_VOLATILITY)
            elif proposal.side == 'buy' and proposed_value + existing_value > self.sized_notional(context.account_value, vol) and proposed_value + existing_value <= context.account_value * self.config.max_position_fraction:
                reasons.append(RiskReason.VOLATILITY_SIZE_LIMIT)
            if proposed_value + existing_value > (
                context.account_value * self.config.max_position_fraction
            ):
                reasons.append(RiskReason.POSITION_TOO_LARGE)
            if (
                proposal.ticker not in context.position_values
                and context.open_position_count >= self.config.max_open_positions
            ):
                reasons.append(RiskReason.TOO_MANY_POSITIONS)

        if proposal.asset_class == "option":
            if not self.config.options_unlocked:
                reasons.append(RiskReason.OPTIONS_LOCKED)
            if (proposal.max_loss_usd is None or proposal.max_loss_usd <= 0 or proposal.option_strategy not in {'long_call', 'long_put'} or proposal.multiplier != 100 or proposal.quantity != proposal.quantity.to_integral_value() or (proposal.side == 'buy' and proposal.max_loss_usd != proposed_value)):
                reasons.append(RiskReason.OPTION_NOT_DEFINED_RISK)
            if proposal.naked_short_call:
                reasons.append(RiskReason.NAKED_SHORT_CALL)
            if proposal.expiry is None or proposal.expiry < context.now.date() or (proposal.expiry == context.now.date() and not closing) or proposal.strike is None or proposal.option_type is None or proposal.option_strategy != f'long_{proposal.option_type}':
                reasons.append(RiskReason.OPTION_NOT_DEFINED_RISK)

        drawdown = (
            (context.peak_value - context.current_value) / context.peak_value
            if context.peak_value > 0
            else Decimal("0")
        )
        emergency_close = closing and drawdown >= self.config.drawdown_lock_fraction
        if not emergency_close:
            if context.orders_today >= self.config.max_orders_per_day:
                reasons.append(RiskReason.DAILY_ORDER_LIMIT)
            prior_sides = context.traded_sides_today.get(proposal.ticker, frozenset())
            opposite = "sell" if proposal.side == "buy" else "buy"
            if opposite in prior_sides:
                reasons.append(RiskReason.SAME_DAY_ROUND_TRIP)

        if (
            not closing
            and context.daily_pnl
            <= -(context.account_value * self.config.daily_loss_fraction)
        ):
            reasons.append(RiskReason.DAILY_LOSS_LIMIT)

        if drawdown >= self.config.drawdown_lock_fraction and not closing:
            if not context.manually_unlocked_after_drawdown:
                reasons.append(RiskReason.DRAWDOWN_LOCK)
                actions.extend(("propose_close_all", "manual_unlock_required"))
        elif (
            drawdown >= self.config.drawdown_buy_block_fraction
            and proposal.side == "buy"
            and not closing
        ):
            reasons.append(RiskReason.DRAWDOWN_BUY_BLOCK)
            actions.append("alert_drawdown_10")

        request_id = proposal.client_order_id or proposal.proposal_id
        if request_id in context.seen_client_order_ids:
            reasons.append(RiskReason.DUPLICATE_ORDER)
        if context.auto_approve_requested:
            reasons.append(RiskReason.AUTO_APPROVE_FORBIDDEN)
        if context.kill_switch and not closing:
            reasons.append(RiskReason.KILL_SWITCH)
        if any(item.contains_instructions for item in proposal.evidence):
            reasons.append(RiskReason.INJECTED_INSTRUCTIONS)

        unique_reasons = tuple(dict.fromkeys(reasons))
        allowed = not unique_reasons
        status = "allowed" if allowed else (
            "would_have_blocked" if context.stage == 1 else "blocked"
        )
        return RiskVerdict(
            allowed=allowed,
            status=status,
            reasons=unique_reasons,
            actions=tuple(dict.fromkeys(actions)),
        )
