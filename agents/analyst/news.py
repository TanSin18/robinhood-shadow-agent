"""Free news feeds, no keys: Google News RSS search and SEC EDGAR filings.

Everything fetched here is untrusted text. It is stored as data, shown with its source link, and
passed to the commentary model only inside a clearly labelled data block. It never reaches the
official run, the risk engine or any order path.

EDGAR asks every client to identify itself with a contact address. The desk only calls EDGAR if
the operator has written one line (for example "Your Name you@example.com") to
robinhood-diagnostics/analyst/contact.txt; otherwise filings are skipped and the reason recorded.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

MAX_BYTES = 1_000_000
TIMEOUT = 6
TOTAL_SECONDS = 40
QUERY = {'SOXX': 'semiconductor stocks', 'SPY': 'S&P 500', 'QQQ': 'Nasdaq 100', 'VTI': 'US stock market', 'GLD': 'gold price',
         'TLT': 'Treasury bonds yields', 'XLE': 'energy stocks oil', 'XLK': 'technology stocks', 'XLF': 'bank stocks',
         'XLV': 'health care stocks', 'XLU': 'utilities stocks', 'XLP': 'consumer staples stocks', 'XLY': 'consumer discretionary stocks',
         'XLI': 'industrial stocks', 'XLB': 'materials stocks', 'XLRE': 'real estate stocks REIT', 'XLC': 'communication services stocks',
         'AAPL': 'Apple AAPL', 'AMZN': 'Amazon AMZN', 'GOOGL': 'Alphabet Google GOOGL', 'META': 'Meta Platforms META',
         'MSFT': 'Microsoft MSFT', 'NVDA': 'Nvidia NVDA', 'MARKET': 'stock market today'}
CIK = {'AAPL': 320193, 'AMZN': 1018724, 'GOOGL': 1652044, 'META': 1326801, 'MSFT': 789019, 'NVDA': 1045810}
FORMS = {'8-K', '10-Q', '10-K', '6-K', 'SC 13D', 'SC 13G', '4'}
_TAG = re.compile(r'<[^>]+>')


def clean(text, limit=300):
    text = html.unescape(_TAG.sub(' ', text or ''))
    return re.sub(r'\s+', ' ', text).strip()[:limit]


def _get(url, headers=None, opener=None):
    req = urllib.request.Request(url, headers={'User-Agent': 'AgentDesk-research/1.0', **(headers or {})})
    with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('RESPONSE_TOO_LARGE')
    return data


def parse_rss(data, ticker, now, max_age_hours=48, limit=6):
    if b'<!DOCTYPE' in data[:500] or b'<!ENTITY' in data:
        raise ValueError('DTD_REFUSED')                  # no entity expansion from untrusted XML
    root = ET.fromstring(data)
    out = []
    for item in root.iter('item'):
        title = clean(item.findtext('title'))
        link = (item.findtext('link') or '').strip()
        src = item.find('source')
        source = clean(src.text if src is not None else '', 80)
        try:
            pub = parsedate_to_datetime(item.findtext('pubDate') or '')
            pub = pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pub = None
        if not title or not link.startswith('https://'):
            continue
        if pub and now - pub > timedelta(hours=max_age_hours):
            continue
        out.append({'ticker': ticker, 'title': title, 'source': source or urllib.parse.urlsplit(link).netloc,
                    'url': link[:500], 'published': pub.isoformat() if pub else None, 'feed': 'google_news_rss'})
        if len(out) >= limit:
            break
    return out


def google_news(ticker, now, opener=None):
    q = urllib.parse.quote(f'{QUERY.get(ticker, ticker)} when:2d')
    url = f'https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en'
    return parse_rss(_get(url, opener=opener), ticker, now)


def edgar(ticker, now, contact, opener=None, days=3):
    cik = CIK.get(ticker)
    if not cik or not contact:
        return []
    data = json.loads(_get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json', {'User-Agent': contact}, opener))
    recent = (data.get('filings') or {}).get('recent') or {}
    out = []
    for form, filed, acc, doc, desc in zip(recent.get('form', []), recent.get('filingDate', []), recent.get('accessionNumber', []),
                                           recent.get('primaryDocument', []), recent.get('primaryDocDescription', []) or [''] * 9999):
        try:
            when = datetime.fromisoformat(filed).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if now - when > timedelta(days=days) or form not in FORMS:
            continue
        url = f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-", "")}/{doc}'
        out.append({'ticker': ticker, 'title': clean(f'{form} filed {filed}: {desc or doc}'), 'source': 'SEC EDGAR', 'url': url,
                    'published': when.isoformat(), 'feed': 'sec_edgar', 'form': form})
    return out[:5]


def collect(tickers, now, *, contact=None, opener=None, clock=time.monotonic):
    """Best effort within TOTAL_SECONDS. Returns (items, problems)."""
    start, items, problems = clock(), [], []
    for t in list(dict.fromkeys(list(tickers) + ['MARKET'])):
        if clock() - start > TOTAL_SECONDS:
            problems.append({'ticker': t, 'error': 'TIME_BUDGET'})
            continue
        for fn in (google_news, lambda tk, n, opener=None: edgar(tk, n, contact, opener)):
            try:
                items.extend(fn(t, now, opener=opener))
            except Exception as error:      # network, parse, size: recorded, never raised
                problems.append({'ticker': t, 'error': type(error).__name__})
    if not contact:
        problems.append({'ticker': '*', 'error': 'EDGAR_SKIPPED_NO_CONTACT_FILE'})
    seen, unique = set(), []
    for i, it in enumerate(items):
        key = it['title'].lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        unique.append({**it, 'id': f'news:{len(unique) + 1}'})
    return unique[:80], problems
