"""Educational lane map, kept separate from historical evidence."""
from .components import esc


def step(title, description, checks):
    return '<details class="lane-step"><summary>'+esc(title)+'<span>Explore</span></summary><div class="lane-expand"><p>'+esc(description)+'</p><ul>'+''.join('<li>'+esc(c)+'</li>' for c in checks)+'</ul><small>Design requirement · not a recorded result</small></div></details>'


def render(state):
    html = '''<section class="lane-atlas" id="lanes"><div class="lane-heading"><div><h2>Two paths. One safety standard.</h2><p>“Lane” means a separate paper experiment — not a transfer of your real money.</p></div></div>
<div class="lane-switch" role="group" aria-label="Lane explanation view"><button type="button" data-lane-mode="guide" aria-pressed="true">How it works</button><button type="button" data-lane-mode="record" aria-pressed="false">Latest saved review</button></div>
<div data-lane-view="guide"><p class="lane-note">Design map, not a live activity feed. Open a step to see what it is meant to check.</p>
<div class="lane-root"><strong>Start with evidence</strong><span>Market data → review existing holdings → consider new ideas</span></div>
<div class="lane-fork"><article class="lane-track lane-a"><header><span class="lane-letter">A</span><div><h3>Shares &amp; ETFs</h3><p>Own a piece of a company, or a basket of investments.</p></div></header><p class="lane-example">Think: company shares or a broad-market fund. No contract expiry.</p>'''
    html += step('Find a suitable investment', 'A symbol is a candidate, not a recommendation.', ['Eligible instrument and strategy', 'Fresh prices and sufficient history', 'Tradable spread and available cash'])
    html += step('Build and challenge the case', 'Research supports a selection; the Critic looks for reasons to reject it.', ['Evidence and sources', 'What would prove the idea wrong?', 'Deterministic strategy rules; AI only where permitted'])
    html += step('Size it safely', 'Code decides how much the paper account can afford.', ['Settled cash and actual holdings', 'Volatility-scaled size and position limits', 'Costs, breakers and an exit plan'])
    html += '''<div class="lane-destination"><strong>Paper proposal, no trade, or blocked</strong><span>No trade is not the same as a technical failure.</span></div></article>
<article class="lane-track lane-b"><header><span class="lane-letter">B</span><div><h3>Defined-risk options</h3><p>A contract with an expiry date and a bounded potential loss.</p></div></header><p class="lane-example">Think: a time-limited contract linked to a stock or ETF. Defined risk ≠ low risk.</p>'''
    html += step('Check the exact contract', 'The underlying ticker alone is not enough.', ['Underlying, call or put, strike and expiry', 'Contract multiplier and exercise / settlement terms', 'Fresh bid and ask, liquidity and earnings timing'])
    html += step('Understand the downside', 'Show maximum loss before considering a proposal.', ['Premium, spread, fees and modeled slippage', 'Time decay and volatility exposure', 'Exit, expiry and assignment handling where applicable'])
    html += step('Pass the options safety gate', 'Missing required contract evidence must stop this lane.', ['Defined maximum loss within limits', 'Cash, concentration and breaker checks', 'A blocked option never becomes a Lane A trade'])
    html += '''<div class="lane-destination"><strong>Paper proposal, no trade, or paused</strong><span>The other lane’s outcome stays separate.</span></div></article></div>
<details class="lane-lab"><summary><span>Strategy testing lab</span><small>Before promotion · explore the checks</small></summary><p>These are the agreed evaluation requirements. This preview does not load test artifacts, so it cannot certify completion.</p><div class="lane-test-grid">'''
    for title, text in [('Historical test', 'Would the registered strategy work on unseen periods, after modeled costs?'), ('Difficult markets', 'Check coverage of 2008, 2020 and 2022. Report actual ticker history and survivorship bias.'), ('Simulated outcomes', 'Block bootstrap and trade reshuffling: chance of beating VTI, drawdowns and loss risk.'), ('Promotion review', 'Compare with no-AI and random arms, then evaluate the registered shadow-mode gates.')]:
        html += '<details><summary>'+esc(title)+'</summary><p>'+esc(text)+'</p><strong>No result loaded</strong></details>'
    html += '</div></details></div><div data-lane-view="record"><h3>Latest saved review</h3>'
    reviews = state.get('decision_room', [])
    if not reviews:
        html += '<p>Not recorded. There is no saved review to inspect.</p>'
    else:
        review = reviews[0]
        html += '<p>'+esc(review.get('timestamp') or 'Time not recorded')+'</p><p>Shared review record — stage evidence below is not proof that each lane passed each check.</p>'
        for stage in review.get('stages', []):
            html += '<details class="lane-step"><summary>'+esc(stage.get('key', 'Stage').replace('_', ' ').title())+'<span>'+esc(stage.get('status_label') or 'Not recorded')+'</span></summary><div class="lane-expand"><h4>Original report</h4><p>'+esc(stage.get('summary') or 'Not recorded')+'</p>'
            for field in ('inputs', 'sources', 'blockers', 'handoff'):
                value = stage.get('inspector', {}).get(field)
                if isinstance(value, list): value = ' · '.join(str(v) for v in value)
                html += '<h4>'+esc(field.title())+'</h4><p>'+esc(value or 'Not recorded')+'</p>'
            html += '</div></details>'
        for lane, title in [('A', 'Shares & ETFs'), ('B', 'Defined-risk options')]:
            html += '<h4>Lane '+lane+' · '+esc(title)+'</h4>'
            rows = review.get('lanes', {}).get(lane, []) if review.get('selection_recorded') else []
            if not rows: html += '<p>Individual selection details not recorded here. No outcome inferred.</p>'
            for row in rows:
                html += '<details class="lane-step"><summary>'+esc(row.get('instrument', 'Candidate'))+'<span>'+esc(row.get('state', 'Not recorded'))+'</span></summary><p>'+esc(row.get('reason') or 'Not recorded')+'</p></details>'
    return html+'</div></section>'
