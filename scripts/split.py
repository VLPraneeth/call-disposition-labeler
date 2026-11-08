"""Create a fixed, stratified dev/holdout split of the labeled calls.

Stratifies on (disposition, sub_disposition). Seeded, so the split is reproducible.
The holdout is meant to be scored only at a few logged checkpoints (see reports/ERROR_ANALYSIS.md).

Usage: python scripts/split.py [gold.jsonl] [out.json] [dev_size] [seed]
"""
import json
import random
import sys
from collections import defaultdict


def main(gold="data/gold.jsonl", out="data/split.json", dev_size="30", seed="20261108"):
    dev_size, rng = int(dev_size), random.Random(int(seed))
    rows = [json.loads(l) for l in open(gold, encoding="utf-8")]
    strata = defaultdict(list)
    for r in rows:
        strata[(r["disposition"], r["sub_disposition"])].append(r["transcript_id"])
    frac = dev_size / len(rows)
    dev, hold = [], []
    # Large strata first get their proportional share; singletons alternate so both sides see rare labels.
    singles = []
    for key in sorted(strata):
        ids = sorted(strata[key])
        rng.shuffle(ids)
        if len(ids) == 1:
            singles.extend(ids)
            continue
        k = max(1, min(len(ids) - 1, round(len(ids) * frac)))
        dev += ids[:k]
        hold += ids[k:]
    rng.shuffle(singles)
    for s in singles:
        (dev if len(dev) < dev_size and len(dev) / dev_size <= len(hold) / (len(rows) - dev_size) else hold).append(s)
    # Final size adjustment, deterministic.
    while len(dev) > dev_size:
        hold.append(dev.pop())
    while len(dev) < dev_size:
        dev.append(hold.pop())
    split = {"seed": int(seed), "dev": sorted(dev), "holdout": sorted(hold)}
    json.dump(split, open(out, "w", encoding="utf-8"), indent=1)
    lab = {r["transcript_id"]: (r["disposition"], r["sub_disposition"]) for r in rows}
    for name in ("dev", "holdout"):
        c = defaultdict(int)
        for i in split[name]:
            c[lab[i]] += 1
        print(name, len(split[name]), dict(sorted(c.items())))


if __name__ == "__main__":
    main(*sys.argv[1:])
