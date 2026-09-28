"""E6: determinism is about identical bytes. What happens when the bytes change but the
meaning does not? For each eval request we send semantically equivalent variants and
count decision flips against the original request.

  key_order    : `state` object keys reversed (recursively)
  option_order : choice/score options presented in reverse order (labels unchanged)
  whitespace   : trailing space + doubled spaces in the instructions
  uid          : TypeSafe's cookbook protocol, a fresh random `uid` in `state`

Usage: python invariance.py --api URL --label det_on --out results/e6_det_on.json
"""

import argparse
import asyncio
import copy
import json
import random
from pathlib import Path

import httpx
import orjson

ROOT = Path(__file__).resolve().parents[1]


def reverse_keys(x):
    if isinstance(x, dict):
        return {k: reverse_keys(x[k]) for k in reversed(list(x))}
    if isinstance(x, list):
        return [reverse_keys(v) for v in x]
    return x


def variants(req, rng):
    out = {}
    v = copy.deepcopy(req)
    v["state"] = reverse_keys(v["state"])
    out["key_order"] = v
    q = next(iter(req["questions"].values()))
    if q["type"] == "choice":
        v = copy.deepcopy(req)
        (qid, qq), = v["questions"].items()
        qq["criteria"] = dict(reversed(list(qq["criteria"].items())))
        out["option_order"] = v
    v = copy.deepcopy(req)
    (qid, qq), = v["questions"].items()
    if isinstance(qq["instructions"], str):
        qq["instructions"] = qq["instructions"].replace(". ", ".  ") + " "
        out["whitespace"] = v
    v = copy.deepcopy(req)
    if isinstance(v["state"], dict):
        v["state"] = {"uid": f"{rng.randrange(15)}:{rng.getrandbits(32):08x}", **v["state"]}
        out["uid"] = v
    return out


def decision(ans):
    if ans["type"] == "noul":
        return ans["noul"] >= 0.5, ans["noul"]
    if ans["type"] == "choice":
        return ans["choice"], ans["probabilities"][ans["choice"]]
    top = max(ans["probabilities"], key=ans["probabilities"].get)
    return top, ans["score"]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = [json.loads(line) for line in open(ROOT / "nimble/data/eval.jsonl")]
    rng = random.Random(3)
    client = httpx.AsyncClient(base_url=args.api, timeout=600)
    sem = asyncio.Semaphore(16)

    async def ask(body):
        async with sem:
            r = await client.post("/v1/systemone", content=orjson.dumps(body),
                                  headers={"Content-Type": "application/json"})
        r.raise_for_status()
        return next(iter(r.json()["answers"].values()))

    async def one(row):
        req = {"model": "nimble-latest", **row["input"]}
        base = await ask(req)
        res = {}
        for name, body in variants(req, rng).items():
            ans = await ask(body)
            (d0, p0), (d1, p1) = decision(base), decision(ans)
            res[name] = {"flip": d0 != d1, "abs_dp": abs(p1 - p0), "identical": ans == base}
        return res

    per = await asyncio.gather(*(one(r) for r in rows))
    summary = {}
    for name in ("key_order", "option_order", "whitespace", "uid"):
        xs = [p[name] for p in per if name in p]
        summary[name] = {"n": len(xs), "flips": sum(x["flip"] for x in xs),
                         "identical": sum(x["identical"] for x in xs),
                         "mean_abs_dp": sum(x["abs_dp"] for x in xs) / len(xs)}
        print(f"[{args.label}] {name:12s} n={len(xs):3d} identical={summary[name]['identical']:3d} "
              f"flips={summary[name]['flips']:3d} mean|dp|={summary[name]['mean_abs_dp']:.4f}", flush=True)
    json.dump({"label": args.label, "summary": summary, "rows": per}, open(args.out, "w"))


if __name__ == "__main__":
    asyncio.run(main())
