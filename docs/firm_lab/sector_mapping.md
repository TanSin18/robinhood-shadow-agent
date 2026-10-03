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

On2026-10-03 at23:11:03UTC, the other proposed current internal classifications
were recorded after official-source verification: AAPL/NVDA→XLK, AMZN→XLY,
GOOGL/META→XLC. These are internal inferences from issuer business descriptions
and the fund mandates, not licensed GICS membership or historical facts.

- [Apple device/software description](https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/).
- [NVIDIA accelerated computing description](https://www.nvidia.com/en-us/about-nvidia/).
- [Amazon business lines](https://www.aboutamazon.com/what-we-do): retail classification does not erase cloud/entertainment exposure.
- [Google product description](https://about.google/).
- [Meta company description](https://www.meta.com/about/company-info/).

VTI/SPY have no single sector. SOXX is thematic;
comparison to XLK must be labeled proxy, not whole-sector identity.

Current stored price history ends2026-09-30. A mapping first established2026-10-03
cannot classify those sessions as point-in-time history. No mapping deployment
or additional ETF price collection has been performed by this code checkpoint.
Sector breadth requires a point-in-time constituent snapshot; the observed
research shortlist is not the complete sector universe.

The manual generator persists hashed classifications and dated membership
records in `research_sector_mappings`. It reads those records before loading
all required comparator histories. The fixed comparison set XLK/XLY/XLC is
`observed-three-sector-subset-v1`, established23:11:03UTC with an October3
effective date. It is a three-sector subset, never a whole-market rank.
Missing any comparator window leaves leadership unavailable. Rank-change5
requires this same set to have been effective five sessions earlier.

`CONSTITUENTS` records can be explicitly registered through the research store
with source URLs, content hash, known-at, version and effective dates; no live
constituent snapshot exists yet. Complete constituent windows are required for
breadth/participation. Every consumed member and membership record contributes
to source references and the result's latest known-at.
