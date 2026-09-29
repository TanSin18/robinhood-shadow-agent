from .components import deferred


def render(state):
    if state.get('preview'):
        from .lanes import render as lane_map
        return '<div class="desk-intro"><h1>Portfolio &amp; the two lanes</h1><p>Understand the experiment before following its results.</p></div>'+lane_map(state)+'''
<div class="portfolio-worlds"><section class="insight-hero"><span class="desk-eyebrow">SIMULATED</span><h2>Paper experiment</h2><p>Practice positions and results belong here. This preview does not yet load a verified holdings snapshot.</p><strong class="quiet-status">Holdings not loaded</strong><a class="desk-primary" href="/room">See recorded decisions →</a></section>
<section class="insight-hero broker-world"><span class="desk-eyebrow">REAL ACCOUNT · READ ONLY</span><h2>Broker account</h2><p>Real holdings must come from a verified Agentic account snapshot, never from paper balances.</p><strong class="quiet-status">Not connected in preview</strong><p class="small-note">This preview never contacts the broker. Missing balances are not zero balances.</p></section></div>'''
    return deferred('Portfolio', 'U4')
