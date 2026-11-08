"""Score predictions against gold, mirroring the published scoring contract.

- Per-field accuracy: disposition, sub_disposition (credited only with the correct parent),
  lead_quality, next_call_at (exact string match; null must be JSON null).
- Missing / unparseable records score 0 on every field.
- Weighted score out of 70 (15/20/15/20) and whole-record exact match.

Usage: python scripts/evaluate.py <predictions.jsonl> [gold.jsonl] [--ids split.json:dev] [--errors]
"""
import argparse
import json
from collections import Counter

FIELDS = ["disposition", "sub_disposition", "lead_quality", "next_call_at"]
WEIGHTS = {"disposition": 15, "sub_disposition": 20, "lead_quality": 15, "next_call_at": 20}


def load(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            try:
                r = json.loads(line)
                out[str(r["transcript_id"])] = r
            except (json.JSONDecodeError, KeyError):
                pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pred")
    ap.add_argument("gold", nargs="?", default="data/gold.jsonl")
    ap.add_argument("--ids", help="split.json:dev | split.json:holdout | file with ids")
    ap.add_argument("--errors", action="store_true", help="print every mismatch")
    a = ap.parse_args()

    gold, pred = load(a.gold), load(a.pred)
    ids = sorted(gold)
    if a.ids:
        path, _, key = a.ids.partition(":")
        ids = sorted(json.load(open(path))[key]) if key else [l.strip() for l in open(path) if l.strip()]

    correct, exact, conf = Counter(), 0, {f: Counter() for f in FIELDS}
    missing = [i for i in ids if i not in pred]
    for i in ids:
        g, p = gold[i], pred.get(i, {})
        ok = {
            "disposition": p.get("disposition") == g["disposition"],
            "sub_disposition": p.get("disposition") == g["disposition"] and p.get("sub_disposition") == g["sub_disposition"],
            "lead_quality": p.get("lead_quality") == g["lead_quality"],
            "next_call_at": i in pred and p.get("next_call_at") == g["next_call_at"],
        }
        for f in FIELDS:
            correct[f] += ok[f]
            if not ok[f]:
                conf[f][(g[f], p.get(f))] += 1
        exact += all(ok.values())
        if a.errors and not all(ok.values()):
            diffs = [f"{f}: gold={g[f]!r} pred={p.get(f)!r}" for f in FIELDS if not ok[f]]
            print(f"{i}  " + " | ".join(diffs))

    n = len(ids)
    print(f"\nN={n}  missing={len(missing)}")
    score = 0.0
    for f in FIELDS:
        acc = correct[f] / n
        score += acc * WEIGHTS[f]
        print(f"  {f:16s} {correct[f]:3d}/{n}  {acc:6.1%}")
    print(f"  {'exact match':16s} {exact:3d}/{n}  {exact / n:6.1%}")
    print(f"  weighted label score: {score:.1f} / 70")
    if not a.errors:
        for f in ("disposition", "sub_disposition", "lead_quality"):
            if conf[f]:
                print(f"  top {f} confusions (gold -> pred):", dict(conf[f].most_common(5)))


if __name__ == "__main__":
    main()
