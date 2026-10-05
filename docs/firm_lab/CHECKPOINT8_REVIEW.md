# Checkpoint 8 — independent review record

**DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE.**

Nine fresh reviewers read the historical data foundation between 2026-10-04 and the commit this file belongs to. None
had seen the work being written. Each worked on a read-only export of one commit, ran its own experiments on synthetic
data (no licensed data exists), and changed nothing. Every critical and every important finding got a regression test
and a repair; the regressions were run against the commit under review and the failing runs are kept. No critical or
important finding is deferred. The ninth reviewer found none in the package code.

What the reviews could not do: read a real vendor file. Everything below is proven on a synthetic provider. The first
real file is where the vendor's print format, its action-table conventions and its coverage are found out, and the
validation sample exists for that.

## Rounds

| Round | Reviewer(s) | Commit read | Looked for | Critical / important found | Repair | Regressions failing on the commit read |
|---|---|---|---|---|---|---|
| 1 | A | `be81bb8` | adjustment, features, known-at | 1 / 4 | `aacea1e` | 6 (and 1 for the FRED removal, on `be81bb8`) |
| 2 | B, C | `aacea1e` | holdouts, tiers, universe, survivorship; storage, validation, report, isolation | 7 / 19 | `e1a502e` | 17 |
| 3 | D | `e1a502e` | the sixteen repairs of round 2, and new defects | 2 / 6 | `9e593ae` | 10 |
| 4 | E | `9e593ae` | the repairs of round 3 | 2 / 1 | `f00680d` | 5 |
| 5 | F | `f00680d` | the repairs of round 4 | 3 / 3 | `cd05456`, `dac1522` | 4, and 1 |
| 6 | G | `dac1522` | one question: can anything of a row depend on a later split | 3 / 1 | `d196bb1` | 2 |
| 7 | H | `d196bb1` | the repairs of round 6 | 2 / 2 | `8fb60d9` | 4 |
| 8 | I | `8fb60d9` | the repairs of round 7 | 0 / 0 in the package; 1 test that did not test what it said | this commit | the corrected test fails on `d196bb1` |

"Fails on the commit read" means two different things, and the difference matters. Most regressions fail there on
behaviour: the old code runs and gives the wrong answer. Some fail because the old code has no way to express the rule
under test (there was no clock on a capture, no version name on a rule, no range on a volume). For those the defect
itself is on record in the reviewer's own experiment, which is quoted in the test's description. The round-7
regression for a lone coarse bar passed on the old code as first written; the ninth reviewer caught that, the test was
corrected, and it now fails there.

## What was wrong, by subject

**The Checkpoint 7 holdout and the new seals (rounds 2, 3).** A label in the burned window could end inside the
forward holdout; purge rows left the builder with values; the strict count summed purge rows. Later: rows of sealed
sessions left the builder with their features, and a 20-session return is the label of the row 21 sessions earlier;
burned rows read holdout prices through their lookbacks. Now: every boundary has a purge, label and feature values of
every unreadable segment are blanked, and a row after the holdout is computed from its own side of the boundary only.

**Tiers (rounds 2, 3, 4, 7).** A bar the vendor revised kept tier A. A capture time typed by a caller could make an
archive bar "held at the time". A revised bar is a restated value and belongs in tier C under the specification's own
§1, and the code had kept it in tier B. A removed bar left a hole that was the vendor's later doing. The reach that
decides a tier was partly read from reprinted prices. Now: SYSTEM and SUPPLIED clocks, tier C for a row that reads a
revised or removed bar, and a reach found from the exact close alone.

**Storage (rounds 2, 3, 4).** Ingestion was not atomic; capture times could go backwards or into the future; a vendor
that returned to earlier content was dropped as a duplicate; a partial file replaced a year; a removed session was
invisible; `INSERT OR REPLACE` bypassed the append-only triggers; two sources could be read as one series; invalid
numbers were stored; a bar rewritten as a "rescale" kept its date. All repaired.

**The universe (rounds 2, 3, 5, 6, 7).** Past membership read today's master row; a rebuild made every universe
unreadable; a universe did not go stale when a bar it read changed; any rule could carry the registered name; a stock
whose volume a later reverse split made unreadable was screened out, which removed exactly a stock that collapsed
later. Now: membership from bars alone, records keyed by the universe's hash, staleness over every block read, the
day's volume as a range with undecided memberships counted.

**The reprint channel (rounds 1, 3, 4, 5, 6, 7).** This took the most rounds, and one rule came out of it. The vendor
supplies open, high, low, close and volume only as re-adjusted and re-rounded after every later split. Anything
decided from those numbers can differ between a stock that split later and one that did not. In order of discovery:

1. Wilder smoothing carried pre-break prices; print rounding leaked later splits into close-based features (round 1).
2. Withholding high/low/open features only on coarse rows marked the future splitters (round 3).
3. Print precision was read over the whole column, so one later print changed how every earlier bar was judged (round 4).
4. A coarse reprint decided whether a small recorded split was confirmed and whether a dividend counted as large (rounds 4, 5).
5. Labels were built from reprinted opens (round 5).
6. Each bar's high and low were rescaled by its own rounding unit, which moved swings even under an exact reprint (round 6).
7. Volume: thin re-counts after reverse splits; a core feature that read volume decided whether a row existed (rounds 5, 6, 7).

The rule: **whether a row exists, what its close-based features and its label are worth, and which tier it has are
taken only from the unadjusted close and the recorded actions. The vendor's reprinted numbers are read for the shape of
a bar and for its volume, and features built on those are used for every row of a dataset or for none.** Round 6 and
round 7 tested exactly that rule across later forward and reverse splits, reprints at two to eight decimals, earlier
recorded splits, delistings, revisions and data arriving later; round 8 confirmed the last repairs.

**Measurement and report (rounds 2, 3, 5).** Breadth was reported with too few shared windows; a family verdict used
weaker inputs than the specification wrote; regime coverage read closes outside its period; the report could be
written beside the registered database; it listed 13 of 25 bars; H1 was met by one early bar of one security; the page
said things that became false once data was stored. All repaired. The sufficiency specification has five dated
amendments. None lowers a bar.

**Licensing (before round 1).** FRED and ALFRED terms prohibit storing the data and using it to train models without
written consent. Both were removed from the collector and the macro store.

## What the reviewers found sound

- No readable label reaches a sealed price at any boundary of the chronology (round 3 onward, re-checked each round).
- Close-based features, labels, label states, the exact close, applied splits, breaks and tiers: identical with and
  without a later split in every world tried (rounds 6, 7, 8), to 4e-13.
- Within one materialised dataset the pattern of missing values cannot tell a later splitter from any other stock.
- A correct recorded split is never turned into a break, at any print precision tried, including one-digit prints.
- Atomicity: nothing is stored after an interruption at any point tried. Append-only holds through the package's own
  connection. No vendor row is left beside the database.
- Isolation: the package imports the standard library, numpy and the exchange calendar; no network, no broker, no
  trading code, no environment variable. The report and the page hold no price and no instruction.
- Later data arriving, a later delisting and changed holdout prices move nothing in development or the burned window.

## What remains, stated

These are known, bounded or counted, and none is a point-in-time leak for a correct vendor record.

- **Reprinted values on rows that are used.** A reprinted high, low or open is within a twentieth of a cent of the
  day's price for a re-adjusted bar; a feature that divides by a one-cent range or leg shows that as a visible
  fraction. Each re-counted volume is within 0.5% of the day's. Where swings and legs fall does not change.
- **Whether a vendor error is caught** can depend on the reprint: an unrecorded split or a wrong ratio is seen under a
  fine print and can be missed under a coarse one. A check that cannot be made is not a failure.
- **Two readings of the action table** (a split's value is new shares per old; a dividend's value is the amount paid
  per share on the day) are assumptions until a real file is read. A dataset is refused when a visible case
  contradicts either.
- **A vendor that drops trailing zeros** makes a bar whose four prices are all round look coarser than it is. That
  withholds the high/low/open families and widens the audit tolerance at that bar.
- **Volume after very large reverse splits** is a range. Memberships the range leaves open are counted, not settled.
- **A reprinted price that rounds to zero** fails the row checks and the bar is rejected and counted.
- **Minor items left as they are**: `undecided` is a count for the report and is conservative by construction; where
  the vendor adjusted for a split the stored actions do not hold, the ratio is estimated over a stretch of sessions; the
  hashes are integrity checks, not signatures; a person with the file and a SQL prompt can drop a trigger.

## Records

Kept outside the repository with the Checkpoint 7 records (they hold no licensed data): the failing runs of each
round's regressions on the commit read, and the full cloud suite at each repair commit. Last full cloud suite before
this commit, at `8fb60d9`: 1267 passed, 2 failed, 1 skipped; at the round-8 commit `af958e1` the same. The two
failures are the wall-clock tests of the registered dashboard that have failed on every branch since 2026-10-04
13:10 UTC; the skip is the installed-Codex test that only runs on the operator's Mac.
