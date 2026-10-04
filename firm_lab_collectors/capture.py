"""Raw sample capture, started by hand: a few public documents saved exactly as received, with a manifest of what was
asked, what came back and its hash. For checking parsers against the real thing and for audit; nothing is parsed,
stored in the Firm Lab database, scored or traded here.

GET only, to hosts named in advance. The SEC is asked with the operator's declared User-Agent. Every other host is
asked with a plain, honest research User-Agent and no contact address; a host that refuses is recorded as refused and
is not retried or worked around.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import config
from .transport import HttpTransport

SEC_HOSTS = ('www.sec.gov', 'data.sec.gov')
VANGUARD_HOST, NASDAQ_HOST = 'investor.vanguard.com', 'api.nasdaq.com'
PLAIN_AGENT = 'FirmLabResearch/1.0 (personal research; hand-started single requests)'
COMPANIES = (('AAPL', 320193), ('MSFT', 789019), ('NVDA', 1045810), ('AMZN', 1018724), ('GOOGL', 1652044))
PUBLIC = (
    ('vanguard_vti_distribution.json', f'https://{VANGUARD_HOST}/vmf/api/VTI/distribution'),
    ('vanguard_divdat_2026.pdf', f'https://{VANGUARD_HOST}/content/dam/retail/publicsite/en/documents/taxes/DIVDAT_2026.pdf'),
    ('vanguard_divdat_2025.pdf', f'https://{VANGUARD_HOST}/content/dam/retail/publicsite/en/documents/taxes/DIVDAT_012025.pdf'),
    ('nasdaq_vti_dividends.json', f'https://{NASDAQ_HOST}/api/quote/VTI/dividends?assetclass=etf'),
)
VANGUARD_NCSR = ('sec_vanguard_ncsr_fy2025_index.json', 'https://www.sec.gov/Archives/edgar/data/36405/000110465926021502/index.json')


def _save(out, name, reply, manifest):
    target = out / name
    if reply.ok:
        target.write_bytes(reply.body)
    manifest.append({'file': name if reply.ok else None, 'url': reply.url, 'status': reply.status, 'error': reply.error, 'bytes': len(reply.body),
                     'sha256': hashlib.sha256(reply.body).hexdigest() if reply.ok else None, 'fetched_at': reply.fetched_at,
                     'content_type': (reply.headers or {}).get('content-type')})
    return reply


def run(out_dir, *, environ=None, sec_transport=None, plain_transport=None) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    agent = config.sec_user_agent(environ)
    plain = plain_transport or HttpTransport([VANGUARD_HOST, NASDAQ_HOST], user_agent=PLAIN_AGENT, min_interval=1.0)
    for name, url in PUBLIC:
        _save(out, name, plain.get(url, {'Accept': 'application/json, application/pdf;q=0.9, */*;q=0.5'}), manifest)
    if agent:
        sec = sec_transport or HttpTransport(SEC_HOSTS, user_agent=agent, min_interval=0.25, max_bytes=60_000_000)
        _save(out, VANGUARD_NCSR[0], sec.get(VANGUARD_NCSR[1]), manifest)
        for symbol, cik in COMPANIES:
            _save(out, f'sec_companyfacts_{symbol}.json', sec.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'), manifest)
            reply = _save(out, f'sec_submissions_{symbol}.json', sec.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json'), manifest)
            try:
                recent = json.loads(reply.body)['filings']['recent'] if reply.ok else None
            except (ValueError, KeyError, TypeError):
                recent = None
            if not recent:
                continue
            wanted = {}
            for i, form in enumerate(recent.get('form', [])):
                items = str((recent.get('items') or [''] * (i + 1))[i])
                kind = 'periodic' if form in ('10-Q', '10-K') else 'earnings8k' if form == '8-K' and '2.02' in items else None
                if kind and kind not in wanted:
                    wanted[kind] = i
            for kind, i in wanted.items():
                accession = str(recent['accessionNumber'][i])
                if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession):
                    continue
                folder = f'https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace("-", "")}/'
                _save(out, f'sec_{symbol}_{kind}_{accession}.hdr.sgml', sec.get(folder + accession + '.hdr.sgml'), manifest)
                _save(out, f'sec_{symbol}_{kind}_{accession}_index.json', sec.get(folder + 'index.json'), manifest)
                document = str(recent['primaryDocument'][i] or '')
                if kind == 'periodic' and re.fullmatch(r'[A-Za-z0-9._-]+', document):
                    _save(out, f'sec_{symbol}_{kind}_{accession}_{document}', sec.get(folder + document), manifest)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    return {'directory': str(out), 'sec_user_agent_declared': bool(agent), 'requested': len(manifest), 'saved': sum(1 for m in manifest if m['file']),
            'refused': [{'url': m['url'], 'status': m['status'], 'error': m['error']} for m in manifest if not m['file']]}


# ---------------------------------------------------------------------------- macro samples (Checkpoint 5)
# FRED and ALFRED are not asked (Checkpoint 8, 2026-10-04). The St. Louis Fed's terms of use prohibit, without the Bank's written
# consent, storing or archiving FRED content and using it to develop or train machine-learning systems. The same public series are
# taken from the agencies that publish them. A key in the environment is ignored.
MACRO_HOSTS = ('markets.newyorkfed.org', 'home.treasury.gov', 'api.bls.gov', 'www.bls.gov', 'www.federalreserve.gov', 'www.bea.gov', 'apps.bea.gov')
BLS_SERIES = ('CUSR0000SA0', 'CUSR0000SA0L1E', 'CUUR0000SA0', 'LNS14000000', 'CES0000000001')
FED_STATEMENT = re.compile(re.escape('https://www.federalreserve.gov/newsevents/pressreleases/monetary') + r'\d{8}a\.htm')
MACRO_PUBLIC = (
    ('nyfed_effr_search.json', 'https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2025-03-01&endDate=2026-12-31'),
    ('nyfed_effr_last.json', 'https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json'),
    ('treasury_yield_2026.csv', 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all'
                                '?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv'),
    ('treasury_yield_2026.xml',
     'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2026'),
    ('fed_press_monetary.xml', 'https://www.federalreserve.gov/feeds/press_monetary.xml'),
    ('fed_fomc_calendar.htm', 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'),
    ('fed_openmarket.htm', 'https://www.federalreserve.gov/monetarypolicy/openmarket.htm'),
    ('bls_cpi_schedule.htm', 'https://www.bls.gov/schedule/news_release/cpi.htm'),
    ('bls_empsit_schedule.htm', 'https://www.bls.gov/schedule/news_release/empsit.htm'),
    ('bls_cpi.rss', 'https://www.bls.gov/feed/cpi.rss'),
    ('bls_empsit.rss', 'https://www.bls.gov/feed/empsit.rss'),
    ('bea_schedule.htm', 'https://www.bea.gov/news/schedule'),
    ('bea_rss.xml', 'https://apps.bea.gov/rss/rss.xml'),
)


def run_macro(out_dir, *, environ=None, transport=None, keyed_transport=None) -> dict:
    """Raw macro samples from the agencies that publish them, saved as received, with a manifest. Nothing is parsed or stored in the
    database. FRED and ALFRED are not asked. ``keyed_transport`` is accepted for older callers and never used."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    net = transport or HttpTransport(MACRO_HOSTS, user_agent=PLAIN_AGENT, min_interval=1.0, timeout=30)
    accept = {'Accept': 'application/json, text/csv, application/xml, text/html;q=0.8, */*;q=0.5'}
    for name, url in MACRO_PUBLIC:
        reply = _save(out, name, net.get(url, accept), manifest)
        if name == 'fed_press_monetary.xml' and reply.ok:          # the newest FOMC statement page, to see how the decision is worded
            text = reply.body.decode('utf-8', 'replace')
            for item in re.findall(r'<item>(.*?)</item>', text, re.S):
                link = FED_STATEMENT.search(item)
                if link and 'FOMC statement' in item:
                    _save(out, 'fed_fomc_statement_latest.htm', net.get(link.group(0), accept), manifest)
                    break
    for series in BLS_SERIES:
        _save(out, f'bls_{series}.json', net.get(f'https://api.bls.gov/publicAPI/v1/timeseries/data/{series}', accept), manifest)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    return {'directory': str(out), 'requested': len(manifest), 'saved': sum(1 for m in manifest if m['file']),
            'refused': [{'url': m['url'], 'status': m['status'], 'error': m['error']} for m in manifest if not m['file']]}
