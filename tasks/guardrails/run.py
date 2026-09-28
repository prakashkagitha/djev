"""Screen every item with the cookbook's input battery, R times, identical bytes each time.

Repeats are spread out in time (round r of all items, then round r+1), the way an
attacker's retries or a CI rerun would arrive. Results stream to calls.jsonl and a rerun
resumes where it stopped.

  python -m tasks.guardrails.run --backend hosted --repeats 10
  python -m tasks.guardrails.run --backend local --url http://127.0.0.1:8020 --name detjev --repeats 5
"""

import argparse
import asyncio
import json
from pathlib import Path

import orjson

from replaykit.client import Backend, Client, body_bytes
from tasks.guardrails.battery import BATTERY_VERSION, assess, request
from tasks.guardrails.datasets import load

ROOT = Path(__file__).resolve().parents[2]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["hosted", "local"], required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8020")
    ap.add_argument("--name", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if args.backend == "hosted":
        backend = Backend.hosted(ROOT / "typesafe_apikey.txt", model=args.model or "jev-1.13.0",
                                 concurrency=args.concurrency)
    else:
        backend = Backend.local(args.name or "local", args.url, model=args.model or "nimble-latest",
                                concurrency=args.concurrency)
    name = args.name or backend.name
    out_dir = ROOT / "results/guardrails" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    calls = out_dir / "calls.jsonl"
    done = set()
    if calls.exists():
        for line in calls.open():
            r = json.loads(line)
            done.add((r["id"], r["rep"]))
    items = load()[: args.limit]
    raw = {it["id"]: body_bytes(request(it["text"], backend.model)) for it in items}
    client = Client(backend)
    (out_dir / "config.json").write_text(json.dumps(
        {"backend": name, "base_url": backend.base_url, "model": backend.model, "repeats": args.repeats,
         "battery": BATTERY_VERSION, "items": len(items)}, indent=1))

    with calls.open("a") as f:
        for rep in range(args.repeats):
            todo = [it for it in items if (it["id"], rep) not in done]
            if not todo:
                continue

            async def one(it):
                res = await client.ask(raw[it["id"]])
                row = {"id": it["id"], "rep": rep, **{k: res.get(k) for k in
                                                      ("model", "ms", "hash", "fingerprint", "status")}}
                if "answers" in res:
                    row.update(assess(res["answers"]))
                else:
                    row["error"] = res.get("error")
                f.write(orjson.dumps(row).decode() + "\n")
                return row

            rows = await asyncio.gather(*(one(it) for it in todo))
            f.flush()
            errors = sum("error" in r for r in rows)
            ms = sorted(r["ms"] for r in rows if r.get("ms"))
            print(f"[{name}] round {rep + 1}/{args.repeats}: {len(rows)} calls, {errors} errors, "
                  f"p50 {ms[len(ms) // 2] if ms else 0:.0f} ms", flush=True)
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
