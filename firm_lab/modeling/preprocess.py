"""Preprocessing fitted on training rows only, then applied unchanged to whatever is predicted.

Feature choice (by availability), clipping bounds, medians for imputation, and the mean and standard deviation for
scaling are all learned from the training rows passed to ``fit``. ``transform`` only applies them. A test fits on
training rows, changes every validation row, and shows the fitted state does not move.
"""
from __future__ import annotations

import numpy as np

PREPROCESS_VERSION = 'train-only-preprocess-v1'


class Preprocessor:
    def __init__(self, *, minimum_availability=0.10, clip=(1.0, 99.0), indicators=True, scale=True, impute=True):
        self.minimum_availability, self.clip, self.indicators, self.scale, self.impute = minimum_availability, clip, indicators, scale, impute
        self.fitted = False

    def fit(self, X):
        X = np.asarray(X, dtype=float)
        available = np.mean(np.isfinite(X), axis=0) if len(X) else np.zeros(X.shape[1])
        spread = np.array([np.nanstd(X[:, k]) if available[k] > 0 else 0.0 for k in range(X.shape[1])])
        self.keep = np.flatnonzero((available >= self.minimum_availability) & (spread > 0))      # a constant column carries nothing
        kept = X[:, self.keep]
        self.low = np.nanpercentile(kept, self.clip[0], axis=0) if kept.size else np.array([])
        self.high = np.nanpercentile(kept, self.clip[1], axis=0) if kept.size else np.array([])
        clipped = np.clip(kept, self.low, self.high)
        self.median = np.nanmedian(clipped, axis=0) if kept.size else np.array([])
        filled = np.where(np.isfinite(clipped), clipped, self.median)
        self.mean = filled.mean(axis=0) if kept.size else np.array([])
        self.std = filled.std(axis=0) if kept.size else np.array([])
        self.std = np.where(self.std > 0, self.std, 1.0)
        self.flagged = np.flatnonzero(np.mean(np.isfinite(kept), axis=0) < 1.0) if kept.size else np.array([], dtype=int)
        self.fitted = True
        return self

    def transform(self, X):
        if not self.fitted:
            raise ValueError('PREPROCESSOR_NOT_FITTED')
        kept = np.asarray(X, dtype=float)[:, self.keep]
        missing = ~np.isfinite(kept)
        out = np.clip(kept, self.low, self.high)
        if self.impute:
            out = np.where(missing, self.median, out)
        if self.scale:
            out = (out - self.mean) / self.std
        if self.indicators and self.impute and len(self.flagged):
            out = np.hstack([out, missing[:, self.flagged].astype(float)])
        return out

    def names(self, feature_names) -> list:
        kept = [feature_names[k] for k in self.keep]
        return kept + ([kept[k] + '__missing' for k in self.flagged] if self.indicators and self.impute else [])

    def state(self) -> dict:
        return {'version': PREPROCESS_VERSION, 'kept': self.keep.tolist(), 'low': self.low.tolist(), 'high': self.high.tolist(),
                'median': self.median.tolist(), 'mean': self.mean.tolist(), 'std': self.std.tolist(), 'flagged': self.flagged.tolist()}
