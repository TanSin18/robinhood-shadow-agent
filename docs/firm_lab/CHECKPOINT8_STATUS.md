# Checkpoint 8 — status

**DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE.**

Written 2026-10-04. Branch `claude/checkpoint8-data-foundation`, from `claude/checkpoint7-modeling` `3978d1b`.

## Where it stands

`CHECKPOINT 8 = NOT CLOSED`. `OPERATOR PURCHASE DECISION REQUIRED`.

The foundation is built, reviewed nine times and installed read-only. It holds no historical market data, because the
only source that meets the requirements has to be bought, and buying is the operator's decision. With nothing stored,
the answer to the checkpoint's question ("can we build enough genuinely historical, point-in-time-valid data to
support a credible future modeling tournament?") is **not yet**: the strict point-in-time sample count is 0 and every
model family is INSUFFICIENT. Nothing was done to make that look better.

## What exists

| Piece | State |
|---|---|
| Sufficiency specification | Written and committed alone (`45786be`) before any other work; five dated amendments, none lowers a bar |
| Provider decision | Sharadar "Prices — Full History", Personal Use License, $39 per month or $299 per year. Nothing purchased, no account, no key |
| Historical research database | Code and tests; no file exists. Separate file, append-only, versioned, refused beside the registered database and inside a repository |
| Validation | Reject, never repair; receipts per file |
| Bar known-at | `bar-known-at-v1`: usable no earlier than the next session's open |
| Corporate actions | Recorded splits applied as recorded; the vendor's factor is an audit; breaks at spin-offs, large distributions, contradictions |
| Universe | `liquid-us-listed-v1`: monthly, from bars alone, delisted securities included, versioned, known before it takes effect |
| Features | `ohlcv-features-v1`: 80 definitions in eight versions; `close_fractal_3x3_v1` untouched |
| Labels | `forward-close-to-close-price-return-v3` at 5, 10 and 20 sessions, on the exact close |
| Dataset | `pit-dataset-v2`: strict count by segment and tier, manifests and hashes; materialises readable segments only |
| Holdouts | `c9-chronology-v1`: historical holdout 2021-01-04 to 2025-03-28 and forward holdout from 2026-10-05, both sealed; the Checkpoint 7 window burned |
| Readiness report and page | 25 bars, verdict per family, provenance, limitations; read-only; installed |
| Capability rows | six written from the report; model rows untouched |
| Review | nine independent reviewers, eight rounds: `CHECKPOINT8_REVIEW.md` |

## Deployed on the Mac (2026-10-04 23:37 UTC, 19:37 ET)

Read-only dashboard material and research metadata only. Nothing in the registered runtime was written and
`com.openai.robinhood-daily` was not restarted. Folder: `robinhood-diagnostics/checkpoint8-data-foundation-20261004/`.

| Step | Evidence |
|---|---|
| Control A before | fingerprint `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`, 240 files, match; no stop file; fills 3 (23:30 UTC) |
| Bundle | `checkpoint8-bundle-8fb60d9.tgz`, sha256 `f29bf014…e479cf`; every file checked against its sum on the Mac |
| Overlay before | the three existing files equal the Checkpoint 7 install (`1912d247…`, `17146bd3…`, `1518b31a…`); backed up to `overlay-backup/` with their sums |
| Five overlay files | `agents/desk/firm_lab_page.py` `9d7c9505…`, `agents/desk/history_readiness.py` `334ef32a…` (new), `agents/static/botfolio-theme.css` `d4f9e5c5…`, `firm_lab/view.py` `2ef4974f…`, `firm_lab/history_view.py` `429563b3…` (new). `firm_lab/history/` is not in the overlay |
| Readiness file | `robinhood-diagnostics/firm_lab/firm_lab_history_readiness.json`, sha256 `9c29613e…15b862`, report hash `4d5fb851a504…`; built from the live research database's own rows; no history database exists |
| Research database backup | `research-db-backup/firm_lab.db.before-checkpoint8`, sha256 `f58b1d02…903015` (unchanged since Checkpoint 7) |
| Capability rows | written on a copy by `firm_lab.history_capability.record`, then put in place. All 31 tables and the schema compared: only `data_capabilities` (44 → 50) and `events` (57 → 63) differ; the 57 earlier events are a prefix; six capability-status events appended |
| Research database after | sha256 `09862193…d79c001`; integrity ok; BUILD_OBSERVE; experiment registry empty; no order, fill, position, account or cash table |
| Page from the installed overlay | rendered on the Mac from the overlay's own code against the live files (no server): the section is present, the permanent warning once, the purchase decision, strict samples 0, 0 of 25 bars met, INSUFFICIENT for every family, the holdout statement; no action wording; the Checkpoint 7 laboratory section still there; the research database has the same sha256 after rendering |
| Control A after | the same fingerprint, 240 files, match; no stop file; fills 3 (23:37 UTC) |

Left in `_to_delete/` because this session may not delete on the Mac: a compressed copy of the research database
(63 MB) and two fragments of a failed scratch file. They hold nothing licensed. The operator can remove the folder.

**Operator steps still open**: restart the dashboard (`com.openai.robinhood-inbox` only), check the page, run the
native suite from `src/` (a plain export of `8fb60d9`). Commands are in the status note of 2026-10-04 19:40 ET in
`docs/review/CLAUDE_STATUS.md`.

## Capability states

| Capability | State |
|---|---|
| `historical_ohlcv` | UNAVAILABLE |
| `corporate_actions` | PARTIAL_EXISTING (unchanged: VTI cash distributions, benchmark-only) |
| `historical_universe` | UNAVAILABLE |
| `pit_fundamentals` | PARTIAL_EXISTING (531 facts, 20 filings, 5 companies: a sample) |
| `pit_earnings` | PARTIAL_EXISTING (20 events, 5 companies: a sample) |
| `pit_macro` | PARTIAL_EXISTING (fed funds target, PCE; mid-2026 only) |
| `strict_pit_training_data` | UNAVAILABLE |
| `ml_ranker`, `deep_learning`, `transformer_models` | RESEARCH_ONLY (unchanged) |
| `portfolio_optimizer`, `options_strategy`, `rl_policy` | NOT_STARTED (unchanged) |

## Not built, on purpose

A reader for SEC filings keyed by CIK and the bulk path through the Financial Statement Data Sets (a rule decision for
the operator); historical collectors for BLS, BEA, Treasury and the Philadelphia Fed vintages; a historical sector
classification from SIC codes as filed; forward capture of bars each evening (tier A); post-delisting returns (no
source); intraday (deferred, with reasons in `CHECKPOINT8_SOURCES_PIT.md`); bar P7 of the specification.

No tournament, no portfolio construction, no options strategy, no reinforcement learning, no retraining. No model was
trained and no model metric was computed on any segment.

## What the operator decides

1. **The purchase.** One month at $39 first: the first file shows the vendor's print format (bar O7 decides whether the
   high/low/open features can be used at all), its action-table conventions and its coverage. Download the tables
   (SEP, SFP, TICKERS, ACTIONS, SP500) into a private folder outside any repository; no login, key or payment detail
   goes to Claude.
2. **Capture files from FRED or ALFRED**, if any `fred_*.csv`, `fredapi_*.json` or `alfred_*.csv` exist in the capture
   folders: delete them. Their terms do not allow storage.
3. **Forward capture.** Whether and how each day's bars are stored before the next open. Without it nothing reaches
   tier A and the forward holdout accrues as tier B.
4. **SEC history.** Whether the bulk path may carry its own evidence label, and whether to run the free validation
   sample on the five stored companies now.
5. Outside this checkpoint, unchanged: the two wall-clock tests in `tests/test_dashboard.py`; Codex maintenance
   PREPARED_AND_PROVEN_NOT_INSTALLED.
