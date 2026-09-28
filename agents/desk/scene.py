"""Vivid, record-backed Decision room. Presentation only; no model/broker calls."""
from datetime import datetime
from .components import esc
from .team import TEAM
from .workspace import date_label, outcome

ACTORS = ('evidence','research','portfolio','critic','risk','final')
ROLES = {'evidence':'Scanners','research':'Research','portfolio':'Portfolio builder',
         'critic':'Critic','risk':'Safety rules','final':'Outcome'}
POINTS = {'evidence':(85,250),'research':(285,110),'portfolio':(495,250),
          'critic':(705,250),'risk':(915,250),'final':(1125,250)}


def handoffs(review, rows):
    """Only explicit, same-run, typed events become graph edges. No aliases."""
    result=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('cycle_id')!=review.get('review_id'): continue
        targets=row.get('to_actors')
        if (row.get('from_actor') not in ACTORS or not isinstance(targets,list) or
            not targets or any(t not in ACTORS for t in targets) or
            not isinstance(row.get('message'),str) or not row['message'].strip() or
            not isinstance(row.get('seq'),int) or isinstance(row['seq'],bool)): continue
        try:
            if datetime.fromisoformat(row['created_at']).tzinfo is None: continue
        except (KeyError,TypeError,ValueError): continue
        result.append({k:row[k] for k in ('seq','from_actor','to_actors','message','created_at')})
    return sorted(result,key=lambda r:(r['seq'],r['created_at']))


def portrait(key, size=120):
    asset=TEAM[key][2]
    if asset: return f'<img src="/assets/avatars/{asset}" alt="" width="{size}" height="{size}">'
    path='M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5M12 12l8-8' if key=='evidence' else 'M5 12l4 4L19 6'
    return f'<svg class="scene-symbol" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="{path}"/></svg>'


def edge(a,b,expected=False):
    x,y=POINTS[a];u,v=POINTS[b]
    direction=1 if u>x else -1
    x+=70*direction;u-=70*direction
    bend=0 if u>x else 65
    data='' if expected else f' data-edge="{a}-{b}"'
    return f'<path class="scene-edge {"edge-expected" if expected else "edge-recorded"}"{data} d="M{x} {y} C{(x+u)/2} {y+bend} {(x+u)/2} {v+bend} {u} {v}"/>'


def items(values,missing):
    if not isinstance(values,list) or not values: return '<p class="desk-muted">'+esc(missing)+'</p>'
    return '<ul>'+''.join('<li>'+esc(v)+'</li>' for v in values if isinstance(v,str))+'</ul>'


def character(stage,index):
    key=stage['key']; name=TEAM[key][0] if key!='final' else 'Your decision'
    panel=f'character-{index}-{key}'
    inspector=stage.get('inspector',{})
    news=stage.get('details',{}).get('news',[])
    news=[row for row in news if isinstance(row,dict) and isinstance(row.get('fact'),str)] if isinstance(news,list) else []
    facts=''.join('<article class="recorded-fact"><p>'+esc(row['fact'])+'</p><dl><dt>Source</dt><dd>'+esc(row.get('source_url') or 'Not recorded')+'</dd><dt>Observed</dt><dd>'+esc(row.get('observed_at') or 'Not recorded')+'</dd></dl><small>Evidence classification not recorded · freshness not assessed</small></article>' for row in news)
    tabs=''.join(f'<button type="button" role="tab" id="{panel}-{tab}-tab" aria-controls="{panel}-{tab}" aria-selected="{str(tab=="work").lower()}" data-character-tab="{tab}">{label}</button>' for tab,label in [('work','Recorded work'),('ask','Ask'),('tune','Tune')])
    found=f'{len(news)} recorded fact(s) below. Classification and freshness are not assessed.' if news else 'Read the original report below. Structured findings are not available in this legacy view.'
    work='<div class="work-columns"><section><h4>Received</h4>'+items(inspector.get('inputs'),'Inputs were not saved.')+'</section><section><h4>Found</h4><p>'+esc(found)+'</p></section><section><h4>Passed on</h4><p>'+esc(inspector.get('handoff') or 'No handoff was saved.')+'</p></section></div>'
    work+='<div class="evidence-grid"><section><h4>'+('Recorded facts' if news else 'Supporting facts')+'</h4>'+(facts or '<p>Structured supporting facts were not saved.</p>')+'</section><section><h4>Contrary facts</h4><p>No structured contrary-fact classification is available in this view.</p></section><section><h4>Missing information</h4>'+items(inspector.get('blockers'),'Missing-information fields were not saved.')+'</section><section><h4>Sources</h4>'+items(inspector.get('sources'),'Source references were not saved.')+'</section></div>'
    work+='<details class="original-report"><summary>Original report</summary><p>'+esc(stage.get('summary') or 'No report was saved.')+'</p></details>'
    ask=f'<div class="ask-intro">{portrait("explainer",64)}<div><h4>Ask Bubbles about {esc(name)}’s work</h4><p>Unavailable until after the Phase 0 gate and the cited-answer service is tested. No model is connected to this preview.</p></div></div><label for="{panel}-question">Your question</label><textarea disabled id="{panel}-question" placeholder="Questions will use only this agent’s saved records for this review."></textarea><button type="button" disabled>Ask unavailable</button>'
    tune='<p>Read-only — editable after Phase 0 via side test. Safety rules stay locked.</p><div class="tune-row"><div><strong>Research depth</strong><p>Current value not loaded. No setting is implied.</p></div><span class="slider-unavailable" role="img" aria-label="Slider unavailable; no current value loaded"></span><span>Unavailable</span></div><div class="tune-row"><strong>Safety limits</strong><span>Locked</span></div><div class="tune-row"><strong>Real orders</strong><span>Blocked in Stage 1</span></div>'
    content=''.join(f'<section role="tabpanel" id="{panel}-{tab}" aria-labelledby="{panel}-{tab}-tab" data-character-pane="{tab}">{body}</section>' for tab,body in [('work',work),('ask',ask),('tune',tune)])
    return f'<details class="scene-character" id="{panel}"><summary>{esc(name)} · {esc(ROLES[key])}</summary><div class="character-layout"><aside>{portrait(key,170)}<h3>{esc(name)}</h3><p>{esc(ROLES[key])}</p><span class="kind-label">{"AI" if key in {"research","portfolio","critic"} else "Rules, not AI" if key=="risk" else "Recorded outcome" if key=="final" else "Deterministic code"}</span><p class="desk-muted">Performance and model details are not available in this preview.</p></aside><div><div role="tablist" aria-label="{esc(name)} details">{tabs}</div>{content}</div></div></details>'


def scene(review,index,rows):
    recorded=handoffs(review,rows)
    stages={s['key']:s for s in review.get('stages',[]) if s.get('key') in ACTORS}
    mode='Recorded handoffs · replay, not live' if recorded else 'Expected workflow · historical six-stage record'
    paths=''.join(edge(a,b) for a,b in sorted({(e['from_actor'],t) for e in recorded for t in e['to_actors']})) if recorded else ''.join(edge(a,b,True) for a,b in zip(ACTORS,ACTORS[1:]))
    nodes=''
    for key in ACTORS:
        stage=stages.get(key,{})
        name=TEAM[key][0] if key!='final' else 'You'
        nodes+=f'<button type="button" class="scene-node node-{key}" data-actor="{key}" data-character="character-{index}-{key}" aria-controls="character-{index}-{key}" aria-expanded="false">{portrait(key)}<strong>{esc(name)}</strong><span>{esc(ROLES[key])}</span><small>{esc(stage.get("status_label","Not recorded"))}</small></button>'
    disabled='' if recorded else ' disabled'
    log=''
    for n,event in enumerate(recorded):
        a=event['from_actor']; names=', '.join(TEAM[t][0] for t in event['to_actors'])
        edges=' '.join(a+'-'+t for t in event['to_actors'])
        log+=f'<li><button type="button" data-handoff-step="{n}" data-handoff-edges="{edges}"><span class="handoff-from">{esc(TEAM[a][0])} → {esc(names)}</span><span class="handoff-message">{esc(event["message"])}</span><time>{esc(date_label(event["created_at"]))}</time></button></li>'
    first=recorded[0] if recorded else None
    message=first['message'] if first else 'No recorded handoff messages. Explore each character’s saved work below.'
    who=(TEAM[first['from_actor']][0]+' → '+', '.join(TEAM[t][0] for t in first['to_actors'])) if first else 'Historical review'
    panels=''.join(character(stages.get(key,{'key':key}),index) for key in ACTORS)
    ideas='<details class="scene-ideas"><summary>Investment ideas</summary>'
    for lane,candidates in review.get('lanes',{}).items():
        ideas+='<h3>'+('Stocks & ETFs' if lane=='A' else 'Options')+'</h3>'
        for candidate in candidates:
            ideas+='<details><summary>'+esc(candidate.get('instrument','Unnamed idea'))+' · '+esc(candidate.get('state','Not recorded'))+'</summary><p>'+esc(candidate.get('reason','Reason not saved'))+'</p></details>'
        if not candidates: ideas+='<p>Individual selection details were not saved.</p>'
    ideas+='</details>'
    return f'''<section class="scene-review" data-scene-review="{index}">
<div class="scene-review-title"><h2>{esc(outcome(review))}</h2><span>{esc(date_label(review.get('timestamp')))}</span></div>
<div class="scene-stage" data-scene><p class="scene-mode">{mode}</p>
<div class="scene-map"><svg viewBox="0 0 1210 440" preserveAspectRatio="none" aria-hidden="true">{paths}</svg>{nodes}</div>
<aside class="scene-bench" aria-label="Future team members"><span>On the bench</span><div>{portrait('filings_news',64)}<p><strong>Biscuit</strong><small>joins in Phase 1</small></p></div><div>{portrait('explainer',64)}<p><strong>Bubbles</strong><small>Ask arrives after the gate</small></p></div></aside>
<div class="scene-speech" aria-live="polite"><span class="speech-who">{esc(who)}</span><p class="speech-message">{esc(message)}</p></div>
<div class="scene-player" aria-label="Recorded handoff player"><button type="button" data-replay="previous"{disabled}>Previous</button><button type="button" data-replay="play"{disabled}>Play</button><button type="button" data-replay="next"{disabled}>Next / Step</button><button type="button" data-replay="all"{disabled}>Show whole path</button><span data-step-label>{'Step 1 of '+str(len(recorded)) if recorded else 'Playback unavailable — handoffs were not recorded'}</span></div>
<details class="scene-log"><summary>Handoff log · {'all recorded ideas in this run' if recorded else 'not recorded'}</summary><ol>{log}</ol></details>
</div>{ideas}<div class="scene-characters">{panels}</div></section>'''


def render(state):
    reviews=state.get('decision_room',[])
    choices=''.join(f'<option value="{i}">{esc(date_label(r.get("timestamp")))}</option>' for i,r in enumerate(reviews))
    html='<div class="scene-heading"><div><h1>Decision room</h1><p>Meet the team. Follow the evidence. See where the decision stopped.</p></div><label>Review <select id="scene-review">'+choices+'</select></label></div>'
    if not reviews: return html+'<p>No saved review yet.</p>'
    return html+''.join(scene(r,i,state.get('handoffs',[])) for i,r in enumerate(reviews))
