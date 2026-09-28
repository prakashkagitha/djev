"""E9: hosted Jev on byte-identical requests (TypeSafe's cookbooks added a fresh uid per
call, so their published spread mixes noise with uid sensitivity; this isolates noise).

  cookbook  : TypeSafe's two cookbook requests, exact bytes, 15x sequential + 15x concurrent
  drift     : the 24 eval requests used in drift.py, 10 repeats each (concurrent across ids)

Reads the key from typesafe_apikey.txt; never logs it.
Usage: python hosted_jev.py --out results/e9_hosted_jev.json
"""

import argparse
import asyncio
import hashlib
import json
import random
import time
from pathlib import Path

import httpx
import orjson

ROOT = Path(__file__).resolve().parents[1]
URL = "https://api.typesafe.ai/v1/systemone"


def digest(answers):
    return hashlib.sha256(orjson.dumps(answers, option=orjson.OPT_SORT_KEYS)).hexdigest()[:16]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeats", type=int, default=15)
    ap.add_argument("--drift-targets", type=int, default=24)
    ap.add_argument("--drift-repeats", type=int, default=10)
    ap.add_argument("--model", default="jev-1.13.0")
    args = ap.parse_args()
    key = (ROOT / "typesafe_apikey.txt").read_text().strip()
    client = httpx.AsyncClient(timeout=120, headers={"Authorization": f"Bearer {key}"},
                               limits=httpx.Limits(max_connections=16))
    sem = asyncio.Semaphore(8)

    async def ask(body):
        raw = orjson.dumps(body)  # the same bytes every time
        async with sem:
            for attempt in range(5):
                t = time.perf_counter()
                r = await client.post(URL, content=raw, headers={"Content-Type": "application/json"})
                if r.status_code in (429, 529):
                    await asyncio.sleep(1 + attempt)
                    continue
                r.raise_for_status()
                d = r.json()
                return {"answers": d["answers"], "model": d["model"], "ms": (time.perf_counter() - t) * 1000,
                        "hash": digest(d["answers"]), "request_id": r.headers.get("x-typesafe-request-id")}
        raise RuntimeError("rate limited")

    out = {"model_requested": args.model, "cookbook": {}, "drift": {}}
    for kind in ("noul", "choice"):
        body = json.loads((ROOT / f"tasks/typesafe_consistency/requests/{kind}_request.json").read_text())
        body["model"] = args.model
        seq = [await ask(body) for _ in range(args.repeats)]
        conc = await asyncio.gather(*(ask(body) for _ in range(args.repeats)))
        out["cookbook"][kind] = {"sequential": seq, "concurrent": conc}
        for name, runs in (("sequential", seq), ("concurrent", conc)):
            hashes = {r["hash"] for r in runs}
            print(f"[hosted] {kind:6s} {name:10s} distinct answer sets: {len(hashes)}/{len(runs)}  "
                  f"models={sorted({r['model'] for r in runs})}  p50={sorted(r['ms'] for r in runs)[len(runs)//2]:.0f}ms",
                  flush=True)

    rows = [json.loads(line) for line in open(ROOT / "nimble/data/eval.jsonl")]
    random.Random(0).shuffle(rows)  # same 24 targets as drift.py (seed 0)
    targets = rows[: args.drift_targets]
    for rep in range(args.drift_repeats):
        res = await asyncio.gather(*(ask({"model": args.model, **r["input"]}) for r in targets))
        for r, x in zip(targets, res):
            out["drift"].setdefault(r["id"], []).append(x)
    same = sum(len({x["hash"] for x in v}) == 1 for v in out["drift"].values())
    total_distinct = sum(len({x["hash"] for x in v}) for v in out["drift"].values())
    print(f"[hosted] drift: {same}/{len(out['drift'])} requests always identical; "
          f"{total_distinct} distinct answer sets over {len(out['drift'])} requests", flush=True)
    Path(args.out).write_text(json.dumps(out))


if __name__ == "__main__":
    asyncio.run(main())
