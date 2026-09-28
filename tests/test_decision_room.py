from agents.decision_room import project_decision_room


def test_projects_logical_stage_order_and_created_at_fallback():
    records = [
        {
            'trace_id': 'c1',
            'event': 'stage_completed',
            'role': 'critic',
            '_row_id': 5,
            '_created_at': '2026-09-28T14:00:05+00:00',
            'output': {
                'counterargument': 'Check liquidity.',
                'rejected_instruments': ['OPT-1'],
            },
        },
        {
            'trace_id': 'c1',
            'event': 'cycle_started',
            '_row_id': 1,
            '_created_at': '2026-09-28T14:00:00+00:00',
        },
        {
            'trace_id': 'c1',
            'event': 'risk_evaluated',
            '_row_id': 6,
            '_created_at': '2026-09-28T14:00:06+00:00',
            'status': 'blocked',
            'candidate_decisions': [
                {
                    'instrument': 'OPT-1',
                    'lane': 'B',
                    'state': 'blocked',
                    'reason_code': 'stale_quote',
                    'reason': 'Current option quote is unavailable.',
                    'source_refs': [],
                }
            ],
        },
    ]

    review = project_decision_room(records, [])[0]

    assert [stage['key'] for stage in review['stages']] == [
        'evidence',
        'research',
        'portfolio',
        'critic',
        'risk',
        'final',
    ]
    assert review['timestamp'] == '2026-09-28T14:00:06+00:00'
    assert review['lanes']['B'][0]['state'] == 'blocked'


def test_candidate_precedence_never_parses_prose_or_crosses_lanes():
    records = [
        {
            'trace_id': 'c1',
            'event': 'stage_completed',
            'role': 'research',
            '_row_id': 1,
            '_created_at': '2026-09-28T14:00:01+00:00',
            'output': {'summary': 'VTI and OPT-1 are discussed only in prose.'},
            'candidate_decisions': [
                {
                    'instrument': 'VTI',
                    'lane': 'A',
                    'state': 'reviewed',
                    'reason_code': 'research_compared',
                    'reason': 'Compared by Research.',
                    'source_refs': [],
                },
                {
                    'instrument': 'VTI',
                    'lane': 'A',
                    'state': 'advanced',
                    'reason_code': 'strategy_signal',
                    'reason': 'Deterministic signal qualified.',
                    'source_refs': ['signal:VTI'],
                },
                {
                    'instrument': 'VTI',
                    'lane': 'A',
                    'state': 'proposed',
                    'reason_code': 'portfolio_pick',
                    'reason': 'Portfolio proposed VTI.',
                    'source_refs': [],
                },
                {
                    'instrument': 'VTI',
                    'lane': 'B',
                    'state': 'unknown',
                    'reason_code': 'bad',
                    'reason': 'Must be ignored.',
                },
            ],
        }
    ]

    review = project_decision_room(records, [])[0]

    assert [(row['instrument'], row['state']) for row in review['lanes']['A']] == [
        ('VTI', 'proposed')
    ]
    assert review['lanes']['B'] == []


def test_malformed_candidate_details_fail_soft_and_mark_record_incomplete():
    records = [
        {
            'trace_id': 'broken',
            'event': 'stage_completed',
            'role': 'research',
            '_row_id': 1,
            '_created_at': '2026-09-28T14:00:01+00:00',
            'output': {'summary': '<script>bad()</script>'},
            'candidate_decisions': {'instrument': 'VTI'},
        }
    ]

    review = project_decision_room(records, [])[0]

    assert review['record_incomplete'] is True
    assert review['lanes'] == {'A': [], 'B': []}
    assert review['stages'][1]['summary'] == '<script>bad()</script>'


def test_retry_consolidates_to_one_active_stage_and_waiting_is_default():
    records = [
        {
            'trace_id': 'retry',
            'event': 'stage_completed',
            'role': 'research',
            'timestamp': '2026-09-28T14:00:01+00:00',
            '_row_id': 1,
            'output': {'summary': 'First attempt.'},
        },
        {
            'trace_id': 'retry',
            'event': 'stage_started',
            'role': 'research',
            'timestamp': '2026-09-28T14:00:02+00:00',
            '_row_id': 2,
        },
    ]

    review = project_decision_room(records, [])[0]

    research = [stage for stage in review['stages'] if stage['key'] == 'research']
    assert len(research) == 1
    assert research[0]['status'] == 'active'
    assert review['default_stage'] == 'evidence'

    waiting = project_decision_room(
        [
            {
                'trace_id': 'waiting',
                'event': 'cycle_started',
                'timestamp': '2026-09-28T14:00:00+00:00',
                '_row_id': 1,
            }
        ],
        [],
    )[0]
    assert waiting['stages'][0]['status'] == 'waiting'
    assert waiting['default_stage'] == 'evidence'


def test_projection_allowlists_public_details_and_enriches_pending_outcome():
    records = [
        {
            'trace_id': 'privacy',
            'event': 'stage_completed',
            'role': 'research',
            'timestamp': '2026-09-28T14:00:01+00:00',
            '_row_id': 1,
            'output': {
                'summary': 'Safe summary.',
                'compared_symbols': ['VTI'],
                'prompt': 'secret prompt',
                'api_key': 'secret key',
            },
        },
        {
            'trace_id': 'privacy',
            'event': 'cycle_terminal',
            'timestamp': '2026-09-28T14:00:02+00:00',
            '_row_id': 2,
            'payload': {
                'status': 'COMPLETED',
                'reason': 'Paper proposal created.',
                'results': [{'card_id': 'card-1'}],
            },
        },
    ]
    cards = [{'id': 'card-1', 'status': 'PENDING'}]

    review = project_decision_room(records, cards)[0]
    details = review['stages'][1]['details']

    assert details == {'summary': 'Safe summary.', 'compared_symbols': ['VTI']}
    assert review['outcome']['pending_count'] == 1


def test_naive_payload_timestamp_uses_aware_database_time():
    review = project_decision_room(
        [
            {
                'trace_id': 'naive',
                'event': 'data_collected',
                'timestamp': '2026-09-28T14:00:00',
                '_created_at': '2026-09-28T14:00:03+00:00',
                '_row_id': 1,
                'quote_count': 14,
            }
        ],
        [],
    )[0]

    assert review['timestamp'] == '2026-09-28T14:00:03+00:00'


def test_malformed_nested_types_fail_soft_and_mark_review_incomplete():
    review = project_decision_room(
        [
            {
                'trace_id': 'malformed',
                'event': 'cycle_started',
                'timestamp': '2026-09-28T14:00:00+00:00',
                'data_mode': {},
            },
            {
                'trace_id': 'malformed',
                'event': [],
                'role': [],
                'candidate_decisions': [
                    {'instrument': 'VTI', 'lane': [], 'state': []}
                ],
            },
            {
                'trace_id': 'malformed',
                'event': 'cycle_terminal',
                'timestamp': '2026-09-28T14:00:02+00:00',
                'payload': ['not-a-mapping'],
            },
            {
                'trace_id': 'malformed',
                'event': 'risk_evaluated',
                'status': [],
            },
        ],
        [],
    )[0]

    assert review['record_incomplete'] is True
    assert review['data_mode'] == 'not_recorded'
    assert review['lanes'] == {'A': [], 'B': []}
    assert review['status'] == 'unconfirmed'
    assert review['stages'][4]['status'] == 'unavailable'
    assert review['stages'][4]['status_label'] == 'Unavailable'
    assert review['header']['completed_stages'] == 0


def test_recursive_public_schema_removes_nested_secrets():
    review = project_decision_room(
        [
            {
                'trace_id': 'nested-privacy',
                'event': 'stage_completed',
                'role': 'research',
                'timestamp': '2026-09-28T14:00:01+00:00',
                'output': {
                    'summary': 'Public finding.',
                    'news_checked': True,
                    'news': [{
                        'fact': 'Revenue guidance increased.',
                        'source_url': 'https://example.test/filing',
                        'observed_at': '2026-09-28T13:59:00+00:00',
                        'api_key': 'nested-secret',
                        'prompt': 'hidden-prompt',
                    }],
                },
            }
        ],
        [],
    )[0]

    assert review['stages'][1]['details']['news'] == [{
        'fact': 'Revenue guidance increased.',
        'source_url': 'https://example.test/filing',
        'observed_at': '2026-09-28T13:59:00+00:00',
    }]


def test_risk_status_header_and_semantic_inspector_are_truthful():
    base = [
        {
            'trace_id': 'truthful',
            'event': 'cycle_started',
            'timestamp': '2026-09-28T14:00:00+00:00',
            'data_mode': 'live_readonly',
        },
        {
            'trace_id': 'truthful',
            'event': 'data_collected',
            'timestamp': '2026-09-28T14:00:01+00:00',
            'data_mode': 'live_readonly',
            'quote_count': 14,
            'volatility_count': 14,
        },
        {
            'trace_id': 'truthful',
            'event': 'final_refresh',
            'timestamp': '2026-09-28T14:00:04+00:00',
            'data_mode': 'live_readonly',
            'quote_count': 14,
            'missing_instruments': [],
        },
        {
            'trace_id': 'truthful',
            'event': 'risk_evaluated',
            'timestamp': '2026-09-28T14:00:05+00:00',
            'data_mode': 'live_readonly',
            'status': 'not_run',
            'results': [],
            'real_execution': 'blocked',
        },
        {
            'trace_id': 'truthful',
            'event': 'cycle_terminal',
            'timestamp': '2026-09-28T14:00:06+00:00',
            'data_mode': 'live_readonly',
            'payload': {
                'status': 'COMPLETED',
                'reason': 'No eligible paper trade.',
                'decision': {'picks': []},
                'results': [],
                'api_cost_estimate_usd': '0.12',
            },
        },
    ]

    review = project_decision_room(base, [])[0]
    risk = review['stages'][4]
    assert risk['status'] == 'skipped'
    assert risk['status_label'] == 'Not run'
    assert risk['summary'] == 'Deterministic risk checks did not run.'
    assert review['header'] == {
        'short_id': 'truthful',
        'outcome': 'Hold cash',
        'action': 'Nothing needs your approval',
        'data_mode': 'Live read-only',
        'freshness': 'Refreshed at completion',
        'duration': '6 seconds',
        'api_cost_estimate_usd': '0.12',
        'completed_stages': 2,
        'expected_stages': 6,
        'paper_only': True,
    }
    assert risk['inspector']['mandate'].startswith('Apply deterministic')
    assert risk['inspector']['findings'] == ['Deterministic risk checks did not run.']
    assert risk['inspector']['handoff'] == 'Risk checks were skipped; no checked proposal was handed to Final outcome.'

    blocked_records = [dict(item) for item in base]
    blocked_records[3] = {
        **blocked_records[3],
        'status': 'blocked',
        'results': [{'status': 'RISK_BLOCKED', 'reason_code': 'settled_cash'}],
    }
    blocked = project_decision_room(blocked_records, [])[0]['stages'][4]
    assert blocked['status'] == 'blocked'
    assert blocked['summary'] == 'Deterministic risk checks blocked the proposal.'


def test_summaries_validate_counts_and_negative_results_do_not_claim_action():
    secret = 'SYNTHETIC_SECRET_ONLY'
    records = [
        {
            'trace_id': 'negative-result',
            'event': 'data_collected',
            'timestamp': '2026-09-28T14:00:00+00:00',
            'quote_count': {'api_key': secret},
            'volatility_count': [secret],
        },
        {
            'trace_id': 'negative-result',
            'event': 'cycle_terminal',
            'timestamp': '2026-09-28T14:00:01+00:00',
            'payload': {
                'status': 'COMPLETED',
                'decision': {'picks': [{'instrument': 'VTI'}]},
                'results': [{'status': 'UNAFFORDABLE_OR_UNHELD', 'instrument': 'VTI'}],
            },
        },
    ]

    review = project_decision_room(records, [])[0]

    assert secret not in review['stages'][0]['summary']
    assert review['header']['outcome'] == 'Hold cash'
    assert review['header']['action'] == 'Nothing needs your approval'


def test_unknown_result_status_remains_incomplete_and_unconfirmed():
    review = project_decision_room(
        [
            {
                'trace_id': 'unknown-result',
                'event': 'cycle_terminal',
                'timestamp': '2026-09-28T14:00:01+00:00',
                'payload': {
                    'status': 'COMPLETED',
                    'decision': {'picks': [{'instrument': 'VTI'}]},
                    'results': [{'status': 'UNKNOWN', 'instrument': 'VTI'}],
                },
            }
        ],
        [],
    )[0]

    assert review['header']['outcome'] == 'Completion unconfirmed'
    assert review['header']['action'] == 'Check run history'
    assert review['proposal_state'] == 'unknown'
    assert review['record_incomplete'] is True


def test_inspector_preserves_public_pick_risk_and_source_details_without_inventing_handoff():
    records = [
        {
            'trace_id': 'public-details',
            'event': 'stage_completed',
            'role': 'research',
            'timestamp': '2026-09-28T14:00:00+00:00',
            'output': {'summary': 'Compared VTI.', 'compared_symbols': ['VTI']},
            'candidate_decisions': [{
                'instrument': 'VTI', 'lane': 'A', 'state': 'reviewed',
                'reason_code': 'research_compared', 'reason': 'Compared.',
                'source_refs': ['filing:VTI:10-Q'],
            }],
        },
        {
            'trace_id': 'public-details',
            'event': 'stage_completed',
            'role': 'portfolio',
            'timestamp': '2026-09-28T14:00:01+00:00',
            'output': {
                'reason': 'A small paper allocation was proposed.',
                'picks': [{
                    'instrument': 'VTI', 'side': 'buy', 'quantity': '0.4',
                    'limit_price': '100.20', 'max_loss_usd': '40.08',
                    'thesis': 'Broad-market exposure.',
                }],
            },
        },
        {
            'trace_id': 'public-details',
            'event': 'risk_evaluated',
            'timestamp': '2026-09-28T14:00:02+00:00',
            'status': 'blocked',
            'results': [{
                'status': 'RISK_BLOCKED', 'instrument': 'VTI',
                'reasons': ['insufficient_settled_cash'],
            }],
        },
    ]

    review = project_decision_room(records, [])[0]
    portfolio_findings = review['stages'][2]['inspector']['findings']
    risk_blockers = review['stages'][4]['inspector']['blockers']

    assert any('0.4' in finding and '$100.20' in finding for finding in portfolio_findings)
    assert any('Broad-market exposure.' in finding for finding in portfolio_findings)
    assert 'insufficient_settled_cash' in risk_blockers
    assert review['lanes']['A'][0]['source_refs'] == ['filing:VTI:10-Q']
    assert 'expected next step' in review['stages'][1]['inspector']['handoff'].lower()
    assert 'was handed' not in review['stages'][1]['inspector']['handoff'].lower()


def test_legacy_terminal_payload_recovers_recorded_evidence_with_provenance():
    review = project_decision_room(
        [
            {
                'trace_id': 'legacy-evidence',
                'event': 'cycle_terminal',
                'timestamp': '2026-09-28T14:20:17+00:00',
                'data_mode': 'live_readonly',
                'payload': {
                    'status': 'COMPLETED',
                    'quote_count': 14,
                    'volatility_count': 14,
                    'read_tools': ['get_accounts', 'get_equity_quotes'],
                    'decision': {'picks': []},
                    'results': [],
                },
            }
        ],
        [],
    )[0]

    evidence = review['stages'][0]
    assert evidence['status'] == 'completed'
    assert evidence['summary'] == (
        '14 quotes and 14 volatility series recorded in the final cycle record.'
    )
    assert evidence['details'] == {
        'read_tools': ['get_accounts', 'get_equity_quotes'],
        'quote_count': 14,
        'volatility_count': 14,
        'record_source': 'Final cycle record',
    }
    assert evidence['inspector']['sources'] == ['Final cycle record']


def test_completed_zero_pick_legacy_cycle_marks_risk_not_needed():
    review = project_decision_room(
        [
            {
                'trace_id': 'legacy-no-pick',
                'event': 'cycle_terminal',
                'timestamp': '2026-09-28T14:20:17+00:00',
                'data_mode': 'live_readonly',
                'payload': {
                    'status': 'COMPLETED',
                    'market_open': True,
                    'decision': {'picks': []},
                    'results': [],
                },
            }
        ],
        [],
    )[0]

    risk = review['stages'][4]
    assert risk['status'] == 'not_applicable'
    assert risk['status_label'] == 'Not needed'
    assert risk['summary'] == 'No risk check was needed because Portfolio proposed no trades.'
    assert risk['inspector']['inputs'] == ['Portfolio decision: 0 picks.']
    assert risk['inspector']['sources'] == ['Final cycle record']
    assert risk['inspector']['handoff'] == 'No proposal entered deterministic risk checks.'


def test_model_telemetry_never_becomes_a_trading_review():
    reviews = project_decision_room(
        [
            {
                'trace_id': 'real-cycle',
                'event': 'cycle_started',
                'timestamp': '2026-09-28T14:00:00+00:00',
            },
            {
                'trace_id': 'model-call',
                'event': 'codex_readonly_run',
                'timestamp': '2026-09-28T14:00:01+00:00',
                'payload': {'model': 'cheap-research-model'},
            },
            {
                'trace_id': 'sdk-span',
                'event': 'span_start',
                'timestamp': '2026-09-28T14:00:02+00:00',
                'payload': {'object': 'trace.span'},
            },
        ],
        [],
    )

    assert [review['review_id'] for review in reviews] == ['real-cycle']
