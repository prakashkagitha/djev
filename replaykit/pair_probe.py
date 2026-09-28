"""E3 bisection tool: is the target's readout invariant to *who shares its forward pass*?

A list-valued /generate call is scheduled as one batch, so [target, companion] guarantees
the target is prefilled together with a companion of a chosen length. Cache is flushed
before every call, so only batch composition varies. Fast (seconds per config).

Usage: python pair_probe.py --port 30010 --model PATH [--targets 4]
"""

import argparse
import json
import random
import struct

import httpx
from transformers import AutoTokenizer

from replaykit.engine_probe import load_prompts


def bits(xs):
    return [struct.pack(">d", float(x)).hex() for x in xs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=30010)
    ap.add_argument("--model", required=True)
    ap.add_argument("--targets", type=int, default=4)
    ap.add_argument("--out")
    args = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(args.model)
    labels = sorted({tok.encode(c, add_special_tokens=False)[-1] for c in "ABCDEFGH"})
    c = httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=600)
    prompts = load_prompts(60, 0)
    rng = random.Random(1)

    def readout(texts, warm=()):
        c.post("/flush_cache").raise_for_status()
        for w in warm:  # populate the radix/mamba cache first
            c.post("/generate", json={"text": w, "sampling_params": {"max_new_tokens": 1},
                                      "return_logprob": True, "token_ids_logprob": [0]})
        r = c.post("/generate", json={
            "text": texts, "sampling_params": {"max_new_tokens": 1, "temperature": 0.0},
            "return_logprob": True, "logprob_start_len": -1, "token_ids_logprob": labels})
        r.raise_for_status()
        out = r.json()
        out = out if isinstance(out, list) else [out]
        return [[v for v, *_ in o["meta_info"]["output_token_ids_logprobs"][0]] for o in out]

    rows = []
    for ti, target in enumerate(prompts[: args.targets]):
        ref = readout([target])[0]
        for clen in [8, 64, 100, 500, 2000, 6000]:
            comp = prompts[20 + rng.randrange(40)] * 4
            comp = tok.decode(tok.encode(comp)[:clen])
            for order in ("target_first", "target_last"):
                texts = [target, comp] if order == "target_first" else [comp, target]
                got = readout(texts)[0 if order == "target_first" else 1]
                same = bits(got) == bits(ref)
                rows.append({"target": ti, "companion_len": clen, "order": order, "identical": same,
                             "max_abs_diff": max(abs(a - b) for a, b in zip(got, ref))})
        # Same target twice in one batch, and a batch of 8 unrelated companions.
        got = readout([target, target])
        rows.append({"target": ti, "companion_len": "self", "order": "pair",
                     "identical": bits(got[0]) == bits(ref) and bits(got[1]) == bits(ref),
                     "max_abs_diff": max(abs(a - b) for g in got for a, b in zip(g, ref))})
        # (1) companion resumes from a cached prefix (it carries an initial recurrent state).
        comp = prompts[30]
        cids = tok.encode(comp)
        for k in (64, 500, 1000):
            got = readout([target, comp], warm=[tok.decode(cids[:k])])[0]
            rows.append({"target": ti, "companion_len": f"cached_prefix_{k}", "order": "target_first",
                         "identical": bits(got) == bits(ref),
                         "max_abs_diff": max(abs(a - b) for a, b in zip(got, ref))})
        # (2) the target itself resumes from a cached partial prefix.
        tids = tok.encode(target)
        for k in (64, 100, 500, len(tids) // 2):
            got = readout([target], warm=[tok.decode(tids[:k])])[0]
            rows.append({"target": ti, "companion_len": f"self_prefix_{k}", "order": "alone",
                         "identical": bits(got) == bits(ref),
                         "max_abs_diff": max(abs(a - b) for a, b in zip(got, ref))})
        many = [target] + [prompts[20 + i] for i in range(8)]
        got = readout(many)[0]
        rows.append({"target": ti, "companion_len": "8x", "order": "target_first",
                     "identical": bits(got) == bits(ref),
                     "max_abs_diff": max(abs(a - b) for a, b in zip(got, ref))})
    n_same = sum(r["identical"] for r in rows)
    print(f"pair probe: identical {n_same}/{len(rows)}")
    for r in rows:
        if not r["identical"]:
            print("  DIFF", r)
    if args.out:
        json.dump(rows, open(args.out, "w"))


if __name__ == "__main__":
    main()
