"""How it works: a plain-language and trader-level walkthrough of the whole system.

Static content from guide_content (no records needed), so the page renders even
when the database is unavailable. Markup only; styling in /assets/guide.css and
the demo stepper in /assets/guide.js (strict CSP: no inline style or script).
"""
from html import escape

from . import guide_content as C

# Diagram geometry (SVG user units). Colour and motion live in CSS.
W, H = 150, 62
POS = {'read': (10, 104), 'signals': (190, 104), 'gate': (370, 104), 'ai': (550, 24), 'desk': (550, 184),
       'risk': (740, 104), 'arms': (920, 104), 'exits': (1100, 104), 'score': (1280, 104)}
EDGES = [('read', 'signals', ''), ('signals', 'gate', ''), ('gate', 'ai', 'stock signal or holding'),
         ('gate', 'desk', 'ETF signal'), ('ai', 'risk', ''), ('desk', 'risk', ''), ('risk', 'arms', ''),
         ('arms', 'exits', ''), ('exits', 'score', '')]


def esc(value):
    return escape(str(value), quote=True)


def _anchor(node, side):
    x, y = POS[node]
    if side == 'out':
        return x + W, y + H / 2
    return x, y + H / 2


def diagram():
    kinds = {n[0]: n[3] for n in C.FLOW}
    parts = ['<svg class="gd-svg" viewBox="0 0 1440 272" role="img" aria-labelledby="gd-svg-title">',
             '<title id="gd-svg-title">Daily flow: read the market, rules find signals, the AI gate sends stock ideas to '
             'the AI team and ETF ideas to the desk rule, both go through risk checks into three paper accounts, then '
             'selling and scorekeeping.</title>',
             '<defs><marker id="gd-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
             'orient="auto-start-reverse"><path class="gd-arrowhead" d="M0 0L10 5L0 10z"/></marker></defs>']
    for a, b, label in EDGES:
        x1, y1 = _anchor(a, 'out')
        x2, y2 = _anchor(b, 'in')
        mid = (x1 + x2) / 2
        parts.append(f'<path class="gd-edge" data-from="{a}" data-to="{b}" d="M{x1:.0f} {y1:.0f} C{mid:.0f} {y1:.0f} '
                     f'{mid:.0f} {y2:.0f} {x2 - 2:.0f} {y2:.0f}" marker-end="url(#gd-arrow)"/>')
        if label:   # labels sit above/below the gate so no node covers them
            gx, gy = POS[a]
            ly = gy - 18 if y2 < y1 else gy + H + 28
            parts.append(f'<text class="gd-edge-label" x="{gx + W / 2:.0f}" y="{ly:.0f}">{esc(label)}</text>')
    for key, title, sub, kind in C.FLOW:
        x, y = POS[key]
        shape = (f'<rect class="gd-node-box" x="{x}" y="{y}" width="{W}" height="{H}" rx="12"/>' if kind != 'gate' else
                 f'<path class="gd-node-box" d="M{x + W / 2} {y - 8} L{x + W} {y + H / 2} L{x + W / 2} {y + H + 8} L{x} {y + H / 2}z"/>')
        parts.append(f'<a class="gd-node gd-kind-{kind}" data-step="{key}" href="#step-{key}">{shape}'
                     f'<text class="gd-node-title" x="{x + W / 2}" y="{y + 27}">{esc(title)}</text>'
                     f'<text class="gd-node-sub" x="{x + W / 2}" y="{y + 45}">{esc(sub)}</text></a>')
    parts.append('</svg>')
    return ''.join(parts)


def _step(i, step):
    checks = ''.join(f'<li>{esc(c)}</li>' for c in step['checks'])
    who = esc(step['who'])
    return (f'<li class="gd-step" id="step-{esc(step["id"])}" data-step="{esc(step["id"])}">'
            f'<div class="gd-step-head"><span class="gd-num">{i}</span><h3>{esc(step["title"])}</h3>'
            f'<span class="gd-who gd-who-{esc(step["who"].split()[0].lower())}">Decided by: {who}</span></div>'
            f'<p class="gd-plain">{esc(step["plain"])}</p>'
            f'<h4>Checks at this step</h4><ul class="gd-checks">{checks}</ul>'
            f'<p class="gd-example"><strong>Thursday example</strong> {esc(step["example"])}</p>'
            f'<details class="gd-trader"><summary>For traders: exact rules</summary><p>{esc(step["trader"])}</p></details>'
            '</li>')


def body():
    facts = ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in C.INTRO['facts'])
    steps = ''.join(_step(i, s) for i, s in enumerate(C.STEPS, 1))
    timeline = ''.join(f'<tr><th scope="row">{esc(t)}</th><td>{esc(d)}</td></tr>' for t, d in C.TIMELINE)
    assets = ''.join(f'<tr><th scope="row">{esc(a)}</th><td>{esc(b)}</td><td>{esc(s)}</td><td>{esc(st)}</td></tr>'
                     for a, b, s, st in C.ASSETS)
    challenges = ''.join(f'<li>{esc(c)}</li>' for c in C.CHALLENGES)
    glossary = ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in C.GLOSSARY)
    return f'''<div class="gd" data-detail="plain">
<header class="gd-hero"><p class="gd-eyebrow">System walkthrough · rules as of {esc(C.AS_OF)}</p>
<h1>{esc(C.INTRO["title"])}</h1><p class="gd-lede">{esc(C.INTRO["lede"])}</p><dl class="gd-facts">{facts}</dl></header>
<section class="gd-section" aria-labelledby="gd-flow-h"><div class="gd-section-head"><h2 id="gd-flow-h">The daily flow</h2>
<p>Click a box to jump to its step, or play the demo to walk through Thursday's first official run.</p></div>
<div class="gd-demo"><button type="button" class="gd-btn" data-demo="prev">Previous</button>
<button type="button" class="gd-btn gd-btn-main" data-demo="play">Play demo</button>
<button type="button" class="gd-btn" data-demo="next">Next</button>
<button type="button" class="gd-btn gd-btn-quiet" data-demo="detail" aria-pressed="false">Show trader detail</button>
<span class="gd-demo-status" aria-live="polite"></span></div>
<div class="gd-diagram">{diagram()}</div>
<p class="gd-legend"><span class="gd-key gd-kind-code">Written rules (code)</span><span class="gd-key gd-kind-gate">Decision point</span>
<span class="gd-key gd-kind-ai">AI models</span><span class="gd-key gd-kind-you">Involves you</span></p></section>
<section class="gd-section" aria-labelledby="gd-steps-h"><div class="gd-section-head"><h2 id="gd-steps-h">Step by step</h2>
<p>Each step says what happens in plain words, every check it runs, who decides, and what it means on Thursday. Open "For traders" for the exact rule.</p></div>
<ol class="gd-steps">{steps}</ol></section>
<section class="gd-section gd-two" aria-label="Schedule and coverage"><div><h2>A day on the desk (ET)</h2>
<div class="gd-table"><table><tbody>{timeline}</tbody></table></div></div>
<div><h2>What it trades, and how it sells</h2><div class="gd-table"><table><thead><tr><th>Asset</th><th>How it buys</th><th>How it sells</th><th>Status</th></tr></thead>
<tbody>{assets}</tbody></table></div></div></section>
<section class="gd-section" aria-labelledby="gd-ch-h"><div class="gd-section-head"><h2 id="gd-ch-h">What a trader should challenge</h2>
<p>Known weaknesses, stated plainly so a reviewer can start here.</p></div><ul class="gd-challenges">{challenges}</ul></section>
<section class="gd-section" aria-labelledby="gd-gl-h"><h2 id="gd-gl-h">Glossary</h2><dl class="gd-glossary">{glossary}</dl></section>
</div>'''


def render(state=None):
    return body()
