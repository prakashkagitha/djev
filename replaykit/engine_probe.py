"""E0: engine-level batch-invariance probe for the System One workload.

For each target prompt we take a reference readout alone (batch of one), then
repeat the *identical* request while other traffic shares the GPU: background
prompts of random length, some decoding up to 64 tokens so prefill and decode
batches mix, exactly what a busy multi-tenant server looks like.

The readout is what a Jev-style server consumes: the next-token logprobs of a
fixed set of label tokens (`token_ids_logprob`) plus the top-20 distribution.
Every returned float is compared bit-for-bit (repr of the float64 SGLang emits).

Usage: python engine_probe.py --port 30010 --model Qwen/Qwen3-8B --out results/e0_x.json
"""

import argparse
import asyncio
import json
import random
import struct
import time
from pathlib import Path

import httpx
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]


def bits(x: float) -> str:
    return struct.pack(">d", float(x)).hex()


def load_prompts(n: int, seed: int) -> list[str]:
    rows = [json.loads(line) for line in open(ROOT / "nimble/data/eval.jsonl")]
    rng = random.Random(seed)
    rng.shuffle(rows)
    prompts = []
    for row in rows[:n]:
        inp = row["input"]
        q = next(iter(inp["questions"].values()))
        opts = q.get("criteria") or {"true": "yes", "false": "no"}
        if isinstance(opts, list):
            opts = {str(i): d for i, d in enumerate(opts)}
        letters = "ABCDEFGHIJKLMNOP"
        lines = [f"{letters[i]}: {d}" for i, d in enumerate(opts.values())]
        prompts.append(
            "<|im_start|>user\nState:\n" + json.dumps(inp["state"], ensure_ascii=False)
            + "\n\nQuestion: " + json.dumps(q["instructions"], ensure_ascii=False)
            + "\nOptions:\n" + "\n".join(lines)
            + "\nAnswer with one letter.<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\nAnswer:"
        )
    return prompts


class Probe:
    def __init__(self, port: int, label_ids: list[int]):
        self.client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=600,
                                        limits=httpx.Limits(max_connections=512))
        self.label_ids = label_ids

    async def readout(self, text: str) -> dict:
        payload = {
            "text": text,
            "sampling_params": {"max_new_tokens": 1, "temperature": 0.0},
            "return_logprob": True, "logprob_start_len": -1,
            "token_ids_logprob": self.label_ids, "top_logprobs_num": 20,
        }
        r = await self.client.post("/generate", json=payload)
        r.raise_for_status()
        meta = r.json()["meta_info"]
        sel = {tid: v for v, tid, *_ in meta["output_token_ids_logprobs"][0]}
        top = [(tid, v) for v, tid, *_ in meta["output_top_logprobs"][0]]
        return {"labels": [sel[t] for t in self.label_ids], "top": top,
                "cached": meta.get("cached_tokens")}

    async def background(self, text: str, max_new: int):
        payload = {"text": text, "sampling_params": {"max_new_tokens": max_new, "temperature": 0.7}}
        r = await self.client.post("/generate", json=payload)
        r.raise_for_status()

    async def flush(self):
        await self.client.post("/flush_cache")


def fingerprint(out: dict) -> str:
    return "|".join(bits(v) for v in out["labels"]) + "#" + "|".join(
        f"{t}:{bits(v)}" for t, v in out["top"])


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--targets", type=int, default=8)
    ap.add_argument("--trials", type=int, default=12)
    ap.add_argument("--loads", default="0,1,4,16,64")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model)
    label_ids = [tok.encode(f" {c}", add_special_tokens=False)[-1] for c in "ABCDEFGH"]
    label_ids = sorted(set(label_ids + [tok.encode(c, add_special_tokens=False)[-1] for c in "ABCDEFGH"]))
    pool = load_prompts(200, args.seed)
    targets, others = pool[: args.targets], pool[args.targets:]
    probe = Probe(args.port, label_ids)
    rng = random.Random(args.seed)
    loads = [int(x) for x in args.loads.split(",")]

    results = []
    t0 = time.time()
    for ti, target in enumerate(targets):
        await probe.flush()
        ref = await probe.readout(target)  # alone, cold cache
        ref_fp = fingerprint(ref)
        for load in loads:
            for trial in range(args.trials):
                cache = "cold" if trial % 2 == 0 else "warm"
                if cache == "cold":
                    await probe.flush()
                bg = [probe.background(rng.choice(others)[: rng.randint(200, 6000)],
                                       rng.choice([1, 8, 32, 64])) for _ in range(load)]
                # Stagger the target randomly inside the background burst.
                async def delayed():
                    await asyncio.sleep(rng.random() * 0.05 * min(load, 8))
                    return await probe.readout(target)
                outs = await asyncio.gather(delayed(), *bg)
                out = outs[0]
                diffs = [abs(a - b) for a, b in zip(out["labels"], ref["labels"])]
                results.append({
                    "target": ti, "load": load, "trial": trial, "cache": cache,
                    "cached_tokens": out["cached"],
                    "identical": fingerprint(out) == ref_fp,
                    "max_abs_diff": max(diffs),
                    "argmax_flip": max(range(len(diffs)), key=lambda i: out["labels"][i])
                    != max(range(len(diffs)), key=lambda i: ref["labels"][i]),
                    "labels": out["labels"], "ref_labels": ref["labels"],
                })
        done = [r for r in results if r["target"] == ti]
        print(f"target {ti}: identical {sum(r['identical'] for r in done)}/{len(done)} "
              f"max|d|={max(r['max_abs_diff'] for r in done):.3g} ({time.time()-t0:.0f}s)", flush=True)

    summary = {}
    for load in loads:
        rs = [r for r in results if r["load"] == load]
        summary[str(load)] = {
            "n": len(rs), "identical": sum(r["identical"] for r in rs),
            "max_abs_diff": max(r["max_abs_diff"] for r in rs),
            "argmax_flips": sum(r["argmax_flip"] for r in rs),
        }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump({"model": args.model, "port": args.port, "label_ids": label_ids,
               "summary": summary, "results": results}, open(args.out, "w"))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
