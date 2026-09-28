from .components import deferred, card


def render(state):
    if state.get('preview'):
        return '<h1>Road to real money</h1><p>A visible path, not a promise of profit. Real orders remain blocked.</p>'+card('Paper first. Evidence before real money.', '<ol class="money-road"><li><strong>Phase 0</strong><p>Prove the installed daily cycle. Not assessed by this preview.</p></li><li><strong>Paper experiment</strong><p>Compare recorded results against the no-AI arm and benchmarks.</p></li><li><strong>Independent review</strong><p>Check after-cost results, risk, calibration and sample size.</p></li><li><strong>Operator decision</strong><p>No automatic promotion or broker execution.</p></li></ol>')+card('Is the AI paying for itself?', '<p>Not assessed. Comparable official-arm results are not loaded here.</p>')+card('Hits, misses & lessons','<p>Resolved candidate outcomes and lessons are not available in this preview. No scores or gains are inferred.</p>')
    return deferred('Road to money', 'U4')
