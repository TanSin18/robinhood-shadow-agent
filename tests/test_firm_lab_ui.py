"""Dashboard truthfulness (required UI tests 28-35) and the read-only Firm Lab page."""
import hashlib
import re
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from agents.desk import firm_lab_page
from agents.desk.components import ARM_HELP, ARM_NAMES, COMPARE_NOTE, ROUTES, decision_source, shell, truth_bar
from agents.desk.router import render
from firm_lab import cli, view
from test_dashboard import read, serving
from test_desk_v10 import _state
from test_firm_lab_features import _official_with_capsule
from test_inbox_lanes import setup_runtime

DESK = Path(__file__).resolve().parents[1] / 'agents' / 'desk'
RETIRED = ('AI alone', 'AI + your approval', 'Agent alone', 'With your approvals', 'Agent + my approvals', 'Agent + your approvals')


def _pages(state=None):
    state = state or {**_state(), 'analyst': {'exists': False}, 'firm': {'exists': False}, 'decision_room': [], 'history': [],
                      'card_inbox': {'cards': [], 'journal': [], 'acks': []}}
    out = {}
    for path, _ in ROUTES:
        if path == '/ask':
            state = {**state, 'ask': {'exists': False}}
        out[path] = render(path, state, None, '')
    return out


# ---------------------------------------------------------------- 28-30: retired wording
def test_retired_arm_names_are_gone_from_every_page_and_from_the_source():                         # 28, 29
    for path, html in _pages().items():
        for phrase in RETIRED:
            assert phrase not in html, (path, phrase)
    for source in sorted(DESK.glob('*.py')) + [DESK / 'rulebook.json']:
        if source.name == 'frontdoor.py':                 # holds the old -> new table applied to the operational page (tested below)
            continue
        text = source.read_text()
        for phrase in RETIRED:
            assert phrase not in text, (source.name, phrase)
    assert ARM_NAMES['agent_alone'] == 'Automatic arm' and ARM_NAMES['with_approvals'] == 'Approval arm'
    assert ARM_HELP['agent_alone'] == 'Executes eligible registered paper decisions automatically. Each trade shows its actual decision source.'
    portfolio = _pages()['/portfolio']
    assert 'Automatic arm' in portfolio and 'Approval arm' in portfolio and ARM_HELP['agent_alone'] in portfolio


def test_same_money_same_prices_is_replaced_by_the_accurate_sentence():                             # 30
    for path, html in _pages().items():
        assert 'same money, same prices' not in html.lower() and 'see the same prices' not in html.lower(), path
    for source in DESK.glob('*.py'):
        assert 'same money, same prices' not in source.read_text().lower(), source.name
    assert COMPARE_NOTE == ('Same starting capital and opportunity set. Execution timing and prices can differ because the Approval arm '
                            'waits for an operator decision.')
    assert COMPARE_NOTE in _pages()['/portfolio']


def test_official_as_a_quality_word_is_replaced_and_counting_is_shown_separately():
    from agents.desk.components import category_chips, category_prefix
    from agents.desk.run_category import categorize
    review = {'timestamp': '2026-10-01T14:01:00+00:00', 'data_mode': 'live_readonly', 'status': 'COMPLETED'}
    counted = {'category': categorize(review, {'trigger': 'scheduled'})}
    manual = {'category': categorize(review, {'trigger': 'manual'})}
    assert category_prefix(counted) == '[Registered paper run] '
    assert 'Registered paper run</span>' in category_chips(counted) and 'Counts toward experiment: Yes</span>' in category_chips(counted)
    assert 'Counts toward experiment: No</span>' in category_chips(manual)
    assert '>Official<' not in category_chips(counted) and 'cat-official' not in category_chips(counted)     # no green "validated" chip
    for path, html in _pages().items():
        assert '>Official<' not in html and 'Official run' not in html and 'official run' not in html, path


def test_decision_source_comes_from_the_record_and_is_never_guessed():
    assert decision_source(None) == 'not recorded for this fill'
    assert decision_source({'attribution': 'desk_policy_not_ai', 'author': 'Desk rule (no AI)'}) == 'Desk rule (code, no AI)'
    assert decision_source({'proposal': {'model_name': 'deterministic_not_a_model'}}) == 'Desk rule (code, no AI)'
    assert decision_source({'proposal': {'model_name': 'gpt-5.4-2026-03-05'}}) == 'AI proposal (gpt-5.4-2026-03-05)'
    assert decision_source({'proposal': {}}) == 'not recorded for this fill'


# ---------------------------------------------------------------- 31-34: the truth bar
def test_truth_bar_is_on_every_page():                                                              # 31-34
    bar = truth_bar()
    for label, value in (('Mode', 'PAPER'), ('Strategy evidence', 'NOT PROVEN'), ('Real execution', 'DISABLED'), ('Official options', 'PAUSED')):
        assert f'<small>{label}</small><b>{value}</b>' in bar
    for path, html in _pages().items():
        assert bar in html, path
        assert html.index('<main') < html.index(bar) < html.index('</main>')
    assert bar in shell('Anything', '<p>x</p>', '/', {})              # also without records
    assert 'Lane B · Options (PAUSED)' in Path(DESK / 'portfolio.py').read_text()


def test_truth_bar_and_truthful_names_reach_the_operational_page(tmp_path, monkeypatch):
    from agents.desk.frontdoor import make_server
    import test_dashboard
    monkeypatch.setattr(test_dashboard, 'make_server', make_server)
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        legacy = read(url + '/legacy')
        assert truth_bar() in legacy and legacy.count('class="truth-bar"') == 1
        for phrase in RETIRED:
            assert phrase not in legacy
        assert 'Defined-risk options' not in legacy
        assert 'name="csrf"' in legacy and 'action="/legacy#decisions"' in legacy          # the operational forms are untouched
        lab = read(url + '/firm-lab')
        assert 'NO FILLS' in lab and truth_bar() in lab and 'href="/firm-lab" aria-current="page">Firm Lab</a>' in lab
        assert set(re.findall(r'<form[^>]*action="([^"]+)"', lab)) == {'/ask/question'}     # no Firm Lab action exists
        assert 'href="/firm-lab"' in read(url)


# ---------------------------------------------------------------- 35: the Firm Lab page
def test_firm_lab_page_says_no_fills_before_the_database_exists():                                  # 35
    html = firm_lab_page.render({'firm_lab': view.load(path='/nonexistent/firm_lab.db')})
    assert '<h1>Firm Lab</h1>' in html and '>BUILD / OBSERVE</span>' in html and '>NO FILLS</span>' in html and '>NO FIRM TRADING TRACK RECORD</span>' in html
    assert '<b>Development data only. No Firm trading track record exists.</b>' in html
    assert '<dt>Firm fills</dt><dd><b>0</b>' in html and '<dt>Firm trading trial</dt><dd><b>NOT REGISTERED</b>' in html and 'Trial 18' not in html
    assert 'not created on this machine yet' in html and 'No baseline evaluation is recorded yet.' in html
    assert '70% VTI + 30% 3-month U.S. Treasury-bill total return' in html and '>AUCTION_ACCRUAL_INDEX_V1</span>' in html
    assert 'DEFINITION PENDING' not in html and firm_lab_page.WARNING in html and 'any registered Firm trading trial' in firm_lab_page.WARNING
    assert '<form' not in html and '<button' not in html and '<input' not in html and 'style=' not in html
    assert html == firm_lab_page.render({})                                             # no state at all: same honest page


def test_firm_lab_page_shows_the_recorded_state_and_never_a_trade(tmp_path, capsys):
    off = _official_with_capsule(tmp_path)
    path = tmp_path / 'robinhood-diagnostics' / 'firm_lab' / 'firm_lab.db'
    assert cli.main(['ingest', '--official-database', str(off)]) == 0 and path.is_file()       # default location, beside the runtime
    capsys.readouterr()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    html = firm_lab_page.render({'firm_lab': firm_lab_page.load(off)})
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before                              # rendering writes nothing
    for heading in ('System status', 'Data Readiness', 'Derived measures and strategy components', 'Control A baseline — counterfactual plumbing test',
                    'Benchmarks', 'Development warning'):
        assert f'<h2>{heading}</h2>' in html
    assert html.index('System status') < html.index('Data Readiness') < html.index('counterfactual plumbing test') < html.index('Benchmarks')
    assert '<dt>Mode</dt><dd><b>BUILD / OBSERVE</b></dd>' in html and 'robinhood-diagnostics/firm_lab/firm_lab.db' in html
    assert 'DEVELOPMENT COUNTERFACTUAL — NOT A PAPER TRADE' in html and '>DEVELOPMENT_ONLY</span>' in html
    assert '<dt>Rule would select</dt><dd><b>BBB</b></dd>' in html and '<dt>Exchange session date</dt><dd>2026-09-30</dd>' in html
    assert '<dt>Same selection from the new store</dt><dd><b>Yes</b></dd>' in html
    assert 'Firm strategy' not in html.replace('It is not a Firm strategy', '')
    rows = dict(re.findall(r'<tr><td(?: data-label="Data")?><b>([^<]+)</b></td><td(?: data-label="Capability")?><span class="cat cat-\w+">([^<]+)</span>', html))
    assert rows['Daily closes'] == 'AVAILABLE' and rows['Daily baseline features'] == 'AVAILABLE'      # stored closes that passed validation
    for name in ('Fundamentals', 'Analyst estimates and revisions', 'Intraday 1-minute bars', 'VWAP', 'Time-of-day RVOL', 'Order flow and microstructure',
                 'Options Greeks', 'T-bill total return', 'Corporate actions and dividends', 'Earnings events', 'Earnings transcripts',
                 'VTI total return', '70/30 total-return ruler'):
        assert rows[name] == 'UNAVAILABLE', name
    assert rows['Options strategy'] == 'NOT_STARTED' and rows['ML ranker'] == 'NOT_STARTED' and rows['Options chains'] == 'BUILD_ONLY'
    assert rows['Live quotes and trades'] == rows['General news'] == rows['SEC filings'] == 'PARTIAL_EXISTING'
    assert '<h3>VTI</h3>' in html and 'Fixed benchmark' in html and '<h3>70/30</h3>' in html and '>AUCTION_ACCRUAL_INDEX_V1</span>' in html
    assert '<b>70% VTI + 30% 3-month U.S. Treasury-bill total return</b>' in html and 'No fund, yield series or other asset stands in for the bill' in html
    assert '>APPROVED_AND_FROZEN</span>' in html and '>NOT COMPUTED</span>' in html and 'SHA-256 c954c81b330aa3d4' in html
    assert 'The frozen file is never edited' in html and 'nothing reads them to rank, select or trade' in html
    assert '<dt>Rebalancing</dt><dd>monthly, on the first NYSE trading session of each calendar month; no settlement lag, no transaction cost</dd>' in html
    assert '<dt>Observations stored</dt><dd>0</dd>' in html and 'Trial 18' not in html
    lowered = html.lower()
    for word in ('alpha', 'outperform', 'beat the market', 'bought ', 'paper trade placed', 'profit'):
        # "gross profit" is the name of a reported accounting line in the fundamentals section, not a result of the Firm
        assert word not in lowered.replace('no outperformance figure is reported', '').replace('gross profit', '').replace('gross_profit', ''), word
    assert '<form' not in html and '<button' not in html


def test_firm_lab_page_fails_closed_on_an_unreadable_or_unexpected_database(tmp_path):
    broken = firm_lab_page.render({'firm_lab': {'exists': True, 'error': 'DatabaseError', 'mode': None, 'fills': 0}})
    assert 'could not be read' in broken and 'NO FILLS' in broken and 'System status' in broken and 'Capabilities' not in broken
    odd = firm_lab_page.render({'firm_lab': {**view.load(path='/nonexistent/x.db'), 'exists': True, 'mode': 'REGISTERED_PAPER_TRIAL',
                                             'has_execution_tables': True}})
    assert 'UNEXPECTED (REGISTERED_PAPER_TRIAL)' in odd and 'UNEXPECTED: an execution table exists' in odd


def test_snapshot_carries_firm_lab_state_and_the_shared_mirror_hides_it(tmp_path):
    from agents.desk.mirror import make_server
    from agents.desk.preview import snapshot
    inbox, _ = setup_runtime(tmp_path)
    state = snapshot(inbox.path)
    assert state['firm_lab']['mode'] == 'BUILD_OBSERVE' and state['firm_lab']['fills'] == 0 and state['firm_lab']['exists'] is False
    server = make_server(inbox.path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}'
        page = read(url + '/portfolio')
        assert 'href="/firm-lab"' not in page and truth_bar() in page                    # the shared view still carries the truth bar
        with pytest.raises(HTTPError) as error:
            urlopen(url + '/firm-lab')
        assert error.value.code == 404
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_dashboard_code_reaches_firm_lab_only_through_its_read_only_view():
    for source in DESK.glob('*.py'):
        text = source.read_text()
        for line in text.splitlines():
            if re.match(r'\s*(from|import)\s+firm_lab\b', line):
                assert re.search(r'from firm_lab import view$', line.strip()), (source.name, line)
    page = (DESK / 'firm_lab_page.py').read_text()
    assert 'ExecutionBoundary' not in page and 'FirmLabStore' not in page and 'firm_lab.ingest' not in page and 'boundary' not in page


def test_firm_lab_view_loads_in_the_dashboard_service_where_only_the_agents_package_is_overlaid(tmp_path):
    """The dashboard launcher puts the frozen runtime on the import path and appends only the overlay's ``agents`` folder.
    Found live on the Mac: there ``import firm_lab`` fails, so the page must load that one package from its own folder."""
    import json
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    off = _official_with_capsule(tmp_path)
    assert cli.main(['ingest', '--official-database', str(off)]) == 0
    runtime = tmp_path / 'frozen-runtime'                       # a stand-in runtime: an ``agents`` package and no firm_lab
    (runtime / 'agents').mkdir(parents=True)
    (runtime / 'agents' / '__init__.py').write_text('')
    code = f"""
import json, sys
sys.path[:] = [p for p in sys.path if p not in ('', {str(root)!r})]
sys.path.insert(0, {str(runtime)!r})
import agents
agents.__path__.append({str(root / 'agents')!r})
try:
    import firm_lab
    found_directly = True
except ModuleNotFoundError:
    found_directly = False
before = list(sys.path)
from agents.desk import firm_lab_page
state = firm_lab_page.load({str(off)!r})
html = firm_lab_page.render({{'firm_lab': state}})
trading = sorted(m for m in sys.modules if m.split('.')[0] in ('broker', 'risk', 'data', 'eval', 'research', 'scripts', 'config'))
print(json.dumps({{'found_directly': found_directly, 'path_unchanged': sys.path == before, 'mode': state.get('mode'), 'error': state.get('error'),
                  'selected': (state.get('baseline') or {{}}).get('selected_instrument'), 'no_fills': 'NO FILLS' in html,
                  'firm_lab_modules': sorted(m for m in sys.modules if m.startswith('firm_lab')), 'trading_modules': trading}}))
"""
    env = {k: v for k, v in __import__('os').environ.items() if k != 'PYTHONPATH'}
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=tmp_path, env=env, timeout=60)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result['found_directly'] is False                                           # the situation on the Mac
    assert result['error'] is None and result['mode'] == 'BUILD_OBSERVE' and result['selected'] == 'BBB' and result['no_fills']
    assert result['path_unchanged'] and result['trading_modules'] == []
    assert not {'firm_lab.boundary', 'firm_lab.ingest', 'firm_lab.cli'} & set(result['firm_lab_modules'])   # only the read-only view


def test_every_lane_b_heading_says_paused():
    """Found live on the Mac: the collapsed lane map on Portfolio still headed Lane B 'Defined-risk options'."""
    pages = _pages()
    for path, html in pages.items():
        text = re.sub(r'<[^>]+>', ' ', html)
        assert 'Defined-risk options' not in text.replace('Defined-risk options only', ''), path       # the rule of that name stays in the Rule book
        for heading in re.findall(r'<h[1-4][^>]*>([^<]*Lane B[^<]*)</h[1-4]>', html):
            assert 'PAUSED' in heading.upper(), (path, heading)
    assert '<h3>Options (PAUSED)</h3>' in pages['/portfolio']
    from agents.desk import portfolio
    assert portfolio.LANES['B'] == 'Lane B · Options (PAUSED)' and "('B', 'Options (PAUSED)')" in (DESK / 'lanes.py').read_text()
    assert 'Options screen (Lane B · PAUSED)' in (DESK / 'checks.py').read_text()
