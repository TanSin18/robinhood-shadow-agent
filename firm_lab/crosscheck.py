"""Cross-checks between independent sources. Read-only diagnostics: nothing is corrected, merged or scored.

Fundamentals and filings. Sharadar gives the DATE a report was filed (as-reported rows only); SEC EDGAR gives the
moment the filing was accepted. This module lines the two up so the known-at time of a reported number can be read
from the SEC record. It never writes that time into a fundamental row and never builds a time from Sharadar's date:
where no stored SEC filing matches, the answer is that the time is unknown.

A report counts as matched when exactly one stored periodic SEC filing for the same instrument has the same filing
date. The SEC dates a filing accepted after 5:30 p.m. New York time to the next business day, so the filing date and
the acceptance timestamp can fall on different calendar days; both are shown as stored.
"""
from __future__ import annotations

PERIODIC_FORMS = ('10-K', '10-Q', '10-K/A', '10-Q/A', '10-KT', '10-QT', '20-F', '20-F/A', '40-F', '40-F/A')
MATCH, NO_FILING, AMBIGUOUS = 'MATCH', 'NO_SEC_FILING_STORED', 'AMBIGUOUS'


def fundamentals_vs_filings(db, instrument=None) -> list:
    """One entry per as-reported (instrument, dimension, period_end, filing_date) stored from the fundamentals provider."""
    where, args = ("WHERE reporting_basis='as_reported'" + (' AND instrument=?' if instrument else ''), (instrument,) if instrument else ())
    reports = db.execute('SELECT DISTINCT instrument, dimension, period_end, filing_date FROM fundamental_observations ' + where
                         + ' ORDER BY instrument, period_end, dimension', args).fetchall()
    marks = ','.join('?' * len(PERIODIC_FORMS))
    out = []
    for symbol, dimension, period_end, filing_date in reports:
        found = db.execute(f'SELECT DISTINCT accession_number, form_type, filing_date, report_date, accepted_timestamp FROM filing_observations '
                           f'WHERE instrument=? AND filing_date=? AND form_type IN ({marks}) ORDER BY accepted_timestamp',
                           (symbol, filing_date) + PERIODIC_FORMS).fetchall()
        entry = {'instrument': symbol, 'dimension': dimension, 'period_end': period_end, 'provider_filing_date': filing_date,
                 'status': MATCH if len(found) == 1 else AMBIGUOUS if found else NO_FILING,
                 'sec_filings': [{'accession_number': a, 'form_type': f, 'filing_date': d, 'report_date': r, 'accepted_timestamp': t}
                                 for a, f, d, r, t in found]}
        if len(found) == 1:
            entry['sec_accepted_timestamp'] = found[0][4]                  # read from the SEC record, not derived from the date
            entry['period_end_agrees'] = None if not found[0][3] else found[0][3] == period_end
        out.append(entry)
    return out


def summarise(entries) -> dict:
    counts = {MATCH: 0, NO_FILING: 0, AMBIGUOUS: 0}
    for e in entries:
        counts[e['status']] += 1
    return {'reports': len(entries), **counts, 'period_end_disagreements': sum(1 for e in entries if e.get('period_end_agrees') is False)}
