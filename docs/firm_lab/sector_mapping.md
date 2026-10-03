# Research sector mapping — internal taxonomy v1

This is an internal descriptive taxonomy, not a licensed historical GICS dataset.
No mappings are backdated and no network collection runs from feature generation.
An entry requires effective dates, local known-at, version, cited evidence and
a content hash of the mapping record. That hash is NOT a hash of unretained web
content. Missing source capture or reference prices means unavailable.

Official source verification2026-10-03:
[State Street sector fund mandates](https://www.ssga.com/us/en/intermediary/capabilities/equities/sector-investing/select-sector-etfs)
identify XLK technology, XLY consumer discretionary and XLC communication services.
[Microsoft's2026 filing](https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm)
describes its technology business. MSFT→technology/XLK is a supported current
internal classification, not proof of historical membership.

The design's AAPL/NVDA→XLK, AMZN→XLY, GOOGL/META→XLC are proposals until each
issuer description is independently verified and recorded. Do not silently load
them as dated historical facts. VTI/SPY have no single sector. SOXX is thematic;
comparison to XLK must be labeled proxy, not whole-sector identity.

Current stored price history ends2026-09-30. A mapping first established2026-10-03
cannot classify those sessions as point-in-time history. No mapping deployment
or additional ETF price collection has been performed by this code checkpoint.
Sector breadth requires a point-in-time constituent snapshot; the observed
research shortlist is not the complete sector universe.
