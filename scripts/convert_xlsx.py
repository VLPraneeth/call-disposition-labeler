"""Convert the candidate workbook's '50 Labeled Calls' tab into JSONL.

Writes:
  <out_dir>/inputs.jsonl  input-only records: transcript_id, call_started_at, timezone, transcript
  <out_dir>/gold.jsonl    gold labels: transcript_id + the four targets (sheet literal 'null' -> JSON null)

Usage: python scripts/convert_xlsx.py <workbook.xlsx> [out_dir]
Requires openpyxl (only for this one-off conversion; the labeler itself has no third-party deps).
"""
import json
import sys
from pathlib import Path

import openpyxl

INPUT_KEYS = ["transcript_id", "call_started_at", "timezone", "transcript"]
GOLD_KEYS = ["transcript_id", "disposition", "sub_disposition", "lead_quality", "next_call_at"]


def _clean(key, value):
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip().lower() == "null":
            return None
        return value if key == "transcript" else value.strip()
    return str(value)


def main(xlsx: str, out_dir: str = "data") -> None:
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    rows = list(wb["50 Labeled Calls"].iter_rows(values_only=True))
    header = [str(h).strip() for h in rows[0]]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out / "inputs.jsonl", "w", encoding="utf-8", newline="\n") as fi, \
         open(out / "gold.jsonl", "w", encoding="utf-8", newline="\n") as fg:
        for r in rows[1:]:
            rec = {k: _clean(k, v) for k, v in zip(header, r)}
            if not rec.get("transcript_id"):
                continue
            fi.write(json.dumps({k: rec[k] for k in INPUT_KEYS}, ensure_ascii=False) + "\n")
            fg.write(json.dumps({k: rec[k] for k in GOLD_KEYS}, ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {n} records -> {out / 'inputs.jsonl'}, {out / 'gold.jsonl'}")


if __name__ == "__main__":
    main(*sys.argv[1:])
