# Evidence

Detailed results behind the README. All runs were on 2026-09-28 on one H100 NVL. Raw files are in `results/`, and `scripts/run_*.sh` hold the exact command sequences.

**Terms.**
- *Default serving*: the same model, prompt compiler, API and GPU as djev, with SGLang's default (non-deterministic) mode.
- *Identical bytes*: every repeat sends exactly the same request body.

## 1. Serving level: Nimble's 324 held-out Jev-format requests (146 choice, 114 noul, 64 score)

| Claim | Default serving | djev | Files (`results/core/`) |
|---|---|---|---|
| Repeats bit-identical to a solo, cold-cache reference, with 0 / 8 / 32 background tenants (24 requests × 30 repeats) | 12 / 720 | **720 / 720** | `e12_det_off.json`, `e12_final_on.json` |
| Golden file of 324 decisions replayed after a server restart | 1 / 324 | **324 / 324** | `e7_det_off_restart.json`, `e7_det_on_restart.json` |
| Replayed on a second H100, in a new arrival order, from a new build, and through the response memo | | **324 / 324 each** | `e7_det_on_gpu4.json`, `e7_det_on_same.json`, `e7_final_on*.json` |
| Accuracy | 282 / 324 (87.0%) | 282 / 324 (87.0%) | `e5_det_off.json`, `e5_det_on.json` |
| Brier / log loss / ECE | 0.2021 / 0.3877 / 0.0980 | 0.2011 / 0.3857 / 0.0978 | same |
| Median single decision, fresh requests | 50 ms | 51 ms | `e4f_off_fastpath.json`, `e4f_on.json` |
| Decisions/s at 32 concurrent, fresh requests | 45.7 | 45.2 | same |
| Decisions/s on exact repeats with `--memo` | not safe to memoize | 344 | `e4f_on_memo.json` |

## 2. Engine level: label log-probs, 6 targets × 5 load levels (0–64 tenants) × 10 trials

| Model and configuration | Bit-identical | Files |
|---|---|---|
| Qwen3-8B (dense), deterministic off | 121 / 300 | `e0_qwen3_8b_nodet.json` |
| Qwen3-8B, `--enable-deterministic-inference` | 300 / 300 | `e0_qwen3_8b_det.json` |
| Nimble-9B (hybrid), deterministic off | 109 / 300 | `e0_nimble_nodet.json` |
| Nimble-9B, deterministic on (stock SGLang) | 278 / 300 | `e0_nimble_det.json` |
| … + triton backend / + aligned splits only | 284 / 283 | `e3_*.json` |
| **Nimble-9B + djev patches** | **300 / 300** | `e3b_nimble_det_patched.json` |
| Pair probe (target batched with companions, or resumed from its own cached prefix), before / after the patch | 76 / 84 → **84 / 84** | `e3b_pair_patched.json` |

## 3. TypeSafe self-consistency cookbooks: full tables
Metrics follow the cookbooks' published definitions (`tasks/typesafe_consistency/metrics.py`). Each condition is 15 calls: identical bytes or a fresh `uid` per call (TypeSafe's protocol), sent one after another or concurrently. The raw data is in `results/typesafe_consistency/`.

**Moderation cookbook (8 choice questions)**
| Condition | raw agree | policy agree (≥ 0.60) | uncertain | mean prob std | distinct answer sets |
|---|---|---|---|---|---|
| Jev 1.13, published by TypeSafe (fresh `uid`, 2026-09-11) | 90.8% | 99.2% | 25.8% | 0.0098 | not reported |
| Hosted Jev 1.13, fresh `uid`, sequential | 90.8% | 100.0% | 25.0% | 0.0074 | 15 / 15 |
| Hosted Jev 1.13, identical bytes, sequential | 95.0% | 99.2% | 25.8% | 0.0092 | 15 / 15 |
| Hosted Jev 1.13, identical bytes, concurrent | 89.2% | 100.0% | 25.0% | 0.0083 | 15 / 15 |
| Default serving, identical bytes, sequential / concurrent | 100.0% | 100.0% | 25.0% | 0.0019 / 0.0011 | 5 / 15 · 15 / 15 |
| **djev, identical bytes, sequential / concurrent** | 100.0% | 100.0% | 25.0% | **0.0000** | **1 / 15 · 1 / 15** |
| djev, fresh `uid` | 100.0% | 100.0% | 25.0% | 0.0035 | 15 / 15 |

**Insurance cookbook (14 noul questions)**
| Condition | raw agree | policy agree (0.30–0.70 band) | mean prob std | questions crossing 0.5 | distinct answer sets |
|---|---|---|---|---|---|
| Jev 1.13, published by TypeSafe | not reported | not reported | 0.0102 | 1 | not reported |
| Hosted Jev 1.13, fresh `uid`, sequential | 96.2% | 99.0% | 0.0097 | 2 | 15 / 15 |
| Hosted Jev 1.13, identical bytes, sequential | 97.1% | 100.0% | 0.0099 | 1 (`covered` 6 yes / 9 no) | 15 / 15 |
| Default serving, identical bytes, sequential / concurrent | 100.0% | 100.0% | 0.0001 / 0.0005 | 0 | 2 / 15 · 10 / 15 |
| **djev, identical bytes** | 100.0% | 100.0% | **0.0000** | 0 | **1 / 15** |
| djev, fresh `uid` | 98.6% | 100.0% | 0.0068 | 1 (`fraud_flag`) | 15 / 15 |

## 4. Guardrails: full results
The cards are in `results/guardrails/<backend>/card_{strict,permissive}.json`, and the per-call rows in `calls.jsonl`.

| Strict policy | Hosted Jev 1.13 (10 calls/message) | Default serving (5) | djev (5) |
|---|---|---|---|
| Plurality agreement | 99.5% | 99.8% | 100% |
| Messages whose action changed | 44 | 16 | 0 |
| Unsafe messages passed on some calls only | 15 / 954 | 4 / 954 | 0 / 954 |
| Bit-identical across repeats | 9.7% | 0.0% | 100% |
| Recall / false-positive rate / F1 | 68.4% / 10.6% / 0.749 | 74.5% / 10.2% / 0.791 | 74.4% / 10.3% / 0.791 |
| Unsafe pass rate within 1 → 30 retries | 31.6% → 32.4% | 25.5% → 25.7% | 25.6% → 25.6% |
| Median latency, one guard call at a time | not compared | 121 ms | 122 ms |

Permissive policy: hosted Jev 48 changed actions and 15 leaky; djev 0 and 0. The F1 by source and the per-source flips are in the cards.

## 5. Invariance: meaning-preserving edits (`results/core/e6_*`)
| Edit | Decision flips | With `--canonicalize` |
|---|---|---|
| Keys in `state` reordered | 19 / 324 | 0 |
| Choice options reversed | 9 / 146 | 9 / 146 |
| Random `uid` added to state | 4 / 144 | 4 / 144 |
| Extra whitespace | 0 / 324 | 0 |

## 6. Cost notes
Batch-invariant kernels cost almost nothing on this workload: one short prefill and a single token read per question. The patch gives up engine-level reuse of a cached prompt when the exact same request repeats; the exact response memo recovers that. An early benchmark that replayed the same requests at every load level suggested a 2.6× throughput loss. That came from cache hits on repeats, and the fair runs with fresh requests are the `e4f_*` files.
