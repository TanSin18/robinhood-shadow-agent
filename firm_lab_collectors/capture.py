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
