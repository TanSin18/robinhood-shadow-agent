from . import today, decision_room, portfolio, money, scoreboard, controls, health, checks, guide, inbox_page, firm_page, rulebook, architecture
from .components import ROUTES, shell

SCREENS = {'/room': decision_room, '/checks': checks, '/portfolio': portfolio, '/money': money,
           '/scoreboard': scoreboard, '/controls': controls, '/health': health, '/guide': guide, '/inbox': inbox_page, '/firm': firm_page,
           '/rules': rulebook, '/architecture': architecture}


def render(path, state, config, csrf, filters=None):
    if state.get('preview') and path == '/room':
        from .scene import render as scene
        return shell(dict(ROUTES)[path], scene(state), path, state)
    if state.get('preview') and path == '/':
        from .workspace import render as workspace
        return shell(dict(ROUTES)[path], workspace(state), path, state)
    body = today.render(state, config, csrf, filters) if path == '/' else SCREENS[path].render(state)
    return shell(dict(ROUTES)[path], body, path, state)
