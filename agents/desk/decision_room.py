"""Historical six-stage projection, without fabricated idea-level hand-offs."""
from .components import avatar, card, esc


def render(state):
    reviews = state.get('decision_room', [])
    content = '<h1>Decision room</h1><p>Saved public work products. Private chain-of-thought is not recorded.</p>'
    content += '<p class="desk-mode">Historical records · run mode not recorded</p>'
    content += '<p>This run predates idea-by-idea records.</p>'
    content += '<aside class="desk-inactive">'+avatar('filings_news')+'<p>Not active yet: joins when research is split (v1.5.0)</p></aside>'
    if not reviews:
        return content + card('No reviews recorded yet', '<p>Not recorded: there is no saved run to display.</p>')
    picker = '<label for="desk-run">Run</label><select id="desk-run"><option value="">Show all saved runs</option>'
    picker += ''.join(f'<option value="desk-run-{i}">{esc(r.get("timestamp") or r["review_id"])}</option>' for i, r in enumerate(reviews))+'</select>'
    content += picker
    for i, review in enumerate(reviews):
        stages = ''
        for stage in review['stages']:
            key = stage['key']
            fields = ''.join(f'<div><dt>{esc(label.title())}</dt><dd>'+ ('<ul>'+''.join(f'<li>{esc(x)}</li>' for x in value)+'</ul>' if isinstance(value, list) else esc(value))+'</dd></div>' for label, value in stage.get('inspector', {}).items())
            stages += f'<li class="desk-stage" data-desk-stage><details open><summary>{avatar(key)}<span class="desk-chip">{esc(stage["status_label"])}</span></summary><p>{esc(stage["summary"])}</p><dl>{fields}</dl></details></li>'
        selections = ''
        if 'lanes' in review and state.get('preview'):
            selections='<h3>Selections</h3><p>'+('Recorded candidate states are shown below.' if review.get('selection_recorded') else 'Detailed selection states were not recorded for this review.')+'</p>'
            for lane,groups in review['lanes'].items():
                selections+=f'<h4>Lane {esc(lane)}</h4>'
                selections+=(''.join(card(row['instrument'],f'<p>{esc(row["state"])}</p><p>{esc(row["reason"])}</p>') for row in groups)
                             or '<p>No detailed selections recorded.</p>')
        elif 'lanes' in review:
            from agents.dashboard_view import selection_board_view
            selections = selection_board_view(i, review['lanes'], review['proposal_state'], review['selection_recorded']).replace(' hidden', '')
        content += f'<article id="desk-run-{i}" class="desk-run"><h2>{esc(review.get("timestamp") or review["review_id"])}</h2><p>{esc(review.get("outcome", {}).get("reason") or "Not recorded")}</p><ol class="desk-stages">{stages}</ol>{selections}</article>'
    return content
