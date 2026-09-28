"""E7: golden decisions. Record sha256(answers) for all 324 eval requests, or verify a
server against a recorded file. Requests go out 16 at a time, so batch composition
differs between runs by construction.

  python golden.py --api URL --record results/golden_det_on.json
  python golden.py --api URL --verify results/golden_det_on.json --label restart --out results/e7_restart.json
"""

import argparse
import asyncio
import hashlib
import json
import random
from pathlib import Path

import httpx
import orjson

ROOT = Path(__file__).resolve().parents[1]


async def run(api, seed):
    rows = [json.loads(line) for line in open(ROOT / "nimble/data/eval.jsonl")]
    random.Random(seed).shuffle(rows)  # different arrival order each run
    client = httpx.AsyncClient(base_url=api, timeout=600)
    sem = asyncio.Semaphore(16)

    async def one(row):
        async with sem:
            r = await client.post("/v1/systemone",
                                  content=orjson.dumps({"model": "nimble-latest", **row["input"]}),
                                  headers={"Content-Type": "application/json"})
        r.raise_for_status()
        answers = r.json()["answers"]
        digest = hashlib.sha256(orjson.dumps(answers, option=orjson.OPT_SORT_KEYS)).hexdigest()
        return row["id"], digest, answers, r.headers.get("x-detjev-fingerprint")

    results = await asyncio.gather(*(one(r) for r in rows))
    fps = {fp for *_, fp in results}
    return {rid: {"sha256": d, "answers": a} for rid, d, a, _ in results}, fps


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--record")
    ap.add_argument("--verify")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else random.randrange(10**6)
    got, fps = await run(args.api, seed)
    if args.record:
        json.dump({"fingerprints": sorted(fps), "golden": got}, open(args.record, "w"))
        print(f"recorded {len(got)} golden decisions, fingerprint {sorted(fps)}")
        return
    ref = json.load(open(args.verify))
    same = [rid for rid in ref["golden"] if got[rid]["sha256"] == ref["golden"][rid]["sha256"]]
    flips = 0
    for rid in ref["golden"]:
        for qid, a in got[rid]["answers"].items():
            b = ref["golden"][rid]["answers"][qid]
            key = "noul" if a["type"] == "noul" else "choice" if a["type"] == "choice" else None
            if key == "noul":
                flips += (a["noul"] >= 0.5) != (b["noul"] >= 0.5)
            elif key == "choice":
                flips += a["choice"] != b["choice"]
            else:
                flips += max(a["probabilities"], key=a["probabilities"].get) != \
                    max(b["probabilities"], key=b["probabilities"].get)
    summary = {"label": args.label, "n": len(ref["golden"]), "identical": len(same), "decision_flips": flips,
               "fingerprint_ref": ref["fingerprints"], "fingerprint_now": sorted(fps), "seed": seed}
    print(json.dumps(summary))
    if args.out:
        json.dump(summary, open(args.out, "w"))


if __name__ == "__main__":
    asyncio.run(main())
