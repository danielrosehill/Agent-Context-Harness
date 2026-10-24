"""Shared by baseline.py and train.py: dataset pin, input formatting, metrics."""
REPO = "danielrosehill/Agent-Task-Break-Detector"
REV = "30d2dc1c3dfbfae9e41bccbc9a1a8442741dc5c6"  # v0.1


def fmt_pair(r, max_turns=4):
    """(message, context) as the hook will see them: newest exchange first, so truncating the
    second segment drops the oldest history, not the turn the message replies to."""
    turns = r["context"][-max_turns:][::-1]
    ctx = "\n".join(f"AGENT: {t['agent']}\nUSER: {t['user']}" for t in turns)
    return r["message"], ctx


def metrics(y, p, target_precision=0.95):
    """Accuracy at 0.5, AUC-PR, and the best new_task recall at precision >= target (the pass bar)."""
    from sklearn.metrics import average_precision_score, precision_recall_curve
    acc = sum((pi >= 0.5) == bool(yi) for yi, pi in zip(y, p)) / len(y)
    prec, rec, thr = precision_recall_curve(y, p)
    ok = [(r, t) for pr, r, t in zip(prec[:-1], rec[:-1], thr) if pr >= target_precision]
    best = max(ok) if ok else (0.0, None)
    return {"n": len(y), "accuracy": round(acc, 4), "auc_pr": round(float(average_precision_score(y, p)), 4),
            f"recall_at_p{int(target_precision*100)}": round(float(best[0]), 4),
            "threshold": None if best[1] is None else round(float(best[1]), 4)}
