"""Build the system walkthrough outside the dashboard from agents/desk/guide_content.py.

    python scripts/build_walkthrough.py --md docs/SYSTEM_WALKTHROUGH.md --html <file.html>

The Markdown goes to GitHub; the HTML is a standalone, shareable page with the same
content, diagram and demo as the dashboard's /guide.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.desk import guide_content as C  # noqa: E402
from agents.desk.guide import body  # noqa: E402

TOKENS = """
:root{--bg:#f5f6f8;--card:#ffffff;--border:#d8dce4;--text:#141922;--text-3:#545e6e;--cyan:#1f66a3;--violet:#6347c2;--amber:#9a5c08;--ok:#2b7a2f}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#101319;--card:#191e27;--border:#343d4c;--text:#f4f3ef;--text-3:#bac3d2;--cyan:#a5d9d0;--violet:#c6b7f3;--amber:#edca91;--ok:#7fd6b0;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#101319;--card:#191e27;--border:#343d4c;--text:#f4f3ef;--text-3:#bac3d2;--cyan:#a5d9d0;--violet:#c6b7f3;--amber:#edca91;--ok:#7fd6b0;color-scheme:dark}
body{background:var(--bg);color:var(--text);font-family:Geist,system-ui,-apple-system,'Segoe UI',sans-serif;font-size:15px;line-height:1.6}
.gd-page{max-width:1180px;margin:0 auto;padding-inline:16px;padding-block:28px 56px}
.gd-foot{margin-top:40px;font-size:13px;color:var(--text-3)}
"""


def html_page():
    css = (ROOT / 'agents/static/guide.css').read_text()
    js = (ROOT / 'agents/static/guide.js').read_text()
    return ('<title>Agent Desk Walkthrough</title>\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&display=swap">\n'
            f'<style>{TOKENS}\n{css}</style>\n<div class="gd-page">{body()}'
            '<p class="gd-foot">Generated from agents/desk/guide_content.py, the same source as the dashboard page /guide '
            'and docs/SYSTEM_WALKTHROUGH.md. Paper trading only; real orders are blocked.</p></div>\n'
            f'<script>{js}</script>\n')


def markdown():
    out = [f'# {C.INTRO["title"]}: the Agent Desk', '',
           f'_Generated from `agents/desk/guide_content.py` (same source as the dashboard page **How it works**, `/guide`). '
           f'Rules as of {C.AS_OF}._', '', C.INTRO['lede'], '']
    out += [f'- **{k}:** {v}' for k, v in C.INTRO['facts']]
    out += ['', '## The daily flow', '', '```mermaid', 'flowchart LR']
    for key, title, sub, kind in C.FLOW:
        shape = ('{{"%s<br/><small>%s</small>"}}' if kind == 'gate' else '["%s<br/><small>%s</small>"]') % (title, sub)
        out.append(f'  {key}{shape}')
    out += ['  read --> signals --> gate', '  gate -- "stock signal or holding" --> ai', '  gate -- "ETF signal" --> desk',
            '  ai --> risk', '  desk --> risk', '  risk --> arms --> exits --> score', '```', '',
            '## Step by step', '']
    for i, s in enumerate(C.STEPS, 1):
        out += [f'### {i}. {s["title"]}  ·  decided by: {s["who"]}', '', s['plain'], '', '**Checks at this step**', '']
        out += [f'- {c}' for c in s['checks']]
        out += ['', f'**Thursday example:** {s["example"]}', '', f'**For traders:** {s["trader"]}', '']
    out += ['## A day on the desk (ET)', '', '| When | What |', '|---|---|']
    out += [f'| {t} | {d} |' for t, d in C.TIMELINE]
    out += ['', '## What it trades, and how it sells', '', '| Asset | How it buys | How it sells | Status |', '|---|---|---|---|']
    out += [f'| {a} | {b} | {s} | {st} |' for a, b, s, st in C.ASSETS]
    out += ['', '## What a trader should challenge', '']
    out += [f'- {c}' for c in C.CHALLENGES]
    out += ['', '## Glossary', '']
    out += [f'- **{k}:** {v}' for k, v in C.GLOSSARY]
    out += ['', '---', 'Paper trading only. Real orders are blocked. Code references: `agents/daily_cycle.py` (run), '
            '`research/strategy_signals.py` (rules), `agents/budget.py` (AI gate), `risk/engine.py` (risk checks), '
            '`agents/etf_issuer.py` (ETF desk rule), `agents/etf_exit.py` + `agents/v16_policy.py` (selling), '
            '`agents/inbox.py` (paper accounts, cards, settlement), `eval/promotion_stats.py` (scorekeeping).', '']
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--md')
    parser.add_argument('--html')
    args = parser.parse_args()
    if args.md:
        Path(args.md).write_text(markdown())
    if args.html:
        Path(args.html).write_text(html_page())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
