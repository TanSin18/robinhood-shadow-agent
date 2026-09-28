"""Render stored approval data without importing writable inbox components."""
from .components import esc

def preview_card(card):
    p=card.get('proposal',{})
    fields=(('Lane',card.get('lane','Not recorded')),('Quantity',p.get('quantity','Not recorded')),
            ('Recorded limit',p.get('limit_price','Not recorded')),('Good if',p.get('good_if','Not recorded')),
            ('Reconsider if',p.get('invalidation','Not recorded')),('Critic',p.get('critic_counterargument','Not recorded')))
    details=''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k,v in fields)
    return f'<article class="proposal" data-preview-expires="{esc(card.get("expires",""))}"><h3>{esc(p.get("side",""))} {esc(p.get("ticker","Not recorded"))}</h3><span class="desk-chip" data-card-status>{esc(card["status"])}</span><p>{esc(p.get("thesis","Not recorded"))}</p><dl class="conditions">{details}</dl><p data-expiry-label>{esc(card["expiry_label"])}</p><p>View only — approval and rejection are disabled.</p></article>'
