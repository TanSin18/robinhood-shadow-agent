"""Definitions are registered with their tested calculators, never as availability."""
from .types import FAMILIES, canonical


def validate_definition(definition):
    required = {'name', 'family', 'version', 'required_inputs', 'optional_inputs',
                'unit', 'value_type', 'lookback', 'point_in_time', 'cadence',
                'formula', 'missing_behavior'}
    if not required <= definition.keys() or definition['family'] not in FAMILIES:
        raise ValueError('INVALID_DEFINITION')
    canonical(definition)
    return dict(definition)


def definitions():
    from .technical import technical_definitions
    from .structure import structure_definitions
    from .fibonacci import fibonacci_definitions
    from .ohlcv import ohlcv_definitions
    from .sector import sector_definitions
    return technical_definitions()+structure_definitions()+fibonacci_definitions()+ohlcv_definitions()+sector_definitions()
