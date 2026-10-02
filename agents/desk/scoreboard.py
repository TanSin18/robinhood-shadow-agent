from .components import deferred


def render(state):
    if state.get('preview'):
        return '''<div class="desk-intro"><span class="desk-eyebrow">THE EXPERIMENT</span>
<h1>Is the AI working?</h1><p>A good story isn’t enough. The team has to earn its place.</p></div>
<section class="insight-hero"><span class="desk-eyebrow">THE HONEST ANSWER</span>
<h2>Too early to tell.</h2><p>Performance records aren’t connected to this preview. A completed review is evidence of work — not evidence of profit.</p>
<a class="desk-primary" href="/room">Explore the team’s work <span aria-hidden="true">→</span></a></section>
<div class="metric-row"><section><span>Return after costs</span><strong>Not measured</strong><small>No return series available here</small></section>
<section><span>Value added by AI</span><strong>Not measured</strong><small>Requires a matched no-AI comparison</small></section>
<section><span>Cost of intelligence</span><strong>Not measured</strong><small>No verified cost aggregate loaded</small></section></div>
<section class="comparison-board"><div><span class="desk-eyebrow">WHAT WILL COUNT</span><h2>One fair comparison.</h2><p>Same starting conditions. Costs kept visible.</p></div>
<dl><div><dt>Automatic arm</dt><dd>Does the team’s selection add value after its costs?</dd></div>
<div><dt>Approval arm</dt><dd>How do your choices change the result?</dd></div>
<div><dt>No-AI & random</dt><dd>Does intelligence beat a simpler selection rule?</dd></div>
<div><dt>VTI & cash</dt><dd>The reference points. Agent API costs do not belong here.</dd></div></dl></section>
<details class="desk-method"><summary>Why aren’t there charts yet?</summary><p>This view does not load verified performance series. Drawing a curve now would imply results we cannot support. These are evaluation goals, not claims that every comparison is implemented.</p></details>'''
    return deferred('Is the AI working?', 'U4')
