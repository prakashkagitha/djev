"""TypeSafe's two self-consistency cookbooks, replayed against any backend.

Requests are rebuilt verbatim from docs.typesafe.ai (cookbooks/consistency_noul_cookbook,
consistency_choice_cookbook); see requests/README.md. Four conditions, 15 calls each:
  identical/sequential   same bytes, one after another           (pure run-to-run noise)
  identical/concurrent   same bytes, all at once                 (noise under batching)
  uid/sequential         TypeSafe's protocol: fresh uid per call (noise + uid sensitivity)
  uid/concurrent

  python -m tasks.typesafe_consistency.run --backend hosted
  python -m tasks.typesafe_consistency.run --backend local --url http://127.0.0.1:8020 --name detjev
"""

import argparse
import asyncio
import copy
import json
import random
import statistics as st
from pathlib import Path

from replaykit.client import Backend, Client, body_bytes
from tasks.typesafe_consistency.metrics import choice_metrics, noul_metrics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUBRIC_HASH = "fa84120d8444"


def uid(kind, i, rng):
    token = "%08x" % rng.getrandbits(32)
    return f"{i}:{token}" if kind == "noul" else f"{RUBRIC_HASH}:{i}:{token}"


def decision(a):
    if a["type"] == "noul":
        return ("true" if a["noul"] >= 0.5 else "false"), a["noul"]
    return a["choice"], a["probabilities"][a["choice"]]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["hosted", "local"], required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8020")
    ap.add_argument("--name")
    ap.add_argument("--model")
    ap.add_argument("--repeats", type=int, default=15)
    args = ap.parse_args()
    if args.backend == "hosted":
        backend = Backend.hosted(ROOT / "typesafe_apikey.txt", model=args.model or "jev-1.13.0", concurrency=15)
    else:
        backend = Backend.local(args.name or "local", args.url, model=args.model or "nimble-latest", concurrency=15)
    name = args.name or backend.name
    client = Client(backend)
    out = {"backend": name, "model": backend.model, "conditions": []}
    for kind in ("noul", "choice"):
        base = json.loads((HERE / f"requests/{kind}_request.json").read_text())
        base["model"] = backend.model
        for protocol in ("identical", "uid"):
            rng = random.Random(7)
            bodies = []
            for i in range(args.repeats):
                b = copy.deepcopy(base)
                if protocol == "uid":
                    b["state"]["uid"] = uid(kind, i, rng)
                bodies.append(body_bytes(b))
            for mode in ("sequential", "concurrent"):
                if mode == "sequential":
                    res = [await client.ask(b) for b in bodies]
                else:
                    res = await asyncio.gather(*(client.ask(b) for b in bodies))
                qs = {}
                for q in res[0]["answers"]:
                    ds = [decision(r["answers"][q]) for r in res]
                    labels = [d[0] for d in ds]
                    qs[q] = {"p": [d[1] for d in ds], "labels": labels,
                             "counts": {l: labels.count(l) for l in sorted(set(labels))}}
                draws = [r["answers"] for r in res]
                ts = (noul_metrics if kind == "noul" else choice_metrics)(draws)
                cond = {"kind": kind, "protocol": protocol, "mode": mode, "typesafe_metrics": ts, "draws": draws,
                        "distinct_answer_sets": len({r["hash"] for r in res}), "n": len(res),
                        "mean_std": st.mean(st.pstdev(v["p"]) for v in qs.values()),
                        "flipping": [q for q, v in qs.items() if len(v["counts"]) > 1],
                        "plurality_agreement": st.mean(max(v["counts"].values()) / len(res) for v in qs.values()),
                        "models": sorted({r["model"] for r in res if r.get("model")}),
                        "p50_ms": sorted(r["ms"] for r in res)[len(res) // 2], "questions": qs}
                out["conditions"].append(cond)
                print(f"[{name}] {kind:6s} {protocol:9s} {mode:10s} distinct {cond['distinct_answer_sets']:2d}/{len(res)} "
                      f"raw {ts['raw_agree']:.1%} policy {ts['policy_agree']:.1%} unc {ts['uncertain']:.1%} "
                      f"conf {ts['conflicts']} std {ts['mean_std']:.4f} max {ts['max_std']:.4f}", flush=True)
    path = ROOT / "results/typesafe_consistency" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
