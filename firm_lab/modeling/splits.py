"""Chronological validation: expanding walk-forward folds, purged, with an untouched final holdout.

There is no random split anywhere. Sessions are the unit of time; every instrument of a session goes to the same side.

Purge. A training sample at session t has a label that looks ahead ``horizon`` sessions. It may be used for a validation
block that starts at session v0 only if its label window has closed before the block begins: t + horizon < v0.

Embargo. A sample that comes after a validation block shares lookback history with the block's labels. It may be used
for training only after the last validation label has closed and a further ``embargo`` sessions have passed:
t > v1 + horizon + embargo. In the expanding walk-forward used by the tournament nothing later than a block is ever
trained on for that block, so the embargo acts where it matters: between the development period and the final holdout,
and between an inner tuning block and whatever follows it.

Final holdout. The last part of the labelled period. Nothing is tuned or selected on it; it is read once, at the end.
"""
from __future__ import annotations

from dataclasses import dataclass

SPLIT_VERSION = 'expanding-walk-forward-purged-v1'


@dataclass(frozen=True)
class Block:
    name: str
    train: tuple            # session indices allowed for training
    validation: tuple       # session indices predicted
    purged: tuple           # session indices before the block removed because their labels overlap it

    def as_dict(self, sessions=None) -> dict:
        def span(indices):
            return None if not indices else ([sessions[indices[0]], sessions[indices[-1]]] if sessions else [indices[0], indices[-1]])
        return {'name': self.name, 'train': span(self.train), 'train_sessions': len(self.train), 'validation': span(self.validation),
                'validation_sessions': len(self.validation), 'purged': span(self.purged), 'purged_sessions': len(self.purged)}


def may_train(t, v0, v1, *, horizon, embargo) -> bool:
    """Whether a sample at session index t may train a model that is validated on sessions v0..v1."""
    return t + horizon < v0 or t > v1 + horizon + embargo


def block(name, candidates, v0, v1, *, horizon, embargo, past_only=True) -> Block:
    train = tuple(t for t in candidates if may_train(t, v0, v1, horizon=horizon, embargo=embargo) and (not past_only or t < v0))
    purged = tuple(t for t in candidates if t < v0 and not may_train(t, v0, v1, horizon=horizon, embargo=embargo))
    return Block(name, train, tuple(range(v0, v1 + 1)), purged)


def walk_forward(first, last, *, horizon, embargo, folds=5, minimum_train=80, holdout_fraction=0.2, minimum_block=10) -> dict:
    """Fold and holdout definitions over the labelled session indices ``first``..``last`` (inclusive).

    The holdout is the final ``holdout_fraction`` of the labelled sessions. The development period ends where the purge
    and the embargo before the holdout begin. The first ``minimum_train`` development sessions are training only; the
    rest is cut into ``folds`` consecutive validation blocks, each predicted by a model trained on the purged past."""
    labelled = last - first + 1
    holdout_size = max(minimum_block, int(round(labelled * holdout_fraction)))
    holdout_start = last - holdout_size + 1
    development_end = holdout_start - horizon - embargo - 1          # the last development session whose use cannot touch the holdout
    available = development_end - first + 1 - minimum_train
    if available < folds * minimum_block:
        raise ValueError('INSUFFICIENT_SESSIONS_FOR_WALK_FORWARD')
    size, extra = divmod(available, folds)
    blocks, start = [], first + minimum_train
    development = range(first, development_end + 1)
    for k in range(folds):
        end = start + size - 1 + (1 if k < extra else 0)
        blocks.append(block(f'fold_{k + 1}', development, start, end, horizon=horizon, embargo=embargo))
        start = end + 1
    holdout = block('final_holdout', development, holdout_start, last, horizon=horizon, embargo=embargo)
    return {'version': SPLIT_VERSION, 'horizon': horizon, 'embargo': embargo, 'first': first, 'last': last, 'folds': blocks, 'holdout': holdout,
            'development_end': development_end, 'holdout_start': holdout_start,
            'gap_before_holdout': holdout_start - development_end - 1}


def inner(train, *, horizon, embargo, fraction=0.25, minimum_block=10) -> Block:
    """A tuning block inside a training window: its last part is predicted by a model trained on the purged earlier part.
    Used to choose a configuration without looking at the outer validation block."""
    train = tuple(sorted(train))
    size = max(minimum_block, int(round(len(train) * fraction)))
    if len(train) - size - horizon < minimum_block:
        raise ValueError('INSUFFICIENT_SESSIONS_FOR_INNER_SPLIT')
    v0, v1 = train[-size], train[-1]
    return block('inner', train, v0, v1, horizon=horizon, embargo=embargo)


def check(definition) -> list:
    """Reasons the definition is not a valid chronological design; empty when it is. Used by tests and before every run."""
    problems, horizon, embargo = [], definition['horizon'], definition['embargo']
    blocks = list(definition['folds']) + [definition['holdout']]
    for b in blocks:
        if not b.train or not b.validation:
            problems.append(f'{b.name}: empty side')
            continue
        if max(b.train) + horizon >= min(b.validation):
            problems.append(f'{b.name}: a training label window reaches the validation block')
        if set(b.train) & set(b.validation):
            problems.append(f'{b.name}: a session is on both sides')
        if any(t > max(b.validation) for t in b.train):
            problems.append(f'{b.name}: trained on the future')
    for earlier, later in zip(blocks, blocks[1:]):
        if max(earlier.validation) >= min(later.validation):
            problems.append(f'{earlier.name}/{later.name}: validation blocks are not in time order')
    holdout = definition['holdout']
    for b in definition['folds']:
        if max(b.validation) + horizon + embargo >= min(holdout.validation):
            problems.append(f'{b.name}: too close to the final holdout')
    return problems
