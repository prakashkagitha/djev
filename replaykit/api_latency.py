"""E4: what does determinism cost? Closed-loop latency/throughput of /v1/systemone.

For each concurrency c, c workers send eval requests back-to-back (one question each,
as in Jev's typical "smart if-statement" call) for --requests total; we report
p50/p90/p99 end-to-end latency and decisions/second.

Usage: python latency.py --api http://127.0.0.1:8020 --label det_on --out results/e4_det_on.json
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx
import orjson

ROOT = Path(__file__).resolve().parents[1]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--concurrency", default="1,4,16,32")
    ap.add_argument("--requests", type=int, default=80,
                    help="per level; cold levels use disjoint request slices")
    ap.add_argument("--backend", help="SGLang URL; if set, flush its cache before each level")
    ap.add_argument("--repeat-pass", action="store_true",
                    help="after the cold levels, replay the same requests at the top concurrency")
    args = ap.parse_args()
    reqs = [orjson.dumps({"model": "nimble-latest", **json.loads(line)["input"]})
            for line in open(ROOT / "nimble/data/eval.jsonl")]
    client = httpx.AsyncClient(base_url=args.api, timeout=600, limits=httpx.Limits(max_connections=256))
    for body in reqs[:8]:  # warm up kernels / JIT
        await client.post("/v1/systemone", content=body, headers={"Content-Type": "application/json"})
    out = {"label": args.label, "levels": []}
    backend = httpx.AsyncClient(base_url=args.backend, timeout=60) if args.backend else None
    levels = [(int(x), "cold") for x in args.concurrency.split(",")]
    if args.repeat_pass:
        levels.append((levels[-1][0], "repeat"))
    for li, (c, phase) in enumerate(levels):
        offset = (li if phase == "cold" else li - 1) * args.requests + 8
        if backend is not None and phase == "cold":
            await backend.post("/flush_cache")
            await asyncio.sleep(0.5)
        lat, i = [], 0
        lock = asyncio.Lock()

        async def worker():
            nonlocal i
            while True:
                async with lock:
                    if i >= args.requests:
                        return
                    body = reqs[(offset + i) % len(reqs)]
                    i += 1
                t = time.perf_counter()
                r = await client.post("/v1/systemone", content=body,
                                      headers={"Content-Type": "application/json"})
                r.raise_for_status()
                lat.append((time.perf_counter() - t) * 1000)

        t0 = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(c)))
        wall = time.perf_counter() - t0
        level = {"concurrency": c, "phase": phase, "n": len(lat), "p50_ms": pct(lat, 0.5), "p90_ms": pct(lat, 0.9),
                 "p99_ms": pct(lat, 0.99), "mean_ms": sum(lat) / len(lat),
                 "decisions_per_s": len(lat) / wall}
        out["levels"].append(level)
        print(f"[{args.label}] {phase:6s} c={c:3d} p50 {level['p50_ms']:.0f}ms p99 {level['p99_ms']:.0f}ms "
              f"{level['decisions_per_s']:.1f} dec/s", flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(args.out, "w"))


if __name__ == "__main__":
    asyncio.run(main())
