"""E1/E2/E7: does the same Jev request always get the same answer?

1. Reference: each target request is sent alone to an idle server whose cache was
   just flushed (the cleanest possible condition).
2. Repeats: every target is re-sent `--repeats` times while background tenants keep
   the GPU busy: other Jev requests through the API (prefill-heavy) and, optionally,
   free-text generations sent straight to SGLang (decode-heavy), so batches mix.
3. Each repeat's `answers` is compared bit-for-bit (orjson, float64) against the reference,
   and per question we record the raw probability for plots.

Usage: python drift.py --api http://127.0.0.1:8020 --backend http://127.0.0.1:30020 \
          --label det_on --loads 0,8,32 --targets 24 --repeats 10 --out results/e2.json
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


def load_requests(seed: int):
    rows = [json.loads(line) for line in open(ROOT / "nimble/data/eval.jsonl")]
    random.Random(seed).shuffle(rows)
    return [{"id": r["id"], "model": "nimble-latest", **r["input"], "_gold": r["reference"]["target"]}
            for r in rows]


def body(req):
    return {k: v for k, v in req.items() if not k.startswith("_") and k != "id"}


def answer_hash(answers) -> str:
    return hashlib.sha256(orjson.dumps(answers, option=orjson.OPT_SORT_KEYS)).hexdigest()[:16]


def headline(ans: dict) -> tuple[str, float]:
    """(decision, probability behind it) for one answer object."""
    if ans["type"] == "noul":
        return ("true" if ans["noul"] >= 0.5 else "false"), ans["noul"]
    if ans["type"] == "choice":
        return ans["choice"], ans["probabilities"][ans["choice"]]
    level = max(ans["probabilities"], key=ans["probabilities"].get)  # branch on the top level
    return level, ans["score"]


class Runner:
    def __init__(self, api, backend):
        lim = httpx.Limits(max_connections=512, max_keepalive_connections=512)
        self.api = httpx.AsyncClient(base_url=api, timeout=600, limits=lim)
        self.backend = httpx.AsyncClient(base_url=backend, timeout=600, limits=lim)

    async def ask(self, req):
        t = time.perf_counter()
        r = await self.api.post("/v1/systemone", content=orjson.dumps(body(req)),
                                headers={"Content-Type": "application/json"})
        r.raise_for_status()
        return r.json(), (time.perf_counter() - t) * 1000, r.headers.get("x-detjev-fingerprint")

    async def flush(self):
        for _ in range(50):
            r = await self.backend.post("/flush_cache")
            if r.is_success:
                return
            await asyncio.sleep(0.2)
        raise RuntimeError("flush_cache kept failing")

    async def tenant_api(self, pool, stop, rng):
        while not stop.is_set():
            try:
                await self.ask(rng.choice(pool))
            except httpx.HTTPStatusError:
                await asyncio.sleep(0.05)

    async def tenant_generate(self, pool, stop, rng):
        while not stop.is_set():
            text = json.dumps(rng.choice(pool)["state"])[: rng.randint(100, 4000)]
            await self.backend.post("/generate", json={
                "text": text, "sampling_params": {"max_new_tokens": rng.choice([16, 64, 128]),
                                                  "temperature": 0.8}})


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--loads", default="0,8,32")
    ap.add_argument("--targets", type=int, default=24)
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--gen-fraction", type=float, default=0.25,
                    help="share of background tenants doing free-text generation")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    reqs = load_requests(args.seed)
    targets, pool = reqs[: args.targets], reqs[args.targets:]
    run = Runner(args.api, args.backend)
    rng = random.Random(args.seed)

    # Reference: alone, cold cache.
    refs, fingerprint = {}, None
    for req in targets:
        await run.flush()
        out, ms, fingerprint = await run.ask(req)
        refs[req["id"]] = {"answers": out["answers"], "hash": answer_hash(out["answers"]), "ms": ms}
    print(f"[{args.label}] fingerprint={fingerprint}; references done", flush=True)

    trials = []
    for load in [int(x) for x in args.loads.split(",")]:
        stop = asyncio.Event()
        n_gen = round(load * args.gen_fraction)
        tenants = [asyncio.create_task(run.tenant_generate(pool, stop, random.Random(i)))
                   for i in range(n_gen)]
        tenants += [asyncio.create_task(run.tenant_api(pool, stop, random.Random(100 + i)))
                    for i in range(load - n_gen)]
        await asyncio.sleep(2 if load else 0)  # let the queue fill
        t0 = time.time()
        for rep in range(args.repeats):
            order = targets[:]
            rng.shuffle(order)
            # Targets are sent concurrently with each other as well as with tenants.
            outs = await asyncio.gather(*(run.ask(r) for r in order))
            for req, (out, ms, _) in zip(order, outs):
                ref = refs[req["id"]]
                per_q = {}
                for qid, ans in out["answers"].items():
                    d, p = headline(ans)
                    rd, rp = headline(ref["answers"][qid])
                    per_q[qid] = {"type": ans["type"], "decision": d, "p": p, "ref_decision": rd,
                                  "ref_p": rp, "flip": d != rd, "abs_diff": abs(p - rp)}
                trials.append({"id": req["id"], "load": load, "rep": rep, "ms": ms,
                               "identical": answer_hash(out["answers"]) == ref["hash"],
                               "questions": per_q})
        stop.set()
        for t in tenants:
            t.cancel()
        await asyncio.gather(*tenants, return_exceptions=True)
        rs = [t for t in trials if t["load"] == load]
        qs = [q for t in rs for q in t["questions"].values()]
        print(f"[{args.label}] load={load:3d}: identical {sum(t['identical'] for t in rs)}/{len(rs)}"
              f"  flips {sum(q['flip'] for q in qs)}/{len(qs)}"
              f"  max|dp|={max(q['abs_diff'] for q in qs):.3g}"
              f"  p50={sorted(t['ms'] for t in rs)[len(rs)//2]:.0f}ms ({time.time()-t0:.0f}s)",
              flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"label": args.label, "fingerprint": fingerprint, "args": vars(args),
               "references": refs, "trials": trials}, open(args.out, "w"))


if __name__ == "__main__":
    asyncio.run(main())
