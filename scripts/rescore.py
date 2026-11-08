"""Re-apply the current deterministic rules (labeler/decide.py) to facts stored in a run log.

Lets Python-only changes be evaluated without new API calls. Fallback records are skipped
(they have no facts) and written as their logged prediction.

Usage: python scripts/rescore.py <run.log.jsonl> <inputs.jsonl> <out_predictions.jsonl>
"""
import json
import sys

from labeler.decide import decide


def main(log, inputs, out):
    calls = {json.loads(l)["transcript_id"]: json.loads(l)["call_started_at"] for l in open(inputs, encoding="utf-8")}
    metas = [json.loads(l) for l in open(log, encoding="utf-8")][1:]
    n = 0
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for m in metas:
            if not m.get("facts"):
                continue
            o = decide(m["facts"], calls[m["transcript_id"]])
            f.write(json.dumps({"transcript_id": m["transcript_id"], **{k: o[k] for k in
                    ("disposition", "sub_disposition", "lead_quality", "next_call_at")}}) + "\n")
            n += 1
    print(f"rescored {n} records -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
