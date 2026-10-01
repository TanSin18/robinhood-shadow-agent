"""Book C: the matched random control. Same day, same notional fraction, same exit day as its book-A
trade; only the ticker is random, drawn with a seed fixed in the spec so a bad draw can't be re-rolled."""
from __future__ import annotations

import hashlib
import random


def draw(spec, ticket_id: str, eligible):
    pool = sorted(eligible)
    if not pool:
        return None
    seed = int(hashlib.sha256(f'{spec.seed}:{ticket_id}'.encode()).hexdigest(), 16)
    return random.Random(seed).choice(pool)
