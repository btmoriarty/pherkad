#!/usr/bin/env python3
"""null_auc.py: the discriminant's reported AUC when there is nothing to find.

Author and reference pieces are drawn from one distribution (40 features, a
document-level effect of sd 0.5 under a piece-level sd of 1; 40 author
documents of 3 pieces, 60 reference documents of 1), so the true AUC is 0.5.
The script fits fingerprint's discriminant on each simulated pair and reports
the distribution of cv_auc. docs/measured-profile.md quotes its output for
0.5.55 (shrinkage chosen on the folds that scored it) and 0.5.56 (nested).

Usage: null_auc.py [--runs 200] [--tools DIR]
Stdlib only.
"""
import argparse
import os
import random
import statistics
import sys
import time

P = 40


def pool(rng, prefix, docs, per_doc):
    groups, rows = [], []
    for d in range(docs):
        eff = [rng.gauss(0, 0.5) for _ in range(P)]
        for _ in range(per_doc):
            groups.append(f"{prefix}{d}")
            rows.append([eff[j] + rng.gauss(0, 1) for j in range(P)])
    return {"keys": [f"k{j}" for j in range(P)], "groups": groups, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--tools", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "pherkad", "tools"))
    args = ap.parse_args(argv)
    sys.path.insert(0, os.path.abspath(args.tools))
    import fingerprint
    aucs, t0 = [], time.time()
    for seed in range(args.runs):
        rng = random.Random(1000 + seed)
        aucs.append(fingerprint._fit(pool(rng, "a", 40, 3), pool(rng, "r", 60, 1))["cv_auc"])
    print(f"runs {args.runs}: mean cv_auc {statistics.fmean(aucs):.3f}, sd {statistics.stdev(aucs):.3f}, "
          f"range {min(aucs):.3f} to {max(aucs):.3f}, share at or above 0.6: {sum(x >= 0.6 for x in aucs) / args.runs:.2f}, "
          f"{(time.time() - t0) / args.runs:.2f} s per fit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
