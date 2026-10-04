"""Model families D to F: a small feed-forward network, sequence models and a compact transformer encoder.

These are deliberately small. The dataset is tiny by deep-learning standards, and a large network would only memorise
it. Whether even these small ones have enough data is decided by the data-sufficiency gate in the tournament, not here:
a model that fails the gate is still run, so its instability is on record, and is labelled
EXPERIMENTAL_INSUFFICIENT_DATA whatever it scores.

Training uses only the rows it is given. Early stopping uses the last part of those rows, purged by the label horizon,
never the block being predicted. Seeds are fixed; each model is trained under several seeds and the spread is reported.
"""
from __future__ import annotations

import numpy as np

from .models import Model
from .preprocess import Preprocessor

SEEDS = (11, 23, 37)
SEQUENCE_LENGTH = 20


def _torch():
    import torch
    torch.set_num_threads(2)
    return torch


class TorchModel(Model):
    family = 'D_neural'
    requires = ('torch',)
    sequence = False
    heads = ('regression',)             # one entry per output: 'regression' or 'classification'
    EPOCHS = 60

    def network(self, torch, features):
        raise NotImplementedError

    # ------------------------------------------------------------------ data
    def _scale(self, X, fit=False):
        if X.ndim == 3:
            flat = X.reshape(-1, X.shape[-1])
            if fit:
                self.pre = Preprocessor().fit(flat)             # median and a missing-value flag, as for every linear and neural model (plan section 3)
            return self.pre.transform(flat).reshape(X.shape[0], X.shape[1], -1)
        if fit:
            self.pre = Preprocessor().fit(X)
        return self.pre.transform(X)

    def fit(self, X, y, context):
        torch = _torch()
        y = np.asarray(y, dtype=float)
        if y.ndim == 1:
            y = y[:, None]
        heads = self.params.get('heads', self.heads)
        self.heads_used = tuple(heads)
        Z = self._scale(X, fit=True)
        if Z.shape[-1] == 0:
            raise ValueError('NO_USABLE_DESCRIPTOR_FOR_A_NETWORK')
        regression = [k for k, h in enumerate(heads) if h == 'regression']
        self.center = np.zeros(y.shape[1])
        self.spread = np.ones(y.shape[1])
        for k in regression:
            self.center[k], self.spread[k] = np.nanmean(y[:, k]), np.nanstd(y[:, k]) or 1.0
        target = (y - self.center) / self.spread
        # early stopping on the last fifth of the training sessions, purged by the horizon
        sessions = np.asarray(context['session'])
        days = np.unique(sessions)
        horizon = int(context.get('horizon', 20))
        cut = days[int(len(days) * 0.8)] if len(days) >= 30 else None
        if cut is not None:
            stop = sessions >= cut
            learn = sessions + horizon < cut
        else:
            stop, learn = np.zeros(len(sessions), dtype=bool), np.ones(len(sessions), dtype=bool)
        self.learn_sessions = int(len(np.unique(sessions[learn])))      # the sessions gradient steps were taken on: fewer than the training window
        self.models, self.history = [], []
        for seed in self.params.get('seeds', SEEDS):
            torch.manual_seed(seed)
            generator = np.random.default_rng(seed)
            net = self.network(torch, Z.shape[-1])
            optimiser = torch.optim.Adam(net.parameters(), lr=self.params.get('lr', 1e-3), weight_decay=self.params.get('weight_decay', 1e-2))
            a, b = torch.tensor(Z[learn], dtype=torch.float32), torch.tensor(target[learn], dtype=torch.float32)
            c, d = torch.tensor(Z[stop], dtype=torch.float32), torch.tensor(target[stop], dtype=torch.float32)
            best, best_state, waited, epochs = float('inf'), None, 0, 0
            for epoch in range(self.params.get('epochs', self.EPOCHS)):
                net.train()
                order = generator.permutation(len(a))
                for start in range(0, len(order), 256):
                    batch = order[start:start + 256]
                    optimiser.zero_grad()
                    self._loss(torch, net(a[batch]), b[batch], heads).backward()
                    optimiser.step()
                epochs = epoch + 1
                if stop.any():
                    net.eval()
                    with torch.no_grad():
                        score = float(self._loss(torch, net(c), d, heads))
                    if score < best - 1e-5:
                        best, waited = score, 0
                        best_state = {k: v.clone() for k, v in net.state_dict().items()}
                    else:
                        waited += 1
                        if waited >= self.params.get('patience', 8):
                            break
                elif epochs >= self.params.get('fixed_epochs', 25):
                    break
            if best_state is not None:
                net.load_state_dict(best_state)
            net.eval()
            self.models.append(net)
            self.history.append({'seed': seed, 'epochs': epochs, 'stop_loss': None if best == float('inf') else best})
        self.parameter_count = int(sum(p.numel() for p in self.models[0].parameters()))
        return self

    @staticmethod
    def _loss(torch, output, target, heads):
        total, used = 0.0, 0
        for k, head in enumerate(heads):
            mask = ~torch.isnan(target[:, k])
            if not mask.any():
                continue
            if head == 'classification':
                total = total + torch.nn.functional.binary_cross_entropy_with_logits(output[mask, k], target[mask, k])
            else:
                total = total + torch.nn.functional.mse_loss(output[mask, k], target[mask, k])
            used += 1
        return total / max(1, used)

    def predict_seeds(self, X, context=None) -> np.ndarray:
        """[seed, row, head] predictions, in the units of the targets (probabilities for a classification head)."""
        torch = _torch()
        Z = torch.tensor(self._scale(X), dtype=torch.float32)
        out = []
        with torch.no_grad():
            for net in self.models:
                raw = net(Z).numpy().astype(float)
                for k, head in enumerate(self.heads_used):
                    raw[:, k] = 1 / (1 + np.exp(-raw[:, k])) if head == 'classification' else raw[:, k] * self.spread[k] + self.center[k]
                out.append(raw)
        return np.stack(out)

    def predict(self, X, context):
        mean = self.predict_seeds(X).mean(axis=0)
        return mean[:, 0] if mean.shape[1] == 1 else mean

    def describe(self):
        return {'training': self.history, 'parameters': self.parameter_count, 'learn_sessions': self.learn_sessions}


class MLP(TorchModel):
    """Two small hidden layers with dropout, on the row's own descriptors."""

    def network(self, torch, features):
        nn = torch.nn
        drop = self.params.get('dropout', 0.3)
        return nn.Sequential(nn.Linear(features, 32), nn.ReLU(), nn.Dropout(drop), nn.Linear(32, 16), nn.ReLU(), nn.Dropout(drop),
                             nn.Linear(16, len(self.params.get('heads', self.heads))))


class _Sequence(TorchModel):
    family = 'E_sequence'
    sequence = True


class TCN(_Sequence):
    """Two causal dilated convolutions over the last 20 sessions; the output at the final step is read."""

    def network(self, torch, features):
        nn = torch.nn
        heads = len(self.params.get('heads', self.heads))

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.a = nn.Conv1d(features, 16, 3, dilation=1)
                self.b = nn.Conv1d(16, 16, 3, dilation=2)
                self.drop = nn.Dropout(0.2)
                self.out = nn.Linear(16, heads)

            def forward(self, x):
                x = x.transpose(1, 2)
                x = torch.relu(self.a(nn.functional.pad(x, (2, 0))))           # left padding only: a step never sees a later step
                x = torch.relu(self.b(nn.functional.pad(x, (4, 0))))
                return self.out(self.drop(x[:, :, -1]))
        return Net()


class _Recurrent(_Sequence):
    cell = 'GRU'

    def network(self, torch, features):
        nn = torch.nn
        heads = len(self.params.get('heads', self.heads))
        cell = self.cell

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.rnn = getattr(nn, cell)(features, 16, batch_first=True)
                self.drop = nn.Dropout(0.2)
                self.out = nn.Linear(16, heads)

            def forward(self, x):
                output, _ = self.rnn(x)
                return self.out(self.drop(output[:, -1]))
        return Net()


class GRU(_Recurrent):
    cell = 'GRU'


class LSTM(_Recurrent):
    cell = 'LSTM'


class TransformerEncoder(_Sequence):
    """An encoder-only transformer: one layer, two heads, width 16, learned positions, the final step read. Encoder only
    because the targets are scalars; a decoder would only be needed to predict a path, which no target here asks for."""
    family = 'F_transformer'

    def network(self, torch, features):
        nn = torch.nn
        heads = len(self.params.get('heads', self.heads))
        width, layers = self.params.get('width', 16), self.params.get('layers', 1)

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.embed = nn.Linear(features, width)
                self.position = nn.Parameter(torch.zeros(1, SEQUENCE_LENGTH, width))
                layer = nn.TransformerEncoderLayer(width, 2, dim_feedforward=32, dropout=0.2, batch_first=True)
                self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
                self.out = nn.Linear(width, heads)

            def forward(self, x):
                x = self.embed(x) + self.position[:, -x.shape[1]:]
                return self.out(self.encoder(x)[:, -1])
        return Net()


def sufficiency(*, parameters, training_rows, training_sessions, instruments, horizon, average_pair_correlation) -> dict:
    """The data-sufficiency gate for a fitted network. Rows overlap in time and move together across instruments, so the
    count that matters is far smaller than the row count: non-overlapping label windows times the effective number of
    independent instruments. The gate asks for at least ten such observations per trainable parameter; it is a floor
    for taking a result seriously, not a promise that passing it makes a result meaningful."""
    windows = training_sessions / max(1, horizon)
    breadth = instruments / (1 + (instruments - 1) * max(0.0, average_pair_correlation))
    effective = windows * breadth
    return {'parameters': int(parameters), 'training_rows': int(training_rows), 'training_sessions': int(training_sessions),
            'non_overlapping_label_windows': round(windows, 1), 'average_pair_correlation': round(float(average_pair_correlation), 3),
            'effective_independent_instruments': round(breadth, 1), 'effective_independent_observations': round(effective, 1),
            'observations_per_parameter': round(effective / max(1, parameters), 4), 'required_per_parameter': 10,
            'sufficient': bool(effective >= 10 * parameters)}
