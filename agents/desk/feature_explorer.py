"""Escaped, neutral research facts. All geometry uses already-stored levels."""
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import json
from urllib.parse import urlencode
from .components import esc

WARNING='RESEARCH FEATURES ONLY — NOT A TRADE SIGNAL'


def _levels(rows):
    levels=[r for r in rows if r['family']=='fibonacci' and r['unit']=='price' and r['value'] is not None]
    if not levels:
        return '<p>No validated close-based Fibonacci levels in this snapshot.</p>'
    try:
        values=[Decimal(r['value']) for r in levels]
        low,high=min(values),max(values)
        if high<=low:
            return '<p>Stored levels have no drawable range; inspect their values below.</p>'
        lines=[]
        for row,value in zip(levels,values):
            y=30+float((high-value)/(high-low))*280
            label=row['name'].removeprefix('close_fib_').replace('_',' ')
            lines.append(f'<line x1="20" x2="300" y1="{y:.2f}" y2="{y:.2f}"/>'
                         f'<text x="310" y="{y+4:.2f}">{esc(label)} · {value:.2f}</text>')
        graph='<svg class="feature-levels" viewBox="0 0 640 345" role="img" aria-label="Stored close-based Fibonacci levels"><title>Stored close-based Fibonacci levels; descriptive projections only</title>'+''.join(lines)+'</svg>'
        anchor=levels[0].get('audit',{})
        anchors='<dl class="v10-facts">'
        for key,label in [('start','Start anchor'),('end','End anchor')]:
            point=anchor.get(key,{})
            anchors+=f'<div><dt>{label}</dt><dd>Close {esc(point.get("value","Not recorded"))} on {esc(point.get("session","Not recorded"))}<br>Confirmed session: {esc(point.get("confirmed_session","Not recorded"))}<br>Known at: {esc(point.get("known_at","Not recorded"))}</dd></div>'
        anchors+='</dl>'
        table='<table><caption>Stored level values — accessible chart alternative</caption><thead><tr><th scope="col">Projection</th><th scope="col">Price</th></tr></thead><tbody>'+''.join(f'<tr><th scope="row">{esc(r["name"])}</th><td>{esc(r["value"])}</td></tr>' for r in levels)+'</tbody></table>'
        return anchors+graph+'<details><summary>Anchors, confirmation times and exact levels</summary>'+table+f'<pre>{esc(json.dumps(anchor,sort_keys=True,indent=2))}</pre></details>'
    except (ValueError,TypeError,InvalidOperation):
        return '<p>Stored level geometry could not be validated; no chart drawn.</p>'


def render_features(view):
    rows=view.get('rows',[])
    selected=view.get('selected',{})
    form=('<form method="get" action="/firm-lab#fl-features" class="feature-filters">'
          f'<label>Instrument<input name="instrument" maxlength="16" value="{esc(selected.get("instrument",""))}" required></label>'
          f'<label>Session<input type="date" name="session" value="{esc(selected.get("session",""))}" required></label>'
          f'<label>Known by (UTC with offset)<input name="known_by" value="{esc(selected.get("knowledge_cutoff",""))}" required></label>'
          '<button type="submit">View stored snapshot</button></form>')
    choices=''.join(f'<li><a href="/firm-lab?{esc(urlencode(dict(instrument=i,session=s,known_by=k)))}#fl-features">{esc(i)} · {esc(s)} · known by {esc(k)}</a></li>' for i,s,k in view.get('choices',[])[:30])
    if not selected and not choices:
        form=''
    out=f'<section class="v10-panel feature-explorer" id="fl-features"><h2>Research feature explorer</h2><p class="feature-warning"><b>{WARNING}</b></p>'
    out+='<p>These are measurements, not predictions. Opening this page only reads stored results; it cannot calculate, trade or change data.</p>'+form
    if choices:
        out+='<details><summary>Recent stored snapshots</summary><ul>'+choices+'</ul></details>'
    if selected:
        out+=f'<p><b>{esc(selected.get("instrument"))}</b> · Session {esc(selected.get("session"))} · Known by {esc(selected.get("knowledge_cutoff"))}</p>'
        if selected.get('knowledge_cutoff','')[:10]>selected.get('session',''):
            out+='<p class="feature-warning">Retrospective snapshot — later-captured data was used. This is not evidence of what was available on the historical session.</p>'
    if view.get('missing_reason'):
        out+=f'<p>No eligible stored results: {esc(view["missing_reason"])}. Generate deliberately with the research-only CLI; this page never fills gaps.</p>'
    if view.get('invalid_rows'):
        out+=f'<p>{esc(view["invalid_rows"])} invalid stored rows excluded. Missing provenance is not availability.</p>'
    families=defaultdict(list)
    for row in rows:
        families[row['family']].append(row)
    if families.get('fibonacci'):
        out+='<details><summary>Close-based swing and Fibonacci map</summary>'+_levels(families['fibonacci'])+'</details>'
    for family,items in sorted(families.items()):
        available=sum(r['availability']=='AVAILABLE' for r in items)
        out+=f'<details class="feature-family"><summary>{esc(family.replace("_"," ").capitalize())} — {available} of {len(items)} recorded values</summary><dl>'
        for row in items:
            value=json.dumps(row['value'],sort_keys=True) if isinstance(row['value'],(dict,bool)) else row['value']
            out+=f'<div class="feature-row"><dt>{esc(row["name"])}</dt><dd><b>{esc(value if value is not None else "Unavailable")}</b> · {esc(row["unit"])}'
            if row.get('missing_reason'):
                out+=f'<p>{esc(row["missing_reason"])}</p>'
            out+='<details><summary>Evidence and calculation details</summary><dl class="v10-facts">'
            for title,key in [('Known at','known_at'),('Computed at','computed_at'),('Definition version','feature_version'),('Calculation hash','calculation_hash')]:
                out+=f'<div><dt>{title}</dt><dd>{esc(row.get(key) or "Not recorded")}</dd></div>'
            out+='</dl><h4>Source references</h4><ul>'
            for ref in row.get('refs',[]):
                out+=f'<li>{esc(ref["table"])} · row {esc(ref["row_id"])} · known {esc(ref["known_at"])}<br>Content hash: {esc(ref["content_hash"])}</li>'
            out+=f'</ul><pre>{esc(json.dumps(row.get("audit",{}),sort_keys=True,indent=2))}</pre></details></dd></div>'
        out+='</dl></details>'
    return out+'</section>'
