"""Re-apply the current deterministic rules (labeler/decide.py) to facts stored in a run log.

Lets Python-only changes be evaluated without new API calls. For voting runs (sample_facts in
the log) every sample is re-decided and the same majority vote is applied. Fallback records are skipped
(they have no facts) and written as their logged prediction.

Usage: python scripts/rescore.py <run.log.jsonl> <inputs.jsonl> <out_predictions.jsonl>
"""
import json
import os
import sys

from labeler.decide import decide
from labeler.pipeline import vote
from labeler.schema import OUTPUT_KEYS

# RULES env var, e.g. RULES='{"ack_check": false}', toggles individual checks for ablations.
RULES = json.loads(os.environ.get("RULES", "{}"))
# SAMPLES env var: for voting logs, use only the first N samples (default: all).
SAMPLES = int(os.environ.get("SAMPLES", "99"))


def main(log, inputs, out):
    recs = {json.loads(l)["transcript_id"]: json.loads(l) for l in open(inputs, encoding="utf-8")}
    metas = [json.loads(l) for l in open(log, encoding="utf-8")][1:]
    n = 0
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for m in metas:
            if not m.get("facts"):
                continue
            r = recs[m["transcript_id"]]
            preds = []
            for fx in [x for x in (m.get("sample_facts") or [m["facts"]])[:SAMPLES] if x]:
                o = decide(fx, r["call_started_at"], RULES, r["transcript"])
                preds.append({"transcript_id": m["transcript_id"], **{k: o[k] for k in OUTPUT_KEYS[1:]}})
            f.write(json.dumps(vote(m["transcript_id"], preds)) + "\n")
            n += 1
    print(f"rescored {n} records -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
