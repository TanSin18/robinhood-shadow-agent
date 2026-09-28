"""Canonical Stage 1 read contracts shared by the proxy and application."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


REQUEST_MAX_BYTES = 64 * 1024
RESPONSE_MAX_BYTES = 8 * 1024 * 1024


def schema(properties: dict, required: tuple[str, ...] = ()) -> dict:
    result = {"type": "object", "additionalProperties": False}
    if properties:
        result["properties"] = properties
    if required:
        result["required"] = list(required)
    return result


STRING = {"type": "string"}
STRINGS = {"type": ["null", "array"], "items": STRING}

# Structural schemas captured from the official Robinhood MCP catalog.
# Descriptions and titles are deliberately excluded from comparisons.
SCHEMAS = {
    "get_accounts": schema({}),
    "get_portfolio": schema({"account_number": STRING}, ("account_number",)),
    "get_equity_positions": schema(
        {"account_number": STRING, "cursor": STRING}, ("account_number",)
    ),
    "get_equity_quotes": schema({"symbols": STRINGS}, ("symbols",)),
    "get_equity_historicals": schema(
        {
            "symbols": STRINGS,
            **{
                key: STRING
                for key in (
                    "start_time",
                    "end_time",
                    "interval",
                    "bounds",
                    "adjustment_type",
                )
            },
        },
        ("symbols", "start_time"),
    ),
    "get_option_chains": schema(
        {key: STRING for key in ("ids", "underlying_symbol")}
    ),
    "get_option_instruments": schema(
        {
            key: STRING
            for key in (
                "chain_id",
                "chain_symbol",
                "expiration_dates",
                "strike_price",
                "type",
                "state",
                "tradability",
                "ids",
                "cursor",
            )
        }
    ),
    "get_option_quotes": schema(
        {"instrument_ids": STRINGS}, ("instrument_ids",)
    ),
    "get_equity_orders": schema(
        {
            key: STRING
            for key in (
                "account_number",
                "created_at_gte",
                "cursor",
                "order_id",
                "placed_agent",
                "state",
                "symbol",
            )
        },
        ("account_number",),
    ),
    "get_option_orders": schema(
        {
            key: STRING
            for key in (
                "account_number",
                "chain_ids",
                "created_at_gte",
                "cursor",
                "order_id",
                "placed_agent",
                "state",
                "underlying_type",
            )
        },
        ("account_number",),
    ),
    "get_crypto_orders": schema(
        {
            key: STRING
            for key in (
                "rhs_account_number",
                "created_at_gte",
                "cursor",
                "order_id",
                "side",
                "state",
                "state_group",
                "symbol",
                "updated_at_gte",
            )
        },
        ("rhs_account_number",),
    ),
}

READ_METHODS = frozenset(SCHEMAS)


def structural(value):
    if isinstance(value, dict):
        return {k: structural(v) for k, v in value.items() if k not in {'description', 'title'}}
    if isinstance(value, list):
        return [structural(v) for v in value]
    return value

SCHEMA_MANIFEST_SHA256 = '158c6634d4255b68a2f3312eb2d5edc1f2eb81c66bf894d45a69d6765c77cf1e'


def validate_schema_manifest():
    contents = Path(__file__).with_name('read_schemas_v1.4.2.json').read_bytes()
    if hashlib.sha256(contents).hexdigest() != SCHEMA_MANIFEST_SHA256:
        raise ValueError('approved read schema manifest hash mismatch')
    if json.loads(contents) != SCHEMAS or len(SCHEMAS) != 11:
        raise ValueError('approved read schemas changed')
    return SCHEMA_MANIFEST_SHA256


validate_schema_manifest()


@dataclass(frozen=True)
class ToolView:
    name: str
    inputSchema: dict
