# Agent Decision Room

Date: 2026-09-28  
Status: In-chat design approved; written specification awaiting user review. No implementation claim.

## Purpose

Replace the current wall-of-events Agent activity view with an evidence-first decision room. The page must let a non-technical operator answer, in order:

1. What review is this?
2. What did each agent receive, produce and hand off?
3. Which instruments were reviewed, advanced, rejected or blocked?
4. What did the Critic challenge?
5. What deterministic checks ran?
6. Why did the system propose a paper trade or hold cash?
7. Does the operator need to act?

The experience is for daily inspection on both a Mac and an iPhone opened from Pushover. It is not a trace viewer, a chat transcript or a simulation of private chain-of-thought.

## Selected direction

Build a structured **decision room** around the latest review. Market evidence flows through Research, Portfolio, Critic and a visually distinct deterministic Risk Engine before reaching an approval or hold outcome. Each stage is an entity with a stable mandate, inputs, structured work product, handoff and status.

The alternatives are rejected as follows:

- An agent-chat feed would make the system feel active but would bury comparison, ranking and accountability in prose.
- A free-form node graph would look impressive on desktop but perform poorly on a phone and imply relationships the records may not prove.
- A conventional event timeline is retained only as a secondary technical record; it cannot remain the primary explanation.

## Product principles

- **Outcome before machinery.** Start with the final status, operator action and data quality.
- **Entities with mandates, not personalities.** Agents are recognizable roles, not fictional people or mascots.
- **Handoffs are visible.** Every stage shows what entered and what left.
- **Selections are structured.** Instruments belong to explicit reviewed, advanced, rejected, blocked or proposed groups.
- **Evidence and uncertainty are peers.** Missing evidence is as visible as supporting evidence.
- **Deterministic code looks different from AI.** The Risk Engine cannot be mistaken for another model opinion.
- **Absence remains absence.** Historical records with missing fields say “Not recorded”; the UI never extracts invented facts from prose.
- **Safety remains ambient.** Paper-only status and the real-order block stay continuously visible without dominating the analysis.

## Information architecture

The existing Overview remains the schedule and readiness page. Agent activity becomes **Decision room** in navigation, while its deep link remains `#activity` for compatibility with Pushover and saved links.

The page has five layers:

1. **Review header** — selected review, outcome, timestamp, duration, data freshness, estimated AI cost and paper-only state.
2. **Decision flow** — evidence, three agent entities, deterministic Risk Engine and final outcome in execution order.
3. **Selection board** — Lane A and Lane B candidates organized by decision state.
4. **Stage inspector** — the selected entity’s mandate, inputs, findings, sources, blockers and handoff.
5. **Technical record** — collapsed raw structured output for audit and debugging.

The latest review is selected by default. Earlier reviews appear in a compact review switcher labeled by date, time and outcome. The page must not render twenty full review cards simultaneously.

## Layout

Desktop:

```text
┌ Review selector ─────────────── Outcome / action / freshness / cost ┐
├─────────────────────────────────────────────────────────────────────┤
│ Evidence → Research → Portfolio → Critic → Risk Gate → Final       │
├───────────────────────────────────┬─────────────────────────────────┤
│ Selection board                   │ Selected stage                  │
│ Lane A / Lane B                   │ mandate, work, evidence,        │
│ reviewed / advanced / blocked     │ blockers and handoff            │
├───────────────────────────────────┴─────────────────────────────────┤
│ Inspect technical record                                            │
└─────────────────────────────────────────────────────────────────────┘
```

Phone:

```text
Outcome and action
Review selector

Evidence
  ↓
Research
  ↓
Portfolio
  ↓
Critic
  ↓
Risk Gate
  ↓
Final

Lane A | Lane B
Decision rows
Selected stage details
Technical record
```

Desktop content is left aligned. The flow may scroll horizontally only inside its own bounded region at intermediate widths; at phone width it becomes a vertical stepper. The entire document must never overflow horizontally.

## Visual system

The visual language is a calm research desk, not a neon brokerage terminal.

### Color tokens

- Canvas `#F3F6F4` — cool neutral workspace.
- Ink `#172A24` — primary text and structure.
- Forest `#245443` — active state, safe completion and core brand.
- Evidence blue `#2F668C` — sources, data and Research.
- Caution amber `#996A20` — missing evidence, uncertainty and Critic warnings.
- Failure red `#A33F3F` — failures and hard blocks only.

White may be used as paper surface. Tints must be derived from these tokens and maintain WCAG AA contrast. Status cannot be conveyed by hue alone; every state has text and a shape or icon.

### Typography

Use the local system stack headed by `Avenir Next` with a neutral sans-serif fallback. Use one family throughout. Headings use weight and size rather than decorative typefaces. Numeric values use tabular figures in the same family. Body copy remains at least 16px with a line height of at least 1.5 and a readable measure below 80 characters.

### Graphic language

- Use small inline SVG symbols: evidence stack, research lens, allocation balance, critique shield, deterministic gate and operator decision.
- Do not use emoji, headshots, generated avatars, glowing effects or decorative market charts.
- Connectors encode actual sequence. Numbered steps are valid because this flow is ordered.
- Use borders, spacing and alignment to establish hierarchy. Reserve rounded cards for bounded work products, not every text fragment.
- Motion is limited to selection feedback and expanding details. Respect `prefers-reduced-motion`.

## Review header

The header must show:

- Human date and time, plus a short review identifier under details.
- Outcome in plain language: Paper proposal waiting, Hold cash, Review failed, Review in progress or Completion unconfirmed.
- Required operator action, if any, with one direct link to Approvals.
- Data mode and freshness: live read-only, fixture, stale, incomplete or not recorded.
- Completed stages out of expected stages.
- Elapsed duration when both timestamps exist; otherwise Not recorded.
- Estimated API-equivalent cost for this review when recorded; otherwise Not recorded.

It must not claim success from configuration alone. A missing terminal record remains unconfirmed.

## Decision flow entities

Every stage is an accessible button selecting the inspector. It shows role, mandate, status and one concise output line.

### Evidence intake

Mandate: collect allowlisted read-only market/account evidence and deterministic strategy signals.

Show quote count, volatility-series count, history coverage, strategy signal count, missing instruments and freshness. This is a system stage, not an AI agent.

### Research Agent

Mandate: compare the supplied candidates and summarize sourced evidence and uncertainty.

Show candidates compared, key findings, evidence sources, news availability and missing evidence. Never show or claim private chain-of-thought.

### Portfolio Agent

Mandate: turn the research work product into zero or more sized paper proposals.

Show advanced candidates, rejected candidates, proposed allocations, lane, size, rationale and reason for holding cash. A textual mention is not automatically a selection.

### Critic

Mandate: challenge the proposal, reject unsupported candidates and identify missing evidence or invalid assumptions.

Show objections, vetoed/rejected instruments, unresolved concerns and whether the portfolio decision changed.

### Deterministic Risk Engine

Mandate: enforce cash, holdings, position, order, freshness, volatility and Stage 1 rules.

Render this entity with squared corners and a rule-grid motif so it cannot be confused with an AI opinion. Show checks passed, checks blocked and the exact public reason codes translated into plain language. Real broker tools remain outside the flow and blocked.

### Final outcome

Show one of:

- approval required, with proposal count and expiry;
- hold cash, with the principal reason and the next missing condition;
- risk blocked, with failed rules;
- failed/unconfirmed, with the recovery action;
- completed paper action, explicitly labeled as paper.

## Selection board

Use two tabs or segmented controls: **Lane A · Stocks & ETFs** and **Lane B · Defined-risk options**. Each lane contains ordered sections:

1. Proposed
2. Advanced
3. Blocked
4. Rejected
5. Reviewed

Empty sections stay hidden except Proposed, which displays “No proposal” with the recorded reason.

Each decision row contains only fields supported by the trace:

- symbol or contract description;
- decision state;
- strategy signal, if recorded;
- sizing or maximum loss, if recorded;
- deciding stage;
- one plain-language reason;
- data freshness indicator;
- source/evidence count, if recorded.

Rows can expand to show sources, structured explanation and links to the decision record. Sorting is deterministic: decision-state priority, recorded rank, then symbol. The interface must not rank candidates by parsing free-text summaries.

Historical reviews may only provide `compared_symbols` and final `picks`. Those symbols can appear under Reviewed or Proposed; every other unavailable field displays Not recorded. Future cycles use the structured trace contract below.

## Structured activity contract

Keep SQLite `local_traces` append-only. Extend trace payloads rather than creating a second competing activity database.

Every projected event must expose its database `created_at` as fallback time when the payload lacks a timestamp. New cycle events must record an aware UTC timestamp directly.

Future records use these public structured fields where applicable:

```text
trace_id
event
timestamp
role
status
inputs: counts, freshness, source identifiers
findings: short structured statements with source references
candidate_decisions:
  instrument
  lane
  state: reviewed | advanced | rejected | blocked | proposed
  reason_code
  reason
  rank (optional)
  strategy_signal (optional)
  source_refs
blockers
handoff_summary
output
```

The dashboard projection validates types, ignores malformed nested values and records an unavailable state instead of crashing. It maps reason codes to user-facing language in one centralized dictionary. It never logs prompts, secrets, account identifiers, hidden reasoning or raw provider payloads.

The view model groups one cycle into ordered stages regardless of database insertion order. Retries belonging to the same cycle are represented within their stage rather than as duplicate agent entities. Separate cycle identifiers remain separate reviews.

## Interaction model

- Selecting a stage updates the inspector without navigating away.
- The first incomplete or blocked stage is selected by default; otherwise select Final outcome.
- Review switching updates the flow, selections and inspector as one atomic view.
- Lane selection persists only in the current browser session and is not a trading setting.
- Deep links remain stable: `#activity`; optional query parameters may select a review and lane after strict validation.
- Auto-refresh preserves selected review/stage when they still exist. If the selected item disappears, return to the latest review and announce the change through an ARIA live region.
- Technical JSON remains collapsed and must be escaped exactly as today.

## Navigation and responsive behavior

Desktop keeps the existing rail. On small screens, replace the wrapping six-link header with four primary destinations: Overview, Approvals, Decision room and More. More reveals History, Results and Controls in an accessible disclosure. Touch targets are at least 44×44px with at least 8px separation.

The paper-only safety strip remains visible near the top. Pause/resume controls remain explicit confirmation flows; this redesign cannot weaken CSRF, origin or host protections.

Test at 375px, 768px, 1024px and 1440px. No page-level horizontal scrolling, clipped status text or unreachable disclosure content is acceptable.

## Accessibility

- Preserve one H1 and sequential heading order.
- Treat the flow as an ordered list in the accessibility tree; visual connectors are decorative.
- Stage controls expose selected, complete, blocked, waiting and unavailable states in text.
- Keyboard users can move through entities and selection rows in DOM order and activate them with standard controls.
- Focus is visible and never obscured by sticky navigation.
- Status never relies on color alone.
- Expand/collapse state is announced.
- Auto-refresh and live updates do not steal focus.
- Reduced-motion users receive the final state without transitions.

## Empty, partial and failure states

- No reviews: explain when the next review is expected and link to Controls.
- In progress: show completed stages, the active stage and pending stages without inventing percentages.
- Missing timestamps: show Time not recorded and use database creation time only when available and labeled as recorded time.
- Missing candidate decisions: show the supported compared/proposed data and explain that detailed selection states were not recorded for this historical review.
- Failure: keep prior completed work visible and mark the failed boundary.
- Malformed trace: omit unsafe fields, display Activity record incomplete and keep the page usable.
- No proposal: distinguish deliberate Hold cash, insufficient evidence, stale data, risk block and budget interruption.

## Safety and privacy boundaries

- Stage 1 remains paper-only. No new Robinhood tool, order, cancel or money-moving capability is introduced.
- This page is a read-only projection except for existing approval and pause/resume controls.
- Account identifiers remain masked.
- Sources and structured findings may be shown; private chain-of-thought, prompts, secrets and raw authenticated payloads may not.
- The Tailnet-only phone route and loopback route must render the same sanitized information.
- Existing approval expiry, risk checks, notification behavior and default-deny broker policy remain unchanged.

## Implementation boundaries

Expected implementation areas:

- `agents/dashboard.py` — timestamp fallback, ordered cycle/stage projection and selection-board view model.
- `agents/dashboard_view.py` — decision-room semantic HTML and historical fallbacks.
- `agents/static/dashboard.css` — tokenized desktop/mobile layout, entity flow, inspector and decision rows.
- `agents/static/dashboard.js` — stage, review, lane and mobile More interactions with focus preservation.
- `agents/daily_cycle.py` and trace-writing helpers — aware timestamps and structured candidate decisions for future cycles.
- `tests/test_dashboard.py`, `tests/test_dashboard_resources.py` and activity/trace tests — behavior, escaping, accessibility semantics and responsive checks.

No framework, remote font, chart library, external asset host or new persistent service is required. Use server-rendered HTML, local CSS, small local JavaScript and inline/local SVG assets.

## Test strategy

Use test-driven development. Required tests include:

- event ordering is Evidence → Research → Portfolio → Critic → Risk → Final even when stored out of order;
- database `created_at` provides the explicit fallback timestamp;
- malformed events fail soft without exposing raw content;
- agents, deterministic systems and operator action have distinct semantic labels;
- reviewed, advanced, blocked, rejected and proposed candidates map only from structured fields;
- prose mentioning a symbol does not create a selection;
- Lane A and Lane B stay separate;
- historical traces render honest Not recorded fallbacks;
- retries do not duplicate stage entities;
- outcome, missing evidence, risk reasons and approval action agree with the recorded cycle;
- technical JSON and all user/provider text remain escaped;
- deep links and auto-refresh preserve valid selection;
- keyboard focus, ARIA state, heading hierarchy and reduced motion are covered;
- 375px and desktop visual checks show no page-level horizontal overflow;
- loopback and Tailnet host/origin protections continue to pass;
- Stage 1 real-order block regression remains green;
- the complete existing suite passes.

## Acceptance criteria

The upgrade is complete only when:

1. The latest review can be understood without opening technical JSON.
2. Research, Portfolio, Critic and Risk are visually and semantically distinct.
3. The end-to-end handoff and stopping point are visible at a glance.
4. Candidate decisions are organized by lane and state with recorded reasons.
5. Missing historical structure is labeled, not inferred.
6. The experience is usable at 375px and desktop widths.
7. Paper-only and real-order-blocked status remains continuously clear.
8. Current-code tests, including real-order blocking, pass.
9. Browser inspection confirms the rendered desktop and phone layouts.

## Self-review

The design avoids the current repeated-card wall, does not turn agents into fictional people, keeps structured evidence distinct from hidden reasoning, gives deterministic risk checks their own identity, preserves deep links and safety controls, degrades honestly for historical records, and requires mobile verification because Pushover now opens the dashboard on an iPhone. The scope is limited to truthful activity projection, navigation needed to access it and future trace structure; it does not change trading strategy or authorization.
