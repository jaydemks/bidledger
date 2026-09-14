#!/usr/bin/env python3
"""Boil 720,000 awards down to something the site build can carry.

The award store is 98 MB and deliberately kept out of git to keep the repository
small. But the pages that answer "who wins this kind of work here" only
need the shape of it: how many contracts each supplier took, what they were
worth, and a handful of recent examples. That is a few megabytes, which can
live in the repository and be read by the build on every run.

    python scripts/winners_aggregate.py     # writes data/winners.json

Run this after scripts/awards.py and scripts/enrich_awards.py.
"""
import glob
import gzip
import json
import os
import statistics
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AWARDS = os.path.join(ROOT, "data", "awards")
OUT = os.path.join(ROOT, "data", "winners.json")

# A page needs enough behind it to be worth reading. Below this it is a list of
# three companies, which helps nobody and dilutes everything around it.
MIN_AWARDS = 50
MIN_SUPPLIERS = 10
TOP_SUPPLIERS = 25
RECENT = 10


def main():
    files = sorted(glob.glob(os.path.join(AWARDS, "*.jsonl.gz")))
    if not files:
        print("nothing in data/awards — run scripts/awards.py first")
        return 1

    # (country, cpv division) -> stats
    count = defaultdict(int)
    values = defaultdict(list)          # euro values, for the median
    supplier = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))  # count, sum
    recent = defaultdict(list)
    nat = defaultdict(lambda: defaultdict(int))

    rows = 0
    for path in files:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                c, w = r.get("c"), r.get("w")
                if not c or not w:
                    continue
                rows += 1
                eur = r["val_eur"] if r.get("q") == "ok" else None
                for d in r.get("cpv", []):
                    k = (c, d)
                    count[k] += 1
                    if eur:
                        values[k].append(eur)
                        supplier[k][w][1] += eur
                    supplier[k][w][0] += 1
                    if r.get("nat"):
                        nat[k][r["nat"]] += 1
                    recent[k].append((r.get("p", ""), r["id"], w,
                                      eur, r.get("b", "")[:90],
                                      r.get("t", "")[:150]))

    out = {}
    for k, n in count.items():
        sups = supplier[k]
        if n < MIN_AWARDS or len(sups) < MIN_SUPPLIERS:
            continue
        vals = sorted(values[k])
        top = sorted(sups.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))[:TOP_SUPPLIERS]
        recent[k].sort(reverse=True)
        out[f"{k[0]}|{k[1]}"] = {
            "n": n,
            "suppliers": len(sups),
            "priced": len(vals),
            "median": round(vals[len(vals) // 2], 2) if vals else None,
            "total": round(sum(vals), 2) if vals else None,
            "nature": dict(sorted(nat[k].items(), key=lambda kv: -kv[1])),
            "top": [[name, s[0], round(s[1], 2)] for name, s in top],
            "recent": [list(x) for x in recent[k][:RECENT]],
        }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, OUT)

    size = os.path.getsize(OUT)
    print(f"{rows:,} awards read from {len(files)} months")
    print(f"{len(out):,} country-and-sector pairs cleared the bar "
          f"({MIN_AWARDS}+ awards, {MIN_SUPPLIERS}+ suppliers)")
    print(f"{OUT} — {size/1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
