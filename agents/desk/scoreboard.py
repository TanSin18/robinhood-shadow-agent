from .components import deferred


def render(state):
    return deferred('Is the AI working?', 'U4')
