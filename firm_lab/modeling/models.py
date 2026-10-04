"""Model families A to C: naive baselines, linear models and boosted trees. One small interface for all of them.

A model is given training rows and returns numbers for other rows. It never sees a label of a row it predicts, and its
preprocessing is fitted on its own training rows (``preprocess``). No model here outputs an action: a regression
returns a predicted excess return, a classifier a probability, a quantile model a quantile.

Search spaces are small and written down here, before any result exists. Every configuration that is tried is recorded
by the tournament; none is added after looking at an outcome.
"""
from __future__ import annotations

import importlib

import numpy as np

from .preprocess import Preprocessor

REGRESSION, CLASSIFICATION, QUANTILE = 'regression', 'classification', 'quantile'


def available(module) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def versions() -> dict:
    out = {}
    for module in ('numpy', 'sklearn', 'xgboost', 'lightgbm', 'catboost', 'torch'):
        try:
            out[module] = importlib.import_module(module).__version__
        except Exception:
            out[module] = None
    return out


class Model:
    """``fit(X, y, context)`` then ``predict(X, context)``. ``context`` carries the row's instrument index and the raw
    feature names, for the few baselines that need them."""
    family = 'A_baseline'
    kind = REGRESSION
    requires = ()                       # importable modules the model needs
    preprocess = None                   # keyword arguments for Preprocessor, or None when the model reads raw columns
    parameter_count = 0

    def __init__(self, **params):
        self.params = dict(params)

    def fit(self, X, y, context):
        raise NotImplementedError

    def predict(self, X, context):
        raise NotImplementedError

    def describe(self) -> dict:
        return {}

    # shared: train-only preprocessing
    def _prepare(self, X, fit=False):
        if self.preprocess is None:
            return X
        if fit:
            self.pre = Preprocessor(**self.preprocess).fit(X)
        return self.pre.transform(X)

    # shared: a model left with no usable descriptor after the train-only filter predicts its training mean, and says so
    def _without_inputs(self, Z, y) -> bool:
        if Z.shape[-1] > 0:
            self.constant = None
            return False
        y = np.asarray(y, dtype=float)
        self.constant = float(np.clip(np.nanmean(y), 0.01, 0.99)) if self.kind == CLASSIFICATION else (
            float(np.nanquantile(y, self.params['quantile'])) if self.kind == QUANTILE else float(np.nanmean(y)))
        self.parameter_count = 0
        return True

    def _constant(self, X):
        return np.full(len(X), self.constant)


# ---------------------------------------------------------------------------- family A: naive baselines
class Zero(Model):
    """Predicts no excess return for anything. The forecast every later model has to do better than."""

    def fit(self, X, y, context):
        return self

    def predict(self, X, context):
        return np.zeros(len(X))


class HistoricalMean(Model):
    """The mean of the training targets, for everything."""

    def fit(self, X, y, context):
        self.mean = float(np.mean(y))
        return self

    def predict(self, X, context):
        return np.full(len(X), self.mean)


class InstrumentMean(Model):
    """Each instrument's own mean training target; the overall mean for an instrument not seen in training."""

    def fit(self, X, y, context):
        self.overall = float(np.mean(y))
        self.by = {int(i): float(np.mean(y[context['instrument'] == i])) for i in np.unique(context['instrument'])}
        return self

    def predict(self, X, context):
        return np.array([self.by.get(int(i), self.overall) for i in context['instrument']])


class SingleFeature(Model):
    """One descriptor, scaled to the target by a one-variable least-squares line fitted on training rows. With
    ``gate`` the descriptor counts only where the gate descriptor is above zero (the registered-style rule: momentum
    among names above their 200-session average); elsewhere the prediction is the intercept."""

    def fit(self, X, y, context):
        x = self._column(X, context)
        keep = np.isfinite(x)
        self.intercept = float(np.mean(y))
        self.slope = 0.0
        if keep.sum() >= 10 and np.std(x[keep]) > 0:
            self.slope = float(np.cov(x[keep], y[keep])[0, 1] / np.var(x[keep], ddof=1))
            self.intercept = float(np.mean(y[keep]) - self.slope * np.mean(x[keep]))
            self.fallback = float(np.mean(y[~keep])) if (~keep).any() else float(np.mean(y))
        else:
            self.fallback = self.intercept
        return self

    def _column(self, X, context):
        names = context['feature_names']
        x = X[:, names.index(self.params['feature'])].astype(float).copy()
        gate = self.params.get('gate')
        if gate:
            g = X[:, names.index(gate)]
            x[~(g > 0)] = np.nan
        return x

    def predict(self, X, context):
        x = self._column(X, context)
        return np.where(np.isfinite(x), self.intercept + self.slope * x, self.fallback)

    def describe(self):
        return {'slope': self.slope, 'intercept': self.intercept}


class BaseRate(Model):
    """The training share of positive outcomes, as the probability for everything."""
    kind = CLASSIFICATION

    def fit(self, X, y, context):
        self.rate = float(np.clip(np.mean(y), 0.01, 0.99))
        return self

    def predict(self, X, context):
        return np.full(len(X), self.rate)


class TrainQuantile(Model):
    """The training quantile of the target, for everything: the unconditional distribution."""
    kind = QUANTILE

    def fit(self, X, y, context):
        self.value = float(np.quantile(y, self.params['quantile']))
        return self

    def predict(self, X, context):
        return np.full(len(X), self.value)


# ---------------------------------------------------------------------------- family B: linear models
class Ridge(Model):
    family = 'B_linear'
    preprocess = {}

    def fit(self, X, y, context):
        Z = self._prepare(X, fit=True)
        self.intercept = float(np.mean(y))
        gram = Z.T @ Z + float(self.params.get('alpha', 1.0)) * np.eye(Z.shape[1])
        self.coefficients = np.linalg.solve(gram, Z.T @ (y - self.intercept)) if Z.shape[1] else np.zeros(0)
        self.parameter_count = int(Z.shape[1] + 1)
        return self

    def predict(self, X, context):
        return self.intercept + self._prepare(X) @ self.coefficients

class LeastSquares(Ridge):
    """Ordinary least squares on a deliberately small set of descriptors (a tiny ridge term keeps it solvable)."""

    def __init__(self, **params):
        super().__init__(**{**params, 'alpha': 1e-6})


class ElasticNet(Model):
    family = 'B_linear'
    requires = ('sklearn',)
    preprocess = {}

    def fit(self, X, y, context):
        from sklearn.linear_model import ElasticNet as SkElasticNet
        Z = self._prepare(X, fit=True)
        if self._without_inputs(Z, y):
            return self
        self.model = SkElasticNet(alpha=self.params.get('alpha', 0.001), l1_ratio=self.params.get('l1_ratio', 0.5), max_iter=5000,
                                  random_state=context.get('seed', 0)).fit(Z, y)
        self.coefficients = self.model.coef_
        self.parameter_count = int(np.count_nonzero(self.model.coef_) + 1)
        return self

    def predict(self, X, context):
        return self._constant(X) if self.constant is not None else self.model.predict(self._prepare(X))


class Logistic(Model):
    family = 'B_linear'
    kind = CLASSIFICATION
    requires = ('sklearn',)
    preprocess = {}

    def fit(self, X, y, context):
        from sklearn.linear_model import LogisticRegression
        Z = self._prepare(X, fit=True)
        if self._without_inputs(Z, y):
            return self
        self.model = LogisticRegression(C=self.params.get('C', 0.1), max_iter=2000).fit(Z, y.astype(int))
        self.coefficients = self.model.coef_[0]
        self.parameter_count = int(Z.shape[1] + 1)
        return self

    def predict(self, X, context):
        return self._constant(X) if self.constant is not None else self.model.predict_proba(self._prepare(X))[:, 1]


class LinearQuantile(Model):
    family = 'B_linear'
    kind = QUANTILE
    requires = ('sklearn',)
    preprocess = {}

    def fit(self, X, y, context):
        from sklearn.linear_model import QuantileRegressor
        Z = self._prepare(X, fit=True)
        if self._without_inputs(Z, y):
            return self
        self.model = QuantileRegressor(quantile=self.params['quantile'], alpha=self.params.get('alpha', 0.01), solver='highs').fit(Z, y)
        self.parameter_count = int(Z.shape[1] + 1)
        return self

    def predict(self, X, context):
        return self._constant(X) if self.constant is not None else self.model.predict(self._prepare(X))


# ---------------------------------------------------------------------------- family C: boosted trees
class _Tree(Model):
    family = 'C_boosted_trees'
    # trees read the raw values and treat "unavailable" as its own case; only the train-only availability filter is applied
    preprocess = {'impute': False, 'scale': False, 'indicators': False, 'clip': (0.0, 100.0)}

    def _objective(self):
        return self.kind

    def predict(self, X, context):
        if self.constant is not None:
            return self._constant(X)
        Z = self._prepare(X)
        if self.kind == CLASSIFICATION:
            return self.model.predict_proba(Z)[:, 1]
        return self.model.predict(Z)

    def importance(self) -> np.ndarray:
        return np.zeros(0) if self.constant is not None else np.asarray(self.model.feature_importances_, dtype=float)


class XGBoost(_Tree):
    requires = ('xgboost',)

    def fit(self, X, y, context):
        import xgboost
        Z = self._prepare(X, fit=True)
        if self._without_inputs(Z, y):
            return self
        common = dict(n_estimators=self.params.get('n_estimators', 100), max_depth=self.params.get('max_depth', 2),
                      learning_rate=self.params.get('learning_rate', 0.05), subsample=0.8, colsample_bytree=0.8,
                      min_child_weight=self.params.get('min_child_weight', 20), reg_lambda=self.params.get('reg_lambda', 5.0),
                      random_state=context.get('seed', 0), n_jobs=2, tree_method='hist')
        if self.kind == CLASSIFICATION:
            self.model = xgboost.XGBClassifier(**common).fit(Z, y.astype(int))
        elif self.kind == QUANTILE:
            self.model = xgboost.XGBRegressor(objective='reg:quantileerror', quantile_alpha=self.params['quantile'], **common).fit(Z, y)
        else:
            self.model = xgboost.XGBRegressor(**common).fit(Z, y)
        self.parameter_count = int(common['n_estimators'] * (2 ** common['max_depth']))
        return self

    def contributions(self, X) -> np.ndarray:
        """Per-row, per-feature contributions to the prediction (TreeSHAP, computed by the library itself)."""
        import xgboost
        return self.model.get_booster().predict(xgboost.DMatrix(self._prepare(X)), pred_contribs=True)[:, :-1]


class XGBoostClassifier(XGBoost):
    kind = CLASSIFICATION


class LightGBM(_Tree):
    requires = ('lightgbm',)

    def fit(self, X, y, context):
        import lightgbm
        Z = self._prepare(X, fit=True)
        if self._without_inputs(Z, y):
            return self
        common = dict(n_estimators=self.params.get('n_estimators', 100), num_leaves=self.params.get('num_leaves', 4),
                      learning_rate=self.params.get('learning_rate', 0.05), subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                      min_child_samples=self.params.get('min_child_samples', 50), reg_lambda=self.params.get('reg_lambda', 5.0),
                      random_state=context.get('seed', 0), n_jobs=2, verbose=-1, deterministic=True, force_row_wise=True)
        if self.kind == CLASSIFICATION:
            self.model = lightgbm.LGBMClassifier(**common).fit(Z, y.astype(int))
        elif self.kind == QUANTILE:
            self.model = lightgbm.LGBMRegressor(objective='quantile', alpha=self.params['quantile'], **common).fit(Z, y)
        else:
            self.model = lightgbm.LGBMRegressor(**common).fit(Z, y)
        self.parameter_count = int(common['n_estimators'] * common['num_leaves'])
        return self

    def contributions(self, X) -> np.ndarray:
        return self.model.predict(self._prepare(X), pred_contrib=True)[:, :-1]


class LightGBMClassifier(LightGBM):
    kind = CLASSIFICATION


class LightGBMQuantile(LightGBM):
    kind = QUANTILE


class CatBoost(_Tree):
    requires = ('catboost',)

    def fit(self, X, y, context):
        import catboost
        Z = self._prepare(X, fit=True)
        if self._without_inputs(Z, y):
            return self
        common = dict(iterations=self.params.get('iterations', 200), depth=self.params.get('depth', 3),
                      learning_rate=self.params.get('learning_rate', 0.05), l2_leaf_reg=self.params.get('l2_leaf_reg', 10.0),
                      random_seed=context.get('seed', 0), thread_count=2, verbose=False, allow_writing_files=False)
        if self.kind == CLASSIFICATION:
            self.model = catboost.CatBoostClassifier(**common).fit(Z, y.astype(int))
        else:
            self.model = catboost.CatBoostRegressor(**common).fit(Z, y)
        self.parameter_count = int(common['iterations'] * (2 ** common['depth']))
        return self


class CatBoostClassifier(CatBoost):
    kind = CLASSIFICATION


# ---------------------------------------------------------------------------- the predeclared search spaces
SMALL_TECHNICAL = ('return20', 'return63', 'realized_vol20', 'sma50_distance', 'rsi14_wilder')
GRIDS = {
    'ridge': [{'alpha': a} for a in (10.0, 100.0, 1000.0, 10000.0)],
    'elastic_net': [{'alpha': a, 'l1_ratio': 0.5} for a in (0.0005, 0.002, 0.008)],
    'logistic': [{'C': c} for c in (0.001, 0.01, 0.1)],
    'xgboost': [{'max_depth': 2, 'n_estimators': 100, 'learning_rate': 0.05}, {'max_depth': 2, 'n_estimators': 300, 'learning_rate': 0.02},
                {'max_depth': 3, 'n_estimators': 150, 'learning_rate': 0.03, 'min_child_weight': 40}],
    'lightgbm': [{'num_leaves': 4, 'n_estimators': 100, 'learning_rate': 0.05}, {'num_leaves': 4, 'n_estimators': 300, 'learning_rate': 0.02},
                 {'num_leaves': 8, 'n_estimators': 150, 'learning_rate': 0.03, 'min_child_samples': 100}],
    'catboost': [{'depth': 3, 'iterations': 200, 'learning_rate': 0.05}, {'depth': 2, 'iterations': 400, 'learning_rate': 0.03},
                 {'depth': 4, 'iterations': 150, 'learning_rate': 0.05, 'l2_leaf_reg': 30.0}],
}
