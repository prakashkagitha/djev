# Deterministic Jev: plan

Goal: a self-hosted, Jev-wire-compatible System One server (`POST /v1/systemone`; noul/choice/score).
For a fixed deployment fingerprint, the same request must return a **bitwise-identical response**,
no matter what else is running concurrently or what is in the cache. Budget: **one H100 NVL (GPU 3)**.

## Why this is worth doing
TypeSafe's own consistency cookbooks show hosted Jev is *not* deterministic. In one run a noul answer
ranged from 0.43 to 0.53 across repeats, crossing the 0.5 decision threshold, and two choice questions
changed labels. TypeSafe says "no condition achieved perfect determinism". Their open
`system-one-adapter-python` asks a chat LLM to *write* probabilities into JSON, leaves temperature and
seed at provider defaults, and does no logprob readout. So the claim "same input, same decision,
bit-for-bit" is open, and it can be measured.

## Landscape (surveyed 2026-09-28; clones in the session scratchpad `repos/`)
| Repo | Readout | Backend | Verdict |
|---|---|---|---|
| **ekzhang/openjev-sglang** (333★) | prefill-only, one label token, `token_ids_logprob` softmax | **SGLang** | **Base.** Only native SGLang impl; full Jev wire API; ~1.5k LOC + tests; evals vs real Jev |
| **bespokelabsai/nimble** (1.9k★) | same readout, Qwen3.5-9B + LoRA, fitted temperature | ekzhang's server | **Model.** 90.1% vs Jev 93.2% on its held-out set; dense 9B (~18 GB) |
| TheoLeeCJ/SemIf (4.5k★) | final-position letter logits, HF/MLX | no server | Borrow eval matrix + batch-drift methodology (6/777 flips measured) |
| zhangcy122/OpenJev | top-20 logprobs via OpenAI API | client only | Borrow `repro_parallel_nondeterminism.py`; order-invariant mode |
| Zefan-Cai/Open-Jev, Mapika/decider | LoRA + scalar head / calibration RL | HF / vLLM | Candidate 2nd models later; need custom head path in SGLang |
| razorback16/openjev | DiffusionGemma masked slots | vLLM fork | Out of scope (diffusion, stochastic re-reads) |
| daseinlabs/open-jev | multi-token option log-likelihood | MLX/torch | Doesn't map onto the single-token path |

## Determinism mechanism
SGLang `--enable-deterministic-inference`:
- batch-invariant mm/bmm/log_softmax/RMSNorm
- fixed-split attention
- CUDA graphs kept on
- radix cache kept on with **fa3/triton** (with flashinfer it is force-disabled)

Published overhead is ~27–36% end-to-end (FA3, H200).

**Caveat:** SGLang's CI only asserts bitwise *output*-token logprobs. Prefill/`token_ids_logprob`
determinism is covered by manual test modes only, so E0 must verify it.

Nondeterminism sources in ekzhang/Nimble today:
1. N+1 concurrent branch requests, so batch composition varies.
2. Radix-cache hit vs miss for the shared state prefix.
3. Qwen3.5/3.6 hybrid Gated-DeltaNet layers plus the mamba `extra_buffer` state cache. It is unknown whether these are batch-invariant; **main technical risk**.
4. Nimble's launcher uses `flashinfer`, so it must be switched to fa3/triton.

Known porting work:
- ekzhang's profile is Blackwell-only (NVFP4, `trtllm_mha`, fp8 KV) → add an H100 BF16 profile.
- Both pin **SGLang 0.5.19**. The local env is an April-2026 dev build (`3cfd1561d`) → create a separate `detjev` env on 0.5.19 rather than touching the existing `sglang` env.

## Determinism contract
Define `fingerprint = hash(model weights rev, sglang version, GPU SKU, TP, dtype, server flags, prompt-compiler version)`.
Claim: same fingerprint + same request → identical `answers` JSON (probabilities compared as float64 bits).
Expose the fingerprint in `answers[*].stats` / a response header. Nothing is claimed across fingerprints; E7 measures that separately.

## Experiments (all on GPU 3, `CUDA_VISIBLE_DEVICES=3`)

**E0: Environment and engine self-check (½ day)**
- Build the `detjev` env (SGLang 0.5.19, fa3).
- Run `sglang.test.test_deterministic --test-mode {single,mixed,prefix,p_vs_d,radix_cache} --return-logprob` on
  (a) Qwen3-8B (dense, CI-validated control) and (b) Qwen3.5-9B (hybrid GDN).
- Exit: Qwen3-8B passes all modes. The Qwen3.5-9B result decides whether E3 is needed.

**E1: Baseline nondeterminism, deterministic mode OFF (½ day)**
- Setup: ekzhang server + Nimble-9B, H100 BF16 profile. `detjev-bench` harness.
- Test set: ~200 requests (Nimble held-out + BoolQ + TheoLeeCJ TypeSafe subset), all three question types, 2–64 options.
- Each request is repeated 50× under a grid:
  - background concurrency {0, 4, 16, 32}
  - cache {cold (flush), warm}
  - state length {short, > chunked-prefill size}
- Metrics:
  - % bitwise-identical responses
  - max/mean |Δp|
  - argmax-flip rate
  - noul 0.5-threshold crossings
  - score EV spread
- Expected: nonzero drift that matches TheoLeeCJ's ~0.8% flips. This is the headline "before".

**E2: Deterministic mode ON (1 day)**
- Same grid with `--enable-deterministic-inference`. Target: 100% bitwise identical, 0 flips.
- Ablations:
  - attention backend: fa3 vs triton
  - radix on/off
  - branch fan-out serial vs concurrent
  - CUDA graph on/off
- Exit: fa3 + radix cache on passes the full grid.

**E3: Hybrid-architecture fix (conditional, 1–3 days)**
- Only if E0(b)/E2 fail. Bisect by layer type: hook hidden states per layer, run the same prompt at bs=1 vs mixed batch, and find the first divergent layer.
- Likely culprits:
  - GDN chunked-scan kernels (chunk alignment tied to batch)
  - mamba state cache hit/miss path
- Fixes, in order of effort:
  1. Fixed chunk alignment / `truncation_align_size`-style pinning.
  2. Disable the mamba prefix cache.
  3. Batch-invariant GDN kernel.
- Fallback model if this doesn't converge: a dense Qwen3-8B with training-free readout (ekzhang/SemIf prompt), which is known-good.

**E4: Cost of determinism (½ day)**
- Measure p50/p99 latency, req/s and tok/s for OFF vs ON, fa3 vs triton, at concurrency 1–32.
- Compare to Jev's ~100 ms claim and the LMSYS 27–36% overhead.

**E5: Quality preserved (½ day)**
- Compare accuracy, Brier, ECE and NLL between OFF and ON on the same eval set. The kernels change numerics, so check that calibration (Nimble's fitted temperature) still holds.
- Exit: |Δacc| < 0.5 pt, |ΔECE| < 0.005.

**E6: Invariance beyond batching (1 day)**
Determinism ≠ consistency. Measure flips under:
- option-order permutation
- label renaming
- JSON key order of `state`
- whitespace
- question-id changes (the cookbook's cache-busting `uid`)

Mitigation to test: canonicalize the request (sorted keys, normalized whitespace) and optionally symmetrize the order (average over K cyclic label rotations; K× cost). Report flips before and after.

**E7: Cross-run reproducibility (½ day)**
- Check for bitwise identity across:
  - server restart
  - GPU 3 vs GPU 4 (same SKU)
  - a warm cache holding other tenants' prefixes
- Freeze a **golden suite** (request → sha256 of response) as a regression test and CI gate.

**E8: Head-to-head vs hosted Jev (optional; needs a TypeSafe API key)**
Replay TypeSafe's consistency cookbooks (8 choice + noul questions × 15 repeats) against
hosted `jev-latest`, Nimble OFF and Nimble ON. The expected story is Jev std ≈ 0.01 vs ours exactly 0.

**E9: Stretch**
- Qwen3.6-35B-A3B FP8 profile (MoE determinism; fits in 94 GB).
- Port Zefan-Cai's scalar-head model as an SGLang reward-style path for accuracy.

## Deliverables
- `deterministic-jev/` fork of openjev-sglang:
  - H100 deterministic profile
  - fingerprint in responses
  - request canonicalizer
- `bench/`: repeat-request drift harness (E1/E2/E6/E7) + eval harness (E5) + golden suite.
- A results report (before/after drift tables, overhead, quality).

## Order and decision points
1. E0 decides the model:
   - Qwen3.5-9B passes → proceed with Nimble.
   - It fails → E3, or fall back to dense Qwen3-8B.
2. E1 → E2 is the core result.
3. E4/E5 run in parallel with E6.
4. E7 locks it in.

Rough total: 4–6 working days on one GPU.

## Status 2026-09-28 (end of day 1)
Done: E0, E1, E2, E3 (root-caused and fixed), E4 (fair re-measure), E5, E6, E7, E8 (published Jev values only; no API key).
Not done: E9 (MoE), hosted-Jev live replay, fingerprinting patched sources, upstream PR.
See README.md for claims → evidence, and the results page.
