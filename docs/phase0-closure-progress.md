# Phase 0 closure progress

## 1. Portability repair

All seven baseline failures reproduced before edits. The affected 52-test group
passes after replacing private configuration with temporary synthetic settings,
using the current Python interpreter for subprocesses, and building proxy
fixtures from public source/templates. Production code and settings unchanged.

Final fresh full suite after the review fix: **601 passed, 0 failed, 31 warnings**
in 42.26 seconds. Warnings are SDK asyncio deprecations and the module-entrypoint
runpy warning. This result applies to the rehearsal/runtime branch, not the UI
branch or installed scheduled proof.

Correction to earlier diagnosis: the two operational-readiness failures were
caused by a missing relative `.venv/bin/python`, not missing private settings.
Both now use `sys.executable` and an explicit temporary settings path.

An independent reviewer identified missing negative inputs in the bundle fixture.
Harmless `agents/worker.py`, `broker/robinhood.py`, and `data/fixture.db` sentinel
files now ensure the real bundler must exclude forbidden inputs. This is not an
installed proxy test or evidence of actual OS user isolation.

## 2. Phase 0 gaps still open

| Area | Evidence / remaining work |
|---|---|
| Quote freshness | Offline stale-quote/refresh tests pass; no future market-hours claim. |
| Risk and paper pipeline | Offline cash/holdings/risk and approval/fill tests pass; not live fill evidence. |
| Rehearsal isolation | Tested; diagnostic cannot alter official results. |
| Model alignment | Current installed aliases differ from registered dated models; unresolved. |
| Hard inference budget | Codex transport still lacks verified hard output limits. Prior waiver is diagnostic-only. |
| Live registered inference | Separate Responses API access has not been configured/verified; never reuse Codex OAuth as an API key. |
| Installed scheduled proof | Still required separately on current deployed code and config. |
| UI acceptance | Separate branch has additional failures; these are not fixed by this runtime test repair. |

The existing 46-test focused safety group (cycle budget/freshness, Stage 1
pipeline, risk engine, Phase 0 budget, rehearsal) passes. Accounting reservation
tests do not prove a hard provider-side token limit. News and broader discovery
remain deferred until Phase 0 passes; the diagnostic waiver does not open that gate.

## Next dependency

Use the registered Responses API transport and dated models with verified
input-token counts, hard output caps including reasoning, pre-call reservations,
no silent retries/fallbacks, and recorded truncation failures. Live verification
requires operator-configured API access outside chat. Nothing here authorizes
modification of the frozen installed runtime or preregistration.
