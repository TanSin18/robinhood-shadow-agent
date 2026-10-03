"""Company facts from the SEC's XBRL data API, for Firm Lab research only. Raw and normalized facts: nothing is scored,
ranked, compared with an estimate or turned into a ratio.

For one company this reads, from the SEC and nowhere else:

  * the company-facts file (every tagged value the company has filed, with the filing each one appeared in);
  * the company's filing index, to pick the most recent periodic reports (10-Q, 10-K and their amendments);
  * each picked filing's own header, for the acceptance time (the header is authoritative, as for filing metadata);
  * each picked filing's own primary document, to check every kept value against what the company actually tagged.

Normalization is ``firm_lab.fundamentals`` and fails closed. A value that differs from the filing's own document makes
the whole answer unusable (FACT_DIFFERS_FROM_FILING); a value that cannot be found there is kept and flagged.

Versions. The company-facts file holds every periodic filing a fact appeared in, so the version of an observation is
counted over that complete history (``fundamentals.assign_versions``), not over what Firm Lab happens to have stored.
Only the observations of the picked filings are returned.
"""
from __future__ import annotations

from firm_lab import fundamentals, ixbrl
from firm_lab.errors import ProviderRejected
from firm_lab.provenance import Provenance, content_hash
from firm_lab.providers import CompanyFactsProvider
from firm_lab.schemas import SCHEMA_VERSION

from .edgar import ARCHIVE, EdgarFilingsProvider, _fail, _json

FACTS_URL = 'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
FACT_FIELDS = ('end', 'val', 'accn', 'form', 'filed')
TAXONOMY = 'us-gaap'
FACT_DIFFERS = 'FACT_DIFFERS_FROM_FILING'
DOCUMENT_UNREADABLE = 'FILING_DOCUMENT_UNREADABLE'


def flatten(taxonomy_facts, provenance=None) -> list:
    """The watched concepts of the company-facts file as one row per (concept, unit, period, filing), periodic forms only.
    A row that is not in the documented shape makes the answer unusable; it is not skipped."""
    out = []
    for concept in sorted(fundamentals.WATCHED_CONCEPTS):
        entry = taxonomy_facts.get(concept)
        if entry is None:
            continue
        units = entry.get('units') if isinstance(entry, dict) else None
        if not isinstance(units, dict):
            raise ProviderRejected([('MALFORMED_RESPONSE', f'{concept}: no "units" mapping')], provenance)
        for unit in sorted(units):
            rows = units[unit]
            if not isinstance(rows, list):
                raise ProviderRejected([('MALFORMED_RESPONSE', f'{concept}/{unit}: not a list of facts')], provenance)
            for row in rows:
                if not isinstance(row, dict) or any(row.get(k) is None for k in FACT_FIELDS):
                    raise ProviderRejected([('MALFORMED_RESPONSE', f'{concept}/{unit}: a fact lacks one of {", ".join(FACT_FIELDS)}')], provenance)
                if row['form'] not in fundamentals.PERIODIC_FORMS:
                    continue
                out.append({'taxonomy': TAXONOMY, 'concept': concept, 'unit': unit, 'start': row.get('start'), 'end': row['end'], 'val': row['val'],
                            'accn': row['accn'], 'fy': row.get('fy'), 'fp': row.get('fp'), 'form': row['form'], 'filed': row['filed'],
                            'frame': row.get('frame')})
    return out


class SecXbrlFactsProvider(CompanyFactsProvider):
    name = 'SEC EDGAR'

    def __init__(self, transport, *, max_filings=4, filings_reader=None):
        self.transport = transport
        self.max_filings = int(max_filings)
        self.filings_reader = filings_reader or EdgarFilingsProvider(transport)
        self.reports = {}                                   # instrument -> the validation report of its last answer

    def _fetch(self, method, *, instrument, since=None, limit=None, **_):
        if method != 'facts':
            raise NotImplementedError
        symbol = str(instrument).upper()
        report = self.reports[symbol] = {'instrument': symbol, 'rules_version': fundamentals.RULES_VERSION}
        index = self.filings_reader.recent_filings(symbol)
        cik = index['cik']
        url = FACTS_URL.format(cik=cik)
        reply = self.transport.get(url)
        if not reply.ok:
            _fail(reply, f'the company facts of {symbol}')
        data = _json(reply, 'the company facts')
        provenance = Provenance(provider=self.name, source_id=reply.url, source_timestamp=reply.fetched_at, ingested_at=reply.fetched_at,
                                known_at=reply.fetched_at, schema_version=SCHEMA_VERSION, content_hash=content_hash(reply.body))
        if not isinstance(data, dict) or str(data.get('cik', '')).lstrip('0') != str(cik):
            raise ProviderRejected([('CONFLICTING_INSTRUMENT_IDENTITY', f'asked for CIK {cik}, the facts are for '
                                                                       f'{data.get("cik") if isinstance(data, dict) else "?"}')], provenance)
        taxonomy_facts = (data.get('facts') or {}).get(TAXONOMY) if isinstance(data.get('facts'), dict) else None
        if not isinstance(taxonomy_facts, dict):
            raise ProviderRejected([('MALFORMED_RESPONSE', f'the company facts hold no {TAXONOMY} section')], provenance)
        flat = flatten(taxonomy_facts, provenance)

        # The filings to read: the most recent periodic reports, newest first, as the SEC lists them.
        listed = {r['accession_number']: r for r in index['rows'] if r['form'] in fundamentals.PERIODIC_FORMS}
        keep = int(limit or self.max_filings)
        picked = [r for r in index['rows'] if r['form'] in fundamentals.PERIODIC_FORMS and (not since or r['filing_date'] >= str(since)[:10])][:keep]
        if not picked:
            raise ProviderRejected([('INCOMPLETE_HISTORICAL_WINDOW', f'the SEC lists no periodic report of {symbol} filed since {since}')], provenance)
        # An amendment that carries no financial data (for example a 10-K/A that only adds Part III) is left out and named.
        # An original report with no tagged fact is not left out: the answer is unusable.
        with_facts = {f['accn'] for f in flat}
        empty = [r for r in picked if r['accession_number'] not in with_facts]
        missing = [r['accession_number'] for r in empty if not r['form'].endswith('/A')]
        if missing:
            raise ProviderRejected([('NO_FACTS_FOR_FILING', f'{a}: the company facts hold no watched fact for this report') for a in missing], provenance)
        report['amendments_without_financial_facts'] = [r['accession_number'] for r in empty]
        picked = [r for r in picked if r['accession_number'] in with_facts]
        if not picked:
            raise ProviderRejected([('INCOMPLETE_HISTORICAL_WINDOW', f'no periodic report of {symbol} with financial facts filed since {since}')], provenance)
        timing = {}
        for row in picked:
            accession = row['accession_number']
            try:
                header_raw, header_utc = self.filings_reader.header_time(cik, accession)
                _, conflict, offset = self.filings_reader.reconcile(accession, row['json_time'], header_raw, header_utc)
            except ProviderRejected as error:
                raise ProviderRejected(error.issues, provenance) from None
            timing[accession] = {'accepted_timestamp': header_utc.isoformat(), 'accepted_timestamp_json': row['json_time'], 'conflict': conflict,
                                 'json_minus_header_seconds': offset}

        # Normalize the complete periodic history (for version numbers), then keep the picked filings.
        history = {}
        for fact in flat:
            known = listed.get(fact['accn'], {})
            history.setdefault(fact['accn'], {'form': fact['form'], 'report_date': known.get('report_date'), 'filing_date': fact['filed'],
                                              'accepted_timestamp': timing.get(fact['accn'], {}).get('accepted_timestamp')})
        normalized = fundamentals.normalize(flat, history, instrument=symbol, cik=cik)
        chosen = {r['accession_number'] for r in picked}
        versioned = [r for r in fundamentals.assign_versions(normalized['accepted']) if r['accession_number'] in chosen]
        unresolved = [u for u in normalized['unresolved'] if u['accession_number'] in chosen]

        # Check every kept value against the filing's own document.
        documents, unreadable = {}, []
        for row in picked:
            accession, name = row['accession_number'], row['primary_document']
            folder = ARCHIVE.format(cik=cik, folder=accession.replace('-', ''))
            if not name:
                unreadable.append((DOCUMENT_UNREADABLE, f'{accession}: the SEC names no primary document'))
                continue
            page = self.transport.get(folder + name)
            if page.status in (403, 429):
                _fail(page, 'a filing document')
            if not page.ok:
                unreadable.append((DOCUMENT_UNREADABLE, f'{accession}: {page.error or "HTTP " + str(page.status)}'))
                continue
            documents[accession] = (folder + name, ixbrl.numeric_facts(page.body))
        if unreadable:
            raise ProviderRejected(unreadable, provenance)
        records, differing, checks = [], [], {}
        for record in versioned:
            accession = record['accession_number']
            url_of_document, tagged = documents[accession]
            verdict = ixbrl.check(record, tagged)
            checks[verdict] = checks.get(verdict, 0) + 1
            if verdict == ixbrl.MISMATCH:
                differing.append((FACT_DIFFERS, f'{accession} {record["concept"]} {record.get("period_start")}..{record["period_end"]}: the data API says '
                                                f'{record["value"]}, the filing document does not'))
                continue
            when = timing[accession]
            records.append({**record, 'accepted_timestamp_json': when['accepted_timestamp_json'], 'acceptance_time_conflict': when['conflict'],
                            'confirmed_in_filing': verdict, 'source_url': reply.url, 'filing_document_url': url_of_document,
                            'entity_name': data.get('entityName') or index['entity_name'], 'ingestion_timestamp': reply.fetched_at})

        by_accession = {r['accession_number']: {**history[r['accession_number']], **timing[r['accession_number']]} for r in picked}
        quality = fundamentals.quality(records, unresolved, by_accession)
        not_confirmed = sorted({(r['accession_number'], r['normalized_field']) for r in records
                                if r['normalized_field'] in fundamentals.CRITICAL_FIELDS and r['relation_to_filing'] == fundamentals.CURRENT
                                and r['confirmed_in_filing'] != ixbrl.CONFIRMED})
        accepted_by_field, units = {}, {}
        for r in records:
            accepted_by_field[r['normalized_field']] = accepted_by_field.get(r['normalized_field'], 0) + 1
            units[r['unit']] = units.get(r['unit'], 0) + 1
        report.update({
            'cik': f'{cik:010d}', 'entity_name': data.get('entityName') or index['entity_name'], 'raw_facts_in_history': normalized['raw_facts'],
            'raw_facts_in_filings_read': sum(1 for f in flat if f['accn'] in chosen), 'concepts_seen': normalized['concepts_seen'],
            'normalized_accepted': len(records), 'accepted_by_field': dict(sorted(accepted_by_field.items())), 'units': dict(sorted(units.items())),
            'unresolved': len(unresolved),
            'unresolved_detail': [{k: u.get(k) for k in ('field', 'accession_number', 'period_end', 'reason', 'concepts', 'relation')} for u in unresolved][:60],
            'conflicting_concepts': [u for u in unresolved if u['reason'] == fundamentals.CONFLICTING_CONCEPTS][:20],
            'restatements': sum(1 for r in records if r['is_restatement']),
            'checked_against_filing': dict(sorted(checks.items())),
            'filings': [{'accession_number': r['accession_number'], 'form': r['form'], 'report_date': r['report_date'], 'filing_date': r['filing_date'],
                         **timing[r['accession_number']]} for r in picked],
            'quality': {**quality, 'critical_not_confirmed_in_filing': [{'accession_number': a, 'field': f} for a, f in not_confirmed],
                        'passes': quality['passes'] and not not_confirmed},
        })
        if differing:
            raise ProviderRejected(differing, provenance)
        return records, provenance
