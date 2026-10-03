"""Reads the numbers a company tagged in its own filing document (Inline XBRL), so that a fact taken from the SEC's
data API can be checked against the filing itself. Pure text handling: no network, no file, nothing is corrected.

Only entity-level facts are read: a context with a segment (a dimension such as a product line or a region) is left
out, because the data API's company facts are entity-level too. A number written in a format this reader does not
know is skipped, never guessed, so it can only make a check come back "not found", not "confirmed".
"""
from __future__ import annotations

import html
import re
from decimal import Decimal, InvalidOperation

CONFIRMED, MISMATCH, NOT_FOUND, NOT_CHECKED = 'CONFIRMED', 'MISMATCH', 'NOT_FOUND', 'NOT_CHECKED'
_CONTEXT = re.compile(r'<(?:xbrli:)?context\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</(?:xbrli:)?context>', re.S | re.I)
_START = re.compile(r'<(?:xbrli:)?startDate>\s*([0-9-]{10})', re.I)
_END = re.compile(r'<(?:xbrli:)?endDate>\s*([0-9-]{10})', re.I)
_INSTANT = re.compile(r'<(?:xbrli:)?instant>\s*([0-9-]{10})', re.I)
_SEGMENT = re.compile(r'<(?:xbrli:)?(?:segment|scenario)\b', re.I)
_FACT = re.compile(r'<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>', re.S | re.I)
_ATTRIBUTE = re.compile(r'([A-Za-z_:][\w:.-]*)\s*=\s*"([^"]*)"')
_TAG = re.compile(r'<[^>]+>')
ZERO_FORMATS = ('zerodash', 'fixed-zero', 'nocontent', 'numdash')
DOT_DECIMAL = ('num-dot-decimal', 'numdotdecimal', 'numcommadot')
COMMA_DECIMAL = ('num-comma-decimal', 'numcommadecimal', 'numdotcomma')


def contexts(text: str) -> dict:
    """Context id -> (start or None, end) for contexts with no dimension."""
    out = {}
    for identifier, body in _CONTEXT.findall(text):
        if _SEGMENT.search(body):
            continue
        instant, start, end = _INSTANT.search(body), _START.search(body), _END.search(body)
        if instant:
            out[identifier] = (None, instant.group(1))
        elif start and end:
            out[identifier] = (start.group(1), end.group(1))
    return out


def _number(raw: str, fmt: str):
    text = html.unescape(_TAG.sub('', raw)).replace('\xa0', ' ').strip()
    style = fmt.split(':')[-1].lower()
    if style in ZERO_FORMATS:
        return Decimal(0)
    if style in COMMA_DECIMAL:
        text = text.replace('.', '').replace(' ', '').replace(',', '.')
    elif style in DOT_DECIMAL or not fmt:
        text = text.replace(',', '').replace(' ', '')
    else:
        return None                                    # a written-out or unknown format: not read, not guessed
    text = text.strip('()')
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def numeric_facts(document) -> dict:
    """(concept without prefix, start or None, end) -> set of values, for us-gaap facts in dimensionless contexts."""
    text = document.decode('utf-8', 'replace') if isinstance(document, (bytes, bytearray)) else str(document)
    periods = contexts(text)
    out = {}
    for attributes, body in _FACT.findall(text):
        a = dict(_ATTRIBUTE.findall(attributes))
        name, context = a.get('name', ''), a.get('contextRef')
        if not name.startswith('us-gaap:') or context not in periods:
            continue
        value = _number(body, a.get('format', ''))
        if value is None:
            continue
        try:
            value = value * (Decimal(10) ** int(a.get('scale') or 0))
        except (ValueError, InvalidOperation):
            continue
        if a.get('sign') == '-':
            value = -value
        out.setdefault((name.split(':', 1)[1], *periods[context]), set()).add(value)
    return out


def check(record, filing_facts) -> str:
    """Whether the filing's own document carries this fact with this value."""
    if filing_facts is None:
        return NOT_CHECKED
    found = filing_facts.get((record['concept'], record.get('period_start'), record['period_end']))
    if not found:
        return NOT_FOUND
    try:
        wanted = Decimal(str(record['value']))
    except InvalidOperation:
        return MISMATCH
    return CONFIRMED if wanted in found else MISMATCH
