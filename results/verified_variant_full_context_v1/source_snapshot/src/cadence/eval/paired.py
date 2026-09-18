"""Paired comparisons: resample the same message IDs, never independent system means."""

from __future__ import annotations

import numpy as np
from scipy.stats import binomtest

from cadence.config import intent_ids
from cadence.eval.metrics import macro_f1


def compare(
    golden: list[dict], left: list[dict], right: list[dict], *, n_boot: int = 2000, seed: int = 2026
) -> dict:
    def index(rows):
        by_id = {r["id"]: r for r in rows}
        if len(by_id) != len(rows):
            raise ValueError("Duplicate prediction IDs")
        return by_id

    a, b = index(left), index(right)
    ids = [g["id"] for g in golden]
    if len(set(ids)) != len(ids) or set(a) != set(ids) or set(b) != set(ids):
        raise ValueError("Paired systems must cover exactly the same golden IDs")
    gold_intent = np.array([g["gold"]["intent"] for g in golden])
    gold_esc = np.array([g["gold"]["should_escalate"] for g in golden], dtype=bool)
    ai, bi = (np.array([s[i]["intent"] for i in ids]) for s in (a, b))
    ae, be = (np.array([s[i]["decision"] == "escalate" for i in ids]) for s in (a, b))

    def stats(ix, intents, escalation):
        g, pred = gold_esc[ix], escalation[ix]
        auto = ~pred
        return {
            "intent_accuracy": float(np.mean(gold_intent[ix] == intents[ix])),
            "macro_f1": macro_f1(gold_intent[ix], intents[ix], labels=intent_ids()),
            "decision_accuracy": float(np.mean(g == pred)),
            "escalation_recall": float(np.mean(pred[g])) if g.any() else None,
            "auto_handle_rate": float(np.mean(auto)),
            "unsafe_auto_rate": float(np.mean(g[auto])) if auto.any() else None,
        }

    ix = np.arange(len(ids))
    sa, sb = stats(ix, ai, ae), stats(ix, bi, be)
    rng = np.random.default_rng(seed)
    draws = {k: [] for k in sa}
    for _ in range(n_boot):
        sample = rng.choice(ix, size=len(ix), replace=True)
        x, y = stats(sample, ai, ae), stats(sample, bi, be)
        for k in draws:
            if x[k] is not None and y[k] is not None:
                draws[k].append(x[k] - y[k])

    def mcnemar(ca, cb):
        a_only, b_only = int(np.sum(ca & ~cb)), int(np.sum(cb & ~ca))
        return {
            "left_only_correct": a_only,
            "right_only_correct": b_only,
            "p_exact": float(binomtest(a_only, a_only + b_only, 0.5).pvalue) if a_only + b_only else 1.0,
        }

    return {
        "n": len(ids),
        "seed": seed,
        "bootstrap_resamples": n_boot,
        "direction": "left minus right",
        "left": sa,
        "right": sb,
        "delta": {
            k: {
                "estimate": sa[k] - sb[k] if sa[k] is not None and sb[k] is not None else None,
                "ci95": np.quantile(draws[k], [0.025, 0.975]).tolist() if draws[k] else None,
                "valid_resamples": len(draws[k]),
            }
            for k in sa
        },
        "intent_mcnemar": mcnemar(ai == gold_intent, bi == gold_intent),
        "decision_mcnemar": mcnemar(ae == gold_esc, be == gold_esc),
    }
