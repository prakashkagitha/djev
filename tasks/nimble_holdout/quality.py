"""E5: accuracy and calibration on Nimble's 324 held-out Jev-format requests.

Decision rule per type (the same way a caller would branch on the answer):
  noul   -> true iff noul >= 0.5          (gold: bool)
  choice -> argmax label                  (gold: label key)
  score  -> argmax level                  (gold: level index); also MAE of the expected score
Calibration uses the full per-option distribution: multiclass Brier, NLL of gold,
ECE over the top-probability (10 equal-width bins).

Usage: python quality.py --api http://127.0.0.1:8020 --label det_on --out results/e5_det_on.json
"""

import argparse
import asyncio
import json
import math
from pathlib import Path

import httpx
import orjson

ROOT = Path(__file__).resolve().parents[2]


def distribution(ans):
    if ans["type"] == "noul":
        return {"true": ans["noul"], "false": 1 - ans["noul"]}
    return ans["probabilities"]


def gold_key(qtype, target):
    if qtype == "noul":
        return "true" if target else "false"
    return str(target)


def summarize(rows):
    n = len(rows)
    acc = sum(r["correct"] for r in rows) / n
    brier = sum(r["brier"] for r in rows) / n
    nll = sum(r["nll"] for r in rows) / n
    bins = [[] for _ in range(10)]
    for r in rows:
        bins[min(9, int(r["top_p"] * 10))].append(r)
    ece = sum(len(b) / n * abs(sum(x["correct"] for x in b) / len(b) - sum(x["top_p"] for x in b) / len(b))
              for b in bins if b)
    reliability = [{"bin": i, "n": len(b),
                    "conf": sum(x["top_p"] for x in b) / len(b) if b else None,
                    "acc": sum(x["correct"] for x in b) / len(b) if b else None} for i, b in enumerate(bins)]
    return {"n": n, "accuracy": acc, "correct": sum(r["correct"] for r in rows), "brier": brier,
            "nll": nll, "ece": ece, "reliability": reliability}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--concurrency", type=int, default=16)
    args = ap.parse_args()

    data = [json.loads(line) for line in open(ROOT / "nimble/data/eval.jsonl")]
    sem = asyncio.Semaphore(args.concurrency)
    client = httpx.AsyncClient(base_url=args.api, timeout=600)

    async def one(row):
        req = {"model": "nimble-latest", **row["input"]}
        async with sem:
            r = await client.post("/v1/systemone", content=orjson.dumps(req),
                                  headers={"Content-Type": "application/json"})
        r.raise_for_status()
        (qid, ans), = r.json()["answers"].items()
        dist = distribution(ans)
        gold = gold_key(ans["type"], row["reference"]["target"])
        top = max(dist, key=dist.get)
        out = {"id": row["id"], "type": ans["type"], "gold": gold, "pred": top, "correct": top == gold,
               "top_p": dist[top], "dist": dist,
               "brier": sum((p - (k == gold)) ** 2 for k, p in dist.items()),
               "nll": -math.log(max(dist.get(gold, 0.0), 1e-12))}
        if ans["type"] == "score":
            out["score_abs_err"] = abs(ans["score"] - int(gold))
        return out

    rows = await asyncio.gather(*(one(r) for r in data))
    result = {"label": args.label, "all": summarize(rows),
              "by_type": {t: summarize([r for r in rows if r["type"] == t])
                          for t in ("noul", "choice", "score")},
              "score_mae": sum(r["score_abs_err"] for r in rows if "score_abs_err" in r)
              / max(1, sum("score_abs_err" in r for r in rows)),
              "rows": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(result, open(args.out, "w"))
    a = result["all"]
    print(f"[{args.label}] acc {a['correct']}/{a['n']} = {a['accuracy']:.3f}  brier {a['brier']:.4f}  "
          f"nll {a['nll']:.4f}  ece {a['ece']:.4f}  | "
          + "  ".join(f"{t}:{v['accuracy']:.3f}" for t, v in result["by_type"].items()))


if __name__ == "__main__":
    asyncio.run(main())
