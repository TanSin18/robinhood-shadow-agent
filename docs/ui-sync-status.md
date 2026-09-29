# GitHub UI checkpoint — September 28, 2026

## Verified pre-gate repair

Fresh reproduction: **36 failed, 581 passed**. After repair: **617 passed,
0 failed, 27 warnings**, 42.25 seconds. No tests were skipped or removed.

- Seven portability failures depended on absent private settings, a personal
  hostname, a relative virtual environment or private proxy bundle input. Reused
  the synthetic fixtures/sys.executable repair from runtime commit 584b197.
- Twenty-nine dashboard/inbox failures were caused by an early replacement of
  the operational renderer. This lost its expected filters/history, evidence
  and controls, including CSRF form discovery. Restored the operational server
  file to main's implementation; the separate Agent Desk preview is intact.

Passing legacy contracts is not operational Agent Desk acceptance. The live
replacement remains unimplemented/unapproved pending the scheduled Phase 0 gate
and explicit integration tests for Agent Desk approvals, controls, history,
filters, notifications, safe redirects and security/accessibility parity.

Read-only installed readiness assessment: **ready=false**, with the blocker
"No fresh authenticated full cycle is proven under the installed launchd service
for this code/configuration." Its matching test receipt reports 589 passing
tests; the isolated 615-test runtime branch is not the installed service.
No broker/model calls, official database writes, merge or service restart were
performed for this UI repair. GET-side expiry remains a tracked Phase 1 fix;
the dedicated preview continues to compute expiry without writes.

## Previous checkpoint (historical)

Synced the latest eight preview UI files from the local Agent Desk worktree.
No runtime, broker, scheduler, configuration or preregistration changes.
No service restart or deployment. This branch is a development snapshot, not
an acceptance-approved dashboard replacement.

Fresh full suite: **581 passed, 36 failed, 27 warnings**.
Focused preview suite: **6 passed**. Visual polish suite: **3 passed**.
Seven failures match the sanitized runtime export baseline. The additional
legacy dashboard/inbox failures have not been diagnosed here; do not label
them harmless or claim dashboard acceptance. Fix and verify before merging.

## Failing tests

- `tests/test_config_and_schemas.py::test_default_config_is_stage_one_paper_only`
- `tests/test_config_and_schemas.py::test_installed_service_config_uses_private_phone_dashboard_url`
- `tests/test_dashboard.py::test_clear_filters_stays_in_its_section_and_skip_target_accepts_focus`
- `tests/test_dashboard.py::test_control_rejects_cross_origin_unknown_actions_and_symlink_stops`
- `tests/test_dashboard.py::test_dashboard_has_next_history_results_and_no_fake_success`
- `tests/test_dashboard.py::test_dashboard_separates_views_and_keeps_pause_discoverable`
- `tests/test_dashboard.py::test_decision_room_keeps_security_and_accessibility_contracts`
- `tests/test_dashboard.py::test_decision_room_links_pending_approval_and_marks_failed_boundary`
- `tests/test_dashboard.py::test_decision_room_renders_entities_flow_selections_and_honest_fallbacks`
- `tests/test_dashboard.py::test_decision_rows_expose_recorded_source_references`
- `tests/test_dashboard.py::test_filters_are_collapsed_until_needed_and_active_filters_stay_visible`
- `tests/test_dashboard.py::test_filters_escape_evidence_and_report_route_cannot_read_files`
- `tests/test_dashboard.py::test_fixture_balances_are_labeled_in_results_and_hold_can_be_filtered`
- `tests/test_dashboard.py::test_fixture_cycles_are_visibly_labeled_and_assets_change_evidence_hash`
- `tests/test_dashboard.py::test_form_referrer_policy_preserves_same_origin_posts_but_rejects_null`
- `tests/test_dashboard.py::test_get_confirmation_never_places_csrf_token_in_url`
- `tests/test_dashboard.py::test_historical_pending_proposal_never_claims_no_proposal`
- `tests/test_dashboard.py::test_historical_review_does_not_invent_unrecorded_selection_details`
- `tests/test_dashboard.py::test_history_explains_strategy_signal_result_and_next_trigger`
- `tests/test_dashboard.py::test_history_gives_standalone_failure_a_plain_language_fallback`
- `tests/test_dashboard.py::test_history_groups_recovery_day_and_marks_reviewed_incident_resolved`
- `tests/test_dashboard.py::test_history_labels_closed_market_cycle_as_after_hours_and_does_not_claim_fresh_quotes`
- `tests/test_dashboard.py::test_malformed_trace_http_view_stays_available_and_nested_secrets_are_removed`
- `tests/test_dashboard.py::test_mobile_navigation_has_three_primary_links_and_more_disclosure`
- `tests/test_dashboard.py::test_optional_view_receipt_failure_does_not_break_dashboard`
- `tests/test_dashboard.py::test_overview_does_not_record_hidden_cards_and_view_receipts_require_csrf`
- `tests/test_dashboard.py::test_pending_filter_and_lane_filter_never_change_paper_accounts`
- `tests/test_dashboard.py::test_pushover_test_button_is_csrf_protected_and_records_delivery`
- `tests/test_dashboard.py::test_resume_never_clears_an_external_stop_or_starts_a_cycle`
- `tests/test_dashboard.py::test_review_header_and_stage_inspector_use_plain_language`
- `tests/test_inbox_web.py::test_exact_configured_tailnet_host_and_https_origin_are_allowed`
- `tests/test_inbox_web.py::test_local_page_and_origin_csrf_defenses`
- `tests/test_operational_readiness.py::test_configuration_fingerprint_is_stable_across_processes`
- `tests/test_operational_readiness.py::test_verifier_cli_reports_missing_evidence_without_writing_account`
- `tests/test_private_proxy_bundle.py::test_bundle_has_no_execution_adapters_or_operator_symlinks`
- `tests/test_private_proxy_bundle.py::test_bundle_rejects_python_symlink_to_operator_home`
