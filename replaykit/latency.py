"""Closed-loop latency for any backend on a task's requests (fresh items per level, no repeats)."""
import argparse, asyncio, json, time
from pathlib import Path
from replaykit.client import Backend, Client, body_bytes
from tasks.guardrails.battery import request
from tasks.guardrails.datasets import load

ROOT = Path(__file__).resolve().parents[1]

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["hosted", "local"], required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8020")
    ap.add_argument("--name", required=True)
    ap.add_argument("--levels", default="1,8,32")
    ap.add_argument("--per-level", type=int, default=96)
    args = ap.parse_args()
    b = (Backend.hosted(ROOT / "typesafe_apikey.txt", concurrency=64) if args.backend == "hosted"
         else Backend.local(args.name, args.url, concurrency=64))
    c = Client(b)
    items = load()
    out = []
    for li, conc in enumerate(int(x) for x in args.levels.split(",")):
        chunk = items[li * args.per_level:(li + 1) * args.per_level]
        q, lat = list(chunk), []
        async def worker():
            while q:
                it = q.pop()
                t = time.perf_counter()
                await c.ask(body_bytes(request(it["text"], b.model)))
                lat.append((time.perf_counter() - t) * 1000)
        t0 = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(conc)))
        wall = time.perf_counter() - t0
        lat.sort()
        row = {"concurrency": conc, "n": len(lat), "p50_ms": lat[len(lat) // 2], "p99_ms": lat[int(len(lat) * .99)],
               "messages_per_s": len(lat) / wall}
        out.append(row)
        print(f"[{args.name}] c={conc:3d} p50 {row['p50_ms']:.0f} ms p99 {row['p99_ms']:.0f} ms {row['messages_per_s']:.1f} msg/s", flush=True)
    p = ROOT / "results/guardrails" / args.name / "latency.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out))
    await c.close()

if __name__ == "__main__":
    asyncio.run(main())
