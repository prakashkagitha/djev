"""E8: replay TypeSafe's two consistency cookbooks against our server.

TypeSafe ran one state x 15 sequential calls, injecting a fresh `uid` into `state` on
every call (research/cookbooks/README.md). We run both protocols:
  identical : the exact same bytes 15 times      -> isolates run-to-run noise
  uid       : TypeSafe's protocol, fresh uid/call -> noise + sensitivity to the nuisance field
Each protocol runs on an idle server and under background load (--busy N tenants).

Usage: python cookbook.py --api http://127.0.0.1:8020 --label det_on --out results/e8_det_on.json
"""

import argparse
import asyncio
import copy
import json
import random
import statistics
from pathlib import Path

import httpx
import orjson

ROOT = Path(__file__).resolve().parents[2]
CB = Path(__file__).resolve().parent / "requests"
RUBRIC_HASH = "fa84120d8444"


def make_uid(kind, i, rng):
    token = "%08x" % rng.getrandbits(32)
    return f"{i}:{token}" if kind == "noul" else f"{RUBRIC_HASH}:{i}:{token}"


def headline(ans):
    if ans["type"] == "noul":
        return ans["noul"], "true" if ans["noul"] >= 0.5 else "false"
    return ans["probabilities"][ans["choice"]], ans["choice"]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeats", type=int, default=15)
    ap.add_argument("--busy", type=int, default=16)
    args = ap.parse_args()

    client = httpx.AsyncClient(base_url=args.api, timeout=600,
                               limits=httpx.Limits(max_connections=256))
    pool = [{"model": "nimble-latest", **json.loads(line)["input"]}
            for line in open(ROOT / "nimble/data/eval.jsonl")]

    async def ask(body):
        r = await client.post("/v1/systemone", content=orjson.dumps(body),
                              headers={"Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()["answers"]

    async def tenant(stop, rng):
        while not stop.is_set():
            try:
                await ask(rng.choice(pool))
            except httpx.HTTPError:
                await asyncio.sleep(0.05)

    out = {"label": args.label, "runs": []}
    for kind in ("noul", "choice"):
        base = json.loads((CB / f"{kind}_request.json").read_text())
        base["model"] = "nimble-latest"
        for condition in ("idle", "busy"):
            stop = asyncio.Event()
            tenants = [asyncio.create_task(tenant(stop, random.Random(i)))
                       for i in range(args.busy if condition == "busy" else 0)]
            await asyncio.sleep(1 if tenants else 0)
            for protocol in ("identical", "uid"):
                rng = random.Random(7)
                repeats = []
                for i in range(args.repeats):  # sequential, like the cookbooks
                    body = copy.deepcopy(base)
                    if protocol == "uid":
                        body["state"]["uid"] = make_uid(kind, i, rng)
                    answers = await ask(body)
                    repeats.append({q: dict(zip(("p", "label"), headline(a))) for q, a in answers.items()})
                per_q = {}
                for q in repeats[0]:
                    ps = [r[q]["p"] for r in repeats]
                    labels = [r[q]["label"] for r in repeats]
                    per_q[q] = {"p": ps, "labels": labels, "std": statistics.pstdev(ps),
                                "min": min(ps), "max": max(ps), "distinct_values": len(set(ps)),
                                "label_counts": {lab: labels.count(lab) for lab in set(labels)}}
                mean_std = statistics.mean(v["std"] for v in per_q.values())
                flips = sum(len(v["label_counts"]) > 1 for v in per_q.values())
                print(f"[{args.label}] {kind:6s} {condition:4s} {protocol:9s} mean std {mean_std:.5f}  "
                      f"questions with >1 label: {flips}/{len(per_q)}", flush=True)
                out["runs"].append({"kind": kind, "condition": condition, "protocol": protocol,
                                    "mean_std": mean_std, "flipping_questions": flips,
                                    "questions": per_q})
            stop.set()
            for t in tenants:
                t.cancel()
            await asyncio.gather(*tenants, return_exceptions=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(args.out, "w"))


if __name__ == "__main__":
    asyncio.run(main())
