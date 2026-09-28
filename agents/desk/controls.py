from .components import card, esc


def render(state):
    if state.get('preview'):
        items=('Pause paper activity','Resume paper activity','Run missed cycle','Start over','Choose trade types','Test notification','Acknowledge account change')
        return '<h1>Controls</h1>'+card('Paper activity','<p>'+('Operator pause marker is present.' if state.get('paused') else 'No operator pause marker is present. This does not prove the cycle is running.')+'</p><p>Preview controls cannot change anything.</p><a class="button" href="http://127.0.0.1:8765/#controls">Open live controls on 8765</a>')+card('Operator controls','<div class="preview-controls">'+''.join(f'<div><strong>{esc(label)}</strong><button disabled aria-disabled="true">View only</button></div>' for label in items)+'</div>')
    action = 'resume' if state.get('paused') else 'pause'
    return '<h1>Controls</h1>'+card('Paper activity', '<p>Existing pause/resume controls remain available. Resume cannot clear a safety incident.</p>'+f'<a class="button" href="/control?action={action}">{action.title()} paper activity</a>')+card('Additional controls', '<p>STOP, learning runs and side tests are scheduled for U5. They are not available here yet.</p>')
