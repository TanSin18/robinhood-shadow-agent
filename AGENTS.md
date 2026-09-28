# Instructions for any coding assistant

Read HANDOFF.md, README.md and the approved spec before work. Never treat a plan,
UI animation, passing mock test or cached status as proof of installed operation.

1. This is paper/shadow-only. Never place, cancel, exercise or fund real orders.
2. Never request passwords, MFA codes, OAuth tokens or Pushover secrets in chat.
3. The primary Mac alone runs the official schedule. Clones are development-only.
4. Preserve the Phase 0 gate. Phase 1/2 runtime work requires the operator's
   approval and the recorded gate, including the v1.5 preregistration review.
5. Do not modify preregistration without explicit dated operator authorization.
6. Do not claim dynamic discovery/news/Biscuit/Bubbles are active. See HANDOFF.md.
7. Keep main and UI work separate. No UI merge or dashboard restart before proof.
8. Preview is view-only: mode=ro, no POST, broker, model calls or official writes.
9. Only recorded handoffs draw real edges. Historical workflow is dashed and
   labeled expected. Missing evidence is unknown, never healthy/green.
10. Keep secrets and private runtime state out of commits, PRs, logs and reports.
11. Use tests before fixes, run the full suite and report all failures honestly.
12. No automatic deployment on push, no duplicated scheduled runner, and no
    copying a development database over the primary experiment.

For each handoff, update implemented vs planned behavior, exact tests run,
known blockers and the next permitted step. Model/account changes are not
authorization to change governance or safety policy.
