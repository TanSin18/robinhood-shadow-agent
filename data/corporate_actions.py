from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from uuid import UUID


def quote_with_recorded_identity(item: dict, reads: list[dict]) -> tuple[dict, list[dict]]:
    """Resolve absent quote identity from same-collection, cited broker chain data.

    A ticker alone is never a permanent ID. Missing, conflicting or malformed
    chain evidence leaves the quote unresolved for the normal fail-closed check.
    """
    quote = item.get('quote')
    if not isinstance(quote, dict):
        raise CorporateActionError('CORPORATE_ACTION_UNRESOLVED', 'quote is malformed')
    if any((item.get('permanent_security_id'), quote.get('permanent_security_id'),
            quote.get('instrument_id'), item.get('instrument_id'))):
        return item, []
    symbol = quote.get('symbol')
    identities = set()
    evidence = []
    invalid = False
    for read in reads:
        if read.get('tool') != 'get_option_chains' or read.get('arguments', {}).get('underlying_symbol') != symbol:
            continue
        source_hash = read.get('content_hash', '')
        if read.get('source_id') != 'robinhood-mcp:get_option_chains' or not isinstance(source_hash, str) or len(source_hash) != 64 or any(c not in '0123456789abcdef' for c in source_hash):
            invalid = True
            continue
        for chain in read.get('data', {}).get('chains', []) or []:
            if not isinstance(chain, dict) or chain.get('symbol') != symbol:
                continue
            for underlying in chain.get('underlying_instruments', []) or []:
                # Current MCP leaves this field blank; the requested and returned
                # chain symbols must still match. A contradictory symbol is denied.
                if not isinstance(underlying, dict) or underlying.get('symbol') not in {symbol, ''}:
                    invalid = True
                    continue
                try:
                    url = urlparse(underlying['instrument'])
                    parts = url.path.strip('/').split('/')
                    # Parse identifiers only; never fetch either URL. The second
                    # origin is the literal identifier origin observed in MCP.
                    origins={('https','api.robinhood.com'),('http','edge-internal.brokeback-shard-router.region.rh')}
                    if (url.scheme,url.netloc) not in origins or url.query or url.fragment or len(parts) != 2 or parts[0] != 'instruments':
                        raise ValueError()
                    identity = str(UUID(parts[1]))
                except (KeyError, ValueError, TypeError, AttributeError):
                    invalid = True
                    continue
                identities.add(identity)
                evidence.append({'kind':'identity_resolution','symbol':symbol,
                                 'permanent_security_id':identity,
                                 'source_id':read['source_id'],'source_hash':source_hash})
    if invalid or len(identities) != 1:
        return item, []
    resolved = deepcopy(item)
    resolved['permanent_security_id'] = next(iter(identities))
    return resolved, evidence


class CorporateActionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class NormalizationResult:
    record: dict
    audit: list[dict]


def _aware(value, field):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", f"{field} is invalid")
    return value


def normalize_live_security(record: dict, actions: list[dict], *, known_at: datetime) -> NormalizationResult:
    if known_at.tzinfo is None:
        raise ValueError("known_at must be timezone-aware")
    normalized = deepcopy(record)
    security_id = normalized.get("permanent_security_id")
    if not isinstance(security_id, str) or not security_id:
        raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "permanent security ID is missing")
    audit: list[dict] = []
    applicable = []
    for action in actions:
        action_known = _aware(action.get("known_at"), "known_at")
        effective = _aware(action.get("effective_at"), "effective_at")
        if action_known > known_at or effective > known_at:
            continue
        applicable.append(action)
    applicable.sort(key=lambda item: item["effective_at"])

    for action in applicable:
        kind = action.get("kind")
        if kind not in {"split", "reverse_split", "ticker_change"}:
            raise CorporateActionError(
                "CORPORATE_ACTION_SCOPE_NOT_IMPLEMENTED", f"{kind!r} is Phase 2 scope"
            )
        if action.get("permanent_security_id") != security_id:
            raise CorporateActionError(
                "CORPORATE_ACTION_UNRESOLVED", "permanent security identity does not match"
            )
        announcement = _aware(action.get("announcement_at"), "announcement_at")
        source_id = action.get("source_id")
        content_hash = action.get("content_hash")
        if (
            announcement > known_at
            or not isinstance(source_id, str)
            or not source_id
            or not isinstance(content_hash, str)
            or len(content_hash) != 64
        ):
            raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "action provenance is invalid")
        before = deepcopy(normalized)
        factor = None
        if kind in {"split", "reverse_split"}:
            try:
                factor = Decimal(str(action.get("ratio")))
            except (InvalidOperation, ValueError):
                raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "split ratio is invalid") from None
            if not factor.is_finite() or factor <= 0:
                raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "split ratio is invalid")
            for field in ("price", "cost_basis"):
                if field in normalized:
                    normalized[field] = Decimal(str(normalized[field])) / factor
            for field in ("quantity", "volume"):
                if field in normalized:
                    normalized[field] = Decimal(str(normalized[field])) * factor
            deliverable = normalized.get("option_deliverable")
            if deliverable is not None:
                if not isinstance(deliverable, dict) or not {"strike", "multiplier"} <= set(deliverable):
                    raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "option deliverable is incomplete")
                deliverable["strike"] = Decimal(str(deliverable["strike"])) / factor
                deliverable["multiplier"] = Decimal(str(deliverable["multiplier"])) * factor
        else:
            if action.get("old_symbol") != normalized.get("symbol"):
                raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "ticker lineage does not match")
            new_symbol = action.get("new_symbol")
            if not isinstance(new_symbol, str) or not new_symbol:
                raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "new ticker is invalid")
            normalized["symbol"] = new_symbol
        audit.append(
            {
                "kind": kind,
                "announcement_at": announcement.isoformat(),
                "effective_at": action["effective_at"].isoformat(),
                "source_id": source_id,
                "content_hash": content_hash,
                "adjustment_factor": str(factor) if factor is not None else None,
                "pre_normalized_values": before,
                "normalized_values": deepcopy(normalized),
            }
        )
    return NormalizationResult(record=normalized, audit=audit)


def normalize_live_quote(item: dict, *, known_at: datetime) -> NormalizationResult:
    """Normalize one live quote while retaining a permanent security identity."""

    copied = deepcopy(item)
    quote = copied.get("quote")
    if not isinstance(quote, dict):
        raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "quote is missing")
    security_id = (
        copied.get("permanent_security_id")
        or quote.get("permanent_security_id")
        or quote.get("instrument_id")
        or copied.get("instrument_id")
    )
    raw_actions = copied.get("corporate_actions", [])
    if not isinstance(raw_actions, list):
        raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "actions are malformed")
    actions = []
    for raw in raw_actions:
        if not isinstance(raw, dict):
            raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "action is malformed")
        parsed = dict(raw)
        for field in ("announcement_at", "known_at", "effective_at"):
            if isinstance(parsed.get(field), str):
                try:
                    parsed[field] = datetime.fromisoformat(parsed[field].replace("Z", "+00:00"))
                except ValueError:
                    raise CorporateActionError(
                        "CORPORATE_ACTION_UNRESOLVED", f"{field} is invalid"
                    ) from None
        actions.append(parsed)
    try:
        bid = Decimal(str(quote["bid_price"]))
        ask = Decimal(str(quote["ask_price"]))
    except (KeyError, InvalidOperation, ValueError):
        raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "quote prices are invalid") from None
    if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask <= 0 or bid > ask:
        # A zero-bid option is not evidence of an unresolved split or rename.
        # Keep it excluded without misdiagnosing every other usable security.
        raise CorporateActionError("INVALID_QUOTE_PRICE", "positive finite uncrossed bid/ask required")
    base = {
        "permanent_security_id": security_id,
        "symbol": quote.get("symbol") or quote.get("instrument_id"),
        "price": bid,
    }
    result = normalize_live_security(base, actions, known_at=known_at)
    factor = bid / result.record["price"] if result.record["price"] else Decimal("0")
    if not factor.is_finite() or factor <= 0:
        raise CorporateActionError("CORPORATE_ACTION_UNRESOLVED", "quote adjustment is invalid")
    quote["bid_price"] = str(result.record["price"])
    quote["ask_price"] = str(ask / factor)
    quote["symbol"] = result.record["symbol"]
    copied["permanent_security_id"] = security_id
    return NormalizationResult(record=copied, audit=result.audit)
