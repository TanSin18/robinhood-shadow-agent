from agents.desk.router import render


def review():
    return {'review_id': 'run-1', 'timestamp': '2026-09-28T14:20:00+00:00',
            'stages': [{'key':'research','status':'completed','status_label':'Completed',
                        'summary':'Legacy narrative <script>unsafe</script>',
                        'inspector':{'inputs':['Candidates supplied: VTI'], 'findings':['Legacy narrative'],
                                     'sources':['Not recorded'], 'handoff':'Handoff not recorded.'}}],
            'outcome':{},'lanes':{'A':[],'B':[]}}


def test_historical_scene_without_run_log_shows_unrecorded_edges_bench_and_disabled_player():
    html=render('/room',{'preview':True,'decision_room':[review()]},None,'')
    assert 'scene-map' in html and 'edge-unknown' in html and 'edge-carried' not in html
    assert 'Expected workflow' in html
    assert 'data-replay="play" disabled' in html
    assert 'No recorded handoff messages' in html
    assert 'Biscuit' in html and 'joins in Phase 1' in html
    assert 'data-actor="filings_news"' not in html
    assert 'data-edge=' not in html
    assert 'Original report' in html and '<script>unsafe' not in html
    for name in ('Work','Original report'):
        assert name in html
    assert 'editable after Phase 0 via side test' in html
    assert '<textarea' not in html  # no disabled placeholder controls


def test_only_valid_same_run_records_create_replay_edges():
    from agents.desk.scene import handoffs
    r=review()
    good={'cycle_id':'run-1','seq':1,'from_actor':'research','to_actors':['portfolio'],
          'message':'Cited evidence is ready.','created_at':'2026-09-28T14:00:00+00:00'}
    rows=[good,{**good,'cycle_id':'other'},{**good,'from_actor':'filings_news'},
          {**good,'message':None},{**good,'created_at':'bad'}]
    assert len(handoffs(r,rows))==1
    html=render('/room',{'preview':True,'decision_room':[r],'handoffs':rows},None,'')
    assert 'data-edge="research-portfolio"' in html
    assert 'Cited evidence is ready.' in html
    assert 'data-replay="play" disabled' not in html
    assert 'data-edge="portfolio-critic"' not in html


def test_preview_preserves_money_and_action_destination():
    money=render('/money',{'preview':True},None,'')
    controls=render('/controls',{'preview':True},None,'')
    assert 'Road to real money' in money
    assert 'Not assessed' in money
    assert 'http://127.0.0.1:8765/' in controls
    assert '<form' not in controls


def test_legacy_prose_is_not_reclassified_as_verified_evidence():
    r=review(); r['stages'][0]['summary']='No stale quotes. News was not disabled.'
    html=render('/room',{'preview':True,'decision_room':[r]},None,'')
    assert 'Prices needed refreshing' not in html
    assert 'News was not collected' not in html
    assert 'Structured supporting facts were not saved' in html


def test_saved_structured_news_fact_and_source_are_not_claimed_missing():
    r=review()
    r['stages'][0]['details']={'news':[{'fact':'Recorded announcement',
        'source_url':'https://example.org/filing','published_at':'2026-09-28T12:00:00Z'}]}
    html=render('/room',{'preview':True,'decision_room':[r]},None,'')
    assert 'Recorded announcement' in html
    assert '1 recorded fact(s) below' in html
    assert 'https://example.org/filing' in html
    assert 'Evidence classification not recorded' in html


def test_unknown_tuning_value_has_no_invented_slider_thumb():
    html=render('/room',{'preview':True,'decision_room':[review()]},None,'')
    assert 'slider' not in html and 'type="range"' not in html
