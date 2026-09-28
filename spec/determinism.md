# Deterministic System One: contract (draft 0.1)

A server that claims this contract promises:

> For a fixed **fingerprint**, the same **request bytes** to `POST /v1/systemone` return a response whose `answers` object is **byte-identical** (after JSON canonicalization with sorted keys). This holds regardless of concurrent traffic, cache state, arrival order, or process restarts.

## Fingerprint
Returned in the `x-detjev-fingerprint` header on every response and by `GET /v1/fingerprint`. It is the first 16 hex characters of the sha256 over canonical JSON of:

| Field | Meaning |
|---|---|
| `weights` | sha256 of every weight shard |
| `compiler_sha256` | prompt-compiler source |
| `serve_sha256` | server source |
| `sglang` | engine version and every flag that can change numerics (dtype, TP, attention/linear-attention backends, deterministic flag, radix cache, chunked prefill, mamba cache strategy, CUDA-graph mode, context length) |
| `gpu` | GPU model name |
| `temperature` | probability temperature |
| `canonicalize`, `align_warmup`, `fa3_align` | server options that change prompts or scheduling |

*Planned for 0.2:* hashes of patched engine files, and the driver and CUDA versions.

Two deployments with the same fingerprint must agree. Different fingerprints may disagree; measure that separately.

## Canonicalization (optional, `--canonicalize`)
- `state` objects are re-serialized with sorted keys before prompting.
- Strings are passed unchanged.

The server declares whether canonicalization is on as part of its fingerprint.

## Receipts (planned 0.2)
`x-detjev-receipt: sha256(request bytes) · fingerprint · sha256(answers)`, optionally signed with the server key.

## Compliance test
A server is compliant when `replaykit` reports all of the following:
1. **Identical bytes, idle:** 100% identical over ≥10 repeats of every item in a suite.
2. **Under load:** 100% identical with ≥32 concurrent background requests mixing prefill and decode.
3. **Restart:** 100% of a recorded golden file reproduced after a process restart.
4. **Second device:** 100% reproduced on another GPU of the same model (when available).
5. **Memo equivalence:** responses served from an exact memo equal fresh computations.

## Out of scope
- **Correctness.** A compliant server can be wrong every time.
- **Invariance to meaning-preserving edits.** Option order, whitespace and nuisance fields are measured separately (`replaykit` invariance).
- **Agreement across fingerprints.** Different GPU models, TP sizes or engine versions.
