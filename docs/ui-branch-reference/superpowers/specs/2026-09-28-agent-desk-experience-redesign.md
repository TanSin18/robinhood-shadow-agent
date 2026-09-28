# Agent Desk experience redesign

Status: design for operator review; not implementation approval.

## Purpose and boundaries

Make the investment team understandable without reading logs. Keep the existing character artwork. Within ten seconds the operator should understand the selected review's outcome, what needs attention, and what happens next. Within two interactions they should reach the evidence behind any displayed conclusion.

Only the connected Agentic account is in scope. Never request or expose the main brokerage account. Distinguish real-account observations from paper experiment results everywhere. This design does not authorize new broker methods, real orders, changing preregistration, or bypassing Phase 0.

Frozen main and service 8765 remain untouched. Preview 8766 remains view-only: SQLite mode=ro, short serialized reads, no broker connection, no POST actions. New recorded handoffs and model explanations are post-gate backend work, not UI-only changes. The existing 13 collection errors remain a release blocker.

## Direction and alternatives

Recommended: an evidence-first workspace. Today answers the operator's questions; Decision room explains a particular decision. Keep the existing dark palette, local Geist fonts and SVG portraits, but replace repeated reports with focused panels.

Not selected: a chat-first interface (hard to audit or compare) or a map-only interface (hides schedules, holdings and failures). Chat is an optional explanation tool, not navigation or control.

## Visual system

Retain approved base #0f1012, surface #17181b, text #f2f3f5, code cyan #3dc6ff, AI violet #b9a3ff and warning amber #f5b54a. Color always accompanies a text status. Use Geist for prose, Geist Mono only for numeric comparisons. Preserve 44px targets, visible keyboard focus, self-hosted assets and strict CSP. No new framework, animation library, remote font or GitHub runtime dependency is required.

Desktop: quiet left navigation, generous central workspace, contextual evidence drawer. Phone: one column, evidence opens as a full-width sheet with Back; no hover-only actions or sideways canvas navigation. The seven existing routes remain available; deferred routes explain their missing data once rather than filling the screen with placeholders.

## Today

```
Agent Desk       Today                         Last refreshed: [time]
                 [Paper activity state]        [Refresh records]
Today
Decision room    Latest review                 Needs you
Portfolio        Outcome in one sentence       Pending approvals or none
Results          Main reason in one sentence   Operational alert, if present
Controls         [Explore this review]
Health
                 What happens next
                 Verified schedule + timezone; expected, not guaranteed

                 Team progress for selected review
                 Find — Research — Choose — Challenge — Protect — Outcome

                 Paper performance             Recent activity
                 Available values only         Three concise dated events
```

Do not treat an operator pause as a safety incident. Distinguish paused, stopped by safety, scheduled, running, finished, failed and unknown. A completed hold differs from an operational failure. A schedule is not proof of a successful background run. Show the observation time and stale/unknown status alongside operational health.

## Decision room

```
[Review: date, time, recorded mode]   [Idea: recorded candidate]

                   Pip / Research
Scanners --------> Maple / Choose <----> Pickle / Challenge
                          |
                          v
                     Nugget / Protect ------> Outcome

[Previous] [Play recorded events] [Next]      Event x of y

Selected agent: character + role + AI or deterministic code
Received             Found                  Passed on / stopped
Short recorded facts Short recorded facts  Actual recorded destination

[Evidence] [Ask about this work] [Original record]
```

The drawing above is conceptual, not an assertion that these edges occurred. Actual graph edges must come from recorded sender/recipient events. Do not add a Critic rebuttal loop, fund bypass, parallel specialist or successful handoff unless recorded. Historical six-stage records use a visibly labeled expected workflow with dashed connections and no transmission animation. Unimplemented specialists stay out of the active graph.

Motion conveys event progression: highlight the selected recorded edge and reveal its message. Play, pause and step remain operator-controlled. Respect reduced motion with instant selection changes. Never animate idle agents, invent percent progress, or label replay as live. Live state requires a fresh event connection; disconnection changes the label immediately.

## Evidence drawer

One claim per row, grouped as Supporting facts, Contrary facts, Missing information and Sources. Each item has claim text, recorded value/unit when present, source reference, observation time, freshness and the agent output that used it. Sources open the saved excerpt or cited original; the UI must not imply a citation was verified when it was not.

Legacy prose is labeled Original report. Do not manufacture structured facts, citations or confidence from substring matches. Deterministic projection may display existing structured facts; missing fields remain missing. A future LLM summary is separately labeled, cited and validated rather than silently replacing the original record.

## Per-agent questions

Bubbles explains the selected agent's public records, not its hidden reasoning. Bind every request to run ID, agent key and optional candidate ID. Show this scope above the question box, with suggested questions such as What evidence supported this? and What information was missing?

Answers use only authorized, stored records in that scope; every factual claim cites a record. Display Explained by Bubbles, not a new decision from the original agent. No broker tools, arbitrary SQL, settings access, official-memory writes, new research or executions. Exclude order histories and credentials entirely. Store explanation history and costs separately from official arms. Apply explicit per-question budget reservation, timeout, source validation and a visible failure state; never silently switch models. The dated model and cost ceiling require a post-gate implementation-plan decision before enabling calls. Disable the box with an honest reason until those dependencies pass, rather than offering canned fake answers.

## Portfolio

Two explicit tabs: Agentic account (real, read-only) and Paper experiment. Each has snapshot time and source. Display cash and holdings only when present in an authorized snapshot; no snapshot means Connection/snapshot needed, not a zero balance. No account identifiers in the UI or reports. No merging real positions, paper fills or experimental returns.

The preview may show already-stored, authorized sanitized account observations only. It cannot fetch new broker data. After Phase 0, an independently authorized read-only refresh path can use the existing isolated proxy and approved methods; the main app never receives credentials. Real-account observation remains separate from trading evaluation. Performance curves require actual valuation history, not reconstructed gains from current holdings.

## Results and operations

Results answers whether AI adds value using comparable recorded arms, periods, modes and rulebook versions. Show cost, sample size and inconclusive status alongside any comparison. Never synthesize absent benchmark series. API cost is attributed only to the appropriate AI arm.

Controls groups: Paper activity, Reviews, Notifications and Safety recovery. Status is prominent and distinct from available actions. Existing supported actions retain server enforcement, confirmation, CSRF and incident-latch semantics. Unsupported actions are explained, not presented as functioning buttons. In preview, link to the live control page for supported actions; never forward a mutation through 8766. Enabling new controls is post-gate work with endpoint tests, not an animation change.

Health shows scheduler evidence, proxy observation time, authorization expiry, data feeds, notification delivery and safety state. Unknown is never green. Persistent warning banners are concise and link to the specific repair detail.

## Acceptance and release sequence

1. Operator reviews this design and representative Today, evidence and Decision room layouts before implementation planning.
2. Plan separates preview presentation work from U1 handoffs, U4 data projections, U5 controls, U6 live events and U7 explanation services. Phase 0 remains the hard prerequisite for runtime work.
3. Verify plain-language outcomes, source integrity, real/paper separation, replay truthfulness, keyboard navigation and 375px/desktop layout using real records or conspicuously labeled isolated test fixtures.
4. Automated tests cover no inference from missing data, cited evidence bindings, no cross-run chat leakage, injection resistance, validation/cost failures, default-deny broker methods, read-only preview, expiry and independent writer commits.
5. Existing baseline collection errors must be repaired and full dashboard acceptance pass before replacing 8765. Merge only approved dashboard changes; restart only the dashboard after the Phase 0 proof. No automatic merge or deployment follows design approval.
