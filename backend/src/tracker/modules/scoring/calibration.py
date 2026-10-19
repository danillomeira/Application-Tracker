"""Calibração dos pesos de Chance por regressão logística (RF-AVA-08, docs/10 §8).

Nunca ativa sozinho: salva uma versão inativa para o usuário aprovar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.modules.applications.models import Application, ApplicationEvent
from tracker.modules.applications.state_machine import POSITIVE, SENT
from tracker.modules.scoring import features as F
from tracker.modules.scoring.models import JobScore

MIN_SAMPLES = 100
FEATURES = list(F.CHANCE_WEIGHTS)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 3000, lr: float = 0.1) -> tuple[np.ndarray, float]:
    n, d = x.shape
    w, b = np.zeros(d), 0.0
    for _ in range(iters):
        p = _sigmoid(x @ w + b)
        gw = x.T @ (p - y) / n + l2 * w / n
        gb = float(np.mean(p - y))
        w -= lr * gw
        b -= lr * gb
    return w, b


def auc(y: np.ndarray, s: np.ndarray) -> float:
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    wins = sum(float((p > neg).sum() + 0.5 * (p == neg).sum()) for p in pos)
    return wins / (len(pos) * len(neg))


def cross_val_auc(x: np.ndarray, y: np.ndarray, k: int = 5, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(y))
    folds = np.array_split(idx, k)
    scores = []
    for i in range(k):
        test = folds[i]
        train = np.concatenate([folds[j] for j in range(k) if j != i])
        w, b = fit_logistic(x[train], y[train])
        scores.append(auc(y[test], _sigmoid(x[test] @ w + b)))
    return float(np.mean(scores))


async def dataset(session: AsyncSession) -> tuple[np.ndarray, np.ndarray]:
    cutoff = datetime.now(UTC) - timedelta(days=21)
    rows = (
        await session.execute(
            select(Application, JobScore)
            .join(JobScore, and_(JobScore.job_id == Application.job_id, JobScore.is_current.is_(True)))
            .where(Application.status.in_(SENT), Application.submitted_at <= cutoff)
        )
    ).all()
    xs, ys = [], []
    for app, score in rows:
        reached = app.status in POSITIVE
        if not reached:
            reached = bool(
                await session.scalar(
                    select(ApplicationEvent.id).where(
                        ApplicationEvent.application_id == app.id,
                        ApplicationEvent.kind == "status_change",
                        ApplicationEvent.payload["to"].astext.in_(list(POSITIVE)),
                    )
                )
            )
        bd = score.chance_breakdown or {}
        xs.append([float((bd.get(f) or {}).get("value", F.NEUTRAL)) for f in FEATURES])
        ys.append(1.0 if reached else 0.0)
    return np.array(xs).reshape(-1, len(FEATURES)), np.array(ys)


async def calibrate(session: AsyncSession) -> dict[str, Any]:
    from tracker.modules.scoring.service import current_weights, save_weights

    x, y = await dataset(session)
    n = len(y)
    if n < MIN_SAMPLES:
        return {"status": "insufficient_data", "n": n, "needed": MIN_SAMPLES}
    if y.sum() < 5:
        return {"status": "too_few_positives", "n": n, "positives": int(y.sum())}
    cv = cross_val_auc(x, y)
    w, _ = fit_logistic(x, y)
    current = await current_weights(session)
    cur_w = np.array([current.chance_weights.get(f, 0.0) for f in FEATURES])
    current_auc = auc(y, x @ cur_w)
    positive = np.clip(w, 0, None)
    if positive.sum() == 0:
        return {"status": "no_signal", "n": n, "cv_auc": cv}
    new = {f: float(v) for f, v in zip(FEATURES, positive / positive.sum(), strict=True)}
    row = await save_weights(
        session,
        new,
        current.attractiveness_weights,
        current.thresholds,
        "calibrated",
        metrics={"cv_auc": round(cv, 3), "current_auc": round(current_auc, 3), "n": n, "positives": int(y.sum())},
        activate=False,
    )
    return {
        "status": "proposed",
        "version": row.version,
        "weights": new,
        "cv_auc": round(cv, 3),
        "current_auc": round(current_auc, 3),
        "n": n,
    }
